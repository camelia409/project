"""
TN-Flow Vastu Router — vastu_router.py
=======================================
Assigns spatial anchor points (bounding boxes) to primary rooms by overlaying
the Vastu Purusha Mandala — a 3×3 compass grid — onto the legal build envelope.

Background — Vastu Purusha Mandala
────────────────────────────────────
The Vastu Purusha Mandala is the foundational spatial grid of Vastu Shastra.
It divides any rectangular site into nine equal cells (Padas), each governed by
a presiding deity (Devata) whose energy determines the functional suitability of
rooms placed within it.  In the simplified 3×3 model used here, each cell
corresponds to one of the eight compass octants plus a central Brahmasthana:

    ┌──────────────┬──────────────┬──────────────┐  Y
    │  NW          │  N           │  NE          │  ↑  Row 2
    │  (Vayu)      │  (Kubera)    │  (Ishanya)   │  |
    ├──────────────┼──────────────┼──────────────┤  |
    │  W           │  Brahma      │  E           │  |  Row 1
    │  (Varuna)    │  (centre)    │  (Indra)     │  |
    ├──────────────┼──────────────┼──────────────┤  |
    │  SW          │  S           │  SE          │  |  Row 0
    │  (Niruthi)   │  (Yama)      │  (Agni)      │  |
    └──────────────┴──────────────┴──────────────┘  └──→ X
      Col 0 (West)   Col 1 (Ctr)   Col 2 (East)

Engine coordinate system (consistent with constraint.py):
  Origin (0, 0) = South-West corner of the build envelope.
  +X = East,  +Y = North.

Primary public API:
  get_room_anchors(plot_facing, build_zone_polygon, session) → RoomAnchorMap

    Returns:
      { "Kitchen": {"zone": "SE", "bounding_box": Polygon},
        "MasterBedroom": {"zone": "SW", "bounding_box": Polygon}, ... }

    The downstream geometry engine (allocator.py) uses each room's
    ``bounding_box`` as the polygon seed for wall-centric room subdivision.

Secondary helpers (for conflict resolution / debugging):
  get_mandala_grid(envelope_polygon)  → dict[VastuZoneEnum, Polygon]
  describe_anchors(anchors)           → str  (human-readable report)
"""

from __future__ import annotations

from typing import Dict, Optional, List

from shapely.geometry import box, Polygon
from sqlalchemy.orm import Session

from backend.database.models import VastuGridLogic, VastuZoneEnum
from backend.engine.exceptions import (
    VastuRoutingError,
    UnresolvableRoomPlacementError,
    VastuZoneUnavailableError,
)


# ── Type alias ────────────────────────────────────────────────────────────────

# Canonical return type of get_room_anchors().
# Keys are room_type strings; values contain abbreviated zone tag + Polygon.
RoomAnchorMap = Dict[str, Dict]

# Canonical return type of get_mandala_grid().
MandalaGrid = Dict[VastuZoneEnum, Polygon]


# ── Constants ─────────────────────────────────────────────────────────────────

# Valid compass orientations (mirrors VastuGridLogic.plot_facing CHECK constraint)
_VALID_FACINGS: frozenset[str] = frozenset({"North", "South", "East", "West"})

# Map each VastuZoneEnum to its two-letter abbreviated compass tag.
# Used as the "zone" string in the returned RoomAnchorMap dicts.
_ZONE_ABBREVIATION: dict[VastuZoneEnum, str] = {
    VastuZoneEnum.NORTHEAST: "NE",
    VastuZoneEnum.NORTH:     "N",
    VastuZoneEnum.NORTHWEST: "NW",
    VastuZoneEnum.EAST:      "E",
    VastuZoneEnum.WEST:      "W",
    VastuZoneEnum.SOUTHEAST: "SE",
    VastuZoneEnum.SOUTH:     "S",
    VastuZoneEnum.SOUTHWEST: "SW",
}

# Reverse mapping: abbreviated tag → VastuZoneEnum (for external callers)
_ABBREVIATION_TO_ZONE: dict[str, VastuZoneEnum] = {
    v: k for k, v in _ZONE_ABBREVIATION.items()
}

# ── 3×3 Grid Position Table ───────────────────────────────────────────────────
#
# Each Vastu zone maps to a (column, row) index in the 3×3 Mandala grid.
#
# Column index  (col ∈ {0, 1, 2}):
#   col = 0  → West  third  [min_x   .. min_x + W/3]
#   col = 1  → Centre third [min_x + W/3 .. min_x + 2W/3]
#   col = 2  → East  third  [min_x + 2W/3 .. max_x]
#
# Row index (row ∈ {0, 1, 2}):
#   row = 0  → South third  [min_y   .. min_y + H/3]
#   row = 1  → Centre third [min_y + H/3 .. min_y + 2H/3]
#   row = 2  → North third  [min_y + 2H/3 .. max_y]
#
# The Brahmasthana (col=1, row=1) is the sacred centre; no standard room is
# seeded there in VastuGridLogic, so it is deliberately absent from this table.
#
_ZONE_GRID_POSITION: dict[VastuZoneEnum, tuple[int, int]] = {
    # ── South row (row = 0) ──────────────────────────────────────────────────
    VastuZoneEnum.SOUTHWEST: (0, 0),   # Niruthi — stability, heavy mass
    VastuZoneEnum.SOUTH:     (1, 0),   # Yama    — rest, endings
    VastuZoneEnum.SOUTHEAST: (2, 0),   # Agni    — fire, cooking

    # ── Centre row (row = 1) ─────────────────────────────────────────────────
    VastuZoneEnum.WEST:      (0, 1),   # Varuna  — water, nourishment
    #                        (1, 1)    # Brahma  — sacred centre (no room)
    VastuZoneEnum.EAST:      (2, 1),   # Indra   — social energy, sunrise

    # ── North row (row = 2) ──────────────────────────────────────────────────
    VastuZoneEnum.NORTHWEST: (0, 2),   # Vayu    — air, movement, guests
    VastuZoneEnum.NORTH:     (1, 2),   # Kubera  — wealth, water storage
    VastuZoneEnum.NORTHEAST: (2, 2),   # Ishanya — knowledge, sacred
}

# NBC 2016 minimum usable floor area (sq.m) per room type.
# A cell whose area falls below this threshold is considered unusable for
# the corresponding room.  The engine raises VastuZoneUnavailableError when
# a MANDATORY room's assigned cell is below its NBC minimum.
#
# References:
#   NBC 2016 Cl.4.2.1 — habitable rooms ≥ 7.5 m² (9.5 m² for master)
#   NBC 2016 Cl.4.2.4 — kitchen ≥ 4.5 m²
#   NBC 2016 Cl.4.2.6 — bathroom ≥ 1.2 m²
_NBC_MIN_ROOM_AREA_SQM: dict[str, float] = {
    "Kitchen":       4.5,
    "MasterBedroom": 9.5,
    "Bedroom2":      7.5,
    "Bedroom3":      7.5,
    "Pooja":         2.0,
    "Toilet":        1.2,
    "Hall":          9.5,
    "Dining":        6.0,
    "Staircase":     4.5,
    "StoreRoom":     1.5,
    "Entrance":      1.0,
}

# Fallback minimum applied to room types not in the table above.
_DEFAULT_MIN_ROOM_AREA_SQM: float = 2.0


# ── Core Grid Builder ─────────────────────────────────────────────────────────

def get_mandala_grid(envelope_polygon: Polygon) -> MandalaGrid:
    """
    Divide the build envelope into the eight-zone Vastu Purusha Mandala.

    Mathematical Model — Equal Thirds Division:
    ────────────────────────────────────────────
    Let the bounding box of ``envelope_polygon`` be:
        (min_x, min_y, max_x, max_y)

    The total dimensions are:
        W = max_x − min_x     [East-West width, metres]
        H = max_y − min_y     [North-South depth, metres]

    Each cell occupies one-third of the width and one-third of the depth:
        cell_W = W / 3
        cell_H = H / 3

    For cell at grid address (col, row) where col, row ∈ {0, 1, 2}:
        cell_min_x = min_x + col  × cell_W
        cell_min_y = min_y + row  × cell_H
        cell_max_x = min_x + (col + 1) × cell_W
        cell_max_y = min_y + (row + 1) × cell_H

    Numerical example — 9m × 12m envelope:
        cell_W = 3.0 m,  cell_H = 4.0 m  →  cell area = 12.0 m² each

        SE zone  (col=2, row=0):  box(6.0, 0.0,  9.0, 4.0)
        SW zone  (col=0, row=0):  box(0.0, 0.0,  3.0, 4.0)
        NE zone  (col=2, row=2):  box(6.0, 8.0,  9.0, 12.0)
        Centre   (col=1, row=1):  box(3.0, 4.0,  6.0, 8.0)  ← Brahmasthana

    Non-rectangular envelopes (future-proofing):
        Each raw rectangular cell is intersected with the envelope_polygon,
        ensuring no cell extends beyond the legal build boundary.  For the
        standard rectangular envelopes produced by constraint.py this
        intersection is a no-op and adds negligible overhead.

    Args:
        envelope_polygon: Legal build envelope Shapely Polygon.
                          Typically ``BuildZone.envelope_polygon`` from
                          constraint.calculate_build_envelope().
                          Must be a valid, non-empty polygon.

    Returns:
        MandalaGrid: dict mapping each of the 8 VastuZoneEnum values to its
                     clipped Shapely Polygon cell.
                     The Brahmasthana (centre) cell is NOT included.

    Raises:
        ValueError: If ``envelope_polygon`` is empty or has non-positive area.
    """
    if envelope_polygon is None or envelope_polygon.is_empty:
        raise ValueError(
            "build_zone_polygon is empty. "
            "Call constraint.calculate_build_envelope() before get_mandala_grid()."
        )
    if envelope_polygon.area <= 0:
        raise ValueError(
            f"build_zone_polygon has area={envelope_polygon.area:.4f} m² ≤ 0. "
            "Polygon is degenerate — check setback calculation."
        )

    min_x, min_y, max_x, max_y = envelope_polygon.bounds
    total_w = max_x - min_x   # East-West span of the envelope (metres)
    total_h = max_y - min_y   # North-South span of the envelope (metres)

    # Cell dimensions (one-third each axis)
    cell_w = total_w / 3.0
    cell_h = total_h / 3.0

    grid: MandalaGrid = {}

    for zone_enum, (col, row) in _ZONE_GRID_POSITION.items():
        # ── Compute raw cell rectangle ────────────────────────────────────
        cell_min_x = min_x + col * cell_w
        cell_min_y = min_y + row * cell_h
        cell_max_x = cell_min_x + cell_w
        cell_max_y = cell_min_y + cell_h

        raw_cell: Polygon = box(cell_min_x, cell_min_y, cell_max_x, cell_max_y)

        # ── Clip to actual envelope (handles non-rectangular boundaries) ──
        clipped_cell: Polygon = envelope_polygon.intersection(raw_cell)

        grid[zone_enum] = clipped_cell

    return grid


# ── Public API ────────────────────────────────────────────────────────────────

def get_room_anchors(
    plot_facing:        str,
    build_zone_polygon: Polygon,
    session:            Session,
    priority:           int = 1,
) -> RoomAnchorMap:
    """
    Main entry point — resolve Priority-1 Vastu zone anchors for every room.

    Pipeline:
    ─────────
    1. Guard: validate plot_facing and polygon.
    2. DB query: fetch VastuGridLogic rows for (plot_facing, priority) via
       SQLAlchemy, returning all room-zone assignments at the requested
       priority level.
    3. Mandala overlay: call get_mandala_grid() to divide build_zone_polygon
       into 8 compass-zone cells.
    4. Anchor mapping: for each queried room, look up its assigned zone in
       the mandala grid, run NBC viability checks, and populate the result.
    5. Return: RoomAnchorMap — a plain dict keyed by room_type.

    Coordinate system:
    ──────────────────
    All bounding_box Polygons use the same coordinate origin as the input
    envelope_polygon (SW corner = (min_x, min_y) of the envelope bounds).
    Downstream geometry modules can use these as absolute spatial seeds.

    Example — 9m × 12m North-facing envelope, priority=1:
    ───────────────────────────────────────────────────────
      Input:  plot_facing="North",
              build_zone_polygon=box(1.0, 1.0, 10.0, 13.0)  [9×12m envelope]

      Mandala cell dimensions: 3.0m × 4.0m = 12.0m² each

      DB query returns 11 Priority-1 room rules for "North" facing.
      Zone → cell mapping:

        Kitchen        → SE (col=2, row=0) → box(7.0,  1.0, 10.0,  5.0)
        MasterBedroom  → SW (col=0, row=0) → box(1.0,  1.0,  4.0,  5.0)
        Bedroom2       → W  (col=0, row=1) → box(1.0,  5.0,  4.0,  9.0)
        Bedroom3       → S  (col=1, row=0) → box(4.0,  1.0,  7.0,  5.0)
        Pooja          → NE (col=2, row=2) → box(7.0,  9.0, 10.0, 13.0)
        Toilet         → NW (col=0, row=2) → box(1.0,  9.0,  4.0, 13.0)
        Hall           → E  (col=2, row=1) → box(7.0,  5.0, 10.0,  9.0)
        Dining         → W  (col=0, row=1) → box(1.0,  5.0,  4.0,  9.0)  ← shares W with Bedroom2
        Staircase      → SW (col=0, row=0) → box(1.0,  1.0,  4.0,  5.0)  ← shares SW with MasterBedroom
        StoreRoom      → W  (col=0, row=1) → box(1.0,  5.0,  4.0,  9.0)  ← shares W with Bedroom2
        Entrance       → NE (col=2, row=2) → box(7.0,  9.0, 10.0, 13.0)  ← shares NE with Pooja

      Note: Sharing the same bounding_box is INTENTIONAL.  The allocator
      (geometry.py) is responsible for subdividing cells when multiple rooms
      target the same zone.  The Vastu Router only establishes *which* zone
      each room belongs to — zone conflict resolution is a separate concern.

    Args:
        plot_facing:        Compass direction of the main road-facing edge.
                            Must be 'North', 'South', 'East', or 'West'.
                            Use ``DistrictClimateMatrix.authority`` and the
                            user's plot survey to determine this.
        build_zone_polygon: Shapely Polygon of the legal build envelope.
                            Use ``BuildZone.envelope_polygon`` from
                            constraint.calculate_build_envelope().
        session:            Active SQLAlchemy Session (injected by FastAPI
                            dependency or passed directly in tests/CLI).
        priority:           Vastu priority level to fetch (default: 1).
                            1 = hard mandatory rules.
                            2 = preferred fallback (pass after a P1 conflict).
                            3 = last-resort fallback.

    Returns:
        RoomAnchorMap: dict of the form
          {
            "Kitchen":       {"zone": "SE", "bounding_box": <Polygon>},
            "MasterBedroom": {"zone": "SW", "bounding_box": <Polygon>},
            "Pooja":         {"zone": "NE", "bounding_box": <Polygon>},
            ...
          }
        Only rooms with valid (non-empty) zone cells are included.
        Non-mandatory rooms whose zone cell fails the NBC area check are
        silently omitted with a warning (never raise for non-mandatory rooms).

    Raises:
        ValueError:                    Invalid plot_facing or degenerate polygon.
        VastuRoutingError:             No rules found for the given facing/priority.
        UnresolvableRoomPlacementError: Mandatory room assigned to a zone not in
                                        the mandala grid (data integrity error).
        VastuZoneUnavailableError:     Mandatory room's zone cell is below its
                                        NBC 2016 minimum area threshold.
    """
    # ── Pre-flight guards ─────────────────────────────────────────────────────
    if plot_facing not in _VALID_FACINGS:
        raise ValueError(
            f"Invalid plot_facing '{plot_facing}'. "
            f"Must be one of: {sorted(_VALID_FACINGS)}."
        )

    if build_zone_polygon is None or build_zone_polygon.is_empty:
        raise ValueError(
            "build_zone_polygon must be a valid, non-empty Shapely Polygon. "
            "Obtain it via constraint.calculate_build_envelope() first."
        )

    # ── Step 1: Build the 3×3 Vastu Purusha Mandala grid ─────────────────────
    grid: MandalaGrid = get_mandala_grid(build_zone_polygon)

    # ── Step 2: Query VastuGridLogic for the requested (facing, priority) ─────
    #
    # SQL equivalent:
    #   SELECT * FROM vastu_grid_logic
    #    WHERE plot_facing = :plot_facing
    #      AND priority    = :priority
    #    ORDER BY room_type
    #
    rules: list[VastuGridLogic] = (
        session.query(VastuGridLogic)
        .filter(
            VastuGridLogic.plot_facing == plot_facing,
            VastuGridLogic.priority   == priority,
        )
        .order_by(VastuGridLogic.room_type)
        .all()
    )

    if not rules:
        raise VastuRoutingError(
            f"No VastuGridLogic rules found for plot_facing='{plot_facing}', "
            f"priority={priority}. Ensure the database has been seeded with "
            f"seed_rules_vastu.seed_all() before calling get_room_anchors().",
            plot_facing=plot_facing,
            priority=priority,
        )

    # ── Step 3: Map each room to its zone cell and validate ───────────────────
    anchors: RoomAnchorMap = {}

    for rule in rules:
        zone_enum: VastuZoneEnum = rule.vastu_zone
        zone_abbr: str = _ZONE_ABBREVIATION.get(zone_enum, zone_enum.value)
        cell_poly: Optional[Polygon] = grid.get(zone_enum)

        # ── Check: zone must exist in the mandala ─────────────────────────
        if cell_poly is None or cell_poly.is_empty:
            if rule.is_mandatory:
                raise UnresolvableRoomPlacementError(
                    f"Mandatory room '{rule.room_type}' is assigned to Vastu zone "
                    f"'{zone_enum.value}' which has no corresponding cell in the "
                    f"3×3 mandala grid.  This is a data-integrity error — verify "
                    f"VastuGridLogic seed data for "
                    f"room='{rule.room_type}', facing='{plot_facing}'.",
                    room_type=rule.room_type,
                    plot_facing=plot_facing,
                    tried_zones=[zone_abbr],
                )
            # Non-mandatory rooms with unmapped zones are skipped gracefully
            continue

        # ── Check: NBC 2016 minimum area viability ────────────────────────
        min_area: float = _NBC_MIN_ROOM_AREA_SQM.get(
            rule.room_type, _DEFAULT_MIN_ROOM_AREA_SQM
        )

        if cell_poly.area < min_area:
            if rule.is_mandatory:
                raise VastuZoneUnavailableError(
                    f"Mandatory room '{rule.room_type}' requires ≥{min_area:.1f}m² "
                    f"in the '{zone_enum.value}' Vastu zone, but the 3×3 grid cell "
                    f"has only {cell_poly.area:.2f}m².  "
                    f"The build envelope ({build_zone_polygon.area:.1f}m² total) "
                    f"is too small to accommodate this room at its Vastu-prescribed "
                    f"location.  Consider a larger plot or a lower floor level.",
                    room_type=rule.room_type,
                    zone=zone_abbr,
                    cell_area=round(cell_poly.area, 2),
                    required_min=min_area,
                )
            # Non-mandatory rooms below threshold are silently omitted
            continue

        # ── Record the anchor ─────────────────────────────────────────────
        anchors[rule.room_type] = {
            "zone":         zone_abbr,
            "bounding_box": cell_poly,
        }

    return anchors


# ── Utility Helpers ───────────────────────────────────────────────────────────

def get_all_priority_anchors(
    plot_facing:        str,
    build_zone_polygon: Polygon,
    session:            Session,
) -> dict[int, RoomAnchorMap]:
    """
    Fetch Vastu anchors for all three priority levels in one call.

    Useful for the allocator when it needs to resolve zone conflicts:
    a room blocked at P1 can fall back to its P2 or P3 zone assignment.

    Returns:
        { 1: RoomAnchorMap, 2: RoomAnchorMap, 3: RoomAnchorMap }

        Keys 2 and 3 are empty dicts ({}) if no rules exist at that priority
        (e.g., Entrance only has P1 and P2 rules in the default seed).

    Raises:
        VastuRoutingError: If even priority=1 rules are missing (DB not seeded).
    """
    result: dict[int, RoomAnchorMap] = {}

    for p in (1, 2, 3):
        try:
            result[p] = get_room_anchors(plot_facing, build_zone_polygon, session, priority=p)
        except VastuRoutingError as exc:
            if p == 1:
                raise   # P1 absence is always fatal
            result[p] = {}  # P2/P3 absence is non-fatal (not all rooms have 3 priorities)

    return result


def describe_anchors(
    anchors: RoomAnchorMap,
    indent: int = 2,
) -> str:
    """
    Return a human-readable text report of a RoomAnchorMap.

    Useful for debugging, logging, and CLI output.

    Example output::

        Vastu Anchor Map (11 rooms)
          Kitchen        → SE  bbox=(7.00, 1.00, 10.00, 5.00)  area=12.00 m²
          MasterBedroom  → SW  bbox=(1.00, 1.00,  4.00, 5.00)  area=12.00 m²
          Pooja          → NE  bbox=(7.00, 9.00, 10.00, 13.00) area=12.00 m²
          ...

    Args:
        anchors: RoomAnchorMap returned by get_room_anchors().
        indent:  Number of spaces to use for indentation.

    Returns:
        Formatted multi-line string.
    """
    pad = " " * indent
    lines: List[str] = [f"Vastu Anchor Map ({len(anchors)} rooms)"]

    for room, data in sorted(anchors.items()):
        zone  = data["zone"]
        poly: Polygon = data["bounding_box"]
        minx, miny, maxx, maxy = poly.bounds
        lines.append(
            f"{pad}{room:<16} → {zone:<4} "
            f"bbox=({minx:.2f}, {miny:.2f}, {maxx:.2f}, {maxy:.2f})  "
            f"area={poly.area:.2f} m²"
        )

    return "\n".join(lines)
