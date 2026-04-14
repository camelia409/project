"""
TN-Flow Engine Tests
====================
Tests for exceptions.py, constraint.py, and vastu_router.py
Run from: cd /app/tn_flow_project && pytest tests/test_tn_flow_engine.py -v
"""
import sys
import os
sys.path.insert(0, '/app/tn_flow_project')

import pytest
from shapely.geometry import box, Polygon

from backend.database.db import SessionLocal
from backend.database.models import AuthorityEnum, FloorLevelEnum, VastuZoneEnum


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def session():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture(scope="module")
def valid_build_zone(session):
    """Standard valid 12x20m CMDA G+1 on 12m road build zone"""
    from backend.engine.constraint import calculate_build_envelope
    return calculate_build_envelope(
        plot_width=12.0, plot_depth=20.0,
        authority=AuthorityEnum.CMDA, floor_level=FloorLevelEnum.G_PLUS_1,
        road_width=12.0, session=session, plot_facing="North"
    )


@pytest.fixture(scope="module")
def envelope_9x12():
    """Simple 9x12m envelope for mandala grid tests"""
    return box(0.0, 0.0, 9.0, 12.0)


# ── exceptions.py tests ───────────────────────────────────────────────────────

class TestExceptionHierarchy:
    """Test all 8 exception classes and their inheritance chain"""

    def test_tnflow_base_error_exists(self):
        from backend.engine.exceptions import TNFlowBaseError
        assert issubclass(TNFlowBaseError, Exception)

    def test_tncdbr_validation_error_inherits_base(self):
        from backend.engine.exceptions import TNFlowBaseError, TNCDBRValidationError
        assert issubclass(TNCDBRValidationError, TNFlowBaseError)

    def test_road_width_insufficient_error_inherits(self):
        from backend.engine.exceptions import TNCDBRValidationError, RoadWidthInsufficientError
        assert issubclass(RoadWidthInsufficientError, TNCDBRValidationError)

    def test_plot_too_small_error_inherits(self):
        from backend.engine.exceptions import TNCDBRValidationError, PlotTooSmallError
        assert issubclass(PlotTooSmallError, TNCDBRValidationError)

    def test_floor_level_not_permitted_error_inherits(self):
        from backend.engine.exceptions import TNCDBRValidationError, FloorLevelNotPermittedError
        assert issubclass(FloorLevelNotPermittedError, TNCDBRValidationError)

    def test_setback_exceeds_plot_error_inherits(self):
        from backend.engine.exceptions import TNCDBRValidationError, SetbackExceedsPlotError
        assert issubclass(SetbackExceedsPlotError, TNCDBRValidationError)

    def test_insufficient_build_envelope_error_inherits(self):
        from backend.engine.exceptions import TNCDBRValidationError, InsufficientBuildEnvelopeError
        assert issubclass(InsufficientBuildEnvelopeError, TNCDBRValidationError)

    def test_vastu_routing_error_inherits_base(self):
        from backend.engine.exceptions import TNFlowBaseError, VastuRoutingError
        assert issubclass(VastuRoutingError, TNFlowBaseError)

    def test_unresolvable_room_placement_error_inherits(self):
        from backend.engine.exceptions import VastuRoutingError, UnresolvableRoomPlacementError
        assert issubclass(UnresolvableRoomPlacementError, VastuRoutingError)

    def test_vastu_zone_unavailable_error_inherits(self):
        from backend.engine.exceptions import VastuRoutingError, VastuZoneUnavailableError
        assert issubclass(VastuZoneUnavailableError, VastuRoutingError)

    def test_context_stores_kwargs(self):
        from backend.engine.exceptions import PlotTooSmallError
        exc = PlotTooSmallError("Too small", plot_area=25.0, required_area=27.0)
        assert exc.context["plot_area"] == 25.0
        assert exc.context["required_area"] == 27.0

    def test_to_dict_returns_correct_keys(self):
        from backend.engine.exceptions import PlotTooSmallError
        exc = PlotTooSmallError("Too small", plot_area=25.0)
        d = exc.to_dict()
        assert "error_type" in d
        assert "message" in d
        assert "context" in d
        assert d["error_type"] == "PlotTooSmallError"
        assert d["message"] == "Too small"

    def test_to_dict_context_contains_kwargs(self):
        from backend.engine.exceptions import VastuZoneUnavailableError
        exc = VastuZoneUnavailableError("Zone unavailable", room_type="Kitchen", zone="SE")
        d = exc.to_dict()
        assert d["context"]["room_type"] == "Kitchen"


# ── constraint.py tests ───────────────────────────────────────────────────────

class TestBuildZone:
    """Tests for calculate_build_envelope() and BuildZone properties"""

    def test_valid_build_zone_returns_build_zone(self, valid_build_zone):
        from backend.engine.constraint import BuildZone
        assert isinstance(valid_build_zone, BuildZone)

    def test_envelope_polygon_is_shapely_polygon(self, valid_build_zone):
        assert isinstance(valid_build_zone.envelope_polygon, Polygon)
        assert valid_build_zone.envelope_polygon.area > 0

    def test_envelope_width_m_property(self, valid_build_zone):
        w = valid_build_zone.envelope_width_m
        assert isinstance(w, float)
        assert w > 0
        # 12m wide plot - front/rear setbacks should be < 12
        assert w < 12.0

    def test_envelope_depth_m_property(self, valid_build_zone):
        d = valid_build_zone.envelope_depth_m
        assert isinstance(d, float)
        assert d > 0
        assert d < 20.0

    def test_usable_ratio_property(self, valid_build_zone):
        ratio = valid_build_zone.usable_ratio
        assert 0.0 < ratio <= 1.0

    def test_carpet_area_budget_sqm_property(self, valid_build_zone):
        carpet = valid_build_zone.carpet_area_budget_sqm
        assert carpet > 0
        assert carpet < valid_build_zone.envelope_area_sqm

    def test_floor_level_not_permitted_for_g1_on_narrow_road(self, session):
        from backend.engine.constraint import calculate_build_envelope
        from backend.engine.exceptions import FloorLevelNotPermittedError
        with pytest.raises(FloorLevelNotPermittedError):
            calculate_build_envelope(
                plot_width=12.0, plot_depth=20.0,
                authority=AuthorityEnum.CMDA, floor_level=FloorLevelEnum.G_PLUS_1,
                road_width=4.0, session=session
            )

    def test_plot_too_small_error_for_undersized_plot(self, session):
        from backend.engine.constraint import calculate_build_envelope
        from backend.engine.exceptions import PlotTooSmallError
        with pytest.raises(PlotTooSmallError):
            calculate_build_envelope(
                plot_width=3.0, plot_depth=3.0,
                authority=AuthorityEnum.CMDA, floor_level=FloorLevelEnum.G_PLUS_1,
                road_width=12.0, session=session
            )

    def test_is_buildable_returns_true_for_valid_plot(self, session):
        from backend.engine.constraint import is_buildable
        ok, reason = is_buildable(
            12.0, 20.0, AuthorityEnum.CMDA, FloorLevelEnum.G_PLUS_1, 12.0, session
        )
        assert ok is True
        assert reason == ""

    def test_is_buildable_returns_false_for_invalid_plot(self, session):
        from backend.engine.constraint import is_buildable
        ok, reason = is_buildable(
            3.0, 3.0, AuthorityEnum.CMDA, FloorLevelEnum.G_PLUS_1, 12.0, session
        )
        assert ok is False
        assert len(reason) > 0


# ── vastu_router.py tests ─────────────────────────────────────────────────────

class TestGetMandalaGrid:
    """Tests for get_mandala_grid()"""

    def test_returns_8_cells(self, envelope_9x12):
        from backend.engine.vastu_router import get_mandala_grid
        grid = get_mandala_grid(envelope_9x12)
        assert len(grid) == 8

    def test_each_cell_area_equals_12_sqm(self, envelope_9x12):
        from backend.engine.vastu_router import get_mandala_grid
        grid = get_mandala_grid(envelope_9x12)
        for zone, cell in grid.items():
            assert abs(cell.area - 12.0) < 0.001, f"Zone {zone}: area={cell.area}"

    def test_se_cell_is_correct_box(self, envelope_9x12):
        from backend.engine.vastu_router import get_mandala_grid
        grid = get_mandala_grid(envelope_9x12)
        se_cell = grid[VastuZoneEnum.SOUTHEAST]
        minx, miny, maxx, maxy = se_cell.bounds
        assert abs(minx - 6.0) < 0.001
        assert abs(miny - 0.0) < 0.001
        assert abs(maxx - 9.0) < 0.001
        assert abs(maxy - 4.0) < 0.001

    def test_raises_value_error_for_empty_polygon(self):
        from backend.engine.vastu_router import get_mandala_grid
        from shapely.geometry import Polygon
        with pytest.raises(ValueError):
            get_mandala_grid(Polygon())


class TestGetRoomAnchors:
    """Tests for get_room_anchors()"""

    def test_returns_room_anchor_map(self, envelope_9x12, session):
        from backend.engine.vastu_router import get_room_anchors
        anchors = get_room_anchors("North", envelope_9x12, session)
        assert isinstance(anchors, dict)
        assert len(anchors) > 0

    def test_kitchen_in_se_for_north_facing(self, envelope_9x12, session):
        from backend.engine.vastu_router import get_room_anchors
        anchors = get_room_anchors("North", envelope_9x12, session)
        assert "Kitchen" in anchors
        assert anchors["Kitchen"]["zone"] == "SE"

    def test_master_bedroom_in_sw_for_north_facing(self, envelope_9x12, session):
        from backend.engine.vastu_router import get_room_anchors
        anchors = get_room_anchors("North", envelope_9x12, session)
        assert "MasterBedroom" in anchors
        assert anchors["MasterBedroom"]["zone"] == "SW"

    def test_pooja_in_ne_for_north_facing(self, envelope_9x12, session):
        from backend.engine.vastu_router import get_room_anchors
        anchors = get_room_anchors("North", envelope_9x12, session)
        assert "Pooja" in anchors
        assert anchors["Pooja"]["zone"] == "NE"

    def test_toilet_in_nw_for_north_facing(self, envelope_9x12, session):
        from backend.engine.vastu_router import get_room_anchors
        anchors = get_room_anchors("North", envelope_9x12, session)
        assert "Toilet" in anchors
        assert anchors["Toilet"]["zone"] == "NW"

    def test_bounding_box_is_polygon_with_area(self, envelope_9x12, session):
        from backend.engine.vastu_router import get_room_anchors
        anchors = get_room_anchors("North", envelope_9x12, session)
        for room, data in anchors.items():
            assert isinstance(data["bounding_box"], Polygon)
            assert data["bounding_box"].area > 0

    def test_raises_vastu_zone_unavailable_for_tiny_plot(self, session):
        from backend.engine.vastu_router import get_room_anchors
        from backend.engine.exceptions import VastuZoneUnavailableError
        tiny_plot = box(0.0, 0.0, 5.0, 6.0)
        with pytest.raises(VastuZoneUnavailableError):
            get_room_anchors("North", tiny_plot, session)

    def test_raises_value_error_for_invalid_facing(self, envelope_9x12, session):
        from backend.engine.vastu_router import get_room_anchors
        with pytest.raises(ValueError):
            get_room_anchors("NorthEast", envelope_9x12, session)

    def test_south_facing_entrance_in_se(self, session):
        """Entrance zone for South-facing plot is SE (Grihapati pada)"""
        from backend.engine.vastu_router import get_room_anchors
        envelope = box(0.0, 0.0, 9.0, 12.0)
        anchors = get_room_anchors("South", envelope, session)
        if "Entrance" in anchors:
            assert anchors["Entrance"]["zone"] == "SE"

    def test_west_facing_entrance_in_nw(self, session):
        """Entrance zone for West-facing plot is NW (Sugriva pada)"""
        from backend.engine.vastu_router import get_room_anchors
        envelope = box(0.0, 0.0, 9.0, 12.0)
        anchors = get_room_anchors("West", envelope, session)
        if "Entrance" in anchors:
            assert anchors["Entrance"]["zone"] == "NW"


class TestGetAllPriorityAnchors:
    """Tests for get_all_priority_anchors()"""

    def test_returns_dict_with_keys_1_2_3(self, envelope_9x12, session):
        from backend.engine.vastu_router import get_all_priority_anchors
        result = get_all_priority_anchors("North", envelope_9x12, session)
        assert 1 in result
        assert 2 in result
        assert 3 in result

    def test_priority_1_has_rooms(self, envelope_9x12, session):
        from backend.engine.vastu_router import get_all_priority_anchors
        result = get_all_priority_anchors("North", envelope_9x12, session)
        assert len(result[1]) > 0

    def test_priority_1_contains_kitchen(self, envelope_9x12, session):
        from backend.engine.vastu_router import get_all_priority_anchors
        result = get_all_priority_anchors("North", envelope_9x12, session)
        assert "Kitchen" in result[1]


class TestDescribeAnchors:
    """Tests for describe_anchors()"""

    def test_returns_multiline_string(self, envelope_9x12, session):
        from backend.engine.vastu_router import get_room_anchors, describe_anchors
        anchors = get_room_anchors("North", envelope_9x12, session)
        desc = describe_anchors(anchors)
        assert isinstance(desc, str)
        lines = desc.strip().split("\n")
        assert len(lines) > 1

    def test_contains_room_names(self, envelope_9x12, session):
        from backend.engine.vastu_router import get_room_anchors, describe_anchors
        anchors = get_room_anchors("North", envelope_9x12, session)
        desc = describe_anchors(anchors)
        assert "Kitchen" in desc

    def test_contains_zone_and_bbox(self, envelope_9x12, session):
        from backend.engine.vastu_router import get_room_anchors, describe_anchors
        anchors = get_room_anchors("North", envelope_9x12, session)
        desc = describe_anchors(anchors)
        assert "bbox=" in desc
        assert "SE" in desc


class TestFullPipeline:
    """Full pipeline: calculate_build_envelope → get_room_anchors"""

    def test_full_pipeline_end_to_end(self, session):
        from backend.engine.constraint import calculate_build_envelope
        from backend.engine.vastu_router import get_room_anchors
        bz = calculate_build_envelope(
            plot_width=12.0, plot_depth=20.0,
            authority=AuthorityEnum.CMDA, floor_level=FloorLevelEnum.G_PLUS_1,
            road_width=12.0, session=session, plot_facing="North"
        )
        anchors = get_room_anchors("North", bz.envelope_polygon, session)
        assert isinstance(anchors, dict)
        assert len(anchors) > 0
        assert "Kitchen" in anchors
        assert isinstance(anchors["Kitchen"]["bounding_box"], Polygon)
        assert anchors["Kitchen"]["bounding_box"].area > 0
