"""
TN-Flow Core Spatial Allocator — allocator.py
==============================================
Converts the abstract Vastu zone anchors produced by vastu_router.py into
concrete, non-overlapping rectangular room polygons that collectively tile
the build envelope.

Two responsibilities:
  1. BHK Filtering  — Remove rooms not required for the requested flat type.
  2. Conflict Resolution — When multiple rooms share a Vastu zone cell,
     subdivide that cell proportionally using NBC 2016 minimum areas as
     weights, ensuring each room's slice respects the relative space
     entitlement of each room type.

Design philosophy:
  - The allocator operates purely on Shapely Polygon geometry; it has NO
    knowledge of wall thicknesses.  That concern belongs to geometry.py.
  - Rooms are sorted by NBC weight (descending) before splitting so the most
    important room always gets the largest, most "Vastu-pure" slice of the cell.
  - Splits always run along the LONGER dimension of the current cell to
    maximise room squareness and minimise excessively narrow plans.

Primary public API:
  resolve_spatial_conflicts(bhk_type, room_anchors, build_envelope)
                            -> AllocatedRoomMap

Downstream consumer:
  geometry.py  →  apply_wall_thickness(AllocatedRoomMap, build_envelope)
                  → FloorPlanMap

Coordinate system (consistent throughout the engine):
  Origin (0,0) = South-West corner of the build envelope.
  +X = East,  +Y = North.
"""

from __future__ import annotations

from collections import defaultdict
from enum import Enum
from typing import Dict, FrozenSet, List, Set

from shapely.geometry import box, Polygon

from backend.engine.exceptions import AllocationError


# ── Type aliases ──────────────────────────────────────────────────────────────

# Output of vastu_router.get_room_anchors():
#   { room_type: {"zone": "SE", "bounding_box": Polygon} }
RoomAnchorMap = Dict[str, Dict]

# Output of resolve_spatial_conflicts():
#   { room_type: Polygon }   ← no-overlap, within build_envelope
AllocatedRoomMap = Dict[str, Polygon]


# ── BHK Type Definitions ──────────────────────────────────────────────────────

class BHKType(str, Enum):
    """
    Supported flat type configurations.

    The engine supports four configurations matching common South Indian
    residential plan briefs:

    ONE_BHK (1BHK):
        Single bedroom unit.  No secondary bedrooms, no staircase, no store.
        Minimum viable residential unit per NBC 2016 Cl. 4.2.
        Typical plot: 3×9m EWS to 5×10m standard.

    TWO_BHK (2BHK):
        Two-bedroom unit.  Adds a second bedroom (West zone).
        Most common urban flat type in Tamil Nadu.
        Typical plot: 6×12m to 9×15m.

    THREE_BHK (3BHK):
        Three-bedroom unit.  Adds a third bedroom (South zone).
        Typical plot: 9×15m to 12×18m.

    VILLA (3BHK_VILLA):
        Three-bedroom duplex/independent house with staircase and utility store.
        Requires G+1 floor level (staircase) and a larger plot (≥ 12×22m for
        CMDA to pass NBC area checks after wall deduction).
        Typical plot: 12×20m to 15×25m.
    """
    ONE_BHK = "1BHK"
    TWO_BHK = "2BHK"
    THREE_BHK = "3BHK"
    VILLA = "3BHK_VILLA"


# Canonical room sets per BHK type.
# Rooms NOT in a set are removed from room_anchors before conflict resolution.
# Order within the frozenset is irrelevant — subdivision order is by NBC weight.
BHK_ROOM_SETS: dict[BHKType, FrozenSet[str]] = {
    BHKType.ONE_BHK: frozenset({
        "MasterBedroom", "Kitchen", "Hall", "Toilet", "Entrance",
        "Dining", "Pooja",
    }),
    BHKType.TWO_BHK: frozenset({
        "MasterBedroom", "Bedroom2", "Kitchen", "Hall", "Toilet",
        "Entrance", "Dining", "Pooja",
    }),
    BHKType.THREE_BHK: frozenset({
        "MasterBedroom", "Bedroom2", "Bedroom3", "Kitchen", "Hall",
        "Toilet", "Entrance", "Dining", "Pooja",
    }),
    BHKType.VILLA: frozenset({
        "MasterBedroom", "Bedroom2", "Bedroom3", "Kitchen", "Hall",
        "Toilet", "Entrance", "Dining", "Pooja", "Staircase", "StoreRoom",
    }),
}


# ── NBC 2016 Minimum Area Weights ─────────────────────────────────────────────
#
# These values drive the PROPORTIONAL SUBDIVISION of shared Vastu cells.
# A room with a higher NBC weight receives a proportionally larger slice.
#
# Important: these are GROSS ALLOCATION weights (base polygon area), NOT
# final carpet area targets.  The geometry engine applies wall deductions
# afterwards.  The gross weights are set slightly above the NBC carpet-area
# minimums to leave headroom for wall thickness deductions.
#
# References:
#   NBC 2016 Cl.4.2.1 — habitable rooms: 9.5m² (master), 7.5m² (others)
#   NBC 2016 Cl.4.2.2 — living/lounge: 9.5m²
#   NBC 2016 Cl.4.2.3 — dining: 6.0m²
#   NBC 2016 Cl.4.2.4 — kitchen: 5.0m² (problem brief minimum)
#   NBC 2016 Cl.4.2.6 — bathroom: 1.5m² (practical; NBC gives 1.2m²)
#
NBC_WEIGHTS: dict[str, float] = {
    "MasterBedroom": 9.5,
    "Bedroom2":      7.5,
    "Bedroom3":      7.5,
    "Kitchen":       5.0,
    "Hall":          9.5,
    "Toilet":        1.5,
    "Pooja":         2.0,
    "Dining":        6.0,
    "Staircase":     4.5,
    "StoreRoom":     1.5,
    "Entrance":      1.5,
}

# Applied when a room_type is absent from the NBC_WEIGHTS table.
_DEFAULT_NBC_WEIGHT: float = 2.0

# Minimum cell area (sq.m) below which we refuse to allocate a shared cell.
# A cell smaller than the smallest meaningful single room cannot host two rooms.
_MIN_VIABLE_CELL_AREA: float = 3.0


# ── Private Helpers ───────────────────────────────────────────────────────────

def _nbc_weight(room: str) -> float:
    """Return the NBC area weight for a room, defaulting to 2.0."""
    return NBC_WEIGHTS.get(room, _DEFAULT_NBC_WEIGHT)


def _proportional_bisect(
    cell_polygon: Polygon,
    rooms:        List[str],
    depth:        int = 0,
) -> AllocatedRoomMap:
    """
    Recursively subdivide ``cell_polygon`` among ``rooms`` in proportion to
    their NBC area weights.

    Subdivision algorithm — Equal-Fraction Recursive Bisection:
    ────────────────────────────────────────────────────────────
    At each recursion level:

    1. Sort ``rooms`` by NBC weight DESCENDING so the most important room
       always receives the first (bottom or left) slice.

    2. Compute the weight fraction for the first room:
           fraction = weight(first_room) / Σ weight(all rooms)

    3. Determine the SPLIT AXIS — always the LONGER dimension:
           if cell_height ≥ cell_width  → HORIZONTAL split (split along Y)
           if cell_width  > cell_height → VERTICAL   split (split along X)

       Splitting along the longer dimension maximises the shorter dimension
       of each sub-polygon, producing more square room shapes.

    4. Apply the split:
       HORIZONTAL (Y-split):
           split_y     = min_y + cell_height × fraction
           first_poly  = box(min_x, min_y,    max_x, split_y)
           rest_poly   = box(min_x, split_y,  max_x, max_y)

       VERTICAL (X-split):
           split_x     = min_x + cell_width × fraction
           first_poly  = box(min_x, min_y,    split_x, max_y)
           rest_poly   = box(split_x, min_y,  max_x,   max_y)

    5. Recurse on (rest_poly, remaining_rooms) until one room remains.

    Numerical example — SW cell (3.0m × 5.17m), rooms=[MasterBedroom, Staircase]:
        Total weight = 9.5 + 4.5 = 14.0
        MasterBedroom fraction = 9.5 / 14.0 = 0.6786
        Cell H=5.17 ≥ W=3.0 → HORIZONTAL split
        split_y   = 1.5 + 5.17 × 0.6786 = 5.01m
        MasterBedroom → box(1.5, 1.5, 4.5, 5.01) = 3.00m × 3.51m = 10.53m²
        Staircase     → box(1.5, 5.01, 4.5, 6.67) = 3.00m × 1.66m = 4.98m²

    Args:
        cell_polygon: The Vastu zone cell polygon to subdivide.
        rooms:        List of room names to fit within the cell.
        depth:        Recursion depth counter (for debugging; not used in logic).

    Returns:
        AllocatedRoomMap: { room_name: Polygon } — no overlaps, collectively
        fills cell_polygon.
    """
    if not rooms:
        return {}

    if len(rooms) == 1:
        return {rooms[0]: cell_polygon}

    # Sort rooms by NBC weight descending (largest allocation first)
    sorted_rooms = sorted(rooms, key=_nbc_weight, reverse=True)
    total_weight = sum(_nbc_weight(r) for r in sorted_rooms)

    first_room     = sorted_rooms[0]
    first_fraction = _nbc_weight(first_room) / total_weight

    min_x, min_y, max_x, max_y = cell_polygon.bounds
    cell_w = max_x - min_x
    cell_h = max_y - min_y

    # ── Determine split axis and compute sub-polygons ─────────────────────
    if cell_h >= cell_w:
        # HORIZONTAL split along Y axis
        # Each room gets FULL cell width → preserves the widest possible rooms.
        # First (heaviest) room gets the BOTTOM strip (closer to the South wall,
        # which is the "grounding" side in Vastu for heavy rooms like bedrooms).
        split_y    = min_y + cell_h * first_fraction
        first_poly = box(min_x, min_y,    max_x, split_y)
        rest_poly  = box(min_x, split_y,  max_x, max_y)
    else:
        # VERTICAL split along X axis
        # Each room gets FULL cell height → preserves the tallest possible rooms.
        # First (heaviest) room gets the LEFT strip (closer to the West wall).
        split_x    = min_x + cell_w * first_fraction
        first_poly = box(min_x, min_y, split_x,  max_y)
        rest_poly  = box(split_x, min_y, max_x,  max_y)

    # ── Recurse for remaining rooms ───────────────────────────────────────
    result = {first_room: first_poly}
    result.update(_proportional_bisect(rest_poly, sorted_rooms[1:], depth + 1))
    return result


def _group_by_bounding_box(
    room_anchors:   RoomAnchorMap,
    required_rooms: Set[str],
) -> dict[tuple, list[str]]:
    """
    Group the required subset of room_anchors by their shared bounding-box
    coordinates (i.e., which rooms share the same Vastu zone cell).

    Returns:
        { (min_x, min_y, max_x, max_y): [room_name, ...] }

    Rooms sharing the same (min_x, min_y, max_x, max_y) tuple are in the
    same Vastu zone cell and need subdivision.
    """
    groups: dict[tuple, list[str]] = defaultdict(list)

    for room, data in room_anchors.items():
        if room not in required_rooms:
            continue
        bbox_key = tuple(round(c, 6) for c in data["bounding_box"].bounds)
        groups[bbox_key].append(room)

    return dict(groups)


# ── Public API ────────────────────────────────────────────────────────────────

def resolve_spatial_conflicts(
    bhk_type:       str,
    room_anchors:   RoomAnchorMap,
    build_envelope: Polygon,
) -> AllocatedRoomMap:
    """
    Main entry point — resolve zone conflicts and produce non-overlapping rooms.

    Pipeline:
    ─────────
    1. Parse & validate ``bhk_type`` → resolve required room set.
    2. Filter ``room_anchors`` to only include rooms in the required set.
    3. Group remaining rooms by their Vastu zone cell (shared bounding box).
    4. For each zone group:
       a. Single room in zone  → room gets the entire cell polygon.
       b. Multiple rooms       → call _proportional_bisect() to subdivide the
          cell proportionally by NBC weights, with the highest-weight room
          receiving the bottom/left slice (Vastu-primary position).
    5. Validate: each result polygon lies within build_envelope.
    6. Return: AllocatedRoomMap — { room_name: Polygon }.

    Zone conflict example (North-facing, 3BHK_VILLA):
    ──────────────────────────────────────────────────
    Input room_anchors (P1) for North-facing:
        SW zone: { MasterBedroom(SW), Staircase(SW) }  ← both in SW cell
        W  zone: { Bedroom2(W), Dining(W), StoreRoom(W) } ← three in W cell
        NE zone: { Pooja(NE), Entrance(NE) }            ← two in NE cell

    After resolve_spatial_conflicts("3BHK_VILLA", anchors, envelope):
        MasterBedroom → box(1.5, 1.5,  4.5, 5.01)   [SW-bottom, 10.52m²]
        Staircase     → box(1.5, 5.01, 4.5, 6.67)   [SW-top,     4.98m²]
        Bedroom2      → box(1.5, 6.67, 4.5, 9.58)   [W-bottom,   8.75m²]
        Dining        → box(1.5, 9.58, 4.5, 11.91)  [W-middle,   7.00m²]
        StoreRoom     → box(1.5, 11.91,4.5, 12.50)  [W-top,      1.77m²]
        Pooja         → box(7.5, 12.50,10.5,17.00)  [NE-bottom,  7.75m²]
        Entrance      → box(7.5, ...  ,10.5,17.00)  [NE-top,  ...]
        ...

    Args:
        bhk_type:       String or BHKType enum value: '1BHK', '2BHK', '3BHK',
                        '3BHK_VILLA'. Case-sensitive.
        room_anchors:   RoomAnchorMap from vastu_router.get_room_anchors().
                        Each value must contain a 'bounding_box' Shapely Polygon.
        build_envelope: Shapely Polygon of the legal build zone.
                        Use BuildZone.envelope_polygon from constraint.py.

    Returns:
        AllocatedRoomMap: { room_name: Polygon }
        - No two polygons overlap.
        - Every polygon is within build_envelope.
        - Only rooms in the BHK required set are present.

    Raises:
        ValueError:       Unknown bhk_type string.
        AllocationError:  A shared cell is too small to house its assigned rooms
                          (sum of NBC weights exceeds cell area).
    """
    # ── Step 1: resolve required room set ─────────────────────────────────
    try:
        bhk_enum = BHKType(bhk_type)
    except ValueError:
        valid = [e.value for e in BHKType]
        raise ValueError(
            f"Unknown bhk_type '{bhk_type}'. "
            f"Valid values: {valid}."
        )
    required_rooms: Set[str] = set(BHK_ROOM_SETS[bhk_enum])

    if not room_anchors:
        raise ValueError("room_anchors is empty — run vastu_router.get_room_anchors() first.")

    # ── Step 2: group rooms by shared Vastu cell ───────────────────────────
    zone_groups = _group_by_bounding_box(room_anchors, required_rooms)

    if not zone_groups:
        raise ValueError(
            f"No rooms in room_anchors match the required set for '{bhk_type}'. "
            f"Required: {sorted(required_rooms)}. "
            f"Provided: {sorted(room_anchors.keys())}."
        )

    # ── Step 3: allocate each zone group ──────────────────────────────────
    allocated: AllocatedRoomMap = {}

    for bbox_key, rooms_in_zone in zone_groups.items():
        # Reconstruct the cell polygon from its bounding-box key
        cell_polygon = box(*bbox_key)
        zone_name    = room_anchors[rooms_in_zone[0]]["zone"]

        # ── Pre-allocation viability check ────────────────────────────────
        total_nbc_required = sum(_nbc_weight(r) for r in rooms_in_zone)

        if cell_polygon.area < _MIN_VIABLE_CELL_AREA:
            raise AllocationError(
                f"Vastu zone '{zone_name}' cell ({cell_polygon.area:.2f}m²) is below "
                f"the minimum viable allocation area of {_MIN_VIABLE_CELL_AREA}m². "
                f"Rooms needing this zone: {rooms_in_zone}.",
                zone=zone_name,
                rooms_in_zone=rooms_in_zone,
                cell_area_sqm=round(cell_polygon.area, 2),
                required_sqm=round(total_nbc_required, 2),
            )

        if len(rooms_in_zone) > 1 and cell_polygon.area < total_nbc_required * 0.6:
            # Cell area < 60% of the sum of NBC minimums — impossible to satisfy
            raise AllocationError(
                f"Vastu zone '{zone_name}' cell ({cell_polygon.area:.2f}m²) is too "
                f"small to allocate {len(rooms_in_zone)} rooms "
                f"({', '.join(sorted(rooms_in_zone))}).  "
                f"Sum of NBC weights = {total_nbc_required:.1f}m², "
                f"available = {cell_polygon.area:.2f}m².  "
                f"Use a larger plot or reduce the BHK type.",
                zone=zone_name,
                rooms_in_zone=sorted(rooms_in_zone),
                cell_area_sqm=round(cell_polygon.area, 2),
                required_sqm=round(total_nbc_required, 2),
            )

        # ── Single room: assign full cell ─────────────────────────────────
        if len(rooms_in_zone) == 1:
            allocated[rooms_in_zone[0]] = cell_polygon
            continue

        # ── Multiple rooms: proportional bisection ────────────────────────
        sub_allocations = _proportional_bisect(cell_polygon, rooms_in_zone)
        allocated.update(sub_allocations)

    # ── Step 4: verify all polygons are within the build envelope ─────────
    env_prep = build_envelope.buffer(1e-6)  # tiny tolerance for float edges
    for room, poly in allocated.items():
        if not env_prep.contains(poly):
            # This should never happen given that room_anchors came from
            # get_room_anchors() which uses the same envelope — defensive only
            raise AllocationError(
                f"Room '{room}' polygon {poly.bounds} lies outside the "
                f"build_envelope {build_envelope.bounds}.  "
                f"Ensure room_anchors and build_envelope share the same coordinate space.",
                zone=room_anchors.get(room, {}).get("zone", "?"),
                rooms_in_zone=[room],
                cell_area_sqm=round(poly.area, 2),
                required_sqm=0.0,
            )

    return allocated


def describe_allocations(allocated: AllocatedRoomMap, indent: int = 2) -> str:
    """
    Return a human-readable text report of an AllocatedRoomMap.

    Example output::

        Allocated Rooms (9 rooms, 120.50 m² total)
          MasterBedroom  (1.50, 1.50, 4.50, 5.01)  W=3.00  H=3.51  area=10.52 m²
          Staircase      (1.50, 5.01, 4.50, 6.67)  W=3.00  H=1.66  area= 4.98 m²
          ...

    Args:
        allocated: AllocatedRoomMap from resolve_spatial_conflicts().
        indent:    Left-padding spaces for each room line.
    """
    pad   = " " * indent
    total = sum(p.area for p in allocated.values())
    lines = [f"Allocated Rooms ({len(allocated)} rooms, {total:.2f} m² total)"]

    for room, poly in sorted(allocated.items(), key=lambda x: x[1].bounds[1]):
        min_x, min_y, max_x, max_y = poly.bounds
        lines.append(
            f"{pad}{room:<16} ({min_x:.2f}, {min_y:.2f}, {max_x:.2f}, {max_y:.2f})"
            f"  W={max_x - min_x:.2f}  H={max_y - min_y:.2f}  area={poly.area:.2f} m²"
        )

    return "\n".join(lines)
