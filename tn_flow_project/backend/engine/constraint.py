"""
TN-Flow Validation Gate — constraint.py
========================================
The first checkpoint in the TN-Flow pipeline.

Responsibilities:
  1. Query PlotEligibilityRules to find the applicable TNCDBR 2019 rule.
  2. Validate that the user's plot dimensions meet the rule's minimums.
  3. Apply orientation-aware setbacks via Shapely polygon arithmetic.
  4. Return a BuildZone object containing the legal build envelope polygon,
     FSI limits, coverage limits, and height cap.

Primary public API:
  calculate_build_envelope(plot_width, plot_depth, authority, floor_level,
                           road_width, session, plot_facing="North")
                           -> BuildZone

The vastu_router.py module receives the BuildZone's envelope_polygon as its
primary input.  The geometry.py / allocator.py modules receive the full
BuildZone object for wall-centric polygon subdivision.

Coordinate system (used throughout the engine):
  (0, 0) = South-West corner of the plot
  +X     = East
  +Y     = North
  The road-facing edge is determined by plot_facing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Optional

from shapely.geometry import box, Polygon
from sqlalchemy import and_
from sqlalchemy.orm import Session

from backend.database.models import (
    PlotEligibilityRules,
    AuthorityEnum,
    FloorLevelEnum,
)
from backend.engine.exceptions import (
    RoadWidthInsufficientError,
    PlotTooSmallError,
    FloorLevelNotPermittedError,
    SetbackExceedsPlotError,
    InsufficientBuildEnvelopeError,
)


# ── Constants ─────────────────────────────────────────────────────────────────

# Minimum absolute build envelope area below which we refuse to generate.
# 10m² is the lower bound below which no meaningful residential space can fit.
# (NBC 2016 Cl. 4.2.1 smallest habitable room = 7.5m², plus circulation.)
_MIN_VIABLE_ENVELOPE_SQM: float = 10.0

# Minimum usable dimension (width or depth) of the build envelope.
# A 1.5m corridor is the narrowest meaningful interior circulation space.
_MIN_VIABLE_DIMENSION_M: float = 1.5

# G+1 and G+2 minimum road width prerequisites (TNCDBR 2019 §9).
# Used to generate a more specific error when road_width < these thresholds.
_MIN_ROAD_G1_M: float = 6.0
_MIN_ROAD_G2_M: float = 9.0

# Valid plot-facing values (mirrors VastuGridLogic.plot_facing constraint)
_VALID_FACINGS: frozenset[str] = frozenset({"North", "South", "East", "West"})

# Wall thickness constants (used by downstream geometry.py for carpet area)
EXTERNAL_WALL_THICKNESS_M: float = 0.230   # 230mm brick + plaster
INTERNAL_WALL_THICKNESS_M: float = 0.115   # 115mm half-brick partition


# ── Setback Orientation Formulas ─────────────────────────────────────────────
#
# Returns (min_x, min_y, max_x, max_y) for the build envelope rectangle.
# All coordinates are in absolute plot space: (0,0)=SW, X=East, Y=North.
#
# Left/Right convention:
#   From the perspective of a person standing ON THE ROAD looking INTO the plot.
#
#   Facing North (road to North, viewer looks South):
#     → viewer faces South  → left=East(maxX), right=West(minX)
#
#   Facing South (road to South, viewer looks North):
#     → viewer faces North  → left=West(minX), right=East(maxX)
#
#   Facing East (road to East, viewer looks West):
#     → viewer faces West   → left=South(minY), right=North(maxY)
#
#   Facing West (road to West, viewer looks East):
#     → viewer faces East   → left=North(maxY), right=South(minY)
#
# Arguments:  pw=plot_width, pd=plot_depth,
#             sf=setback_front, sr=setback_rear,
#             sl=setback_side_left, srr=setback_side_right
#
# NOTE: For symmetric setbacks (sl == srr, which is true for all TNCDBR 2019
# seed rows) the result is identical regardless of which side is "left" or
# "right".  The asymmetric formulas are provided for correctness and for
# future site-specific custom setback support.
#
_SETBACK_FORMULA: dict[str, Callable[[float, float, float, float, float, float],
                                      tuple[float, float, float, float]]] = {
    #                           min_x   min_y      max_x       max_y
    "North": lambda pw, pd, sf, sr, sl, srr: (srr,  sr,   pw - sl,   pd - sf),
    "South": lambda pw, pd, sf, sr, sl, srr: (sl,   sf,   pw - srr,  pd - sr),
    "East":  lambda pw, pd, sf, sr, sl, srr: (sr,   sl,   pw - sf,   pd - srr),
    "West":  lambda pw, pd, sf, sr, sl, srr: (sf,   srr,  pw - sr,   pd - sl),
}


# ── BuildZone Data Class ──────────────────────────────────────────────────────

@dataclass
class BuildZone:
    """
    Immutable output of calculate_build_envelope().

    Encapsulates every piece of information the downstream pipeline needs to
    generate a legal, TNCDBR-compliant floor plan:

      - The Shapely polygon of the legal build envelope (post-setbacks).
      - FSI, coverage, and height limits derived from the matched rule.
      - The original plot polygon (for rendering dimension lines/annotations).
      - Traceability back to the matched PlotEligibilityRules row.

    Derived properties (computed automatically from stored fields):
      carpet_area_budget_sqm : Approximate max. carpet area after wall deductions.
      envelope_width_m       : East-West span of the build envelope.
      envelope_depth_m       : North-South span of the build envelope.
      usable_ratio           : envelope_area / plot_area (build efficiency metric).
    """

    # ── Input parameters (echoed for traceability) ────────────────────────
    plot_width_m:   float       # East-West span of the gross plot
    plot_depth_m:   float       # North-South span of the gross plot
    plot_facing:    str         # 'North' | 'South' | 'East' | 'West'
    authority:      AuthorityEnum
    floor_level:    FloorLevelEnum
    road_width_m:   float       # Abutting road width supplied by the user

    # ── Core Shapely geometry ─────────────────────────────────────────────
    plot_polygon:     Polygon   # Raw rectangle: box(0, 0, plot_width, plot_depth)
    envelope_polygon: Polygon   # Usable build area after setback subtraction

    # ── Area metrics (square metres) ─────────────────────────────────────
    plot_area_sqm:     float    # plot_width × plot_depth (gross)
    envelope_area_sqm: float    # envelope_polygon.area (net usable)

    # ── Applied setbacks (metres) — from matched PlotEligibilityRules ────
    setback_front_m:      float
    setback_rear_m:       float
    setback_side_left_m:  float
    setback_side_right_m: float

    # ── Regulatory limits (from matched PlotEligibilityRules) ────────────
    fsi:                  float   # Floor Space Index
    ground_coverage_pct:  float   # Max ground footprint as % of plot area
    max_buildable_sqm:    float   # fsi × plot_area (total built-up area across all floors)
    max_footprint_sqm:    float   # (coverage_pct/100) × plot_area (ground level max)
    max_height_m:         Optional[float]  # None = no explicit cap

    # ── Rule provenance ───────────────────────────────────────────────────
    matched_rule_id:  int
    rule_reference:   Optional[str]

    # ── Derived properties ────────────────────────────────────────────────

    @property
    def envelope_width_m(self) -> float:
        """
        East-West span of the build envelope (post-setback X dimension).

        For North/South-facing plots: plot_width minus side setbacks.
        For East/West-facing plots:   plot_depth minus side setbacks
                                      (the Y axis is the frontage axis).
        """
        minx, _, maxx, _ = self.envelope_polygon.bounds
        return maxx - minx

    @property
    def envelope_depth_m(self) -> float:
        """North-South span of the build envelope (post-setback Y dimension)."""
        _, miny, _, maxy = self.envelope_polygon.bounds
        return maxy - miny

    @property
    def usable_ratio(self) -> float:
        """
        Ratio of build envelope area to gross plot area.
        Indicates what fraction of the plot can actually be built on.
        A value of 0.50 means 50% of the plot is usable after setbacks.
        """
        return self.envelope_area_sqm / self.plot_area_sqm if self.plot_area_sqm > 0 else 0.0

    @property
    def carpet_area_budget_sqm(self) -> float:
        """
        Approximate maximum carpet area (RERA definition) after deducting
        external and average internal wall thicknesses from the envelope area.

        Wall deduction model (PRD — wall-centric approach):
          External walls: 230mm thickness line the entire envelope perimeter.
          Internal walls: 115mm per ~3.5m of linear internal partition
                          (heuristic: 1 wall per 3.5m of plan dimension).

        Formula:
          carpet ≈ envelope_area
                   - external_wall_area (perimeter × 0.230)
                   - internal_wall_area (est. partition length × 0.115)

        This is an ESTIMATE for pre-validation only.  The geometry engine
        (geometry.py) performs the exact wall-centric polygon subtraction.
        """
        perimeter = self.envelope_polygon.length
        ext_wall_area = perimeter * EXTERNAL_WALL_THICKNESS_M

        # Heuristic: average number of internal partitions ≈ plan area / 12
        # Each partition ≈ min(width, depth) / 2 metres long
        avg_partition_length = min(self.envelope_width_m, self.envelope_depth_m) / 2.0
        est_partition_count = max(1, self.envelope_area_sqm / 12.0)
        int_wall_area = est_partition_count * avg_partition_length * INTERNAL_WALL_THICKNESS_M

        return max(0.0, self.envelope_area_sqm - ext_wall_area - int_wall_area)

    def __repr__(self) -> str:
        return (
            f"BuildZone("
            f"{self.authority.value} {self.floor_level.value}, "
            f"plot={self.plot_width_m:.1f}x{self.plot_depth_m:.1f}m "
            f"facing={self.plot_facing}, "
            f"envelope={self.envelope_area_sqm:.1f}sqm "
            f"[{self.envelope_width_m:.2f}x{self.envelope_depth_m:.2f}m], "
            f"FSI={self.fsi}, cov={self.ground_coverage_pct:.0f}%)"
        )


# ── Private Helpers ───────────────────────────────────────────────────────────

def _fetch_eligible_rule(
    authority:   AuthorityEnum,
    floor_level: FloorLevelEnum,
    road_width:  float,
    session:     Session,
) -> PlotEligibilityRules:
    """
    Query PlotEligibilityRules for the best matching row.

    Selection algorithm:
      SELECT * FROM plot_eligibility_rules
       WHERE authority       = :authority
         AND floor_level     = :floor_level
         AND road_width_min_m <= :road_width
       ORDER BY road_width_min_m DESC
       LIMIT 1

    "Best match" = the row with the HIGHEST road_width_min_m that does not
    exceed the actual road width.  This selects the most granular (strictest
    setback, most accurate FSI) rule for the given road condition.

    Absence of any matching row means the floor level is NOT PERMITTED at
    the given road width — the Validation Gate must reject the request.

    Args:
        authority:   CMDA or DTCP (from DistrictClimateMatrix.authority).
        floor_level: Ground, G+1, or G+2 (user input).
        road_width:  Width of the abutting road in metres (user input).
        session:     Active SQLAlchemy session.

    Returns:
        The best matching PlotEligibilityRules ORM object.

    Raises:
        FloorLevelNotPermittedError: When floor_level > Ground and road_width
                                     is below the TNCDBR minimum for that level.
        RoadWidthInsufficientError:  When no rule exists at all for the combo.
    """
    # Guard: check TNCDBR road-width prerequisites before hitting the DB.
    if floor_level == FloorLevelEnum.G_PLUS_1 and road_width < _MIN_ROAD_G1_M:
        raise FloorLevelNotPermittedError(
            f"G+1 construction is not permitted on a {road_width:.1f}m road "
            f"({authority.value}). Minimum road width for G+1 is "
            f"{_MIN_ROAD_G1_M:.1f}m (TNCDBR 2019 §9(1)).",
            floor_level=floor_level.value,
            min_road_required=_MIN_ROAD_G1_M,
            actual_road_width=road_width,
            authority=authority.value,
        )

    if floor_level == FloorLevelEnum.G_PLUS_2 and road_width < _MIN_ROAD_G2_M:
        raise FloorLevelNotPermittedError(
            f"G+2 construction is not permitted on a {road_width:.1f}m road "
            f"({authority.value}). Minimum road width for G+2 is "
            f"{_MIN_ROAD_G2_M:.1f}m (TNCDBR 2019 §9(2)).",
            floor_level=floor_level.value,
            min_road_required=_MIN_ROAD_G2_M,
            actual_road_width=road_width,
            authority=authority.value,
        )

    rule: Optional[PlotEligibilityRules] = (
        session.query(PlotEligibilityRules)
        .filter(
            and_(
                PlotEligibilityRules.authority       == authority,
                PlotEligibilityRules.floor_level     == floor_level,
                PlotEligibilityRules.road_width_min_m <= road_width,
            )
        )
        .order_by(PlotEligibilityRules.road_width_min_m.desc())
        .first()
    )

    if rule is None:
        raise RoadWidthInsufficientError(
            f"No {floor_level.value} construction rule found for "
            f"{authority.value} with road width {road_width:.1f}m. "
            f"Verify that the road width is correct and that this "
            f"configuration is supported by TNCDBR 2019.",
            authority=authority.value,
            floor_level=floor_level.value,
            road_width_m=road_width,
        )

    return rule


def _validate_plot_against_rule(
    plot_width:  float,
    plot_depth:  float,
    plot_facing: str,
    rule:        PlotEligibilityRules,
) -> None:
    """
    Verify that the user's plot satisfies the minimum dimensional requirements
    of the matched PlotEligibilityRules row.

    Three checks are performed:
      1. Gross plot area  >= rule.plot_area_min_sqm
      2. Road frontage    >= rule.plot_width_min_m
      3. Run depth        >= rule.plot_depth_min_m

    Orientation-aware frontage / run mapping:
      For North/South-facing plots the frontage is the X dimension (plot_width)
      and the run is the Y dimension (plot_depth).
      For East/West-facing plots the frontage is the Y dimension (plot_depth)
      and the run is the X dimension (plot_width).
      This is because in Indian practice "plot width" = road-facing dimension,
      which changes based on which compass face abuts the road.

    Args:
        plot_width:  East-West span of the gross plot (metres).
        plot_depth:  North-South span of the gross plot (metres).
        plot_facing: Plot orientation string.
        rule:        The matched PlotEligibilityRules row.

    Raises:
        PlotTooSmallError: If any dimensional check fails.
    """
    plot_area = plot_width * plot_depth

    # Determine road-facing frontage vs run depth based on orientation
    if plot_facing in ("North", "South"):
        frontage, run = plot_width, plot_depth
        frontage_axis, run_axis = "width (X)", "depth (Y)"
    else:  # East, West
        frontage, run = plot_depth, plot_width
        frontage_axis, run_axis = "depth (Y — road-facing for E/W plots)", "width (X)"

    if plot_area < rule.plot_area_min_sqm:
        raise PlotTooSmallError(
            f"Plot area {plot_area:.2f}m² is below the minimum "
            f"{rule.plot_area_min_sqm:.1f}m² required for "
            f"{rule.floor_level.value} on a {rule.road_width_min_m:.1f}m+ "
            f"road ({rule.authority.value}). [{rule.rule_reference or 'TNCDBR 2019'}]",
            dimension="area",
            actual_value=round(plot_area, 2),
            minimum=rule.plot_area_min_sqm,
            authority=rule.authority.value,
            floor_level=rule.floor_level.value,
            rule_ref=rule.rule_reference,
        )

    if frontage < rule.plot_width_min_m:
        raise PlotTooSmallError(
            f"Plot road-frontage ({frontage_axis}) {frontage:.2f}m is below "
            f"the {rule.plot_width_min_m:.1f}m minimum for this rule. "
            f"[{rule.rule_reference or 'TNCDBR 2019'}]",
            dimension="frontage_width",
            actual_value=round(frontage, 2),
            minimum=rule.plot_width_min_m,
            rule_ref=rule.rule_reference,
        )

    if run < rule.plot_depth_min_m:
        raise PlotTooSmallError(
            f"Plot run-depth ({run_axis}) {run:.2f}m is below "
            f"the {rule.plot_depth_min_m:.1f}m minimum for this rule. "
            f"[{rule.rule_reference or 'TNCDBR 2019'}]",
            dimension="run_depth",
            actual_value=round(run, 2),
            minimum=rule.plot_depth_min_m,
            rule_ref=rule.rule_reference,
        )


def _compute_envelope_polygon(
    plot_width:          float,
    plot_depth:          float,
    plot_facing:         str,
    setback_front:       float,
    setback_rear:        float,
    setback_side_left:   float,
    setback_side_right:  float,
) -> Polygon:
    """
    Apply TNCDBR setbacks to a rectangular plot and return the build envelope.

    Mathematical model:
    ──────────────────
    The gross plot is represented as a Shapely box from (0,0) to
    (plot_width, plot_depth) in the engine's fixed coordinate system
    (X = East, Y = North).

    Setbacks define four inset boundaries.  For a North-facing plot
    (road = North edge, high-Y side):

        Build Envelope = box(
            min_x = setback_side_right,             ← West boundary
            min_y = setback_rear,                   ← South boundary
            max_x = plot_width  − setback_side_left,← East boundary
            max_y = plot_depth  − setback_front,    ← North boundary (road side)
        )

    The _SETBACK_FORMULA dict encodes the equivalent min_x/min_y/max_x/max_y
    computation for all four orientations, derived from the left/right
    convention documented in the module constant block.

    Post-computation sanity checks:
      • Envelope dimensions must both be positive (> _MIN_VIABLE_DIMENSION_M).
      • Envelope area must be > _MIN_VIABLE_ENVELOPE_SQM.

    Args:
        plot_width/depth:  Gross plot dimensions (metres).
        plot_facing:       'North' | 'South' | 'East' | 'West'.
        setback_*:         TNCDBR-mandated setbacks (metres) from the rule.

    Returns:
        Shapely Polygon representing the legal build envelope.

    Raises:
        SetbackExceedsPlotError:        If setbacks leave zero or negative area.
        InsufficientBuildEnvelopeError: If remaining area < _MIN_VIABLE_ENVELOPE_SQM.
    """
    if plot_facing not in _VALID_FACINGS:
        raise ValueError(
            f"Invalid plot_facing '{plot_facing}'. "
            f"Must be one of: {sorted(_VALID_FACINGS)}."
        )

    formula = _SETBACK_FORMULA[plot_facing]
    min_x, min_y, max_x, max_y = formula(
        plot_width, plot_depth,
        setback_front, setback_rear,
        setback_side_left, setback_side_right,
    )

    envelope_w = max_x - min_x
    envelope_d = max_y - min_y

    # ── Check 1: envelope dimensions must be positive ─────────────────────
    if envelope_w <= 0 or envelope_d <= 0:
        raise SetbackExceedsPlotError(
            f"After applying setbacks (front={setback_front}m, "
            f"rear={setback_rear}m, sides={setback_side_left}/{setback_side_right}m) "
            f"to a {plot_width}x{plot_depth}m {plot_facing}-facing plot, "
            f"the build envelope has zero or negative dimensions "
            f"(W={envelope_w:.2f}m, D={envelope_d:.2f}m). "
            f"The plot is too narrow for these setbacks.",
            envelope_width_m=round(envelope_w, 3),
            envelope_depth_m=round(envelope_d, 3),
            setback_front_m=setback_front,
            setback_rear_m=setback_rear,
            setback_side_m=max(setback_side_left, setback_side_right),
        )

    # ── Check 2: minimum viable dimension ─────────────────────────────────
    if min(envelope_w, envelope_d) < _MIN_VIABLE_DIMENSION_M:
        raise SetbackExceedsPlotError(
            f"Build envelope dimension {min(envelope_w, envelope_d):.2f}m is below "
            f"the minimum viable interior dimension of {_MIN_VIABLE_DIMENSION_M}m. "
            f"No meaningful room can be fitted in a {envelope_w:.2f}x{envelope_d:.2f}m space.",
            envelope_width_m=round(envelope_w, 3),
            envelope_depth_m=round(envelope_d, 3),
            min_viable_m=_MIN_VIABLE_DIMENSION_M,
        )

    envelope = box(min_x, min_y, max_x, max_y)

    # ── Check 3: minimum viable area ─────────────────────────────────────
    if envelope.area < _MIN_VIABLE_ENVELOPE_SQM:
        raise InsufficientBuildEnvelopeError(
            f"Build envelope area {envelope.area:.2f}m² is below the minimum "
            f"viable floor plan area of {_MIN_VIABLE_ENVELOPE_SQM:.1f}m². "
            f"The plot cannot support any NBC 2016 compliant space layout.",
            envelope_area_sqm=round(envelope.area, 2),
            minimum_sqm=_MIN_VIABLE_ENVELOPE_SQM,
        )

    return envelope


# ── Public API ────────────────────────────────────────────────────────────────

def calculate_build_envelope(
    plot_width:  float,
    plot_depth:  float,
    authority:   AuthorityEnum,
    floor_level: FloorLevelEnum,
    road_width:  float,
    session:     Session,
    plot_facing: str = "North",
) -> BuildZone:
    """
    Validation Gate — main entry point.

    Validates a user's residential plot configuration against TNCDBR 2019
    regulations and returns the legal build envelope as a BuildZone object.

    Pipeline:
    ─────────
    1. Pre-flight guard: validate road_width > 0, plot dimensions > 0.
    2. DB query: fetch best matching PlotEligibilityRules row via
       _fetch_eligible_rule().
    3. Dimension check: verify plot area, frontage, and run depth against
       the rule's minimums via _validate_plot_against_rule().
    4. Polygon arithmetic: apply orientation-aware setbacks via
       _compute_envelope_polygon() to produce the build envelope.
    5. Derived metrics: compute FSI-based buildable area, coverage-based
       footprint limit, carpet area budget.
    6. Return: package everything into a BuildZone dataclass.

    Setback application example (North-facing, 6x12m CMDA plot, 6m road):
    ──────────────────────────────────────────────────────────────────────
      Rule row: front=1.5m, rear=1.0m, sides=1.0m, FSI=2.0, cov=60%
      Plot polygon: box(0, 0, 6, 12)       [6m wide, 12m deep]
      Envelope:     box(1.0, 1.0, 5.0, 10.5)
                    [4m wide × 9.5m deep = 38m² build area]
      FSI:          2.0 × 72m² (plot area) = 144m² total built-up area allowed
      Coverage:     60% × 72m²             = 43.2m² max ground footprint

    Args:
        plot_width:  East-West span of the gross plot in metres.
                     For North/South-facing plots, this is the road frontage.
                     For East/West-facing plots, this is the depth from road.
        plot_depth:  North-South span of the gross plot in metres.
        authority:   AuthorityEnum.CMDA or AuthorityEnum.DTCP.
                     Use DistrictClimateMatrix.authority for the plot's district.
        floor_level: FloorLevelEnum.GROUND, G_PLUS_1, or G_PLUS_2.
        road_width:  Width of the abutting road in metres (minimum 3.0m).
        session:     Active SQLAlchemy Session (injected by FastAPI dependency).
        plot_facing: Compass direction the main entrance faces.
                     Must be 'North', 'South', 'East', or 'West'.
                     Default 'North' (most common in TN urban layouts).

    Returns:
        BuildZone: immutable dataclass containing the build envelope polygon,
                   FSI/coverage/height limits, and full traceability metadata.

    Raises:
        ValueError:                      plot dimensions <= 0 or invalid facing.
        FloorLevelNotPermittedError:     G+1/G+2 requested on road < 6m/9m.
        RoadWidthInsufficientError:      No matching rule in DB for this combo.
        PlotTooSmallError:               Plot dimensions below rule minimums.
        SetbackExceedsPlotError:         Setbacks consume entire plot width/depth.
        InsufficientBuildEnvelopeError:  Envelope < 10m² (no viable floor plan).
    """
    # ── Pre-flight guards ─────────────────────────────────────────────────
    if plot_width <= 0 or plot_depth <= 0:
        raise ValueError(
            f"Plot dimensions must be positive. "
            f"Got: width={plot_width}m, depth={plot_depth}m."
        )
    if road_width <= 0:
        raise ValueError(f"Road width must be positive. Got: {road_width}m.")
    if plot_facing not in _VALID_FACINGS:
        raise ValueError(
            f"Invalid plot_facing '{plot_facing}'. "
            f"Valid values: {sorted(_VALID_FACINGS)}."
        )

    # ── Step 1: fetch matched TNCDBR rule ─────────────────────────────────
    rule = _fetch_eligible_rule(authority, floor_level, road_width, session)

    # ── Step 2: validate plot dimensions against the rule ─────────────────
    _validate_plot_against_rule(plot_width, plot_depth, plot_facing, rule)

    # ── Step 3: build raw plot polygon ────────────────────────────────────
    # Origin (0,0) = SW corner.  All downstream modules use this convention.
    plot_polygon = box(0.0, 0.0, plot_width, plot_depth)

    # ── Step 4: compute build envelope via setback subtraction ───────────
    envelope_polygon = _compute_envelope_polygon(
        plot_width,  plot_depth, plot_facing,
        rule.setback_front_m,
        rule.setback_rear_m,
        rule.setback_side_left_m,
        rule.setback_side_right_m,
    )

    # ── Step 5: compute derived regulatory metrics ────────────────────────
    plot_area       = plot_width * plot_depth         # m²
    envelope_area   = envelope_polygon.area           # m²
    max_buildable   = rule.fsi_value * plot_area      # total floor area across all floors
    max_footprint   = (rule.ground_coverage_pct / 100.0) * plot_area  # ground level cap

    # ── Step 6: return BuildZone ──────────────────────────────────────────
    return BuildZone(
        # Input echo
        plot_width_m   = plot_width,
        plot_depth_m   = plot_depth,
        plot_facing    = plot_facing,
        authority      = authority,
        floor_level    = floor_level,
        road_width_m   = road_width,
        # Geometry
        plot_polygon     = plot_polygon,
        envelope_polygon = envelope_polygon,
        # Areas
        plot_area_sqm     = round(plot_area, 4),
        envelope_area_sqm = round(envelope_area, 4),
        # Setbacks
        setback_front_m      = rule.setback_front_m,
        setback_rear_m       = rule.setback_rear_m,
        setback_side_left_m  = rule.setback_side_left_m,
        setback_side_right_m = rule.setback_side_right_m,
        # Regulatory limits
        fsi                  = rule.fsi_value,
        ground_coverage_pct  = rule.ground_coverage_pct,
        max_buildable_sqm    = round(max_buildable, 2),
        max_footprint_sqm    = round(max_footprint, 2),
        max_height_m         = rule.max_height_m,
        # Provenance
        matched_rule_id  = rule.id,
        rule_reference   = rule.rule_reference,
    )


def is_buildable(
    plot_width:  float,
    plot_depth:  float,
    authority:   AuthorityEnum,
    floor_level: FloorLevelEnum,
    road_width:  float,
    session:     Session,
    plot_facing: str = "North",
) -> tuple[bool, str]:
    """
    Non-raising convenience wrapper around calculate_build_envelope().

    Returns (True, "") if the configuration is valid, or (False, reason_msg)
    if any validation step fails.

    Useful for frontend form validation without requiring try/except.

    Example::

        ok, reason = is_buildable(6, 12, AuthorityEnum.CMDA,
                                  FloorLevelEnum.G_PLUS_1, 6.0, db_session)
        if not ok:
            return JSONResponse({"error": reason}, status_code=422)
    """
    try:
        calculate_build_envelope(
            plot_width, plot_depth, authority, floor_level,
            road_width, session, plot_facing,
        )
        return True, ""
    except Exception as exc:
        return False, str(exc)
