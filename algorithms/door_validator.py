"""
door_validator.py — Door swing arc validation and placement selection
=====================================================================
Ensures every placed door satisfies:

  1. Swing depth — room has enough depth in swing direction for the door
     to open fully PLUS a minimum 0.9 m clear path beyond the open leaf
     (NBC 2016 Part 3 §8.5.1 — clear passage width after door swing).

  2. No wall in arc — the 90° quarter-circle swing zone does not intersect
     any wall segment (prevents doors swinging into T-junction walls or
     room partitions, i.e. "opens into a wall").

  3. Hinge selection — hinge is placed on the side that keeps the open
     door leaf OUT of the main circulation path.

  4. Fallback — if the primary wall has a blocked swing zone, alternate
     hinge positions and candidate positions along the same wall are tried.
     If all positions on the wall are blocked, the caller can try other walls.

Geometry conventions (matching renderer.py):
  Horizontal wall at y=wy  → door gap runs along x; swing is perpendicular (y)
  Vertical   wall at x=wx  → door gap runs along y; swing is perpendicular (x)
  "room_is_below" (horiz.) → room.cy < wy → door swings DOWN into room
  "room_is_right" (vert.)  → room.cx > wx → door swings RIGHT into room

Sources:
  NBC 2016 Part 3 §8.5.1 — corridor/passage minimum clear width 0.9 m
  IS 4021 : 1983 — door leaf dimensions; 750/800/900/1000/1200 mm widths
  Neufert Architects' Data 4e — door swing zone clearances
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Any

__all__ = [
    "DOOR_CLEAR_PATH",
    "DoorPlacement",
    "arc_bbox",
    "swing_depth_ok",
    "swing_blocked",
    "choose_door_placement",
    "door_side_candidates",
]

# ── Constants ────────────────────────────────────────────────────────────────
DOOR_CLEAR_PATH = 0.90      # minimum clear path BEYOND open door leaf (NBC §8.5.1)
_CLEAR_MIN      = 1.20      # minimum side clearance between door and room wall
_WALL_TOL       = 0.08      # tolerance for wall-line intersection tests


# ── Result dataclass ─────────────────────────────────────────────────────────

@dataclass
class DoorPlacement:
    """Result of choose_door_placement()."""
    pos:         float   # door position along wall segment from seg_origin
    hinge:       str     # "L"/"R" (horizontal wall) or "B"/"T" (vertical wall)
    depth_ok:    bool    # room depth ≥ dw + DOOR_CLEAR_PATH
    swing_clear: bool    # no wall segment inside arc bounding box
    clear_depth: float   # actual room depth in swing direction
    violations:  List[str] = field(default_factory=list)


# ── Geometry helpers ─────────────────────────────────────────────────────────

def arc_bbox(
    is_horizontal: bool,
    room_cy: float,
    room_cx: float,
    door_abs_start: float,
    door_wall_coord: float,
    dw: float,
) -> Tuple[float, float, float, float]:
    """
    Return the bounding box (x0, y0, x1, y1) of the 90° door swing arc.

    For a horizontal wall at y=door_wall_coord:
      The arc occupies x ∈ [door_abs_start, door_abs_start+dw] ×
                       y in the room-direction (above or below the wall).

    For a vertical wall at x=door_wall_coord:
      The arc occupies y ∈ [door_abs_start, door_abs_start+dw] ×
                       x in the room-direction (left or right of wall).
    """
    if is_horizontal:
        x0 = door_abs_start
        x1 = door_abs_start + dw
        wy = door_wall_coord
        if room_cy < wy:          # room is below wall → arc sweeps DOWN
            return (x0, wy - dw, x1, wy)
        else:                     # room is above wall → arc sweeps UP
            return (x0, wy,       x1, wy + dw)
    else:
        y0 = door_abs_start
        y1 = door_abs_start + dw
        wx = door_wall_coord
        if room_cx > wx:          # room is to the right → arc sweeps RIGHT
            return (wx,      y0, wx + dw, y1)
        else:                     # room is to the left  → arc sweeps LEFT
            return (wx - dw, y0, wx,      y1)


def swing_depth_ok(
    is_horizontal: bool,
    room_w: float,
    room_h: float,
    dw: float,
) -> Tuple[bool, float]:
    """
    Check that the room has enough depth in the swing direction for the
    door to open 90° AND leave ≥ DOOR_CLEAR_PATH beyond the open leaf.

    Returns (depth_ok, available_depth).
    """
    depth = room_h if is_horizontal else room_w
    needed = dw + DOOR_CLEAR_PATH
    return depth >= needed, depth


def swing_blocked(
    bbox: Tuple[float, float, float, float],
    all_segs: List[Any],   # WallSegment objects (duck-typed to avoid circular import)
    exclude_seg: Any,
    tol: float = _WALL_TOL,
) -> bool:
    """
    Return True if any wall segment (other than the door's own segment)
    intersects the swing arc bounding box — meaning the door would swing
    into a wall.

    bbox : (x0, y0, x1, y1) — the arc's bounding box
    """
    ax0, ay0, ax1, ay1 = bbox

    for s in all_segs:
        if s is exclude_seg:
            continue

        if s.is_horizontal:
            sy = s.y1
            # Wall's y must be INSIDE arc's y band (not touching boundary)
            if ay0 + tol < sy < ay1 - tol:
                x_ovlp = min(s.x2, ax1) - max(s.x1, ax0)
                if x_ovlp > tol:
                    return True
        else:
            sx = s.x1
            # Wall's x must be INSIDE arc's x band
            if ax0 + tol < sx < ax1 - tol:
                y_ovlp = min(s.y2, ay1) - max(s.y1, ay0)
                if y_ovlp > tol:
                    return True

    return False


# ── Hinge selector ────────────────────────────────────────────────────────────

def _preferred_hinge(
    is_horizontal: bool,
    abs_door_start: float,
    abs_door_end: float,
    room_start: float,
    room_end: float,
) -> Tuple[str, str]:
    """
    Return (preferred_hinge, alternate_hinge) based on which side of the
    door has more clearance to the room wall.

    Convention: hinge goes on the side with LESS clearance so that the
    open door leaf swings toward the MORE open side — keeping the
    circulation path clear.
    """
    cl_near = abs_door_start - room_start   # clearance on left / bottom
    cl_far  = room_end  - abs_door_end      # clearance on right / top

    if is_horizontal:
        a = "L" if cl_near <= cl_far else "R"
        b = "R" if a == "L" else "L"
    else:
        a = "B" if cl_near <= cl_far else "T"
        b = "T" if a == "B" else "B"
    return a, b


# ── Main placement chooser ────────────────────────────────────────────────────

def choose_door_placement(
    seg: Any,              # WallSegment
    room: Any,             # Room
    room_start: float,     # absolute start of room span on this wall
    room_end: float,       # absolute end of room span on this wall
    dw: float,             # door width (metres)
    all_segs: List[Any],   # all WallSegments in the floor plan
) -> DoorPlacement:
    """
    Choose the best door position (pos_along) and hinge for *seg*,
    validating the swing arc against wall interference and clear-path rules.

    Strategy (in priority order):
      1. Centred position, preferred hinge
      2. Centred position, alternate hinge
      3. Shifted positions (3 offsets), each hinge
      4. Reduced-clearance fallback (relax side-clearance if room is tight)
      5. Absolute fallback: centred, any hinge — no constraint enforcement

    Returns a DoorPlacement with validity flags; callers can check
    DoorPlacement.swing_clear / DoorPlacement.depth_ok.
    """
    is_h = seg.is_horizontal
    seg_origin = seg.x1 if is_h else seg.y1
    room_span  = room_end - room_start

    # ── Side clearance (1.2 m each side; relaxed if room is too tight)
    avail  = (room_span - dw) / 2.0
    clear  = min(_CLEAR_MIN, max(0.05, avail * 0.70)) if avail < _CLEAR_MIN else _CLEAR_MIN

    pos_center = (room_start - seg_origin) + (room_span - dw) / 2.0
    pos_min    = (room_start - seg_origin) + clear
    pos_max    = (room_end   - seg_origin) - dw - clear

    if pos_min > pos_max:
        pos_min = pos_max = pos_center   # room too tight, just centre

    pos_center = max(pos_min, min(pos_max, pos_center))

    # ── Swing depth check (same for all positions on this wall)
    depth_ok, clear_depth = swing_depth_ok(is_h, room.width, room.height, dw)
    violations = [] if depth_ok else [
        f"room depth {clear_depth:.2f}m < {dw + DOOR_CLEAR_PATH:.2f}m "
        f"(door {dw:.2f}m + {DOOR_CLEAR_PATH:.0f}m clear path)"
    ]

    # ── Candidate positions (centre + 2 offsets)
    pos_range = pos_max - pos_min
    candidates: List[float] = [pos_center]
    if pos_range > 0.30:
        candidates += [
            max(pos_min, pos_center - pos_range * 0.30),
            min(pos_max, pos_center + pos_range * 0.30),
        ]

    wall_coord = seg.y1 if is_h else seg.x1

    # ── Score and try all (position × hinge) combinations
    best: Optional[DoorPlacement] = None
    best_score = -999

    for p in candidates:
        p = max(0.02, round(p, 4))
        abs_start = seg_origin + p
        abs_end   = abs_start + dw

        hinge_a, hinge_b = _preferred_hinge(
            is_h, abs_start, abs_end, room_start, room_end
        )

        for hinge in (hinge_a, hinge_b):
            bbox    = arc_bbox(is_h, room.cy, room.cx,
                               abs_start, wall_coord, dw)
            blocked = swing_blocked(bbox, all_segs, seg)

            score = 0
            if depth_ok:     score += 8
            if not blocked:  score += 4
            if hinge == hinge_a: score += 1          # prefer natural hinge
            score -= abs(p - pos_center) * 3          # prefer centred position

            dp = DoorPlacement(
                pos=p,
                hinge=hinge,
                depth_ok=depth_ok,
                swing_clear=not blocked,
                clear_depth=clear_depth,
                violations=list(violations)
                    + (["swing arc blocked by wall"] if blocked else []),
            )

            if score > best_score:
                best_score = score
                best = dp

    # Always return something — the "best available" even if imperfect
    assert best is not None
    return best


# ── Fallback wall ordering ────────────────────────────────────────────────────

_DOOR_TARGETS: dict = {
    "bathroom":  ["bedroom", "corridor", "living", "dining"],
    "toilet":    ["bedroom", "corridor", "living"],
    "bedroom":   ["corridor", "living", "dining"],
    "corridor":  ["living", "dining", "bedroom"],
    "utility":   ["corridor", "kitchen", "dining"],
    "pooja":     ["living", "corridor", "dining"],
    "study":     ["corridor", "living", "bedroom"],
    "store":     ["corridor", "utility", "kitchen"],
    "kitchen":   ["dining", "corridor", "living"],
    "dining":    ["kitchen", "living", "corridor"],
    "living":    ["corridor", "dining", "bedroom"],
}

_SIDE_ORDER = ["N", "S", "E", "W"]   # default fallback order


def door_side_candidates(
    room: Any,
    all_rooms: List[Any],
    primary_side: str,
) -> List[str]:
    """
    Return an ordered list of wall sides to try for the door, starting
    with primary_side and then falling back to other viable walls.

    Sides that are shared with higher-priority adjacent room types come
    first in the fallback list.
    """
    targets = _DOOR_TARGETS.get(room.room_type, ["corridor", "living"])
    tol = 0.25

    # Map each cardinal side to its best adjacent room priority
    side_prio: dict = {}
    for other in all_rooms:
        if other is room:
            continue
        # North: other is above (other.y ≈ room.y2)
        if abs(other.y - room.y2) < tol:
            x_ov = min(other.x2, room.x2) - max(other.x, room.x)
            if x_ov > 0.3:
                try:    p = targets.index(other.room_type)
                except: p = 50
                side_prio["N"] = min(side_prio.get("N", 99), p)
        # South: other is below (other.y2 ≈ room.y)
        if abs(other.y2 - room.y) < tol:
            x_ov = min(other.x2, room.x2) - max(other.x, room.x)
            if x_ov > 0.3:
                try:    p = targets.index(other.room_type)
                except: p = 50
                side_prio["S"] = min(side_prio.get("S", 99), p)
        # East: other is to the right (other.x ≈ room.x2)
        if abs(other.x - room.x2) < tol:
            y_ov = min(other.y2, room.y2) - max(other.y, room.y)
            if y_ov > 0.3:
                try:    p = targets.index(other.room_type)
                except: p = 50
                side_prio["E"] = min(side_prio.get("E", 99), p)
        # West: other is to the left (other.x2 ≈ room.x)
        if abs(other.x2 - room.x) < tol:
            y_ov = min(other.y2, room.y2) - max(other.y, room.y)
            if y_ov > 0.3:
                try:    p = targets.index(other.room_type)
                except: p = 50
                side_prio["W"] = min(side_prio.get("W", 99), p)

    # Order: primary_side first, then by priority, then any remaining
    others = sorted(
        [s for s in _SIDE_ORDER if s != primary_side],
        key=lambda s: side_prio.get(s, 99),
    )
    return [primary_side] + others
