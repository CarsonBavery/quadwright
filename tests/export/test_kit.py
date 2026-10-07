"""FR-13: serialize the pipeline's Kit into kit.json."""

import json

from shapely.geometry import Polygon

from quadwright.export.kit import write_kit
from quadwright.model import Joint, Kit, Part, Setup, Tier

BASE_PLATE = Polygon([(0, 0), (100, 0), (100, 80), (0, 80)])


def _part(**overrides) -> Part:
    defaults = dict(
        id="part-0000",
        building_ids=("way/1", "way/2"),
        footprint_local=Polygon([(0, 0), (10, 0), (10, 10), (0, 10)]),
        height_mm=12.5,
        tier=Tier.BLOCK,
        position_on_base=(5.0, 7.0),
    )
    return Part(**{**defaults, **overrides})


def test_fr13_writes_valid_json_with_top_level_keys(tmp_path):
    kit = Kit(campus="example-university", base_plate=BASE_PLATE, parts=[_part()])

    path = write_kit(kit, tmp_path / "kit.json")

    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data.keys()) == {"campus", "base_plate", "parts", "report"}
    assert data["campus"] == "example-university"


def test_fr13_creates_parent_directories(tmp_path):
    kit = Kit(campus="example-university", base_plate=BASE_PLATE, parts=[])
    nested = tmp_path / "data" / "interim" / "example-university" / "kit.json"

    path = write_kit(kit, nested)

    assert path == nested
    assert nested.exists()


def test_fr13_base_plate_serializes_as_geojson_polygon(tmp_path):
    kit = Kit(campus="example-university", base_plate=BASE_PLATE, parts=[])
    path = write_kit(kit, tmp_path / "kit.json")

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["base_plate"]["type"] == "Polygon"
    assert data["base_plate"]["coordinates"][0][0] == [0.0, 0.0]


def test_fr13_part_fields_serialize_correctly(tmp_path):
    part = _part(species="walnut", rotation_deg=15.0, grain_axis="y")
    kit = Kit(campus="example-university", base_plate=BASE_PLATE, parts=[part])
    path = write_kit(kit, tmp_path / "kit.json")

    data = json.loads(path.read_text(encoding="utf-8"))
    part_data = data["parts"][0]
    assert part_data["id"] == "part-0000"
    assert part_data["building_ids"] == ["way/1", "way/2"]
    assert part_data["footprint_local"]["type"] == "Polygon"
    assert part_data["height_mm"] == 12.5
    assert part_data["tier"] == "BLOCK"  # enum name, not the raw int
    assert part_data["position_on_base"] == [5.0, 7.0]
    assert part_data["rotation_deg"] == 15.0
    assert part_data["species"] == "walnut"
    assert part_data["grain_axis"] == "y"


def test_fr13_no_joint_serializes_as_null(tmp_path):
    kit = Kit(campus="example-university", base_plate=BASE_PLATE, parts=[_part(joint=None)])
    path = write_kit(kit, tmp_path / "kit.json")

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["parts"][0]["joint"] is None


def test_fr13_joint_with_tenon_serializes_fully(tmp_path):
    joint = Joint(
        kind="tenon",
        clearance_mm=0.15,
        tenon_shape=Polygon([(0, 0), (5, 0), (5, 5), (0, 5)]),
        dowel_points=(),
    )
    kit = Kit(campus="example-university", base_plate=BASE_PLATE, parts=[_part(joint=joint)])
    path = write_kit(kit, tmp_path / "kit.json")

    data = json.loads(path.read_text(encoding="utf-8"))
    joint_data = data["parts"][0]["joint"]
    assert joint_data["kind"] == "tenon"
    assert joint_data["clearance_mm"] == 0.15
    assert joint_data["tenon_shape"]["type"] == "Polygon"
    assert joint_data["dowel_points"] == []


def test_fr13_dowel_joint_serializes_points_without_a_tenon_shape(tmp_path):
    joint = Joint(kind="dowels", clearance_mm=0.1, dowel_points=((1.0, 2.0), (3.0, 4.0)))
    kit = Kit(campus="example-university", base_plate=BASE_PLATE, parts=[_part(joint=joint)])
    path = write_kit(kit, tmp_path / "kit.json")

    data = json.loads(path.read_text(encoding="utf-8"))
    joint_data = data["parts"][0]["joint"]
    assert joint_data["tenon_shape"] is None
    assert joint_data["dowel_points"] == [[1.0, 2.0], [3.0, 4.0]]


def test_fr13_setups_serialize_as_a_list(tmp_path):
    setups = (Setup(index=0, face_up="top"), Setup(index=1, face_up="north", mesh_path="p1-n.stl"))
    kit = Kit(campus="example-university", base_plate=BASE_PLATE, parts=[_part(setups=setups)])
    path = write_kit(kit, tmp_path / "kit.json")

    data = json.loads(path.read_text(encoding="utf-8"))
    setups_data = data["parts"][0]["setups"]
    assert setups_data == [
        {"index": 0, "face_up": "top", "mesh_path": None},
        {"index": 1, "face_up": "north", "mesh_path": "p1-n.stl"},
    ]


def test_fr13_report_passes_through_unchanged(tmp_path):
    kit = Kit(
        campus="example-university",
        base_plate=BASE_PLATE,
        parts=[],
        report={"building_count": 42, "part_count": 7},
    )
    path = write_kit(kit, tmp_path / "kit.json")

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["report"] == {"building_count": 42, "part_count": 7}
