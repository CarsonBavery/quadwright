"""FR-10: fetch and cache LIDAR point cloud tiles, without hitting the network."""

import json

import pytest
import requests

from quadwright.config import CampusArea
from quadwright.sources import lidar

AREA = CampusArea(name="example-university", bbox=(-80.000, 35.000, -79.990, 35.008))
AREA_WITH_LIDAR = CampusArea(
    name="example-university",
    bbox=(-80.000, 35.000, -79.990, 35.008),
    lidar_project="FAKE_STATE/FAKE_County_2020",
)

INSIDE_TILE_BBOX = [-80.0, 35.0, 100.0, -79.99, 35.008, 200.0]  # overlaps AREA.bbox
OUTSIDE_TILE_BBOX = [-70.0, 40.0, 100.0, -69.99, 40.008, 200.0]  # far away


def _fake_index() -> dict:
    return {
        "features": [
            {"bbox": INSIDE_TILE_BBOX, "assets": {"data": {"href": "./LAZ/inside_tile.laz"}}},
            {"bbox": OUTSIDE_TILE_BBOX, "assets": {"data": {"href": "./LAZ/outside_tile.laz"}}},
        ]
    }


def _fake_links_text() -> str:
    return (
        "https://rockyweb.usgs.gov/.../LAZ/inside_tile.laz\n"
        "https://rockyweb.usgs.gov/.../LAZ/outside_tile.laz\n"
    )


class _FakeResponse:
    def __init__(self, *, json_body=None, text_body=None, content=b""):
        self._json_body = json_body
        self.text = text_body
        self._content = content

    def json(self):
        return self._json_body

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size):
        yield self._content

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def _patch_requests_get(monkeypatch, calls: list[str]):
    def fake_get(url, timeout=None, stream=False):
        calls.append(url)
        if url.endswith(".vpc"):
            return _FakeResponse(json_body=_fake_index())
        if url.endswith("0_file_download_links.txt"):
            return _FakeResponse(text_body=_fake_links_text())
        return _FakeResponse(content=b"fake laz bytes")

    monkeypatch.setattr(lidar, "requests", type("_R", (), {"get": staticmethod(fake_get)}))


def test_fr10_returns_empty_without_touching_the_network_when_unset(monkeypatch):
    calls: list[str] = []
    _patch_requests_get(monkeypatch, calls)

    assert lidar.fetch_campus_lidar(AREA, cache_dir="ignored") == []
    assert calls == []


def test_fr10_fetches_only_tiles_overlapping_the_campus_bbox(tmp_path, monkeypatch):
    calls: list[str] = []
    _patch_requests_get(monkeypatch, calls)

    paths = lidar.fetch_campus_lidar(AREA_WITH_LIDAR, cache_dir=tmp_path)

    assert [p.name for p in paths] == ["inside_tile.laz"]
    assert paths[0].exists()
    assert paths[0].read_bytes() == b"fake laz bytes"


def test_fr10_second_fetch_skips_the_network_for_cached_tiles(tmp_path, monkeypatch):
    calls: list[str] = []
    _patch_requests_get(monkeypatch, calls)

    lidar.fetch_campus_lidar(AREA_WITH_LIDAR, cache_dir=tmp_path)
    download_calls_first_run = sum(1 for c in calls if c.endswith(".laz"))
    lidar.fetch_campus_lidar(AREA_WITH_LIDAR, cache_dir=tmp_path)
    download_calls_second_run = (
        sum(1 for c in calls if c.endswith(".laz")) - download_calls_first_run
    )

    assert download_calls_first_run == 1
    assert download_calls_second_run == 0  # tile already on disk, not re-downloaded


def test_fr10_interrupted_download_leaves_no_cached_tile(tmp_path, monkeypatch):
    # A connection that drops mid-stream: one chunk arrives, then an error.
    class _DroppedResponse(_FakeResponse):
        def iter_content(self, chunk_size):
            yield b"first half"
            raise ConnectionError("connection reset")

    def fake_get(url, timeout=None, stream=False):
        if url.endswith(".vpc"):
            return _FakeResponse(json_body=_fake_index())
        if url.endswith("0_file_download_links.txt"):
            return _FakeResponse(text_body=_fake_links_text())
        return _DroppedResponse()

    monkeypatch.setattr(lidar, "requests", type("_R", (), {"get": staticmethod(fake_get)}))

    try:
        lidar.fetch_campus_lidar(AREA_WITH_LIDAR, cache_dir=tmp_path)
    except ConnectionError:
        pass
    else:
        raise AssertionError("the dropped connection should propagate")

    lidar_dir = tmp_path / "example-university" / "lidar"
    # No truncated .laz, no stray .part -- just the manifest of what's still owed.
    assert [p.name for p in lidar_dir.iterdir()] == [lidar.MANIFEST_NAME]


def test_fr10_retry_after_interrupted_download_fetches_the_tile_again(tmp_path, monkeypatch):
    calls: list[str] = []
    attempts = {"n": 0}

    class _DroppedResponse(_FakeResponse):
        def iter_content(self, chunk_size):
            yield b"first half"
            raise ConnectionError("connection reset")

    def fake_get(url, timeout=None, stream=False):
        calls.append(url)
        if url.endswith(".vpc"):
            return _FakeResponse(json_body=_fake_index())
        if url.endswith("0_file_download_links.txt"):
            return _FakeResponse(text_body=_fake_links_text())
        attempts["n"] += 1
        return _DroppedResponse() if attempts["n"] == 1 else _FakeResponse(content=b"whole tile")

    monkeypatch.setattr(lidar, "requests", type("_R", (), {"get": staticmethod(fake_get)}))

    try:
        lidar.fetch_campus_lidar(AREA_WITH_LIDAR, cache_dir=tmp_path)
    except ConnectionError:
        pass
    paths = lidar.fetch_campus_lidar(AREA_WITH_LIDAR, cache_dir=tmp_path)

    assert attempts["n"] == 2  # the failed tile wasn't mistaken for cached
    assert paths[0].read_bytes() == b"whole tile"


def test_fr10_cache_dir_layout_matches_other_fetches(tmp_path, monkeypatch):
    _patch_requests_get(monkeypatch, [])
    paths = lidar.fetch_campus_lidar(AREA_WITH_LIDAR, cache_dir=tmp_path)
    assert paths[0] == tmp_path / "example-university" / "lidar" / "inside_tile.laz"


def _http_error(status: int, retry_after: str | None = None) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status
    if retry_after is not None:
        response.headers["Retry-After"] = retry_after
    return requests.HTTPError(response=response)


class _FailingResponse(_FakeResponse):
    def __init__(self, error: requests.HTTPError):
        super().__init__()
        self._error = error

    def raise_for_status(self):
        raise self._error


def _patch_tile_responses(monkeypatch, tile_responses: list, sleeps: list[float]):
    """Index/links as usual; each tile request pops the next scripted response."""

    def fake_get(url, timeout=None, stream=False):
        if url.endswith(".vpc"):
            return _FakeResponse(json_body=_fake_index())
        if url.endswith("0_file_download_links.txt"):
            return _FakeResponse(text_body=_fake_links_text())
        return tile_responses.pop(0)

    monkeypatch.setattr(lidar, "requests", type("_R", (), {"get": staticmethod(fake_get)}))
    monkeypatch.setattr(lidar.time, "sleep", sleeps.append)


def test_fr10_rate_limited_download_waits_and_retries(tmp_path, monkeypatch):
    sleeps: list[float] = []
    responses = [
        _FailingResponse(_http_error(429)),
        _FailingResponse(_http_error(429)),
        _FakeResponse(content=b"fake laz bytes"),
    ]
    _patch_tile_responses(monkeypatch, responses, sleeps)

    paths = lidar.fetch_campus_lidar(AREA_WITH_LIDAR, cache_dir=tmp_path)

    assert paths[0].read_bytes() == b"fake laz bytes"
    assert sleeps == [10, 20]  # exponential backoff, no Retry-After header


def test_fr10_retry_honors_the_servers_retry_after(tmp_path, monkeypatch):
    sleeps: list[float] = []
    responses = [_FailingResponse(_http_error(429, retry_after="42")), _FakeResponse(content=b"x")]
    _patch_tile_responses(monkeypatch, responses, sleeps)

    lidar.fetch_campus_lidar(AREA_WITH_LIDAR, cache_dir=tmp_path)

    assert sleeps == [42.0]


def test_fr10_does_not_retry_a_missing_tile(tmp_path, monkeypatch):
    sleeps: list[float] = []
    _patch_tile_responses(monkeypatch, [_FailingResponse(_http_error(404))], sleeps)

    with pytest.raises(requests.HTTPError):
        lidar.fetch_campus_lidar(AREA_WITH_LIDAR, cache_dir=tmp_path)
    assert sleeps == []


def test_fr10_gives_up_after_max_attempts(tmp_path, monkeypatch):
    sleeps: list[float] = []
    responses = [_FailingResponse(_http_error(503)) for _ in range(lidar._MAX_ATTEMPTS)]
    _patch_tile_responses(monkeypatch, responses, sleeps)

    with pytest.raises(requests.HTTPError):
        lidar.fetch_campus_lidar(AREA_WITH_LIDAR, cache_dir=tmp_path)
    assert len(sleeps) == lidar._MAX_ATTEMPTS - 1


def test_fr10_fetch_writes_a_manifest_of_the_tiles_it_needs(tmp_path, monkeypatch):
    _patch_requests_get(monkeypatch, [])

    lidar.fetch_campus_lidar(AREA_WITH_LIDAR, cache_dir=tmp_path)

    manifest = tmp_path / "example-university" / "lidar" / lidar.MANIFEST_NAME
    assert json.loads(manifest.read_text())["tiles"] == ["inside_tile.laz"]


def test_fr10_cached_tiles_refuses_a_partial_set(tmp_path):
    lidar_dir = tmp_path / "lidar"
    lidar_dir.mkdir()
    (lidar_dir / lidar.MANIFEST_NAME).write_text(json.dumps({"tiles": ["a.laz", "b.laz"]}))
    (lidar_dir / "a.laz").write_bytes(b"x")

    with pytest.raises(lidar.IncompleteLidarError, match="only 1 of 2"):
        lidar.cached_lidar_tiles(lidar_dir)


def test_fr10_cached_tiles_returns_a_complete_set_in_manifest_order(tmp_path):
    lidar_dir = tmp_path / "lidar"
    lidar_dir.mkdir()
    (lidar_dir / lidar.MANIFEST_NAME).write_text(json.dumps({"tiles": ["b.laz", "a.laz"]}))
    for name in ("a.laz", "b.laz"):
        (lidar_dir / name).write_bytes(b"x")

    assert [p.name for p in lidar.cached_lidar_tiles(lidar_dir)] == ["b.laz", "a.laz"]


def test_fr10_cached_tiles_without_a_manifest_falls_back_to_what_is_there(tmp_path):
    lidar_dir = tmp_path / "lidar"
    lidar_dir.mkdir()
    (lidar_dir / "old_fetch.laz").write_bytes(b"x")

    assert [p.name for p in lidar.cached_lidar_tiles(lidar_dir)] == ["old_fetch.laz"]
    assert lidar.cached_lidar_tiles(tmp_path / "never_fetched") == []


def test_fr10_retries_a_dropped_connection(tmp_path, monkeypatch):
    # e.g. a DNS lookup failing mid-fetch -- transient, unlike a 404.
    sleeps: list[float] = []
    calls = {"n": 0}

    def fake_get(url, timeout=None, stream=False):
        if url.endswith(".vpc"):
            return _FakeResponse(json_body=_fake_index())
        if url.endswith("0_file_download_links.txt"):
            return _FakeResponse(text_body=_fake_links_text())
        calls["n"] += 1
        if calls["n"] == 1:
            raise requests.ConnectionError("Failed to resolve 'rockyweb.usgs.gov'")
        return _FakeResponse(content=b"fake laz bytes")

    monkeypatch.setattr(lidar, "requests", type("_R", (), {"get": staticmethod(fake_get)}))
    monkeypatch.setattr(lidar.time, "sleep", sleeps.append)

    paths = lidar.fetch_campus_lidar(AREA_WITH_LIDAR, cache_dir=tmp_path)

    assert paths[0].read_bytes() == b"fake laz bytes"
    assert sleeps == [10]
