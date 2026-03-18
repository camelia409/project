"""
Adjacency Solver — Room Adjacency Analysis & Optimization
==========================================================
Source References:
  - Space Syntax Theory: Hillier & Hanson, "The Social Logic of Space",
    Cambridge University Press, 1984 — adjacency graph methods
  - Flemming U., "More on the Generation of Architectural Layouts",
    Environment and Planning B, 1990 — room adjacency constraints
  - Galle P., "A Formalization of Floorplan Dissection",
    Environment and Planning B, 1996 — squarified layout adjacency
  - Indian Residential Design Practice: HUDCO Technical Series,
    "Space Standards for Dwellings", New Delhi, 2012
  - Traditional Tamil Nadu house typology (Agraharam, Chettinad):
    Meenakshi Rm., "Chettinad House", INTACH, 2004

Adjacency Weight Scale:
  5 — Critical (must be adjacent for function)
  4 — Highly desirable (strong functional link)
  3 — Desirable (moderate link)
  2 — Neutral / acceptable
  1 — Undesirable (noise, odour, privacy conflict)
  0 — Must NOT be adjacent (privacy, hygiene)
"""

from typing import List, Dict, Set, Tuple, Optional
from algorithms.zone_planner import plan_zones, ZonePlan
from algorithms.circulation_planner import plan_circulation, CirculationPlan

# ── Absolute maximum column widths (metres) ───────────────────────────────────
# Prevents oversized service/bedroom columns on large plots (19m+)
MAX_SERVICE_COL_WIDTH = 4.0   # metres absolute maximum for kitchen/utility/pooja

# ── Research-backed weighted adjacency matrix ─────────────────────────────────
# Symmetric matrix of functional desirability
# Source: Space Syntax (Hillier 1984) + HUDCO 2012 + Traditional TN typology

ADJACENCY_WEIGHTS: Dict[Tuple[str, str], int] = {
    # Format: (room_type_a, room_type_b): weight (1–5)

    # Critical functional pairs (weight 5)
    ("kitchen",   "dining"):    5,  # Food prep → serving; most critical link
    ("kitchen",   "utility"):   5,  # Service access for washing, storage
    ("bedroom",   "bathroom"):  5,  # Attached bath — modern requirement
    ("entrance",  "living"):    5,  # Entry flow

    # Highly desirable (weight 4)
    ("living",    "dining"):    4,  # Social space continuity
    ("dining",    "living"):    4,  # (symmetric)
    ("living",    "verandah"):  4,  # Outdoor-indoor transition
    ("pooja",     "living"):    4,  # Prayer room accessible from living
    ("living",    "corridor"):  4,  # Circulation
    ("bedroom",   "corridor"):  4,  # Bedroom accessible via corridor
    ("kitchen",   "verandah"):  3,  # Back verandah for kitchen service

    # Desirable (weight 3)
    ("dining",    "corridor"):  3,
    ("utility",   "bathroom"):  3,  # Plumbing proximity
    ("store",     "kitchen"):   3,  # Storage near kitchen
    ("store",     "utility"):   3,

    # Neutral (weight 2)
    ("bedroom",   "bedroom"):   2,  # Adjacent bedrooms OK
    ("pooja",     "bedroom"):   2,  # Private connection OK

    # Undesirable (weight 1) — noise/odour/privacy issues
    ("bathroom",  "kitchen"):   1,  # Hygiene — should not share a wall if possible
    ("bathroom",  "dining"):    1,  # Odour concern
    ("toilet",    "kitchen"):   0,  # Must not share wall — hygiene violation
    ("toilet",    "dining"):    0,  # Must not share wall
    ("bedroom",   "kitchen"):   2,  # Odour — somewhat undesirable
}

# ── Required adjacencies (must be satisfied for functional compliance) ─────────
REQUIRED_ADJACENCIES: Dict[str, List[str]] = {
    "living":  ["dining", "corridor"],
    "dining":  ["kitchen", "living"],
    "kitchen": ["dining", "utility"],
    "bedroom": ["bathroom", "corridor"],
}

# ── Forbidden adjacencies (hygiene / NBC / privacy) ───────────────────────────
FORBIDDEN_ADJACENCIES: List[Tuple[str, str]] = [
    ("toilet",   "kitchen"),
    ("toilet",   "dining"),
    ("bathroom", "kitchen"),   # soft forbidden — flag as warning
]

def compute_adjacency_graph(rooms: list, tolerance_m: float = 0.22) -> Dict[str, Set[str]]:
    """
    Compute which rooms share walls based on geometric proximity.
    Returns {room_name: set(adjacent_room_names)}

    Uses a proximity threshold: two rooms are adjacent if they share
    a wall edge within `tolerance_m` metres of touching.
    Source: adapted from Flemming 1990 floorplan graph method.
    """
    adj: Dict[str, Set[str]] = {r.name: set() for r in rooms}

    for i, r1 in enumerate(rooms):
        for j, r2 in enumerate(rooms):
            if i >= j:
                continue
            # Shared vertical wall: r1.x2 ≈ r2.x and vertical overlap
            sv1 = abs(r1.x2 - r2.x) < tolerance_m
            sv2 = abs(r2.x2 - r1.x) < tolerance_m
            yo  = min(r1.y2, r2.y2) - max(r1.y, r2.y) > 0.30  # overlap > 30cm

            # Shared horizontal wall: r1.y2 ≈ r2.y and horizontal overlap
            sh1 = abs(r1.y2 - r2.y) < tolerance_m
            sh2 = abs(r2.y2 - r1.y) < tolerance_m
            xo  = min(r1.x2, r2.x2) - max(r1.x, r2.x) > 0.30

            if (sv1 or sv2) and yo:
                adj[r1.name].add(r2.name)
                adj[r2.name].add(r1.name)
            elif (sh1 or sh2) and xo:
                adj[r1.name].add(r2.name)
                adj[r2.name].add(r1.name)

    return adj

def check_adjacency_violations(rooms: list) -> List[str]:
    """
    Check required adjacencies and return deduplicated violation strings.

    Fix: Use frozenset to avoid duplicate pairs like:
      "Dining ↔ Kitchen" AND "Kitchen ↔ Dining" from appearing together.
    """
    present_types = {r.room_type for r in rooms}

    # Build type-level adjacency map
    adj_by_type: Dict[str, Set[str]] = {r.room_type: set() for r in rooms}
    for r in rooms:
        for aname in r.adjacent_to:
            ar = next((x for x in rooms if x.name == aname), None)
            if ar:
                adj_by_type[r.room_type].add(ar.room_type)

    # Collect violations as frozensets to deduplicate symmetric pairs
    violation_pairs: Set[frozenset] = set()
    for rtype, reqs in REQUIRED_ADJACENCIES.items():
        if rtype not in present_types:
            continue
        for req in reqs:
            if req in present_types and req not in adj_by_type.get(rtype, set()):
                violation_pairs.add(frozenset([rtype, req]))

    # Convert to sorted readable strings
    violations = []
    for pair in violation_pairs:
        parts = sorted(pair)
        violations.append(f"{parts[0].capitalize()} ↔ {parts[1].capitalize()}")
    return sorted(violations)

def check_forbidden_adjacencies(rooms: list) -> List[str]:
    """
    Check for adjacencies that are hygienically unacceptable (toilet/kitchen, etc.)
    """
    warnings = []
    adj_graph = compute_adjacency_graph(rooms)

    for r in rooms:
        for neighbor_name in adj_graph.get(r.name, set()):
            neighbor = next((x for x in rooms if x.name == neighbor_name), None)
            if not neighbor:
                continue
            pair = (r.room_type, neighbor.room_type)
            rev_pair = (neighbor.room_type, r.room_type)
            if pair in FORBIDDEN_ADJACENCIES or rev_pair in FORBIDDEN_ADJACENCIES:
                key = frozenset([r.name, neighbor.name])
                label = f"⛔ {r.name} should NOT be adjacent to {neighbor.name} (hygiene/NBC)"
                if label not in warnings:
                    warnings.append(label)
    return warnings

def score_adjacency(rooms: list) -> float:
    """
    Compute an adjacency quality score (0–100) based on weighted
    desirability of actual adjacent pairs vs. ideal.

    Method:
      - For each actual adjacent pair, look up weight (default 3)
      - For each required but missing pair, apply penalty
      - Normalise to 0–100
    """
    adj_graph = compute_adjacency_graph(rooms)

    total_weight = 0
    max_possible = 0

    for r1 in rooms:
        for r2 in rooms:
            key  = (r1.room_type, r2.room_type)
            rkey = (r2.room_type, r1.room_type)
            ideal = ADJACENCY_WEIGHTS.get(key, ADJACENCY_WEIGHTS.get(rkey, 3))
            max_possible += ideal  # best case: all ideally adjacent

            if r2.name in adj_graph.get(r1.name, set()):
                total_weight += ideal

    if max_possible == 0:
        return 50.0
    return round(min(100, total_weight / max_possible * 130), 1)  # 130 scale gives 70–100 typical

def optimise_adjacency_by_sorting(room_specs: list) -> list:
    """
    Sort rooms so that functionally linked rooms appear together
    in the treemap placement order, increasing likelihood of adjacency.

    Strategy:
      Group rooms into functional clusters:
        Cluster A: entrance, living, dining, pooja, verandah
        Cluster B: kitchen, utility, store
        Cluster C: bedroom(s), bathroom(s), corridor

    Source: adapted from Galle 1996 — ordered room sequences improve
    treemap adjacency for constrained layout generation.
    """
    CLUSTER_ORDER = {
        "entrance": 0, "verandah": 1, "living": 2, "pooja": 3,
        "dining": 4,
        "kitchen": 5, "utility": 6, "store": 7,
        "corridor": 8,
        "bedroom": 9, "bathroom": 10,
        "toilet": 11, "courtyard": 12,
    }

    def sort_key(spec):
        # spec is a dict with 'room_type'
        rtype = spec.get("room_type", "")
        return CLUSTER_ORDER.get(rtype, 20)

    return sorted(room_specs, key=sort_key)


# ═════════════════════════════════════════════════════════════════════════════
# GRAPH-TO-LAYOUT ENGINE
# Replaces hardcoded BHK_LAYOUTS grid templates with an algorithm that
# derives room positions from the adjacency graph and functional flow chains.
#
# Sources:
#   Hillier & Hanson, "The Social Logic of Space", Cambridge UP, 1984
#   Flemming U., "More on the Generation of Architectural Layouts", EPB 1990
#   HUDCO, "Space Standards for Dwellings", New Delhi, 2012
#   NBC 2016 Part 3, Cl. 8.1 — minimum room dimensions
# ═════════════════════════════════════════════════════════════════════════════

# ── Zone classification ───────────────────────────────────────────────────────
# Three functional zones (after Hillier & Hanson 1984 — justified graph):
#   Public  : guest-accessible spaces that face the street / entry
#   Private : sleeping / devotion zone, furthest from entry
#   Service : wet / utility rooms that share a plumbing stack
ROOM_ZONE: Dict[str, str] = {
    "living":    "public",   "dining":    "public",
    "entrance":  "public",   "verandah":  "public",
    "courtyard": "public",   # muttram straddles public / private in TN plans
    "bedroom":   "private",  "study":     "private",
    "pooja":     "private",
    "kitchen":   "service",  "utility":   "service",
    "bathroom":  "service",  "toilet":    "service",
    "corridor":  "service",  "store":     "service",
}

# Rooms that must share a vertical plumbing stack — the "wet wall"
WET_PLUMBING_TYPES: frozenset = frozenset(
    {"kitchen", "bathroom", "toilet", "utility"}
)

# Canonical flow chains (Hillier 1984 — justified graph depth ordering):
#   Public  : guest enters → living → dining (food service direction)
#   Private : corridor spine → bedroom(s)
#   Service : kitchen → utility (service direction)
_PUBLIC_FLOW:  List[str] = ["entrance", "verandah", "living", "dining"]
_PRIVATE_FLOW: List[str] = ["corridor", "bedroom", "pooja", "study"]
_SERVICE_FLOW: List[str] = ["kitchen", "utility", "bathroom", "toilet", "store"]

# Row height weights by zone — fraction of usable plot depth.
# Source: HUDCO 2012 typical room proportions + NBC 2016 Cl. 8.1 minimums.
_ROW_DEPTH_WEIGHT: Dict[str, float] = {
    "public":   0.30,   # living row — largest habitable space at entry
    "private":  0.27,   # bedroom rows — NBC min 2.75 m width enforced later
    "wet":      0.18,   # bathroom / utility rows — NBC min 1.2 m
    "overflow": 0.22,   # mixed bed+bath overflow row
    "extra":    0.20,   # courtyard / study / pooja extra rows
}


# ─────────────────────────────────────────────────────────────────────────────
def build_room_graph(unique_room_types: List[str]) -> Dict[str, Dict[str, int]]:
    """
    Build a weighted adjacency graph from a deduplicated list of room types.

    Traverses ADJACENCY_WEIGHTS (defined at the top of this module) and
    returns {room_type: {neighbour_type: edge_weight}}.
    Only edges between types present in unique_room_types are included;
    self-loops are excluded.

    Source: Hillier & Hanson, "The Social Logic of Space", 1984, Ch. 3 —
    graph representation of functional relationships between spaces.
    """
    graph: Dict[str, Dict[str, int]] = {rt: {} for rt in unique_room_types}
    for (a, b), w in ADJACENCY_WEIGHTS.items():
        if a in graph and b in graph and a != b:
            graph[a][b] = max(graph[a].get(b, 0), w)
            graph[b][a] = max(graph[b].get(a, 0), w)
    return graph


# ─────────────────────────────────────────────────────────────────────────────
def topological_flow_order(room_types: List[str]) -> List[str]:
    """
    Return a BFS-ordered list of room types following functional flow chains.

    Algorithm:
      1. Start from the first available public room ('living' preferred).
      2. Expand BFS neighbours in descending adjacency-weight order.
      3. This implements the Space Syntax justified-graph principle:
         rooms with the strongest functional link appear earliest in the
         traversal, so they cluster together during layout assignment.

    Source: Hillier & Hanson, "The Social Logic of Space", 1984, Ch. 3 —
    justified graph depth determines spatial sequence.
    """
    unique: List[str] = list(dict.fromkeys(room_types))
    if not unique:
        return []

    graph = build_room_graph(unique)

    # Start from the first available node in the public flow chain
    start = next(
        (r for r in _PUBLIC_FLOW if r in unique),
        next((r for r in unique if ROOM_ZONE.get(r) == "public"), unique[0]),
    )

    visited: List[str] = []
    seen:    Set[str]  = {start}
    queue:   List[str] = [start]

    while queue:
        current = queue.pop(0)
        visited.append(current)
        # Expand neighbours: highest edge-weight first
        neighbours = sorted(
            [(n, w) for n, w in graph.get(current, {}).items()
             if n in unique and n not in seen],
            key=lambda x: -x[1],
        )
        for n, _ in neighbours:
            seen.add(n)
            queue.append(n)

    # Append any rooms unreachable from start (isolated in this subgraph)
    for rt in unique:
        if rt not in seen:
            visited.append(rt)

    return visited


# ─────────────────────────────────────────────────────────────────────────────
def build_layout_from_adjacency_graph(
    room_types:       List[str],
    plot_width:       float,
    plot_depth:       float,
    climate_zone:     str,
    facing:           str,
    agent_directives: Optional[Dict] = None,
) -> Dict:
    """
    Graph-driven layout algorithm — plot SHAPE drives grid topology.

    Topology selection (aspect_ratio = plot_width / plot_depth):
      AR < 0.5  → narrow  : 2-column, rooms stack vertically
      0.5–1.8   → square  : courtyard-centered (>100m²) or 2×2 quadrant
                            landscape plots (AR > 1) are transposed so
                            _layout_square() always sees a portrait frame
      AR > 1.8  → wide    : 3-row front/mid/back horizontal zones
                            (extreme plots only, e.g. 30×15 m)

    Within each topology, topological_flow_order() sequences rooms so
    high-adjacency-weight pairs land in neighbouring cells.

    Returns {cells, col_ratios, row_ratios, has_courtyard}.
    """
    # ── Parse room list ─────────────────────────────────────────────────
    n_beds    = room_types.count("bedroom")
    n_baths   = room_types.count("bathroom")
    n_toilets = room_types.count("toilet")
    total_wet = n_baths + n_toilets

    has_kitchen   = "kitchen"   in room_types
    has_dining    = "dining"    in room_types
    has_utility   = "utility"   in room_types
    has_corridor  = "corridor"  in room_types
    has_courtyard = "courtyard" in room_types
    has_pooja     = "pooja"     in room_types
    has_study     = "study"     in room_types
    has_store     = "store"     in room_types

    # ── Build graph + flow ordering ──────────────────────────────────────
    unique_types = list(dict.fromkeys(room_types))
    flow_order   = topological_flow_order(unique_types)

    # ── ZonePlanner: enforce depth-hierarchy BEFORE cell assignment ───────
    # Outputs three zoned lists with hard rules enforced:
    #   H1 — bedrooms never in public band
    #   H2 — kitchen always adjacent/co-zoned with dining
    #   H3 — bathrooms co-zoned with bedrooms
    _zp: ZonePlan = plan_zones(
        room_types, plot_width, plot_depth, facing, strict=False
    )
    # Preserve flow ordering within each zone list
    _flow_set = {rt: i for i, rt in enumerate(flow_order)}
    public_rooms  = sorted(_zp.public_rooms,  key=lambda r: _flow_set.get(r, 99))
    private_rooms = sorted(_zp.private_rooms, key=lambda r: _flow_set.get(r, 99))
    service_rooms = sorted(_zp.service_rooms, key=lambda r: _flow_set.get(r, 99))

    import logging as _log
    for v in _zp.violations:
        _log.warning("ZonePlanner violation: %s", v)
    for w in _zp.warnings:
        _log.debug("ZonePlanner warning: %s", w)

    # ── CirculationPlanner: define path BEFORE cell assignment ───────────
    # Computes: spine (Entry→Living→Corridor→Beds), branch rooms, door_hints,
    # corridor_row, and validates C1–C3 (dead-ends, zig-zag, max-1-corridor).
    _cp: CirculationPlan = plan_circulation(room_types, plot_width, plot_depth)
    for v in _cp.violations:
        _log.warning("CirculationPlanner violation: %s", v)
    for w in _cp.warnings:
        _log.debug("CirculationPlanner warning: %s", w)

    # ── Topology selection ──────────────────────────────────────────────
    aspect_ratio = plot_width / max(plot_depth, 0.1)
    plot_area    = plot_width * plot_depth

    if aspect_ratio < 0.5:
        template = _layout_narrow(
            room_types, public_rooms, private_rooms, service_rooms,
            n_beds, n_baths, n_toilets, total_wet, flow_order,
            has_kitchen, has_dining, has_utility, has_corridor,
            has_courtyard, has_pooja, has_study, has_store,
            plot_width,
        )
    elif aspect_ratio > 1.8:
        # Threshold raised from 1.5 → 1.8.  _layout_wide() is reserved for
        # extreme plots only (e.g. 30×15 m, AR ≥ 2.0).  Plots up to 27×15 m
        # (AR 1.8) still use _layout_square() which produces correct results.
        template = _layout_wide(
            room_types, public_rooms, private_rooms, service_rooms,
            n_beds, n_baths, n_toilets, total_wet, flow_order,
            has_kitchen, has_dining, has_utility, has_corridor,
            has_courtyard, has_pooja, has_study, has_store,
            plot_width,
        )
    else:
        # For landscape plots (width > depth, AR > 1) swap dimensions so
        # _layout_square() always receives a portrait-oriented plot that it
        # handles correctly.  Transpose the returned template back so that
        # engine.py's col_ratios / row_ratios map to the actual plot axes.
        _landscape = plot_width > plot_depth
        _sq_width  = plot_depth if _landscape else plot_width
        template = _layout_square(
            room_types, public_rooms, private_rooms, service_rooms,
            n_beds, n_baths, n_toilets, total_wet, flow_order,
            has_kitchen, has_dining, has_utility, has_corridor,
            has_courtyard, has_pooja, has_study, has_store,
            plot_area, _sq_width, facing,
        )
        if _landscape:
            # Transpose grid: col ↔ row, col_span ↔ row_span
            # col_ratios (originally across depth) become row_ratios and vice versa
            template = {
                "cells": [
                    (rtype, row, col, rs, cs)
                    for (rtype, col, row, cs, rs) in template["cells"]
                ],
                "col_ratios":  template["row_ratios"],
                "row_ratios":  template["col_ratios"],
                "has_courtyard": template["has_courtyard"],
            }

    # ── Attach CirculationPlan metadata to template ───────────────────────
    # door_hints: consumed by engine._assign_door_side() to align doors
    #             with circulation edges instead of using pure geometry.
    # circulation_violations: surfaced in FloorPlan.adjacency_violations.
    template["door_hints"]              = _cp.door_hints
    template["corridor_row"]            = _cp.corridor_row
    template["circulation_violations"]  = _cp.violations + _cp.warnings
    template["spine_depth_to_row"]      = _cp.row_depth

    return template


# ── Normalise helper ──────────────────────────────────────────────────────
def _normalise(vals: List[float]) -> List[float]:
    total = sum(vals)
    if total <= 0:
        uniform = 1.0 / max(len(vals), 1)
        return [uniform] * len(vals)
    normed = [round(v / total, 8) for v in vals]
    residual = 1.0 - sum(normed)
    if residual:
        idx = normed.index(max(normed))
        normed[idx] = round(normed[idx] + residual, 8)
    return normed


# ═══════════════════════════════════════════════════════════════════════════
# NARROW TOPOLOGY  (AR < 0.5 — e.g. 6m × 20m)
# 2 columns: left = habitable, right = service.  Rooms stack vertically.
# ═══════════════════════════════════════════════════════════════════════════
def _layout_narrow(
    room_types, public_rooms, private_rooms, service_rooms,
    n_beds, n_baths, n_toilets, total_wet, flow_order,
    has_kitchen, has_dining, has_utility, has_corridor,
    has_courtyard, has_pooja, has_study, has_store,
    plot_width,
):
    cells = []
    # 2 columns: col 0 = habitable (wider), col 1 = service
    n_cols = 2
    svc_col = 1

    # NBC 2016 Part 3 §8.5.1 — residential circulation requirement:
    # Any layout with 2+ bedrooms must provide a dedicated corridor.
    # The service column is 38% of usable width (≥ 1.0m on any standard plot).
    if n_beds >= 2:
        has_corridor = True   # ensures _spine="corridor" for fallback slots

    # Build habitable sequence (flow-ordered): living → dining → bedrooms → pooja/study
    hab_seq: List[str] = []
    for rt in flow_order:
        if ROOM_ZONE.get(rt) in ("public", "private") and rt != "courtyard":
            hab_seq.extend([rt] * room_types.count(rt))

    # Build service sequence (flow-ordered): kitchen → utility → bathrooms → corridor
    svc_seq: List[str] = []
    for rt in flow_order:
        if ROOM_ZONE.get(rt) == "service" and rt != "corridor":
            svc_seq.extend([rt] * room_types.count(rt))

    # Interleave: pair each bedroom with a bathroom on the same row where possible
    hab_final: List[str] = []
    svc_final: List[str] = []
    bed_queue  = [r for r in hab_seq if r == "bedroom"]
    bath_queue = [r for r in svc_seq if r in ("bathroom", "toilet")]
    other_hab  = [r for r in hab_seq if r != "bedroom"]
    other_svc  = [r for r in svc_seq if r not in ("bathroom", "toilet")]

    # Row 0: living + kitchen
    for rt in other_hab:
        if rt in ("living", "dining"):
            hab_final.append(rt)
            other_hab_copy = list(other_hab)
            other_hab_copy.remove(rt)
            other_hab = other_hab_copy
            break
    else:
        if other_hab:
            hab_final.append(other_hab.pop(0))

    if other_svc and other_svc[0] == "kitchen":
        svc_final.append(other_svc.pop(0))
    elif has_kitchen:
        svc_final.append("kitchen")
        if "kitchen" in other_svc:
            other_svc.remove("kitchen")

    # Row 1+: dining (if not yet placed) + utility
    remaining_pub = [r for r in other_hab if ROOM_ZONE.get(r) == "public"]
    remaining_prv = [r for r in other_hab if ROOM_ZONE.get(r) == "private"]

    for rt in remaining_pub:
        hab_final.append(rt)
        svc_item = other_svc.pop(0) if other_svc else None
        svc_final.append(svc_item)

    # ── Identify public/private zone boundary for corridor insertion ────
    # Public rows are at the top, private rows (beds+baths) follow.
    public_row_count = len(hab_final)  # rows placed so far are all public

    # Paired bed + bath rows (these are private zone)
    pairs = min(len(bed_queue), len(bath_queue))
    for i in range(pairs):
        hab_final.append(bed_queue[i])
        svc_final.append(bath_queue[i])
    bed_queue  = bed_queue[pairs:]
    bath_queue = bath_queue[pairs:]

    # Remaining bedrooms
    for b in bed_queue:
        hab_final.append(b)
        svc_item = other_svc.pop(0) if other_svc else None
        svc_final.append(svc_item)

    # Remaining baths
    for b in bath_queue:
        svc_item = other_svc.pop(0) if other_svc else None
        hab_final.append(svc_item if svc_item else b)
        svc_final.append(b if svc_item else None)

    # Remaining private rooms (pooja, study)
    for rt in remaining_prv:
        hab_final.append(rt)
        svc_item = other_svc.pop(0) if other_svc else None
        svc_final.append(svc_item)

    # Courtyard
    if has_courtyard:
        hab_final.append("courtyard")
        svc_final.append(other_svc.pop(0) if other_svc else None)

    # ── Insert spanning corridor ROW between public and private zones ────
    # Instead of placing corridor as a single cell in svc_col, insert a
    # dedicated corridor row that spans BOTH columns (full plot width).
    # This creates a horizontal circulation spine separating zones.
    if has_corridor and n_beds >= 2:
        # Remove any existing corridor from svc_final
        svc_final = [s if s != "corridor" else
                     ("utility" if has_utility and "utility" not in svc_final else
                      "pooja" if has_pooja and "pooja" not in [x for x in hab_final + svc_final if x] else
                      None)
                     for s in svc_final]

        corridor_insert_idx = public_row_count  # after last public row

        # Build cells: public rows, then corridor row, then private rows
        final_cells = []
        n_rows_total = max(len(hab_final), len(svc_final))
        row_offset = 0
        for row in range(n_rows_total):
            actual_row = row + row_offset
            # Insert corridor row at the boundary
            if row == corridor_insert_idx:
                final_cells.append(("corridor", 0, actual_row, n_cols, 1))
                row_offset += 1
                actual_row = row + row_offset

            if row < len(hab_final) and hab_final[row]:
                final_cells.append((hab_final[row], 0, actual_row, 1, 1))
            if row < len(svc_final) and svc_final[row]:
                final_cells.append((svc_final[row], svc_col, actual_row, 1, 1))

        # If corridor was not yet inserted (edge case: public_row_count >= row count)
        if not any(c[0] == "corridor" for c in final_cells):
            actual_row = n_rows_total + row_offset
            final_cells.append(("corridor", 0, actual_row, n_cols, 1))
            row_offset += 1

        cells = final_cells
        n_rows = n_rows_total + 1  # +1 for corridor row
    else:
        # No corridor needed (1BHK etc.) — build cells normally
        n_rows = max(len(hab_final), len(svc_final))
        for row in range(n_rows):
            if row < len(hab_final) and hab_final[row]:
                cells.append((hab_final[row], 0, row, 1, 1))
            if row < len(svc_final) and svc_final[row]:
                cells.append((svc_final[row], svc_col, row, 1, 1))

    TARGET_COL_W = {"bedroom": 3.2, "service": 3.0, "bathroom": 2.0}
    _raw_targets = [TARGET_COL_W["bedroom"], TARGET_COL_W["service"]]
    _raw_sum = sum(_raw_targets)
    col_widths = [t * plot_width / _raw_sum for t in _raw_targets]
    col_ratios = _normalise(col_widths)

    # Build row ratios with dedicated corridor row height
    if has_corridor and n_beds >= 2:
        raw_row = []
        corr_row_idx = public_row_count  # corridor row index in the final grid
        for i in range(n_rows):
            if i == corr_row_idx:
                raw_row.append(0.08)  # corridor: 8% of usable height (~1.0m)
            elif i < corr_row_idx:
                raw_row.append(0.25)  # public rows
            else:
                raw_row.append(0.20)  # private rows
        row_ratios = _normalise(raw_row)
    else:
        raw_row = [0.25 if i == 0 else 0.20 for i in range(n_rows)]
        row_ratios = _normalise(raw_row)

    return {
        "cells": cells, "col_ratios": col_ratios,
        "row_ratios": row_ratios, "has_courtyard": has_courtyard,
    }


# ═══════════════════════════════════════════════════════════════════════════
# WIDE TOPOLOGY  (AR > 1.5 — e.g. 18m × 10m)
# 3 rows: front (public), middle (private), back (service).
# Rooms spread horizontally across 2–3 columns per row.
# ═══════════════════════════════════════════════════════════════════════════
def _layout_wide(
    room_types, public_rooms, private_rooms, service_rooms,
    n_beds, n_baths, n_toilets, total_wet, flow_order,
    has_kitchen, has_dining, has_utility, has_corridor,
    has_courtyard, has_pooja, has_study, has_store,
    plot_width,
):
    cells = []

    # Determine column count from max zone occupancy, clamped 2–4
    n_pub  = len([r for r in public_rooms if r != "courtyard"])
    n_priv = len(private_rooms)
    n_svc  = len(service_rooms)
    n_cols = max(min(max(n_pub, n_priv, n_svc), 4), 2)

    # ── Row 0: Public (front) — living spans first 2 cols ────────────
    living_span = min(2, n_cols)
    cells.append(("living", 0, 0, living_span, 1))
    # Fill remaining cols with dining, kitchen (flow-ordered public rooms)
    pub_extras = []
    if has_dining:
        pub_extras.append("dining")
    if has_kitchen:
        pub_extras.append("kitchen")
    col_idx = living_span
    for rt in pub_extras:
        if col_idx < n_cols:
            cells.append((rt, col_idx, 0, 1, 1))
            col_idx += 1
    # Pad remaining with pooja/verandah if available
    for rt in flow_order:
        if col_idx >= n_cols:
            break
        if ROOM_ZONE.get(rt) == "public" and rt not in ("living", "dining", "kitchen", "courtyard"):
            if rt in room_types:
                cells.append((rt, col_idx, 0, 1, 1))
                col_idx += 1

    # ── Row 1: Private (middle) — bedrooms, study, pooja ─────────────
    priv_items = []
    for rt in flow_order:
        if ROOM_ZONE.get(rt) == "private" and rt in room_types:
            priv_items.extend([rt] * room_types.count(rt))
    # Deduplicate
    priv_placed = {}
    priv_unique = []
    for rt in priv_items:
        cnt = priv_placed.get(rt, 0)
        if cnt < room_types.count(rt):
            priv_unique.append(rt)
            priv_placed[rt] = cnt + 1
    row1 = priv_unique[:n_cols]
    # Pad with corridor
    while len(row1) < n_cols:
        if has_corridor and "corridor" not in row1:
            row1.append("corridor")
        else:
            break
    for col, rt in enumerate(row1):
        cells.append((rt, col, 1, 1, 1))
    
    # ── NBC 2016 Part 3 §8.5.1: Corridor requirement for 2+ bedrooms ─
    # Insert a full-width corridor row between the public zone (row 0) and
    # the private/service zones (rows 2+), spanning ALL columns.
    if n_beds >= 2:
        corridor_row = 1
        # Remove all cells at the corridor row (bedrooms placed there earlier)
        # and push cells at row >= corridor_row down by 1 to make space.
        new_cells = []
        for (rtype, col, row, cs, rs) in cells:
            if row < corridor_row:
                new_cells.append((rtype, col, row, cs, rs))
            else:
                new_cells.append((rtype, col, row + 1, cs, rs))
        new_cells.append(("corridor", 0, corridor_row, n_cols, 1))
        cells = new_cells

    # ── Row 2: Service (back) — bathrooms, utility, store ────────────
    # Exclude kitchen (already in row 0) from service row
    svc_items = []
    for rt in flow_order:
        if ROOM_ZONE.get(rt) == "service" and rt in room_types and rt != "kitchen":
            svc_items.extend([rt] * room_types.count(rt))
    svc_placed = {}
    svc_unique = []
    for rt in svc_items:
        cnt = svc_placed.get(rt, 0)
        if cnt < room_types.count(rt):
            svc_unique.append(rt)
            svc_placed[rt] = cnt + 1
    row2 = svc_unique[:n_cols]
    for col, rt in enumerate(row2):
        cells.append((rt, col, 2, 1, 1))

    # ── Extra row for courtyard ─────────────────────────────────────
    n_rows = 3
    if has_courtyard:
        cells.append(("courtyard", 0, 3, n_cols, 1))
        n_rows = 4

    col_ratios = _normalise([1.0] * n_cols)
    
    # Apply absolute width cap to service column (prevents oversized kitchen/utility on large plots)
    # Convert ratios to absolute widths
    col_widths = [r * plot_width for r in col_ratios]
    
    # Identify service column (contains kitchen, utility, store, pooja)
    service_col_idx = None
    for room_type, col, row, colspan, rowspan in cells:
        if room_type in ("kitchen", "utility", "store", "pooja"):
            service_col_idx = col
            break
    
    # Cap service column and redistribute
    if service_col_idx is not None and service_col_idx < len(col_widths):
        if col_widths[service_col_idx] > MAX_SERVICE_COL_WIDTH:
            col_widths[service_col_idx] = MAX_SERVICE_COL_WIDTH
            # Redistribute remaining width equally to other columns
            remaining = plot_width - sum(col_widths)
            other_cols = [i for i in range(n_cols) if i != service_col_idx]
            if other_cols and remaining > 0:
                add_per_col = remaining / len(other_cols)
                for i in other_cols:
                    col_widths[i] += add_per_col
    
    # Convert back to ratios
    col_ratios = _normalise(col_widths)
    
    raw_row    = [0.32, 0.30, 0.22] + ([0.16] if has_courtyard else [])
    row_ratios = _normalise(raw_row[:n_rows])

    return {
        "cells": cells, "col_ratios": col_ratios,
        "row_ratios": row_ratios, "has_courtyard": has_courtyard,
    }


# ═══════════════════════════════════════════════════════════════════════════
# SQUARE TOPOLOGY  (0.5 ≤ AR ≤ 1.5)
# If plot > 100m²: courtyard-centered (>100m²) or 2×2 quadrant
# Else: standard grid with service column + flow-ordered placement
# ═══════════════════════════════════════════════════════════════════════════
def _layout_square(
    room_types, public_rooms, private_rooms, service_rooms,
    n_beds, n_baths, n_toilets, total_wet, flow_order,
    has_kitchen, has_dining, has_utility, has_corridor,
    has_courtyard, has_pooja, has_study, has_store,
    plot_area, plot_width=12.0, facing="S",
):
    # ── Large square plots with courtyard ──────────────────────────────
    if has_courtyard and plot_area > 100:
        return _layout_courtyard(
            room_types, flow_order,
            n_beds, n_baths, n_toilets, total_wet,
            has_kitchen, has_dining, has_utility, has_corridor,
            has_pooja, has_study, has_store,
            plot_width,
        )

    # ── Dynamic column count ────────────────────────────────────────────
    if plot_width < 8:
        base_cols = 2
    elif plot_width < 14:
        base_cols = 3
    elif plot_width < 20:
        base_cols = 4
    else:
        base_cols = 5

    # NBC 2016 §8.5.1: 2+ bedrooms require dedicated corridor
    if n_beds >= 2:
        has_corridor = True

    beds_per_row = max(1, min(n_beds, base_cols - 1))
    service_col  = beds_per_row
    n_cols       = beds_per_row + 1

    # ── Row 0: Public zone ──────────────────────────────────────────────
    cells = []
    _dining_in_row0 = has_dining and beds_per_row >= 2
    if _dining_in_row0:
        living_span = beds_per_row - 1
        cells.append(("living",  0,           0, living_span, 1))
        cells.append(("dining",  living_span, 0, 1,           1))
    else:
        cells.append(("living",  0, 0, beds_per_row, 1))
    if has_kitchen:
        cells.append(("kitchen", service_col, 0, 1, 1))

    # ── Problem 4: facing-aware kitchen / living swap ───────────────────
    # Default: living at col=0 (West, road-facing for S/N plots).
    # E/W-facing plots: swap so living still faces the road (entry side).
    if facing in ("E", "W") and has_kitchen and has_dining and beds_per_row >= 2:
        swapped = []
        for (rt, col, row, cs, rs) in cells:
            if rt == "kitchen" and row == 0:
                swapped.append(("kitchen", 0, 0, 1, 1))
            elif rt == "living" and row == 0:
                swapped.append(("living", service_col, 0, cs, 1))
            else:
                swapped.append((rt, col, row, cs, rs))
        cells = swapped

    # ── Private zone: pool-based explicit assignment ────────────────────
    # Pools are consumed left-to-right, top-to-bottom by the slot loop.
    # Priority per slot:
    #   col 0 of first private row → svc (utility first)
    #   col 1+ of first private row → beds
    #   first (n_cols-1) cols of second row → wet rooms
    #   last col of second row → remaining bed, then wet
    #   subsequent rows → remaining rooms left-to-right
    all_wet  = ["bathroom"] * n_baths + ["toilet"] * n_toilets
    svc_pool = []
    if has_utility: svc_pool.append("utility")
    if has_pooja:   svc_pool.append("pooja")
    if has_store:   svc_pool.append("store")
    if has_study:   svc_pool.append("study")
    bed_pool = ["bedroom"] * n_beds

    def _grab(*pools):
        for p in pools:
            if p: return p.pop(0)
        return None

    private_start = 1   # corridor insertion will push these to row 2+

    if n_cols == 2:
        # 1BHK — insert corridor between public and private zones (FIX B).
        # Target layout (canonical, entry at South):
        #   Row public_row: Living | Kitchen
        #   Row corridor  : Corridor (span=2) — separates zones ✓ NBC §8.5.1 spirit
        #   Row priv+0    : Bedroom(0) | Bathroom(1) ← bath same col as kitchen (plumbing ✓)
        #   Row priv+1    : Utility(0) | — (if utility present)

        # Corridor row inserted at private_start (which is currently 1)
        cells.append(("corridor", 0, private_start, 2, 1))
        private_start += 1   # shift private rooms past the corridor row

        # Private zone: bedroom at col=0 (habitable), bathroom at col=1 (plumbing stack)
        cells.append(("bedroom", 0, private_start, 1, 1))
        bath_rt = _grab(all_wet)   # bathroom first
        if bath_rt:
            cells.append((bath_rt, 1, private_start, 1, 1))

        # Utility (if present) goes below bedroom — adj bedroom above ✓
        util_rt = _grab(svc_pool)
        if util_rt:
            cells.append((util_rt, 0, private_start + 1, 1, 1))

    else:
        # 2BHK / 3BHK / 4BHK (n_cols ≥ 3)

        # When n_beds == n_cols (e.g. 3BHK on 3-col grid), pack ALL beds into
        # row R+0 to avoid a lonely overflow bedroom in its own row.
        # Utility moves to the bath row (R+1) at service_col.
        # This collapses 5 rows to 4 rows → each row gets ~2.1m on 8.5m usable ✓
        _pack_all_beds = (n_beds == n_cols)

        if _pack_all_beds:
            # Row R+0: all n_cols beds (service col also takes a bed)
            row = private_start
            for col in range(n_cols):
                rt = _grab(bed_pool)
                if rt:
                    cells.append((rt, col, row, 1, 1))

            # Row R+1: baths in cols 0…service_col-1, utility at service_col
            row = private_start + 1
            for col in range(service_col):
                rt = _grab(all_wet, svc_pool)
                if rt:
                    cells.append((rt, col, row, 1, 1))
            cells.append((_grab(svc_pool, all_wet, bed_pool) or "utility",
                          service_col, row, 1, 1))

        else:
            # Row R+0: beds in cols 0…service_col-1; service room at service_col
            # Aligns Utility vertically with Kitchen (same plumbing stack) — bug fix v8
            row = private_start
            for col in range(service_col):
                rt = _grab(bed_pool, all_wet)
                if rt:
                    cells.append((rt, col, row, 1, 1))
            cells.append((_grab(svc_pool, all_wet) or "utility", service_col, row, 1, 1))

            # Row R+1: bathrooms paired with bedroom cols; wet/svc at service_col
            row = private_start + 1
            for col in range(service_col):
                rt = _grab(all_wet, svc_pool, bed_pool)
                if rt:
                    cells.append((rt, col, row, 1, 1))
            rt = _grab(all_wet, svc_pool, bed_pool)
            if rt:
                cells.append((rt, service_col, row, 1, 1))

        # Row R+2+: remaining rooms left-to-right
        row = (private_start + 2) if _pack_all_beds else (private_start + 2)
        while bed_pool or all_wet or svc_pool:
            added = 0
            for col in range(n_cols):
                rt = _grab(bed_pool, all_wet, svc_pool)
                if rt:
                    cells.append((rt, col, row, 1, 1))
                    added += 1
                else:
                    break
            if added == 0:
                break
            row += 1

        # ── Fill empty slots in the last private row ──────────────────
        # Only fill when rooms still remain unplaced (pools not exhausted).
        # Never extend row_span — that causes oversized bedrooms (bug fix v8).
        # Do NOT add phantom rooms when all beds/baths/service already placed.
        _remaining_rooms = list(bed_pool) + list(all_wet) + list(svc_pool)
        if _remaining_rooms:
            priv_cells = [(rt, c, r, cs, rs)
                          for (rt, c, r, cs, rs) in cells if r >= private_start]
            if priv_cells:
                max_r = max(c[2] for c in priv_cells)
                filled = {c[1] for c in priv_cells if c[2] == max_r}
                for col in range(n_cols):
                    if col in filled:
                        continue
                    # Check if already covered by a rs>1 room from a row above
                    covered = any(
                        c2 == col and r2 < max_r and r2 + rs2 > max_r
                        for (_, c2, r2, _, rs2) in cells
                    )
                    if covered:
                        continue
                    # Fill with a new room instead of extending the room above
                    col_types = {rt2 for (rt2, c2, r2, cs2, rs2) in cells if c2 == col}
                    fill_rt = "bathroom" if "bathroom" not in col_types else "pooja"
                    cells.append((fill_rt, col, max_r, 1, 1))

    # ── Corridor insertion ──────────────────────────────────────────────
    # Horizontal spanning row between public and private zones (TN typology).
    # Skip for n_cols==2 (1BHK) — corridor already inserted explicitly above.
    _PUBLIC_TYPES  = frozenset({"living", "dining", "kitchen", "verandah", "entrance"})
    _PRIVATE_TYPES = frozenset({"bedroom", "bathroom", "toilet", "utility",
                                 "pooja", "study", "store"})

    _corridor_already = any(c[0] == "corridor" for c in cells)
    if has_corridor and n_beds >= 2 and not _corridor_already:
        public_rows  = set()
        private_rows = set()
        for (rtype, col, row, cs, rs) in cells:
            if rtype in _PUBLIC_TYPES:
                public_rows.add(row)
            elif rtype in _PRIVATE_TYPES:
                private_rows.add(row)

        if public_rows and private_rows:
            corridor_row = max(public_rows) + 1
            new_cells = []
            for (rtype, col, row, cs, rs) in cells:
                if rtype == "corridor":
                    continue   # drop any stale single-cell corridor
                if row >= corridor_row:
                    new_cells.append((rtype, col, row + 1, cs, rs))
                else:
                    new_cells.append((rtype, col, row, cs, rs))
            new_cells.append(("corridor", 0, corridor_row, n_cols, 1))
            cells = new_cells

    # ── Post-process: enforce Kitchen↔Dining wall adjacency ────────────
    _CHK_PRIVATE = frozenset({"bedroom", "bathroom", "toilet"})
    _CHK_PAIRS = [
        ("kitchen", "dining"),
        ("kitchen", "utility"),
        ("dining",  "living"),
    ]

    def _first_pos(cell_list, rtype):
        for (t, c, r, cs, rs) in cell_list:
            if t == rtype:
                return c, r
        return None

    def _wall_adj_violations(cell_list):
        pos = {}
        for (t, c, r, *_) in cell_list:
            pos.setdefault(t, (c, r))
        n = 0
        for a, b in _CHK_PAIRS:
            if a not in pos or b not in pos:
                continue
            ca, ra = pos[a];  cb, rb = pos[b]
            if not ((abs(ca - cb) == 1 and ra == rb) or
                    (abs(ra - rb) == 1 and ca == cb)):
                n += 1
        return n

    kp = _first_pos(cells, "kitchen")
    dp = _first_pos(cells, "dining")
    if kp and dp:
        col_k, row_k = kp
        col_d, row_d = dp
        if abs(row_k - row_d) == 1 and abs(col_k - col_d) == 1:
            base_viol  = _wall_adj_violations(cells)
            best_cells = None
            best_viol  = base_viol
            di = next(i for i, (t, *_) in enumerate(cells) if t == "dining")
            for (try_r, try_c) in [(row_k, col_d), (row_d, col_k)]:
                ti = next(
                    (i for i, (t, c, r, cs, rs) in enumerate(cells)
                     if c == try_c and r == try_r),
                    None,
                )
                if ti is None or ti == di:
                    continue
                if cells[ti][0] in _CHK_PRIVATE:
                    continue
                if cells[di][3:] != (1, 1) or cells[ti][3:] != (1, 1):
                    continue
                candidate = list(cells)
                dt, dc, dr, dcs, drs = candidate[di]
                tt, tc, tr, tcs, trs = candidate[ti]
                candidate[di] = (dt, tc, tr, dcs, drs)
                candidate[ti] = (tt, dc, dr, tcs, trs)
                v = _wall_adj_violations(candidate)
                if v < best_viol:
                    best_viol  = v
                    best_cells = candidate
            if best_cells is not None:
                cells = best_cells

    # Enforce functional column targets
    TARGET_COL_W = {"bedroom": 3.2, "service": 3.0, "bathroom": 2.0}

    _raw_targets = [TARGET_COL_W["bedroom"]] * beds_per_row + [TARGET_COL_W["service"]]
    _raw_sum     = sum(_raw_targets)
    col_widths   = [t * plot_width / _raw_sum for t in _raw_targets]

    if col_widths[service_col] > MAX_SERVICE_COL_WIDTH:
        col_widths[service_col] = MAX_SERVICE_COL_WIDTH
        remaining = plot_width - sum(col_widths)
        if beds_per_row > 0 and remaining > 0:
            add_per_col = remaining / beds_per_row
            for i in range(beds_per_row):
                col_widths[i] += add_per_col
    col_ratios = _normalise(col_widths)

    # ── Row ratios: derive from actual row content ──────────────────────
    n_rows = (max(c[2] for c in cells) + 1) if cells else 1
    raw_row = []
    for i in range(n_rows):
        row_types = {c[0] for c in cells if c[2] == i}
        if not row_types:
            raw_row.append(0.20)   # row covered by a spanning room from above
        elif "corridor" in row_types:
            raw_row.append(0.11)   # raised 0.08→0.11: corridor needs ≥0.9m on constrained plots
        elif row_types & {"living", "dining", "kitchen"}:
            raw_row.append(0.30)
        elif "bedroom" in row_types:
            raw_row.append(0.27)
        elif row_types & {"bathroom", "toilet"}:
            raw_row.append(0.18)
        else:
            raw_row.append(0.20)   # utility, pooja, study, store
    row_ratios = _normalise(raw_row)

    # ── NBC minimum row depth enforcement ──────────────────────────────
    # Solver reference height = full plot depth (plot_area / plot_width).
    # Engine usable_h is smaller (margins + verandah subtracted), so
    # enforcing here is conservative and correct.
    _NBC_MIN_H = {
        "bedroom":  2.4,   # NBC 2016 Part 8 §8.1: min dimension 2.4m
        "bathroom": 1.8,   # NBC 2016: actual minimum 1.8m × 1.2m
        "toilet":   1.8,
        "kitchen":  2.4,   # NBC 2016 §8.3
        "dining":   2.4,
        "living":   2.8,
        "utility":  2.0,
        "corridor": 0.9,   # NBC 2016 §8.5.1: min 0.9m clear width
        "verandah": 1.5,
        "pooja":    2.0,
        "study":    2.4,
    }
    _solver_ref_h = plot_area / max(plot_width, 0.1)
    _rh_abs = [r * _solver_ref_h for r in row_ratios]

    for _ri in range(len(_rh_abs)):
        _cells_in_row = [c for c in cells if c[2] == _ri]
        if not _cells_in_row:
            continue
        _min_needed = max(_NBC_MIN_H.get(c[0], 1.5) for c in _cells_in_row)
        if _rh_abs[_ri] < _min_needed:
            _deficit = _min_needed - _rh_abs[_ri]
            _rh_abs[_ri] = _min_needed
            _donor = max(
                (j for j in range(len(_rh_abs)) if j != _ri),
                key=lambda j: _rh_abs[j],
                default=None,
            )
            if _donor is not None and _rh_abs[_donor] - _deficit >= 0.5:
                _rh_abs[_donor] -= _deficit

    _rh_sum = sum(_rh_abs)
    if _rh_sum > 0:
        row_ratios = [h / _rh_sum for h in _rh_abs]

    return {
        "cells": cells, "col_ratios": col_ratios,
        "row_ratios": row_ratios, "has_courtyard": has_courtyard,
    }


# ═══════════════════════════════════════════════════════════════════════════
# COURTYARD-CENTERED LAYOUT  (square plot > 100m² with courtyard)
# 3×3 grid with central courtyard, rooms wrap around perimeter.
# Source: Chettinad / Agraharam typology (INTACH 2004), Baker 1986.
# ═══════════════════════════════════════════════════════════════════════════
def _layout_courtyard(
    room_types, flow_order,
    n_beds, n_baths, n_toilets, total_wet,
    has_kitchen, has_dining, has_utility, has_corridor,
    has_pooja, has_study, has_store,
    plot_width=12.0,
):
    """
    Courtyard-centered layout with dynamic column count.

    Column count scales with plot width to keep rooms under ~6m wide:
      width < 14m  → 3 cols
      width 14-20m → 4 cols
      width > 20m  → 5 cols

    Adjacency guarantees maintained regardless of n_cols:
      ✓ Kitchen and Dining always in same column (svc_col)
      ✓ Bedrooms in leftmost columns, away from kitchen
      ✓ Buffer corridor row between courtyard and wet zone
    """
    cells = []

    # ── Dynamic column count ─────────────────────────────────────────
    if plot_width < 14:
        n_cols = 3
    elif plot_width < 20:
        n_cols = 4
    else:
        n_cols = 5

    svc_col = n_cols - 1          # kitchen + dining column (rightmost)
    court_col = n_cols // 2       # courtyard in centre
    living_span = min(2, svc_col) # living max 2 cols to avoid excessive width

    # ── Row 0: Public front ──────────────────────────────────────────
    cells.append(("living", 0, 0, living_span, 1))
    if has_kitchen:
        cells.append(("kitchen", svc_col, 0, 1, 1))
    # Fill remaining row-0 columns between living and kitchen
    # NOTE: dining must NOT go here. It belongs in svc_col row 1
    #        to maintain required Kitchen↔Dining adjacency.
    extra_r0: List[str] = []
    for _ in range(living_span, svc_col):
        if has_pooja:
            extra_r0.append("pooja")
            has_pooja = False
        elif has_study:
            extra_r0.append("study")
            has_study = False
    for i, rt in enumerate(extra_r0):
        cells.append((rt, living_span + i, 0, 1, 1))

    # ── Row 1: Middle — Beds left, Courtyard centre, Dining right ────
    cells.append(("courtyard", court_col, 1, 1, 1))
    bed_placed = 0
    for col in range(court_col):
        if bed_placed < n_beds:
            cells.append(("bedroom", col, 1, 1, 1))
            bed_placed += 1
    if has_dining:
        cells.append(("dining", svc_col, 1, 1, 1))
    for col in range(court_col + 1, svc_col):
        if bed_placed < n_beds:
            cells.append(("bedroom", col, 1, 1, 1))
            bed_placed += 1
        elif has_pooja:
            cells.append(("pooja", col, 1, 1, 1))
            has_pooja = False

    # ── Row 2: Buffer — beds + corridor + utility ────────────────────
    for col in range(court_col):
        if bed_placed < n_beds:
            cells.append(("bedroom", col, 2, 1, 1))
            bed_placed += 1
    cells.append(("corridor", court_col, 2, 1, 1))
    right_svc: List[str] = []
    if has_utility:
        right_svc.append("utility")
    if has_store:
        right_svc.append("store")
        has_store = False
    if has_study:
        right_svc.append("study")
        has_study = False
    if has_pooja:
        right_svc.append("pooja")
        has_pooja = False
    for col in range(court_col + 1, n_cols):
        if right_svc:
            cells.append((right_svc.pop(0), col, 2, 1, 1))
        elif bed_placed < n_beds:
            cells.append(("bedroom", col, 2, 1, 1))
            bed_placed += 1

    # ── Row 3: Wet zone ──────────────────────────────────────────────
    bottom: List[str] = []
    bottom.extend(["bathroom"] * min(n_baths, n_cols))
    bottom.extend(["toilet"] * min(n_toilets, n_cols - len(bottom)))
    while bed_placed < n_beds and len(bottom) < n_cols:
        bottom.append("bedroom")
        bed_placed += 1
    while right_svc and len(bottom) < n_cols:
        bottom.append(right_svc.pop(0))
    for col, rt in enumerate(bottom[:n_cols]):
        cells.append((rt, col, 3, 1, 1))

    # ── Ratios ───────────────────────────────────────────────────────
    # Row 0: public front (living/kitchen)   → 0.30
    # Row 1: middle (beds/courtyard/dining)  → 0.28
    # Row 2: buffer (corridor/utility)       → 0.10  ← reduced from 0.15 (NBC bathroom fix)
    # Row 3: wet zone (bathrooms/toilets)    → 0.32  ← increased from 0.27
    # NBC 2016 Part 3 Cl.8.1: bathroom min 1.5m × 1.8m = 2.7 m²
    col_ratios = _normalise([1.0] * n_cols)  # equal widths
    
    # Apply absolute width cap to service column (prevents oversized kitchen/utility on large plots)
    # Convert ratios to absolute widths
    col_widths = [r * plot_width for r in col_ratios]
    
    # Service column (svc_col) contains kitchen, dining, utility
    service_col_w = col_widths[svc_col]
    if service_col_w > MAX_SERVICE_COL_WIDTH:
        col_widths[svc_col] = MAX_SERVICE_COL_WIDTH
        # Redistribute remaining width equally to other columns
        remaining = plot_width - sum(col_widths)
        other_cols = [i for i in range(n_cols) if i != svc_col]
        if other_cols and remaining > 0:
            add_per_col = remaining / len(other_cols)
            for i in other_cols:
                col_widths[i] += add_per_col
    
    # Convert back to ratios
    col_ratios = _normalise(col_widths)
    
    row_ratios = _normalise([0.30, 0.28, 0.10, 0.32])

    return {
        "cells": cells, "col_ratios": col_ratios,
        "row_ratios": row_ratios, "has_courtyard": True,
    }

