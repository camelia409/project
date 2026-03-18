"""
Design Constraints Module — Extracted from 2BHK Reference Floor Plan
(North-facing 12×15m, Coimbatore, Tamil Nadu)

Codifies 10 strict architectural rules as hard/soft constraints with
mathematical conditions, priority weights, and penalty functions.

Usage:
    from algorithms.design_constraints import (
        evaluate_all_constraints,
        MANDATORY_ADJ, FORBIDDEN_ADJ, ZONE_MAP,
    )
    report = evaluate_all_constraints(fp)
    # report["score"]      → 0–100 weighted constraint satisfaction
    # report["violations"] → list of hard-constraint failures
    # report["penalties"]  → dict of soft-constraint deductions
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Callable
import math

# ═══════════════════════════════════════════════════════════════════════════════
# ZONE SEGMENTATION
# ═══════════════════════════════════════════════════════════════════════════════

ZONE_MAP: Dict[str, str] = {
    # Public — first contact from entry, social spaces
    "verandah":  "public",
    "living":    "public",
    "dining":    "public",
    # Semi-private — service / transition
    "kitchen":   "semi_private",
    "utility":   "semi_private",
    "corridor":  "semi_private",
    "pooja":     "semi_private",
    "store":     "semi_private",
    # Private — bedrooms and attached wet rooms
    "bedroom":   "private",
    "bathroom":  "private",
    "toilet":    "private",
    # Special
    "courtyard": "public",
    "office":    "semi_private",
    "study":     "semi_private",
    "lightwell": "semi_private",
}

ZONE_DEPTH_ORDER = {"public": 0, "semi_private": 1, "private": 2}

# ═══════════════════════════════════════════════════════════════════════════════
# ADJACENCY MATRICES
# ═══════════════════════════════════════════════════════════════════════════════

# Mandatory adjacencies: these pairs MUST share a wall (≥0.3m overlap)
# Format: (room_type_a, room_type_b, min_shared_wall_m)
MANDATORY_ADJ: List[Tuple[str, str, float]] = [
    ("living",   "verandah",  1.2),   # R1: entry buffer → living transition
    ("living",   "corridor",  1.0),   # R2: living as circulation hub
    ("living",   "dining",    2.0),   # R2: social continuity (if dining exists)
    ("kitchen",  "dining",    2.4),   # R3: food-prep → serving (shared counter wall)
    ("kitchen",  "utility",   1.2),   # R3: service cluster
    ("bedroom",  "bathroom",  1.2),   # R8: attached bath access
    ("bedroom",  "corridor",  0.9),   # R6: corridor serves all bedrooms
    ("corridor", "living",    1.0),   # R6: corridor connects public to private
]

# Forbidden adjacencies: these pairs must NOT share a wall
# Format: (room_type_a, room_type_b, reason)
FORBIDDEN_ADJ: List[Tuple[str, str, str]] = [
    ("toilet",   "kitchen",  "NBC Part 8 Cl.5.1 — hygiene"),
    ("toilet",   "dining",   "NBC Part 8 — odour/hygiene"),
    ("bathroom", "kitchen",  "Hygiene — plumbing cross-contamination risk"),
    ("bedroom",  "kitchen",  "Cooking odour infiltration into sleeping zone"),
]

# Weighted desirability matrix (0–5 scale, used for soft scoring)
# 5 = critical, 4 = highly desirable, 3 = desirable, 2 = neutral, 1 = undesirable
ADJ_WEIGHT_MATRIX: Dict[Tuple[str, str], int] = {
    ("kitchen",  "dining"):    5,
    ("kitchen",  "utility"):   5,
    ("bedroom",  "bathroom"):  5,
    ("living",   "verandah"):  5,
    ("living",   "dining"):    4,
    ("living",   "corridor"):  4,
    ("bedroom",  "corridor"):  4,
    ("pooja",    "living"):    4,
    ("dining",   "corridor"):  3,
    ("utility",  "bathroom"):  3,   # plumbing stack
    ("store",    "kitchen"):   3,
    ("bedroom",  "bedroom"):   2,
    ("bedroom",  "kitchen"):   1,   # undesirable
    ("bathroom", "kitchen"):   0,   # forbidden
    ("toilet",   "kitchen"):   0,   # forbidden
    ("toilet",   "dining"):    0,   # forbidden
}


# ═══════════════════════════════════════════════════════════════════════════════
# ROOM PROPORTION LIMITS  (from reference plan measurements)
# ═══════════════════════════════════════════════════════════════════════════════

# {room_type: (min_width, min_depth, max_aspect_ratio, min_area, max_area)}
ROOM_PROPORTIONS: Dict[str, Tuple[float, float, float, float, float]] = {
    "living":    (3.0, 3.6, 1.70, 12.0, 30.0),   # ref: 5.8×3.6 = 20.9m², AR 1.61
    "dining":    (2.5, 2.7, 1.50,  7.0, 15.0),
    "bedroom":   (3.0, 3.0, 1.40,  9.0, 20.0),   # ref: master 4.2×3.2, AR 1.31
    "kitchen":   (2.4, 2.8, 1.50,  5.0, 12.0),   # ref: 2.8×3.2 = 8.96m², AR 1.14
    "bathroom":  (1.2, 1.8, 1.80,  1.8,  6.0),   # ref: 2.0×2.4 = 4.8m², AR 1.20
    "toilet":    (0.9, 1.2, 1.80,  1.1,  4.0),
    "utility":   (1.2, 1.5, 1.80,  2.0,  6.0),   # ref: 1.9×2.2 = 4.18m², AR 1.16
    "corridor":  (0.9, 1.5, 8.00,  1.5, 20.0),   # corridors are naturally elongated
    "verandah":  (1.5, 2.0, 2.50,  3.0, 12.0),   # ref: 3.6×2.2 = 7.92m², AR 1.64
    "pooja":     (1.2, 1.2, 1.30,  1.5,  4.0),   # ref: 1.4×1.4 = 1.96m², AR 1.0
    "courtyard": (2.5, 2.5, 1.50,  6.0, 25.0),
    "office":    (2.4, 2.4, 1.50,  6.0, 12.0),
    "study":     (2.0, 2.0, 1.60,  4.0, 10.0),
    "store":     (1.2, 1.2, 1.80,  1.5,  6.0),
}


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTRAINT DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ConstraintResult:
    rule_id: str
    name: str
    constraint_type: str          # "hard" or "soft"
    passed: bool
    score: float                  # 0.0–1.0 (1.0 = fully satisfied)
    weight: float                 # priority weight for overall score
    penalty: float                # deduction if failed (0.0–1.0)
    detail: str = ""              # human-readable explanation
    violations: List[str] = field(default_factory=list)


def _rooms_adjacent(r1, r2, tolerance: float = 0.22) -> bool:
    """Two rooms are adjacent if edges are within tolerance and overlap > 0.3m."""
    # Horizontal adjacency (left/right neighbours)
    h_gap = max(r1.x - (r2.x + r2.width), r2.x - (r1.x + r1.width))
    v_overlap = min(r1.y + r1.height, r2.y + r2.height) - max(r1.y, r2.y)
    if h_gap <= tolerance and v_overlap > 0.3:
        return True
    # Vertical adjacency (top/bottom neighbours)
    v_gap = max(r1.y - (r2.y + r2.height), r2.y - (r1.y + r1.height))
    h_overlap = min(r1.x + r1.width, r2.x + r2.width) - max(r1.x, r2.x)
    if v_gap <= tolerance and h_overlap > 0.3:
        return True
    return False


def _room_centroid_depth(room, entry_y: float, plot_depth: float) -> float:
    """Normalised depth of room centroid from entry wall (0.0=entry, 1.0=rear)."""
    cy = room.y + room.height / 2.0
    return abs(cy - entry_y) / plot_depth if plot_depth > 0 else 0.5


# ─── RULE 1: Public-to-Private Depth Zoning ──────────────────────────────────
def rule_01_depth_zoning(fp) -> ConstraintResult:
    """Public rooms must be closer to entry than private rooms.
    Condition: mean_centroid(public) < mean_centroid(semi_private) < mean_centroid(private)
    """
    # Detect entry wall: verandah/living with highest y = entry side
    entry_rooms = [r for r in fp.rooms if r.room_type in ("verandah", "living")]
    if entry_rooms:
        entry_y = max(r.y + r.height for r in entry_rooms)
    else:
        entry_y = fp.plot_height   # fallback: assume entry at max-y
    depth = fp.plot_height

    zone_depths: Dict[str, List[float]] = {"public": [], "semi_private": [], "private": []}
    for r in fp.rooms:
        zone = ZONE_MAP.get(r.room_type, "semi_private")
        # Depth = distance from entry wall (high y = near entry = low depth)
        cy = r.y + r.height / 2.0
        d = (entry_y - cy) / depth if depth > 0 else 0.5
        d = max(0.0, min(1.0, d))
        zone_depths[zone].append(d)

    means = {}
    for z in ("public", "semi_private", "private"):
        vals = zone_depths[z]
        means[z] = sum(vals) / len(vals) if vals else 0.5

    violations = []
    if means["public"] > means["private"]:
        violations.append(
            f"Public zone centroid ({means['public']:.2f}) deeper than private ({means['private']:.2f})"
        )
    if means["public"] > means["semi_private"] + 0.05:
        violations.append(
            f"Public zone ({means['public']:.2f}) deeper than semi-private ({means['semi_private']:.2f})"
        )

    passed = len(violations) == 0
    # Partial credit: how much of the ordering is correct
    score = 1.0
    if not passed:
        # Score based on how inverted the ordering is
        ideal_order = [means["public"], means["semi_private"], means["private"]]
        actual_sorted = sorted(ideal_order)
        if ideal_order == actual_sorted:
            score = 1.0
        elif ideal_order[0] <= ideal_order[2]:
            score = 0.5   # at least public < private
        else:
            score = 0.0

    return ConstraintResult(
        rule_id="R01", name="Public→Private Depth Zoning",
        constraint_type="hard", passed=passed, score=score,
        weight=0.15, penalty=0.20, violations=violations,
        detail=f"Depth means — public: {means['public']:.2f}, semi: {means['semi_private']:.2f}, private: {means['private']:.2f}",
    )


# ─── RULE 2: Living Room as Central Hub ──────────────────────────────────────
def rule_02_living_hub(fp) -> ConstraintResult:
    """Living room must be adjacent to: (a) entry/verandah, (b) corridor, (c) kitchen or dining.
    Condition: adjacency_count(living, {verandah, corridor, kitchen|dining}) >= 2
    """
    livings = [r for r in fp.rooms if r.room_type == "living"]
    if not livings:
        return ConstraintResult(
            rule_id="R02", name="Living as Central Hub",
            constraint_type="hard", passed=False, score=0.0,
            weight=0.12, penalty=0.15,
            violations=["No living room found"],
        )

    living = livings[0]
    targets = {"verandah", "corridor", "kitchen", "dining"}
    adj_types = set()
    for r in fp.rooms:
        if r is living:
            continue
        if r.room_type in targets and _rooms_adjacent(living, r):
            adj_types.add(r.room_type)

    required_min = 2
    count = len(adj_types)
    passed = count >= required_min
    score = min(1.0, count / 3.0)

    violations = []
    if not passed:
        missing = targets - adj_types
        violations.append(f"Living adjacent to {adj_types or 'none'}, missing from {missing}")

    return ConstraintResult(
        rule_id="R02", name="Living as Central Hub",
        constraint_type="hard", passed=passed, score=score,
        weight=0.12, penalty=0.15, violations=violations,
        detail=f"Living adjacent to: {adj_types}",
    )


# ─── RULE 3: Kitchen–Dining–Utility Service Cluster ─────────────────────────
def rule_03_service_cluster(fp) -> ConstraintResult:
    """Kitchen must share wall >= 2.4m with dining/living.
    Kitchen must be adjacent to utility.
    Kitchen + utility + common toilet form contiguous block.
    """
    kitchens  = [r for r in fp.rooms if r.room_type == "kitchen"]
    utilities = [r for r in fp.rooms if r.room_type == "utility"]
    livings   = [r for r in fp.rooms if r.room_type in ("living", "dining")]

    violations = []
    checks_passed = 0
    total_checks  = 3

    if not kitchens:
        violations.append("No kitchen found")
        return ConstraintResult(
            rule_id="R03", name="Service Cluster (Kitchen-Dining-Utility)",
            constraint_type="hard", passed=False, score=0.0,
            weight=0.10, penalty=0.15, violations=violations,
        )

    kit = kitchens[0]

    # Check 1: Kitchen adjacent to dining/living
    kit_adj_social = any(
        _rooms_adjacent(kit, r) for r in livings
    )
    if kit_adj_social:
        checks_passed += 1
    else:
        violations.append("Kitchen not adjacent to living/dining")

    # Check 2: Kitchen adjacent to utility
    kit_adj_util = any(
        _rooms_adjacent(kit, u) for u in utilities
    ) if utilities else False
    if kit_adj_util:
        checks_passed += 1
    elif utilities:
        violations.append("Kitchen not adjacent to utility")
    else:
        checks_passed += 1   # no utility required (1BHK)

    # Check 3: Kitchen + utility share a column (plumbing alignment)
    if utilities and kitchens:
        u = utilities[0]
        col_overlap = min(kit.x + kit.width, u.x + u.width) - max(kit.x, u.x)
        if col_overlap >= 0.5:
            checks_passed += 1
        else:
            violations.append(f"Kitchen-utility column overlap only {col_overlap:.2f}m (need >= 0.5m)")
    else:
        checks_passed += 1

    passed = checks_passed == total_checks
    score  = checks_passed / total_checks

    return ConstraintResult(
        rule_id="R03", name="Service Cluster (Kitchen-Dining-Utility)",
        constraint_type="hard", passed=passed, score=score,
        weight=0.10, penalty=0.15, violations=violations,
    )


# ─── RULE 4: Wet Area Linear Stacking ────────────────────────────────────────
def rule_04_wet_stacking(fp) -> ConstraintResult:
    """All wet rooms (bathroom, toilet, kitchen, utility) must have plumbing walls
    aligned along one axis. Max plumbing run <= building_width * 0.6.
    Condition: all wet rooms share at least one common column band.
    """
    wet_types = {"bathroom", "toilet", "kitchen", "utility"}
    wet_rooms = [r for r in fp.rooms if r.room_type in wet_types]

    if len(wet_rooms) < 2:
        return ConstraintResult(
            rule_id="R04", name="Wet Area Linear Stacking",
            constraint_type="soft", passed=True, score=1.0,
            weight=0.08, penalty=0.10,
            detail="Fewer than 2 wet rooms — stacking N/A",
        )

    # Find maximum x-overlap across all wet room pairs
    # Ideal: all wet rooms overlap in x (vertical plumbing stack)
    xs = [(r.x, r.x + r.width) for r in wet_rooms]
    common_left  = max(x[0] for x in xs)
    common_right = min(x[1] for x in xs)
    x_overlap = max(0.0, common_right - common_left)

    # Alternative: check y-overlap (horizontal plumbing run)
    ys = [(r.y, r.y + r.height) for r in wet_rooms]
    common_bot = max(y[0] for y in ys)
    common_top = min(y[1] for y in ys)
    y_overlap  = max(0.0, common_top - common_bot)

    best_overlap = max(x_overlap, y_overlap)
    axis = "vertical" if x_overlap >= y_overlap else "horizontal"

    # Plumbing run: distance from first to last wet room centroid along the stack axis
    if axis == "vertical":
        centroids = sorted(r.y + r.height / 2 for r in wet_rooms)
    else:
        centroids = sorted(r.x + r.width / 2 for r in wet_rooms)
    plumbing_run = centroids[-1] - centroids[0] if centroids else 0

    violations = []
    max_run = fp.plot_width * 0.6 if axis == "horizontal" else fp.plot_height * 0.6
    if plumbing_run > max_run:
        violations.append(f"Plumbing run {plumbing_run:.1f}m exceeds {max_run:.1f}m limit")

    if best_overlap < 0.3:
        violations.append(f"Wet rooms lack common {axis} band (overlap={best_overlap:.2f}m)")

    passed = len(violations) == 0
    score = min(1.0, best_overlap / 1.0) * (1.0 - max(0, plumbing_run - max_run) / max_run)
    score = max(0.0, score)

    return ConstraintResult(
        rule_id="R04", name="Wet Area Linear Stacking",
        constraint_type="soft", passed=passed, score=score,
        weight=0.08, penalty=0.10, violations=violations,
        detail=f"Stack axis: {axis}, overlap: {best_overlap:.2f}m, run: {plumbing_run:.1f}m",
    )


# ─── RULE 5: Room Aspect Ratios ──────────────────────────────────────────────
def rule_05_aspect_ratios(fp) -> ConstraintResult:
    """Every room must satisfy: 1.0 <= aspect_ratio <= max_ar (per type).
    Master bedroom >= 12.5m², secondary >= 9.0m².
    """
    violations = []
    room_scores = []

    bed_index = 0
    for r in fp.rooms:
        props = ROOM_PROPORTIONS.get(r.room_type)
        if not props:
            continue

        min_w, min_d, max_ar, min_area, max_area = props
        ar = r.aspect_ratio

        # Aspect ratio check
        if ar > max_ar:
            violations.append(
                f"{r.name}: AR={ar:.2f} exceeds max {max_ar:.1f}"
            )
            room_scores.append(max(0, 1.0 - (ar - max_ar) / max_ar))
        else:
            room_scores.append(1.0)

        # Area bounds
        if r.area < min_area - 0.5:     # 0.5m² tolerance
            violations.append(
                f"{r.name}: area={r.area:.1f}m² below min {min_area:.1f}m²"
            )
        # Width minimum
        actual_min_dim = min(r.width, r.height)
        if actual_min_dim < min_w - 0.1:  # 10cm tolerance
            violations.append(
                f"{r.name}: min dimension={actual_min_dim:.2f}m below {min_w:.1f}m"
            )

        # Bedroom-specific: master >= 12.5m², secondary >= 9.0m²
        if r.room_type == "bedroom":
            bed_index += 1
            threshold = 12.5 if bed_index == 1 else 9.0
            if r.area < threshold - 0.5:
                violations.append(
                    f"{r.name}: {r.area:.1f}m² below {'master' if bed_index==1 else 'secondary'} min {threshold}m²"
                )

    avg_score = sum(room_scores) / len(room_scores) if room_scores else 1.0
    passed = len(violations) == 0

    return ConstraintResult(
        rule_id="R05", name="Room Proportions & Aspect Ratios",
        constraint_type="hard", passed=passed, score=avg_score,
        weight=0.12, penalty=0.15, violations=violations,
        detail=f"{len(room_scores)} rooms checked, avg AR compliance: {avg_score:.2f}",
    )


# ─── RULE 6: Corridor Dimensions & Reach ─────────────────────────────────────
def rule_06_corridor(fp) -> ConstraintResult:
    """Corridor width 0.9–1.5m. Length <= 40% of building depth.
    Must connect living zone to all bedrooms.
    """
    corridors = [r for r in fp.rooms if r.room_type == "corridor"]
    bedrooms  = [r for r in fp.rooms if r.room_type == "bedroom"]
    livings   = [r for r in fp.rooms if r.room_type == "living"]

    if not corridors:
        # No corridor — acceptable only for 1BHK
        if len(bedrooms) <= 1:
            return ConstraintResult(
                rule_id="R06", name="Corridor Dimensions & Reach",
                constraint_type="soft", passed=True, score=0.8,
                weight=0.08, penalty=0.10,
                detail="1BHK — corridor optional",
            )
        return ConstraintResult(
            rule_id="R06", name="Corridor Dimensions & Reach",
            constraint_type="hard", passed=False, score=0.0,
            weight=0.08, penalty=0.15,
            violations=[f"No corridor found but {len(bedrooms)} bedrooms need access"],
        )

    violations = []
    corr = corridors[0]

    # Width check (min dimension of corridor)
    corr_width = min(corr.width, corr.height)
    if corr_width < 0.9:
        violations.append(f"Corridor width {corr_width:.2f}m below 0.9m NBC minimum")
    elif corr_width > 1.5:
        violations.append(f"Corridor width {corr_width:.2f}m exceeds 1.5m (wasted space)")

    # Length check: spanning corridors run along width; max 100% of width is acceptable
    corr_length = max(corr.width, corr.height)
    max_length = max(fp.plot_width, fp.plot_height) * 0.70
    if corr_length > max_length:
        violations.append(
            f"Corridor length {corr_length:.1f}m exceeds 40% of depth ({max_length:.1f}m)"
        )

    # Bedroom connectivity: every bedroom must be adjacent to corridor
    beds_connected = sum(1 for b in bedrooms if _rooms_adjacent(corr, b))
    if beds_connected < len(bedrooms):
        violations.append(
            f"Only {beds_connected}/{len(bedrooms)} bedrooms adjacent to corridor"
        )

    # Living connectivity
    living_connected = any(_rooms_adjacent(corr, lv) for lv in livings)
    if not living_connected and livings:
        violations.append("Corridor not connected to living room")

    passed = len(violations) == 0
    connectivity_ratio = beds_connected / max(1, len(bedrooms))
    width_ok = 1.0 if 0.9 <= corr_width <= 1.5 else 0.5
    score = 0.5 * connectivity_ratio + 0.3 * width_ok + 0.2 * (1.0 if living_connected else 0.0)

    return ConstraintResult(
        rule_id="R06", name="Corridor Dimensions & Reach",
        constraint_type="hard", passed=passed, score=score,
        weight=0.08, penalty=0.15, violations=violations,
        detail=f"Width: {corr_width:.2f}m, beds connected: {beds_connected}/{len(bedrooms)}",
    )


# ─── RULE 7: Entry Buffer (Verandah) ─────────────────────────────────────────
def rule_07_entry_buffer(fp) -> ConstraintResult:
    """A verandah/foyer (depth >= 1.5m, width >= 2.0m) must exist between
    main entrance and living room. Verandah placed on entry-facing wall.
    """
    verandahs = [r for r in fp.rooms if r.room_type == "verandah"]

    if not verandahs:
        return ConstraintResult(
            rule_id="R07", name="Entry Buffer (Verandah)",
            constraint_type="soft", passed=False, score=0.0,
            weight=0.06, penalty=0.08,
            violations=["No verandah/foyer found"],
            detail="Verandah provides thermal buffer + social transition",
        )

    v = verandahs[0]
    violations = []

    if v.height < 1.5 and v.width < 1.5:
        violations.append(f"Verandah depth {min(v.width, v.height):.2f}m below 1.5m minimum")
    if max(v.width, v.height) < 2.0:
        violations.append(f"Verandah span {max(v.width, v.height):.2f}m below 2.0m minimum")

    # Must be adjacent to living
    livings = [r for r in fp.rooms if r.room_type == "living"]
    if livings and not any(_rooms_adjacent(v, lv) for lv in livings):
        violations.append("Verandah not adjacent to living room")

    # Should be on entry side (high y in canonical layout — verandah near top)
    if v.y + v.height < fp.plot_height * 0.5:
        violations.append("Verandah not on entry side of plan")

    passed = len(violations) == 0
    score = 1.0 if passed else max(0.0, 1.0 - len(violations) * 0.3)

    return ConstraintResult(
        rule_id="R07", name="Entry Buffer (Verandah)",
        constraint_type="soft", passed=passed, score=score,
        weight=0.06, penalty=0.08, violations=violations,
    )


# ─── RULE 8: Attached Toilet per Bedroom ─────────────────────────────────────
def rule_08_attached_bath(fp) -> ConstraintResult:
    """Master bedroom must have an attached bathroom (adjacent, door into bedroom).
    Attached bathroom min 2.0m × 2.0m (3.6m²).
    """
    bedrooms  = sorted(
        [r for r in fp.rooms if r.room_type == "bedroom"],
        key=lambda r: r.area, reverse=True,
    )
    bathrooms = [r for r in fp.rooms if r.room_type in ("bathroom", "toilet")]

    if not bedrooms:
        return ConstraintResult(
            rule_id="R08", name="Attached Toilet per Bedroom",
            constraint_type="hard", passed=True, score=1.0,
            weight=0.08, penalty=0.12,
        )

    violations = []
    beds_with_bath = 0

    for i, bed in enumerate(bedrooms):
        has_adj_bath = any(_rooms_adjacent(bed, b) for b in bathrooms)
        if has_adj_bath:
            beds_with_bath += 1
        elif i == 0:
            violations.append(f"Master bedroom ({bed.name}) has no attached bathroom")

    # At least master must have attached bath
    passed = beds_with_bath >= 1
    score = beds_with_bath / max(1, len(bedrooms))

    return ConstraintResult(
        rule_id="R08", name="Attached Toilet per Bedroom",
        constraint_type="hard", passed=passed, score=score,
        weight=0.08, penalty=0.12, violations=violations,
        detail=f"{beds_with_bath}/{len(bedrooms)} bedrooms have attached bath",
    )


# ─── RULE 9: Vastu Puja Room in NE Quadrant ──────────────────────────────────
def rule_09_puja_placement(fp) -> ConstraintResult:
    """If puja room exists, it must be in the NE quadrant of the building footprint.
    Min 1.2×1.2m. Must have window on N or E wall.
    """
    poojas = [r for r in fp.rooms if r.room_type == "pooja"]

    if not poojas:
        return ConstraintResult(
            rule_id="R09", name="Puja Room NE Placement (Vastu)",
            constraint_type="soft", passed=True, score=1.0,
            weight=0.04, penalty=0.05,
            detail="No puja room in layout — rule N/A",
        )

    p = poojas[0]
    violations = []

    # NE quadrant: x > midpoint, y > midpoint (canonical: south=entry=y0, north=y_max)
    mid_x = fp.plot_width / 2
    mid_y = fp.plot_height / 2
    pcx = p.x + p.width / 2
    pcy = p.y + p.height / 2

    # In canonical orientation (entry=South, y increases northward):
    # NE = right half (x > mid) AND top half (y > mid)
    in_ne = pcx >= mid_x * 0.8 and pcy >= mid_y * 0.8   # 20% tolerance
    if not in_ne:
        violations.append(
            f"Puja centroid ({pcx:.1f}, {pcy:.1f}) not in NE quadrant "
            f"(need x>{mid_x:.1f}, y>{mid_y:.1f})"
        )

    # Size check
    if min(p.width, p.height) < 1.2:
        violations.append(f"Puja min dimension {min(p.width, p.height):.2f}m below 1.2m")

    # Window on N or E
    ne_windows = {"N", "NE", "E"}
    has_ne_window = any(w in ne_windows for w in p.windows)
    if not has_ne_window:
        violations.append("Puja lacks N or E window (Vastu requirement)")

    passed = len(violations) == 0
    score = 1.0 if passed else max(0.0, 1.0 - len(violations) * 0.35)

    return ConstraintResult(
        rule_id="R09", name="Puja Room NE Placement (Vastu)",
        constraint_type="soft", passed=passed, score=score,
        weight=0.04, penalty=0.05, violations=violations,
    )


# ─── RULE 10: Structural Grid Alignment ──────────────────────────────────────
def rule_10_grid_alignment(fp) -> ConstraintResult:
    """All room partition edges must snap to a structural grid.
    Column spacing 2.5–4.5m. Wall thickness 230mm (outer), 115mm (inner).
    No room edge should deviate > 0.15m from the nearest grid line.
    """
    # Collect all unique x and y edges
    x_edges = set()
    y_edges = set()
    for r in fp.rooms:
        x_edges.update([round(r.x, 3), round(r.x + r.width, 3)])
        y_edges.update([round(r.y, 3), round(r.y + r.height, 3)])

    x_sorted = sorted(x_edges)
    y_sorted = sorted(y_edges)

    violations = []

    # Check column spacing
    x_spans = [x_sorted[i+1] - x_sorted[i] for i in range(len(x_sorted)-1)]
    x_spans = [s for s in x_spans if s > 0.3]   # ignore wall thicknesses
    for span in x_spans:
        if span > 4.5:
            violations.append(f"X-grid span {span:.2f}m exceeds 4.5m structural limit")

    y_spans = [y_sorted[i+1] - y_sorted[i] for i in range(len(y_sorted)-1)]
    y_spans = [s for s in y_spans if s > 0.3]
    for span in y_spans:
        if span > 4.5:
            violations.append(f"Y-grid span {span:.2f}m exceeds 4.5m structural limit")

    # Check alignment: rooms in the same grid row should share y-edges
    # Count how many room edges deviate from the nearest grid line
    misaligned = 0
    total_edges = 0
    for r in fp.rooms:
        for edge_x in [r.x, r.x + r.width]:
            total_edges += 1
            min_dist = min(abs(edge_x - gx) for gx in x_sorted)
            if min_dist > 0.15:
                misaligned += 1
        for edge_y in [r.y, r.y + r.height]:
            total_edges += 1
            min_dist = min(abs(edge_y - gy) for gy in y_sorted)
            if min_dist > 0.15:
                misaligned += 1

    alignment_ratio = 1.0 - (misaligned / max(1, total_edges))
    if alignment_ratio < 0.85:
        violations.append(
            f"Only {alignment_ratio:.0%} edges aligned to grid (need >= 85%)"
        )

    passed = len(violations) == 0
    score = alignment_ratio

    return ConstraintResult(
        rule_id="R10", name="Structural Grid Alignment",
        constraint_type="soft", passed=passed, score=score,
        weight=0.07, penalty=0.10, violations=violations,
        detail=f"Grid: {len(x_sorted)} x-lines, {len(y_sorted)} y-lines, alignment: {alignment_ratio:.0%}",
    )


# ─── BONUS: Forbidden Adjacency Check ────────────────────────────────────────
def rule_00_forbidden_adjacency(fp) -> ConstraintResult:
    """No forbidden room pairs may share a wall."""
    violations = []
    for r1 in fp.rooms:
        for r2 in fp.rooms:
            if r1 is r2:
                continue
            for fa, fb, reason in FORBIDDEN_ADJ:
                if (r1.room_type == fa and r2.room_type == fb):
                    if _rooms_adjacent(r1, r2):
                        violations.append(
                            f"{r1.name} adjacent to {r2.name} — FORBIDDEN ({reason})"
                        )

    passed = len(violations) == 0
    return ConstraintResult(
        rule_id="R00", name="Forbidden Adjacency Violations",
        constraint_type="hard", passed=passed,
        score=1.0 if passed else 0.0,
        weight=0.10, penalty=0.25, violations=violations,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MASTER EVALUATOR
# ═══════════════════════════════════════════════════════════════════════════════

ALL_RULES: List[Callable] = [
    rule_00_forbidden_adjacency,
    rule_01_depth_zoning,
    rule_02_living_hub,
    rule_03_service_cluster,
    rule_04_wet_stacking,
    rule_05_aspect_ratios,
    rule_06_corridor,
    rule_07_entry_buffer,
    rule_08_attached_bath,
    rule_09_puja_placement,
    rule_10_grid_alignment,
]


def evaluate_all_constraints(fp) -> Dict:
    """Run all 11 constraint rules against a FloorPlan.

    Returns:
        {
            "score":       float (0–100),
            "passed":      int,
            "failed":      int,
            "hard_pass":   bool (all hard constraints satisfied),
            "violations":  List[str],
            "results":     List[ConstraintResult],
            "breakdown":   Dict[str, float],   # rule_id → individual score
        }
    """
    results: List[ConstraintResult] = []
    for rule_fn in ALL_RULES:
        try:
            cr = rule_fn(fp)
            results.append(cr)
        except Exception as e:
            results.append(ConstraintResult(
                rule_id="ERR", name=rule_fn.__name__,
                constraint_type="soft", passed=False, score=0.0,
                weight=0.0, penalty=0.0,
                violations=[f"Rule evaluation error: {e}"],
            ))

    # Weighted score
    total_weight = sum(cr.weight for cr in results)
    if total_weight > 0:
        weighted_score = sum(cr.score * cr.weight for cr in results) / total_weight * 100
    else:
        weighted_score = 0.0

    # Hard constraint gate
    hard_results = [cr for cr in results if cr.constraint_type == "hard"]
    hard_pass = all(cr.passed for cr in hard_results)

    # Collect all violations
    all_violations = []
    for cr in results:
        for v in cr.violations:
            all_violations.append(f"[{cr.rule_id}] {v}")

    breakdown = {cr.rule_id: round(cr.score * 100, 1) for cr in results}

    return {
        "score":      round(weighted_score, 1),
        "passed":     sum(1 for cr in results if cr.passed),
        "failed":     sum(1 for cr in results if not cr.passed),
        "hard_pass":  hard_pass,
        "violations": all_violations,
        "results":    results,
        "breakdown":  breakdown,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# QUICK REFERENCE TABLE (for documentation / debugging)
# ═══════════════════════════════════════════════════════════════════════════════

CONSTRAINT_SUMMARY = [
    # (rule_id, name, type, weight, condition_summary)
    ("R00", "Forbidden Adjacency",       "hard", 0.10, "toilet!=kitchen, toilet!=dining, bath!=kitchen, bed!=kitchen"),
    ("R01", "Depth Zoning",              "hard", 0.15, "mean_depth(public) < mean_depth(semi) < mean_depth(private)"),
    ("R02", "Living Hub",                "hard", 0.12, "living.adj({verandah,corridor,kitchen|dining}) >= 2"),
    ("R03", "Service Cluster",           "hard", 0.10, "kitchen.adj(dining) AND kitchen.adj(utility) AND col_overlap>=0.5m"),
    ("R04", "Wet Stacking",              "soft", 0.08, "all wet rooms share column band; plumbing_run <= 0.6*width"),
    ("R05", "Room Proportions",          "hard", 0.12, "AR <= max_ar per type; master>=12.5m²; secondary>=9.0m²"),
    ("R06", "Corridor",                  "hard", 0.08, "width 0.9–1.5m; length<=40% depth; connects living↔all beds"),
    ("R07", "Entry Buffer",              "soft", 0.06, "verandah depth>=1.5m, width>=2.0m, adj(living), on entry wall"),
    ("R08", "Attached Bath",             "hard", 0.08, "master bedroom.adj(bathroom) required"),
    ("R09", "Puja NE Placement",         "soft", 0.04, "puja centroid in NE quadrant; min 1.2×1.2m; window N|E"),
    ("R10", "Grid Alignment",            "soft", 0.07, ">=85% edges on grid; column spacing 2.5–4.5m"),
]
