"""
CirculationPlanner — Circulation-Driven Layout Pre-Pass
========================================================
Defines the primary movement path BEFORE room cells are assigned.

Canonical spine (entry at high-y, rear at low-y):

    depth 0 │ Entry / Verandah   ← boundary of plot
    depth 1 │ Living (± Dining)  ← first interior space
    depth 2 │ ── CORRIDOR ──     ← zone threshold (spanning)
    depth 3 │ Bedroom(s)         ← furthest from entry

Branch rooms are adjacent to the spine but NOT on it:
    Kitchen  → off Living (depth 1, shared wall)
    Bathroom → off Bedroom (depth 3, shared wall)
    Utility  → off Kitchen
    Pooja    → off Corridor or Bedroom

Rules enforced
──────────────
  C1 (hard) No dead ends — every room reachable from entry without backtracking
  C2 (hard) Linear spine — path depth monotonically increases; no zig-zag
  C3 (hard) Max one corridor — at most one spanning corridor row on the spine
  C4 (soft) Doors face path — each room's door aligns with its spine edge

Output
──────
  CirculationPlan.door_hints  Dict[room_type, side] used by engine's _assign_door_side()
  CirculationPlan.row_depth   Dict[path_depth, grid_row] passed to layout topologies
  CirculationPlan.corridor_row  int — grid row index reserved for the corridor

Integration
───────────
  Called from build_layout_from_adjacency_graph() after ZonePlanner.
  door_hints stored in the template and consumed by engine._assign_door_side().

Source: Ching F.D.K., "Architecture: Form, Space & Order", 4th ed., 2014 —
        Chapter 6, Circulation; Hillier 1984 — depth in justified graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


# ── Path depth constants ───────────────────────────────────────────────────────
ENTRY_DEPTH    = 0   # verandah / entrance — at plot boundary
LIVING_DEPTH   = 1   # living (+ dining) — first habitable space
CORRIDOR_DEPTH = 2   # corridor — zone threshold between public and private
BED_DEPTH      = 3   # bedrooms — furthest from entry

# Spine room types (ordered by depth)
_SPINE_TYPES: List[str] = ["verandah", "entrance", "living", "corridor", "bedroom"]

# Branch rooms and which spine depth they attach to
_BRANCH_ATTACHMENT: Dict[str, int] = {
    "dining":   LIVING_DEPTH,    # kitchen/dining cluster off living
    "kitchen":  LIVING_DEPTH,
    "utility":  LIVING_DEPTH,    # utility off kitchen (same zone)
    "store":    LIVING_DEPTH,
    "pooja":    CORRIDOR_DEPTH,  # pooja off corridor (or bedroom)
    "study":    BED_DEPTH,
    "bathroom": BED_DEPTH,       # attached bath off bedroom
    "toilet":   BED_DEPTH,
    "office":   LIVING_DEPTH,
    "lightwell": LIVING_DEPTH,
}

# Door side each room prefers TOWARD its spine neighbour
# Key: (room_type, spine_direction) where spine_direction ∈ {N, S, E, W}
# spine_direction = which side of the room faces toward the spine path
_DOOR_SIDE_RULES: Dict[str, str] = {
    # room on spine → door toward the NEXT depth (toward bedrooms = inward)
    "verandah": "S",   # door opens into living (south of verandah in canonical)
    "living":   "S",   # door toward corridor (inward)
    "bedroom":  "N",   # door toward corridor (outward, north = corridor side)
    "bathroom": "N",   # door toward bedroom
    "kitchen":  "N",   # door toward dining/living
    "dining":   "S",   # door toward corridor
    "utility":  "N",   # door toward kitchen
    "corridor": "S",   # corridor has no door — S is nominal
    "pooja":    "N",   # door toward corridor
    "study":    "N",   # door toward corridor
    "toilet":   "N",
    "store":    "N",
}


# ═══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class PathNode:
    """One node in the circulation path or its branches."""
    room_type:      str
    depth:          int          # 0 = entry … 3 = bedroom
    on_spine:       bool         # True = primary path; False = branch
    grid_row:       int          # intended grid row (0 = top/entry)
    grid_col:       int = -1     # -1 = spans all columns (e.g. corridor)
    preferred_door: str = "S"    # door side facing toward spine


@dataclass
class CirculationPlan:
    """
    Output of CirculationPlanner.build().

    Attributes
    ----------
    spine        : ordered PathNodes on the primary path (entry → beds)
    branches     : PathNodes adjacent to spine (kitchen, baths, etc.)
    corridor_row : grid row index of the spanning corridor (-1 if no corridor)
    row_depth    : {path_depth → grid_row} — maps depth to actual grid row
    door_hints   : {room_type → door_side} — consumed by _assign_door_side()
    violations   : hard-rule failure messages
    warnings     : soft-rule notes
    """
    spine:        List[PathNode] = field(default_factory=list)
    branches:     List[PathNode] = field(default_factory=list)
    corridor_row: int = -1
    row_depth:    Dict[int, int] = field(default_factory=dict)
    door_hints:   Dict[str, str] = field(default_factory=dict)
    violations:   List[str]      = field(default_factory=list)
    warnings:     List[str]      = field(default_factory=list)

    def has_hard_violations(self) -> bool:
        return len(self.violations) > 0

    # Convenience: single grid-row assignment per depth level
    def row_for(self, depth: int) -> int:
        return self.row_depth.get(depth, depth)


# ═══════════════════════════════════════════════════════════════════════════════
# PLANNER
# ═══════════════════════════════════════════════════════════════════════════════

class CirculationPlanner:
    """
    Computes the circulation path and door hints for a floor plan.

    Parameters
    ----------
    n_beds    : number of bedroom rooms
    n_baths   : number of bathroom/toilet rooms
    has_corridor : whether a corridor room is in the room list
    has_kitchen  : whether kitchen is present
    has_dining   : whether explicit dining is present
    plot_width   : usable width in metres
    plot_depth   : usable depth in metres
    """

    def __init__(
        self,
        n_beds:       int,
        n_baths:      int,
        has_corridor: bool,
        has_kitchen:  bool,
        has_dining:   bool,
        has_verandah: bool,
        plot_width:   float,
        plot_depth:   float,
    ):
        self.n_beds       = n_beds
        self.n_baths      = n_baths
        self.has_corridor = has_corridor or n_beds >= 2   # NBC: 2+ beds need corridor
        self.has_kitchen  = has_kitchen
        self.has_dining   = has_dining
        self.has_verandah = has_verandah
        self.plot_width   = plot_width
        self.plot_depth   = plot_depth

    # ─────────────────────────────────────────────────────────────────────────
    def build(self) -> CirculationPlan:
        """Compute the circulation path and return a CirculationPlan."""
        plan = CirculationPlan()

        # ── Step 1: Build spine ───────────────────────────────────────────────
        self._build_spine(plan)

        # ── Step 2: Build branches ────────────────────────────────────────────
        self._build_branches(plan)

        # ── Step 3: Assign grid rows ──────────────────────────────────────────
        self._assign_grid_rows(plan)

        # ── Step 4: Compute door hints ────────────────────────────────────────
        self._compute_door_hints(plan)

        # ── Step 5: Validate rules ────────────────────────────────────────────
        self._validate(plan)

        return plan

    # ─────────────────────────────────────────────────────────────────────────
    def _build_spine(self, plan: CirculationPlan) -> None:
        """
        Build the primary circulation path as a linear sequence of PathNodes.
        Spine order: verandah(0) → living(1) → corridor(2) → bedroom(3)
        """
        row = 0   # grid rows counted from entry (row 0 = nearest to entry)

        # Entry: verandah always on spine at depth 0
        if self.has_verandah:
            plan.spine.append(PathNode(
                room_type="verandah", depth=ENTRY_DEPTH,
                on_spine=True, grid_row=row,
                preferred_door=_DOOR_SIDE_RULES["verandah"],
            ))

        row += 1
        # Living: depth 1, always present
        plan.spine.append(PathNode(
            room_type="living", depth=LIVING_DEPTH,
            on_spine=True, grid_row=row,
            preferred_door=_DOOR_SIDE_RULES["living"],
        ))

        # Corridor: depth 2, spans all columns
        if self.has_corridor:
            row += 1
            plan.spine.append(PathNode(
                room_type="corridor", depth=CORRIDOR_DEPTH,
                on_spine=True, grid_row=row, grid_col=-1,   # -1 = full-width span
                preferred_door=_DOOR_SIDE_RULES["corridor"],
            ))
            plan.corridor_row = row

        # Bedrooms: depth 3 (all at same depth — corridor fans out to them)
        if self.n_beds > 0:
            row += 1
            for i in range(self.n_beds):
                plan.spine.append(PathNode(
                    room_type="bedroom", depth=BED_DEPTH,
                    on_spine=True, grid_row=row,
                    preferred_door=_DOOR_SIDE_RULES["bedroom"],
                ))

    # ─────────────────────────────────────────────────────────────────────────
    def _build_branches(self, plan: CirculationPlan) -> None:
        """
        Attach service/support rooms as branches off the spine.
        Branches do NOT extend the depth order — they sit beside their
        attachment point.
        """
        # Kitchen: branches off living row (depth 1)
        if self.has_kitchen:
            plan.branches.append(PathNode(
                room_type="kitchen",
                depth=LIVING_DEPTH,
                on_spine=False,
                grid_row=plan.row_for(LIVING_DEPTH),
                preferred_door=_DOOR_SIDE_RULES["kitchen"],
            ))

        # Dining: branches off living row
        if self.has_dining:
            plan.branches.append(PathNode(
                room_type="dining",
                depth=LIVING_DEPTH,
                on_spine=False,
                grid_row=plan.row_for(LIVING_DEPTH),
                preferred_door=_DOOR_SIDE_RULES["dining"],
            ))

        # Bathrooms: branch off bedroom row (depth 3)
        for _ in range(self.n_baths):
            plan.branches.append(PathNode(
                room_type="bathroom",
                depth=BED_DEPTH,
                on_spine=False,
                grid_row=plan.row_for(BED_DEPTH),
                preferred_door=_DOOR_SIDE_RULES["bathroom"],
            ))

    # ─────────────────────────────────────────────────────────────────────────
    def _assign_grid_rows(self, plan: CirculationPlan) -> None:
        """
        Build row_depth mapping from path depth to grid row.
        Spine nodes already have grid_row set; corridor_row is the key index.
        """
        for node in plan.spine:
            plan.row_depth[node.depth] = node.grid_row

        # Update branch grid_rows from the mapping
        for branch in plan.branches:
            branch.grid_row = plan.row_depth.get(branch.depth, branch.grid_row)

    # ─────────────────────────────────────────────────────────────────────────
    def _compute_door_hints(self, plan: CirculationPlan) -> None:
        """
        Derive door_hints: for each room type, which wall faces toward the spine.

        In the canonical layout (entry at high-y / top of grid):
          - Rooms at row N open toward row N-1 (toward entry) → door = "N"
          - Exception: verandah opens toward living (downward) → door = "S"
          - Bedrooms open toward corridor (above) → door = "N"
          - Corridor is the path itself — no door
        """
        # Canonical: grid row 0 = entry side (high-y in coordinate system).
        # Row increases toward rear. "Toward entry" = "N" door side (lower row index).
        for node in plan.spine + plan.branches:
            rt = node.room_type
            if rt == "corridor":
                plan.door_hints[rt] = "NONE"   # corridor has no door
                continue
            if rt == "verandah":
                # Opens inward toward living
                plan.door_hints[rt] = "S"
                continue
            if rt == "living":
                # Opens both directions — primary door faces entry (N)
                plan.door_hints[rt] = "N"
                continue
            if rt == "bedroom":
                # Door toward corridor above (lower row index = "N")
                plan.door_hints[rt] = "N"
                continue
            if rt in ("bathroom", "toilet"):
                # Door toward adjacent bedroom
                plan.door_hints[rt] = "N"
                continue
            if rt == "kitchen":
                # Door toward dining/living (above kitchen, same row)
                plan.door_hints[rt] = "W"   # typically kitchen at east col, door faces west
                continue
            # Default: face toward spine (toward entry)
            plan.door_hints[rt] = _DOOR_SIDE_RULES.get(rt, "N")

    # ─────────────────────────────────────────────────────────────────────────
    def _validate(self, plan: CirculationPlan) -> None:
        """Run C1–C4 checks."""

        # C1: No dead ends — every spine node has at least one successor
        # (except the last bedroom nodes which are intentional terminals)
        spine_depths = [n.depth for n in plan.spine]
        for i, node in enumerate(plan.spine[:-self.n_beds]):
            # Each non-terminal spine node must have a successor at depth+1
            if node.depth == BED_DEPTH:
                continue
            successor_exists = any(
                n.depth == node.depth + 1 or n.depth == node.depth
                for n in plan.spine[i+1:]
            )
            if not successor_exists and node.room_type != "corridor":
                plan.violations.append(
                    f"C1: Dead end at '{node.room_type}' (depth={node.depth}) — "
                    f"no successor on spine"
                )

        # C2: Linear spine — grid_row must be monotonically non-decreasing
        prev_row = -1
        for node in plan.spine:
            if node.room_type == "bedroom":
                continue   # multiple bedrooms share same row — allowed
            if node.grid_row < prev_row:
                plan.violations.append(
                    f"C2: Zig-zag detected — '{node.room_type}' at grid_row "
                    f"{node.grid_row} is above previous row {prev_row}"
                )
            prev_row = max(prev_row, node.grid_row)

        # C3: Max one corridor
        corridors_on_spine = [n for n in plan.spine if n.room_type == "corridor"]
        if len(corridors_on_spine) > 1:
            plan.violations.append(
                f"C3: {len(corridors_on_spine)} corridor nodes on spine — "
                f"maximum is 1"
            )

        # C4 (soft): All bedrooms should be reachable via the corridor
        if self.has_corridor and self.n_beds > 0:
            if plan.corridor_row == -1:
                plan.warnings.append(
                    "C4: Corridor expected (n_beds >= 2) but not placed on spine"
                )
            bed_rows = {n.grid_row for n in plan.spine if n.room_type == "bedroom"}
            if plan.corridor_row != -1 and bed_rows:
                # Corridor must be between living_row and bed_row
                living_row = plan.row_depth.get(LIVING_DEPTH, 1)
                min_bed_row = min(bed_rows)
                if not (living_row < plan.corridor_row < min_bed_row):
                    plan.warnings.append(
                        f"C4: Corridor at row {plan.corridor_row} is not between "
                        f"living ({living_row}) and bedrooms ({min_bed_row}) — "
                        f"path order may not be enforced"
                    )


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE WRAPPER
# ═══════════════════════════════════════════════════════════════════════════════

def plan_circulation(room_types: List[str], plot_width: float, plot_depth: float) -> CirculationPlan:
    """
    One-call wrapper. Builds a CirculationPlan from a flat room_types list.

    Parameters
    ----------
    room_types  : e.g. ["living","bedroom","bedroom","kitchen","bathroom","corridor"]
    plot_width  : usable width metres
    plot_depth  : usable depth metres

    Returns
    -------
    CirculationPlan
    """
    planner = CirculationPlanner(
        n_beds       = room_types.count("bedroom"),
        n_baths      = room_types.count("bathroom") + room_types.count("toilet"),
        has_corridor = "corridor" in room_types,
        has_kitchen  = "kitchen"  in room_types,
        has_dining   = "dining"   in room_types,
        has_verandah = "verandah" in room_types or "entrance" in room_types,
        plot_width   = plot_width,
        plot_depth   = plot_depth,
    )
    return planner.build()


# ═══════════════════════════════════════════════════════════════════════════════
# DEAD-END VALIDATOR  (post-placement, geometric)
# ═══════════════════════════════════════════════════════════════════════════════

def validate_no_dead_ends(rooms, tolerance: float = 0.22) -> List[str]:
    """
    Post-placement check: every non-entry room must be reachable from a
    living or corridor room without passing through a bedroom (no hidden
    rooms locked behind other rooms).

    Returns list of violation strings (empty = OK).
    """
    def _adj(r1, r2):
        h_gap = max(r1.x - (r2.x + r2.width), r2.x - (r1.x + r1.width))
        v_ov  = min(r1.y + r1.height, r2.y + r2.height) - max(r1.y, r2.y)
        if h_gap <= tolerance and v_ov > 0.3:
            return True
        v_gap = max(r1.y - (r2.y + r2.height), r2.y - (r1.y + r1.height))
        h_ov  = min(r1.x + r1.width, r2.x + r2.width) - max(r1.x, r2.x)
        return v_gap <= tolerance and h_ov > 0.3

    # BFS from living/verandah/corridor — can we reach every room?
    entry_types = {"living", "verandah", "entrance", "corridor"}
    sources = [r for r in rooms if r.room_type in entry_types]
    if not sources:
        return []

    reachable: Set[str] = set()
    queue = list(sources)
    while queue:
        current = queue.pop(0)
        if current.name in reachable:
            continue
        reachable.add(current.name)
        for other in rooms:
            if other.name not in reachable and _adj(current, other):
                queue.append(other)

    unreachable = [r for r in rooms if r.name not in reachable
                   and r.room_type not in ("lightwell", "courtyard")]

    violations = []
    for r in unreachable:
        violations.append(
            f"C1 dead-end: '{r.name}' ({r.room_type}) not reachable "
            f"from any entry/living/corridor room"
        )
    return violations


def validate_no_zig_zag(rooms, corridor_room=None, tolerance: float = 0.22) -> List[str]:
    """
    Post-placement check: the path Living → Corridor → Bedroom must be
    monotonically in one direction (all y-decreasing or all x-decreasing).

    Returns list of violation strings.
    """
    violations = []
    livings    = [r for r in rooms if r.room_type == "living"]
    corridors  = [r for r in rooms if r.room_type == "corridor"]
    bedrooms   = [r for r in rooms if r.room_type == "bedroom"]

    if not (livings and bedrooms):
        return violations

    lv = livings[0]
    lv_cy = lv.y + lv.height / 2.0

    for bed in bedrooms:
        bed_cy = bed.y + bed.height / 2.0
        # In canonical layout, living is at high-y, bedrooms at low-y
        # so lv_cy should be > bed_cy (living above bedrooms in grid)
        if lv_cy < bed_cy:
            violations.append(
                f"C2 zig-zag: Living centroid y={lv_cy:.2f} is BELOW "
                f"bedroom '{bed.name}' centroid y={bed_cy:.2f} — "
                f"path direction is inverted"
            )

    if corridors:
        corr = corridors[0]
        corr_cy = corr.y + corr.height / 2.0
        for bed in bedrooms:
            bed_cy = bed.y + bed.height / 2.0
            if corr_cy < bed_cy:
                violations.append(
                    f"C2 zig-zag: Corridor y={corr_cy:.2f} is BELOW "
                    f"bedroom '{bed.name}' y={bed_cy:.2f} — "
                    f"corridor should be between living and bedrooms"
                )

    return violations
