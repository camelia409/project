"""
TN-Flow Allocator & Geometry Tests
====================================
Tests for allocator.py and geometry.py
Run from: cd /app/tn_flow_project && pytest tests/test_allocator_geometry.py -v
"""
import sys
sys.path.insert(0, '/app/tn_flow_project')

import pytest
from shapely.geometry import box, Polygon

from backend.database.db import SessionLocal
from backend.database.models import AuthorityEnum, FloorLevelEnum


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def session():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture(scope="module")
def build_zone_12x22_north(session):
    """12x22m CMDA G+1 North-facing — standard test plot"""
    from backend.engine.constraint import calculate_build_envelope
    return calculate_build_envelope(
        plot_width=12.0, plot_depth=22.0,
        authority=AuthorityEnum.CMDA, floor_level=FloorLevelEnum.G_PLUS_1,
        road_width=12.0, session=session, plot_facing="North"
    )


@pytest.fixture(scope="module")
def build_zone_12x20_north(session):
    """12x20m CMDA G+1 North-facing — for SpaceDeficitError test"""
    from backend.engine.constraint import calculate_build_envelope
    return calculate_build_envelope(
        plot_width=12.0, plot_depth=20.0,
        authority=AuthorityEnum.CMDA, floor_level=FloorLevelEnum.G_PLUS_1,
        road_width=12.0, session=session, plot_facing="North"
    )


@pytest.fixture(scope="module")
def anchors_2bhk_north(session, build_zone_12x22_north):
    """2BHK North-facing room anchors for 12x22m plot"""
    from backend.engine.vastu_router import get_room_anchors
    return get_room_anchors("North", build_zone_12x22_north.envelope_polygon, session)


@pytest.fixture(scope="module")
def allocated_2bhk_north(build_zone_12x22_north, anchors_2bhk_north):
    """Resolved 2BHK North-facing allocations"""
    from backend.engine.allocator import resolve_spatial_conflicts
    return resolve_spatial_conflicts("2BHK", anchors_2bhk_north, build_zone_12x22_north.envelope_polygon)


# ── exceptions.py: SpaceDeficitError & AllocationError ────────────────────────

class TestNewExceptions:
    """SpaceDeficitError and AllocationError tests"""

    def test_space_deficit_error_exists(self):
        from backend.engine.exceptions import SpaceDeficitError
        assert SpaceDeficitError is not None

    def test_allocation_error_exists(self):
        from backend.engine.exceptions import AllocationError
        assert AllocationError is not None

    def test_space_deficit_inherits_tncdbr(self):
        from backend.engine.exceptions import SpaceDeficitError, TNCDBRValidationError
        assert issubclass(SpaceDeficitError, TNCDBRValidationError)

    def test_allocation_error_inherits_tncdbr(self):
        from backend.engine.exceptions import AllocationError, TNCDBRValidationError
        assert issubclass(AllocationError, TNCDBRValidationError)

    def test_space_deficit_to_dict_keys(self):
        from backend.engine.exceptions import SpaceDeficitError
        err = SpaceDeficitError(
            "test",
            room_type="Bedroom2",
            base_area_sqm=10.0,
            carpet_area_sqm=7.0,
            nbc_minimum_sqm=7.5,
            wall_overhead_sqm=3.0,
            base_dims="3.0x4.0m",
            clear_dims="2.71x3.71m",
        )
        d = err.to_dict()
        ctx = d["context"]
        for key in ("room_type", "base_area_sqm", "carpet_area_sqm", "nbc_minimum_sqm",
                    "wall_overhead_sqm", "base_dims", "clear_dims"):
            assert key in ctx, f"Missing key: {key}"


# ── BHKType Enum ───────────────────────────────────────────────────────────────

class TestBHKTypeEnum:
    def test_enum_values(self):
        from backend.engine.allocator import BHKType
        assert BHKType.ONE_BHK.value == "1BHK"
        assert BHKType.TWO_BHK.value == "2BHK"
        assert BHKType.THREE_BHK.value == "3BHK"
        assert BHKType.VILLA.value == "3BHK_VILLA"


# ── resolve_spatial_conflicts: BHK filtering ──────────────────────────────────

class TestBHKFiltering:

    def test_1bhk_excludes_bedroom2_bedroom3_staircase_storeroom(self, anchors_2bhk_north, build_zone_12x22_north):
        from backend.engine.allocator import resolve_spatial_conflicts
        allocated = resolve_spatial_conflicts("1BHK", anchors_2bhk_north, build_zone_12x22_north.envelope_polygon)
        for excluded in ("Bedroom2", "Bedroom3", "Staircase", "StoreRoom"):
            assert excluded not in allocated, f"{excluded} should be excluded from 1BHK"

    def test_3bhk_villa_includes_staircase_storeroom(self, session, build_zone_12x22_north):
        from backend.engine.constraint import calculate_build_envelope
        from backend.engine.vastu_router import get_room_anchors
        from backend.engine.allocator import resolve_spatial_conflicts
        bz = calculate_build_envelope(
            plot_width=15.0, plot_depth=25.0,
            authority=AuthorityEnum.CMDA, floor_level=FloorLevelEnum.G_PLUS_1,
            road_width=12.0, session=session, plot_facing="North"
        )
        anchors = get_room_anchors("North", bz.envelope_polygon, session)
        allocated = resolve_spatial_conflicts("3BHK_VILLA", anchors, bz.envelope_polygon)
        assert "Staircase" in allocated, "Staircase should be present in 3BHK_VILLA"
        assert "StoreRoom" in allocated, "StoreRoom should be present in 3BHK_VILLA"


# ── _proportional_bisect ───────────────────────────────────────────────────────

class TestProportionalBisect:

    def test_masterbedroom_at_bottom_staircase_at_top(self):
        """SW cell (3×6.33m): MasterBedroom gets lower y, Staircase gets top"""
        from backend.engine.allocator import _proportional_bisect
        cell = box(1.5, 1.5, 4.5, 7.83)  # 3.0m x 6.33m
        result = _proportional_bisect(cell, ["MasterBedroom", "Staircase"])
        assert "MasterBedroom" in result
        assert "Staircase" in result
        mb_miny = result["MasterBedroom"].bounds[1]
        st_miny = result["Staircase"].bounds[1]
        assert mb_miny < st_miny, "MasterBedroom should be at the bottom (lower y)"

    def test_proportions_match_nbc_weights(self):
        """MasterBedroom should get ~67.86% of SW cell area"""
        from backend.engine.allocator import _proportional_bisect
        cell = box(1.5, 1.5, 4.5, 7.83)  # 3.0m x 6.33m
        result = _proportional_bisect(cell, ["MasterBedroom", "Staircase"])
        total_area = cell.area
        mb_area = result["MasterBedroom"].area
        expected_fraction = 9.5 / (9.5 + 4.5)  # 0.6786
        actual_fraction = mb_area / total_area
        assert abs(actual_fraction - expected_fraction) < 0.01, (
            f"MasterBedroom fraction {actual_fraction:.4f} expected {expected_fraction:.4f}"
        )


# ── No overlaps and within envelope ───────────────────────────────────────────

class TestAllocationGeometry:

    def test_no_overlapping_polygons(self, allocated_2bhk_north):
        rooms = list(allocated_2bhk_north.items())
        for i in range(len(rooms)):
            for j in range(i + 1, len(rooms)):
                name_a, poly_a = rooms[i]
                name_b, poly_b = rooms[j]
                intersection = poly_a.intersection(poly_b)
                assert intersection.area < 1e-8, (
                    f"Overlap between {name_a} and {name_b}: {intersection.area:.2e}m²"
                )

    def test_all_polygons_within_envelope(self, allocated_2bhk_north, build_zone_12x22_north):
        env = build_zone_12x22_north.envelope_polygon.buffer(1e-6)
        for room, poly in allocated_2bhk_north.items():
            assert env.contains(poly), f"{room} polygon lies outside build_envelope"


# ── AllocationError on undersized cell ────────────────────────────────────────

class TestAllocationError:

    def test_allocation_error_on_tiny_cell(self):
        """Cell area < 60% of sum NBC weights should raise AllocationError"""
        from backend.engine.allocator import resolve_spatial_conflicts
        from backend.engine.exceptions import AllocationError
        # Tiny cell (2m x 2m = 4m²), force two rooms with combined weight >6.67m²
        # We'll construct a minimal room_anchors with a tiny shared cell
        tiny_cell = box(0.0, 0.0, 2.0, 2.0)
        room_anchors = {
            "MasterBedroom": {"zone": "SW", "bounding_box": tiny_cell},
            "Hall":          {"zone": "SW", "bounding_box": tiny_cell},
        }
        envelope = box(0.0, 0.0, 10.0, 10.0)
        # Total NBC weight = 9.5 + 9.5 = 19.0; 60% = 11.4; cell area = 4.0 < 11.4
        with pytest.raises(AllocationError):
            resolve_spatial_conflicts("2BHK", room_anchors, envelope)

    def test_value_error_on_unknown_bhk_type(self, anchors_2bhk_north, build_zone_12x22_north):
        from backend.engine.allocator import resolve_spatial_conflicts
        with pytest.raises(ValueError):
            resolve_spatial_conflicts("5BHK", anchors_2bhk_north, build_zone_12x22_north.envelope_polygon)


# ── describe_allocations ───────────────────────────────────────────────────────

class TestDescribeAllocations:

    def test_describe_allocations_format(self, allocated_2bhk_north):
        from backend.engine.allocator import describe_allocations
        text = describe_allocations(allocated_2bhk_north)
        assert isinstance(text, str)
        assert len(text) > 0
        # Check it contains room names, dims, area
        for room in allocated_2bhk_north:
            assert room in text
        assert "W=" in text
        assert "H=" in text
        assert "area=" in text


# ── geometry.py: _classify_wall_thicknesses ────────────────────────────────────

class TestClassifyWallThicknesses:

    def test_left_edge_on_envelope_returns_ext_wall(self):
        from backend.engine.geometry import _classify_wall_thicknesses, EXT_WALL_T
        envelope = box(1.5, 1.5, 10.5, 20.5)
        base = box(1.5, 1.5, 4.5, 5.0)  # left edge ON envelope.minx
        left_t, right_t, bottom_t, top_t = _classify_wall_thicknesses(base, envelope)
        assert abs(left_t - EXT_WALL_T) < 1e-9, f"Left edge should be EXT_WALL_T=0.23, got {left_t}"

    def test_interior_edges_return_int_wall_half(self):
        from backend.engine.geometry import _classify_wall_thicknesses, INT_WALL_HALF
        envelope = box(1.5, 1.5, 10.5, 20.5)
        # Interior room (not touching any envelope edge)
        base = box(4.5, 5.0, 7.5, 10.0)
        left_t, right_t, bottom_t, top_t = _classify_wall_thicknesses(base, envelope)
        assert abs(left_t - INT_WALL_HALF) < 1e-9
        assert abs(right_t - INT_WALL_HALF) < 1e-9
        assert abs(bottom_t - INT_WALL_HALF) < 1e-9
        assert abs(top_t - INT_WALL_HALF) < 1e-9


# ── apply_wall_thickness ───────────────────────────────────────────────────────

class TestApplyWallThickness:

    def test_sw_corner_room_insets(self):
        """SW corner room: left=0.23, bottom=0.23, right=0.0575, top=0.0575"""
        from backend.engine.geometry import _classify_wall_thicknesses, EXT_WALL_T, INT_WALL_HALF
        envelope = box(1.5, 1.5, 10.5, 20.5)
        sw_room = box(1.5, 1.5, 4.5, 6.0)
        left_t, right_t, bottom_t, top_t = _classify_wall_thicknesses(sw_room, envelope)
        assert abs(left_t - EXT_WALL_T) < 1e-9,   f"Left should be EXT: {left_t}"
        assert abs(bottom_t - EXT_WALL_T) < 1e-9, f"Bottom should be EXT: {bottom_t}"
        assert abs(right_t - INT_WALL_HALF) < 1e-9, f"Right should be INT: {right_t}"
        assert abs(top_t - INT_WALL_HALF) < 1e-9,   f"Top should be INT: {top_t}"

    def test_2bhk_all_rooms_pass_nbc(self, allocated_2bhk_north, build_zone_12x22_north):
        """2BHK on 12x22m CMDA G+1: all rooms pass NBC carpet area minimums"""
        from backend.engine.geometry import apply_wall_thickness, NBC_CARPET_MINIMUMS
        floor_plan = apply_wall_thickness(allocated_2bhk_north, build_zone_12x22_north.envelope_polygon)
        assert len(floor_plan) == 8, f"Expected 8 rooms for 2BHK, got {len(floor_plan)}"
        for room, data in floor_plan.items():
            nbc_min = NBC_CARPET_MINIMUMS.get(room, 1.5)
            assert data["carpet_area_sqm"] >= nbc_min, (
                f"{room}: {data['carpet_area_sqm']:.2f}m² < NBC {nbc_min}m²"
            )

    def test_floor_plan_map_has_correct_keys(self, allocated_2bhk_north, build_zone_12x22_north):
        """FloorPlanMap entries must have clear_polygon, carpet_area_sqm, dimensions"""
        from backend.engine.geometry import apply_wall_thickness
        from shapely.geometry import Polygon as ShapelyPolygon
        floor_plan = apply_wall_thickness(allocated_2bhk_north, build_zone_12x22_north.envelope_polygon)
        for room, data in floor_plan.items():
            assert "clear_polygon" in data, f"{room}: missing clear_polygon"
            assert "carpet_area_sqm" in data, f"{room}: missing carpet_area_sqm"
            assert "dimensions" in data, f"{room}: missing dimensions"
            assert isinstance(data["clear_polygon"], ShapelyPolygon)
            assert isinstance(data["carpet_area_sqm"], float)
            assert isinstance(data["dimensions"], tuple)
            assert len(data["dimensions"]) == 2

    def test_space_deficit_error_on_small_plot(self, session):
        """12×20m plot should raise SpaceDeficitError for Bedroom2 (clear < 7.5m²)"""
        from backend.engine.constraint import calculate_build_envelope
        from backend.engine.vastu_router import get_room_anchors
        from backend.engine.allocator import resolve_spatial_conflicts
        from backend.engine.geometry import apply_wall_thickness
        from backend.engine.exceptions import SpaceDeficitError
        bz = calculate_build_envelope(
            plot_width=12.0, plot_depth=20.0,
            authority=AuthorityEnum.CMDA, floor_level=FloorLevelEnum.G_PLUS_1,
            road_width=12.0, session=session, plot_facing="North"
        )
        anchors = get_room_anchors("North", bz.envelope_polygon, session)
        allocated = resolve_spatial_conflicts("2BHK", anchors, bz.envelope_polygon)
        with pytest.raises(SpaceDeficitError):
            apply_wall_thickness(allocated, bz.envelope_polygon)


# ── get_wall_schedule ──────────────────────────────────────────────────────────

class TestGetWallSchedule:

    def test_wall_schedule_has_32_entries_for_8_rooms(self, allocated_2bhk_north, build_zone_12x22_north):
        from backend.engine.geometry import get_wall_schedule
        schedule = get_wall_schedule(allocated_2bhk_north, build_zone_12x22_north.envelope_polygon)
        assert len(schedule) == 32, f"Expected 32 entries (8 rooms × 4 faces), got {len(schedule)}"

    def test_wall_schedule_has_correct_wall_types(self, allocated_2bhk_north, build_zone_12x22_north):
        from backend.engine.geometry import get_wall_schedule
        schedule = get_wall_schedule(allocated_2bhk_north, build_zone_12x22_north.envelope_polygon)
        for entry in schedule:
            assert entry["wall_type"] in ("External", "Internal"), (
                f"Unexpected wall_type: {entry['wall_type']}"
            )
            if entry["wall_type"] == "External":
                assert abs(entry["thickness_m"] - 0.23) < 1e-6
            else:
                assert abs(entry["thickness_m"] - 0.0575) < 1e-6


# ── describe_floor_plan ────────────────────────────────────────────────────────

class TestDescribeFloorPlan:

    def test_describe_floor_plan_format(self, allocated_2bhk_north, build_zone_12x22_north):
        from backend.engine.geometry import apply_wall_thickness, describe_floor_plan
        floor_plan = apply_wall_thickness(allocated_2bhk_north, build_zone_12x22_north.envelope_polygon)
        text = describe_floor_plan(floor_plan)
        assert isinstance(text, str)
        assert len(text) > 0
        for room in floor_plan:
            assert room in text
        assert "NBC min" in text
        assert "m²" in text


# ── Full Pipeline Tests ────────────────────────────────────────────────────────

class TestFullPipeline:

    @pytest.mark.parametrize("facing,width,depth,bhk", [
        ("North", 12.0, 22.0, "2BHK"),
        ("South", 12.0, 22.0, "2BHK"),
        ("East",  15.0, 22.0, "2BHK"),
        ("West",  15.0, 22.0, "2BHK"),
        ("North", 15.0, 25.0, "3BHK_VILLA"),
        ("North", 12.0, 22.0, "1BHK"),
        ("North", 12.0, 22.0, "3BHK"),
    ])
    def test_full_pipeline_nbc_pass(self, session, facing, width, depth, bhk):
        """Full pipeline: all 7 scenarios should pass NBC checks"""
        from backend.engine.constraint import calculate_build_envelope
        from backend.engine.vastu_router import get_room_anchors
        from backend.engine.allocator import resolve_spatial_conflicts
        from backend.engine.geometry import apply_wall_thickness
        bz = calculate_build_envelope(
            plot_width=width, plot_depth=depth,
            authority=AuthorityEnum.CMDA, floor_level=FloorLevelEnum.G_PLUS_1,
            road_width=12.0, session=session, plot_facing=facing
        )
        anchors = get_room_anchors(facing, bz.envelope_polygon, session)
        allocated = resolve_spatial_conflicts(bhk, anchors, bz.envelope_polygon)
        from backend.engine.geometry import NBC_CARPET_MINIMUMS
        floor_plan = apply_wall_thickness(allocated, bz.envelope_polygon)
        for room, data in floor_plan.items():
            nbc_min = NBC_CARPET_MINIMUMS.get(room, 1.5)
            assert data["carpet_area_sqm"] >= nbc_min, (
                f"[{bhk}/{facing}] {room}: {data['carpet_area_sqm']:.2f}m² < NBC {nbc_min}m²"
            )
