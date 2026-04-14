"""
TN-Flow API Routes — routes.py
================================
FastAPI route handlers for the two primary endpoints.

POST /api/validate-plot
    Runs the Validation Gate only (constraint.py).
    Returns BuildZone metadata: setbacks, FSI, envelope dimensions.
    Does NOT run the Vastu Router, Allocator, or Geometry Engine.
    Fast response (~5ms); useful for a real-time "Is my plot buildable?" check.

POST /api/generate-layout
    Runs the full pipeline:
        1. District lookup      → AuthorityEnum
        2. Validation Gate      → BuildZone (envelope polygon + FSI)
        3. Vastu Router         → RoomAnchorMap (zone assignments)
        4. Spatial Allocator    → AllocatedRoomMap (proportional cell subdivision)
           with geometry fallback (SpaceDeficitError drops optional rooms)
        5. Geometry Engine      → FloorPlanMap (clear polygons + carpet areas)
        6. SVG Renderer         → raw SVG string
    Returns full room data and embeddable SVG.

Error handling:
    TNCDBRValidationError / VastuRoutingError → HTTP 422 with structured JSON body.
    Not-found (district) → HTTP 404.
    Unexpected errors    → HTTP 500 (let FastAPI's default handler respond).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database.db import get_db
from backend.database.models import (
    AuthorityEnum, FloorLevelEnum, DistrictClimateMatrix,
)
from backend.engine.constraint import calculate_build_envelope, is_buildable
from backend.engine.vastu_router import get_room_anchors
from backend.engine.allocator import resolve_with_geometry_fallback
from backend.engine.exceptions import (
    TNFlowBaseError,
    TNCDBRValidationError,
    VastuRoutingError,
    SpaceDeficitError,
    AllocationError,
)
from backend.engine.geometry import NBC_CARPET_MINIMUMS
from backend.render.svg_builder import FloorPlanSVGExporter
from backend.api.schemas import (
    ValidatePlotRequest, ValidatePlotResponse, SetbackDetail,
    GenerateRequest,    GenerateResponse, RoomData,
)


router = APIRouter(prefix="/api", tags=["layout-engine"])


# ── Dependency helpers ────────────────────────────────────────────────────────

def _floor_level_enum(level_str: str) -> FloorLevelEnum:
    """Convert floor level string to enum (raises 400 if invalid)."""
    try:
        return FloorLevelEnum(level_str)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid floor_level '{level_str}'. "
                   f"Valid values: {[e.value for e in FloorLevelEnum]}",
        )


def _authority_enum(auth_str: str) -> AuthorityEnum:
    """Convert authority string to enum (raises 400 if invalid)."""
    try:
        return AuthorityEnum(auth_str)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid authority '{auth_str}'. Valid values: CMDA, DTCP",
        )


def _lookup_district(district_name: str, db: Session) -> DistrictClimateMatrix:
    """
    Look up a district by name (case-insensitive).
    Raises HTTP 404 if not found.
    """
    record = (
        db.query(DistrictClimateMatrix)
        .filter(DistrictClimateMatrix.district_name.ilike(district_name.strip()))
        .first()
    )
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"District '{district_name}' not found in the TN district database. "
                f"Check spelling or use the canonical district name (e.g. 'Chennai', "
                f"'Coimbatore', 'Madurai')."
            ),
        )
    return record


# ── POST /api/validate-plot ───────────────────────────────────────────────────

@router.post(
    "/validate-plot",
    response_model=ValidatePlotResponse,
    summary="Validate plot against TNCDBR 2019 regulations",
    description=(
        "Checks whether the given plot dimensions, road width, and floor level "
        "are legally permitted under TNCDBR 2019.  Returns the calculated build "
        "envelope (setbacks, FSI, max buildable area) without generating a layout."
    ),
)
def validate_plot(
    req: ValidatePlotRequest,
    db:  Session = Depends(get_db),
) -> ValidatePlotResponse:
    """
    Pipeline:
        1. Resolve authority + floor_level enums from request strings.
        2. Call constraint.calculate_build_envelope() with Shapely disabled
           internally only for validation; we use is_buildable() first to
           avoid raising on non-buildable plots for this endpoint.
        3. If buildable: return full BuildZone details.
        4. If not buildable: return is_buildable=False with the reason string.
    """
    authority   = _authority_enum(req.authority)
    floor_level = _floor_level_enum(req.floor_level)

    # Quick pre-check (non-raising)
    ok, reason = is_buildable(
        req.plot_width, req.plot_depth,
        authority, floor_level,
        req.road_width, db,
        req.plot_facing,
    )

    if not ok:
        return ValidatePlotResponse(
            is_buildable=False,
            plot_area_sqm=round(req.plot_width * req.plot_depth, 2),
            envelope_area_sqm=0.0,
            envelope_width_m=0.0,
            envelope_depth_m=0.0,
            fsi=0.0,
            ground_coverage_pct=0.0,
            max_buildable_sqm=0.0,
            max_footprint_sqm=0.0,
            max_height_m=None,
            setbacks=SetbackDetail(
                front_m=0.0, rear_m=0.0,
                side_left_m=0.0, side_right_m=0.0,
            ),
            rule_ref="",
            reason=reason,
        )

    # Buildable — compute full envelope details
    try:
        bz = calculate_build_envelope(
            req.plot_width, req.plot_depth,
            authority, floor_level,
            req.road_width, db,
            req.plot_facing,
        )
    except TNCDBRValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.to_dict()) from exc

    return ValidatePlotResponse(
        is_buildable=True,
        plot_area_sqm=bz.plot_area_sqm,
        envelope_area_sqm=bz.envelope_area_sqm,
        envelope_width_m=round(bz.envelope_width_m, 4),
        envelope_depth_m=round(bz.envelope_depth_m, 4),
        fsi=bz.fsi,
        ground_coverage_pct=bz.ground_coverage_pct,
        max_buildable_sqm=bz.max_buildable_sqm,
        max_footprint_sqm=bz.max_footprint_sqm,
        max_height_m=bz.max_height_m,
        setbacks=SetbackDetail(
            front_m=bz.setback_front_m,
            rear_m=bz.setback_rear_m,
            side_left_m=bz.setback_side_left_m,
            side_right_m=bz.setback_side_right_m,
        ),
        rule_ref=bz.rule_ref,
        reason=None,
    )


# ── POST /api/generate-layout ─────────────────────────────────────────────────

@router.post(
    "/generate-layout",
    response_model=GenerateResponse,
    summary="Generate a Vastu-compliant floor plan layout",
    description=(
        "Runs the full TN-Flow pipeline: TNCDBR 2019 validation → Vastu Purusha "
        "Mandala zone routing → proportional spatial allocation → wall-centric "
        "geometry → CAD-style SVG rendering.  "
        "Optional rooms (StoreRoom, Pooja) are silently dropped if the plot is "
        "too small to fit them within NBC 2016 minimums."
    ),
)
def generate_layout(
    req: GenerateRequest,
    db:  Session = Depends(get_db),
) -> GenerateResponse:
    """
    Full pipeline — five sequential stages.

    Stage 1: District → Authority
        Query DistrictClimateMatrix for the given district name.
        Extract authority (CMDA / DTCP).

    Stage 2: Validation Gate
        constraint.calculate_build_envelope(plot_width, plot_depth, authority,
            floor_level, road_width, session, plot_facing)
        → BuildZone (envelope_polygon, FSI, setbacks, etc.)
        Raises TNCDBRValidationError (→ HTTP 422) if plot is non-compliant.

    Stage 3: Vastu Router
        vastu_router.get_room_anchors(plot_facing, envelope_polygon, session)
        → RoomAnchorMap { room_type: {"zone": "SE", "bounding_box": Polygon} }
        Queries VastuGridLogic for Priority-1 zone assignments.

    Stage 4: Spatial Allocator + Geometry (with fallback)
        allocator.resolve_with_geometry_fallback(bhk_type, anchors, envelope)
        → (AllocatedRoomMap, dropped_rooms, FloorPlanMap)
        Internally calls resolve_spatial_conflicts() then apply_wall_thickness().
        Progressively drops optional rooms (StoreRoom → Pooja → ...) if
        SpaceDeficitError is raised for them.

    Stage 5: SVG Renderer
        svg_builder.FloorPlanSVGExporter(floor_plan, build_zone, allocated,
            plot_width, plot_depth, bhk_type, plot_facing, dropped).export()
        → raw SVG string (embeddable <svg> element)
    """
    # ── Stage 1: District → Authority ─────────────────────────────────────
    district_record = _lookup_district(req.district, db)
    authority       = district_record.authority
    floor_level     = _floor_level_enum(req.floor_level)

    # ── Stage 2: Validation Gate ──────────────────────────────────────────
    try:
        bz = calculate_build_envelope(
            req.plot_width, req.plot_depth,
            authority, floor_level,
            req.road_width, db,
            req.plot_facing,
        )
    except TNCDBRValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.to_dict()) from exc

    # ── Stage 3: Vastu Router ─────────────────────────────────────────────
    try:
        room_anchors = get_room_anchors(req.plot_facing, bz.envelope_polygon, db)
    except VastuRoutingError as exc:
        raise HTTPException(status_code=422, detail=exc.to_dict()) from exc

    # ── Stage 4: Spatial Allocator + Geometry (fallback-enabled) ─────────
    try:
        allocated, dropped, floor_plan = resolve_with_geometry_fallback(
            req.bhk_type, room_anchors, bz.envelope_polygon
        )
    except (SpaceDeficitError, AllocationError) as exc:
        raise HTTPException(status_code=422, detail=exc.to_dict()) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # ── Stage 5: SVG Renderer ─────────────────────────────────────────────
    exporter = FloorPlanSVGExporter(
        floor_plan=floor_plan,
        build_zone=bz,
        allocated=allocated,
        plot_width=req.plot_width,
        plot_depth=req.plot_depth,
        bhk_type=req.bhk_type,
        plot_facing=req.plot_facing,
        dropped_rooms=dropped,
    )
    svg_str = exporter.export()

    # ── Build response ────────────────────────────────────────────────────
    room_list: list[RoomData] = []
    for room_name, data in floor_plan.items():
        w_m, d_m = data["dimensions"]
        zone     = room_anchors.get(room_name, {}).get("zone", "?")
        nbc_min  = NBC_CARPET_MINIMUMS.get(room_name, 1.5)
        room_list.append(RoomData(
            room_name=room_name,
            zone=zone,
            carpet_area_sqm=data["carpet_area_sqm"],
            width_m=w_m,
            depth_m=d_m,
            nbc_minimum_sqm=nbc_min,
        ))

    # Sort rooms by carpet area descending for a natural read order
    room_list.sort(key=lambda r: -r.carpet_area_sqm)

    total_carpet = sum(r.carpet_area_sqm for r in room_list)

    return GenerateResponse(
        district=district_record.district_name,
        authority=authority.value,
        plot_facing=req.plot_facing,
        plot_area_sqm=bz.plot_area_sqm,
        envelope_area_sqm=bz.envelope_area_sqm,
        fsi=bz.fsi,
        max_buildable_sqm=bz.max_buildable_sqm,
        bhk_type=req.bhk_type,
        rooms_dropped=dropped,
        rooms=room_list,
        total_carpet_sqm=round(total_carpet, 2),
        svg=svg_str,
    )
