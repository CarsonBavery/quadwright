"""FR-10: fetch and cache LIDAR point cloud tiles, without hitting the network."""

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


def test_fr10_cache_dir_layout_matches_other_fetches(tmp_path, monkeypatch):
    _patch_requests_get(monkeypatch, [])
    paths = lidar.fetch_campus_lidar(AREA_WITH_LIDAR, cache_dir=tmp_path)
    assert paths[0] == tmp_path / "example-university" / "lidar" / "inside_tile.laz"
