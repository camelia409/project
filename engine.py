"""
Floor Plan Engine v5 — Agent-Integrated
- Orientation-aware layout: entry zone ALWAYS on the facing side
- Proper window assignment for ALL rooms including interior
- Generate 3 variants, return best scored one
- Laurie Baker + Tamil Nadu Climate Logic
- BHK templates redesigned for correct Kitchen–Dining edge-adjacency
- Adjacency violations deduplicated via frozenset pairs
- Integrates data modules: tn_climate_data, nbc_standards, tn_setbacks, vastu_data
- **v5**: Agent outputs drive room sizing, setbacks, Vastu placement, climate strategy
"""

import logging
import math
import random
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Set, Any

# ── Research data imports ────────────────────────────────────
try:
    from data.tn_setbacks import compute_usable_area, get_setback_for_plot
    from data.nbc_standards import check_nbc_compliance, NBC_ROOM_MINIMUMS
    from data.vastu_data import VASTU_FACING_SCORES, VASTU_ROOM_DIRECTION_SCORES
    from data.tn_climate_data import PASSIVE_STRATEGIES, COMFORT_THRESHOLDS
    _DATA_AVAILABLE = True
except ImportError:
    _DATA_AVAILABLE = False

# ── Furniture-first minimum room dimensions ───────────────────────────────
try:
    from algorithms.furniture_sizer import FURNITURE_MIN_DIMS, FURNITURE_MIN_ROW_DEPTH
    _FURNITURE_SIZER_AVAILABLE = True
except ImportError:
    _FURNITURE_SIZER_AVAILABLE = False
    FURNITURE_MIN_ROW_DEPTH = {}

# ── Ventilation strategy ──────────────────────────────────────────────────
try:
    from algorithms.ventilation_rules import (
        suggest_windows as _vent_suggest_windows,
        evaluate_plan  as _vent_evaluate_plan,
    )
    _VENT_RULES_AVAILABLE = True
except ImportError:
    _VENT_RULES_AVAILABLE = False

# ── Structural grid ───────────────────────────────────────────────────────
try:
    from algorithms.structural_grid import (
        StructuralGrid, build_grid, snap_dims_to_grid, choose_bay_counts, rotate_grid
    )
    _STRUCTURAL_GRID_AVAILABLE = True
except ImportError:
    _STRUCTURAL_GRID_AVAILABLE = False

# ── Graph-to-layout algorithm (adjacency_solver) ─────────────────────────
try:
    from algorithms.adjacency_solver import build_layout_from_adjacency_graph
    _GRAPH_LAYOUT_AVAILABLE = True
except ImportError:
    _GRAPH_LAYOUT_AVAILABLE = False

# ── Agent integration helper: extract actionable data from AgentReport ────
def _extract_agent_directives(agent_report) -> Dict[str, Any]:
    """
    Parse structured agent outputs into concrete engine directives.
    Returns a dict with keys the engine can use directly.
    """
    d: Dict[str, Any] = {
        "setbacks": None,           # {front, rear, side}
        "room_areas": {},           # room_type -> target area m2
        "vastu_placement": {},      # room_type -> preferred_direction
        "climate_strategies": [],   # list of strategy strings
        "window_rules": {},         # room_type -> [preferred sides]
        "has_courtyard": False,
        "avoid_west_bedroom": False,
        "max_ground_coverage": None,
        "agent_scores": {},         # domain -> primary score
        "special_needs_list": [],   # passed through for explanations
    }

    if agent_report is None:
        return d

    # ── Regulatory agent → setbacks + max coverage ──────────────
    reg = getattr(agent_report, "regulatory_out", None)
    if reg and reg.recommendations:
        recs = reg.recommendations
        try:
            front = float(str(recs.get("Front Setback", "1.5")).replace("m", "").strip())
            rear  = float(str(recs.get("Rear Setback",  "1.5")).replace("m", "").strip())
            side_str = str(recs.get("Side Setbacks", "1.0"))
            side  = float(side_str.split("m")[0].strip())
            d["setbacks"] = {"front": front, "rear": rear, "side": side}
        except (ValueError, IndexError):
            pass
        # Max ground coverage
        try:
            gc_str = str(recs.get("Max Ground Coverage", ""))
            if "m2" in gc_str.lower():
                d["max_ground_coverage"] = float(gc_str.split("m2")[0].strip())
        except (ValueError, IndexError):
            pass

    # ── Arch agent → room area targets (from HUDCO spatial programme) ────
    arch = getattr(agent_report, "arch_out", None)
    if arch and arch.recommendations:
        prog_str = str(arch.recommendations.get("Spatial Programme", ""))
        # Parse "Living: 14m2 | Dining: 10m2 | Kitchen: 7m2 ..."
        for part in prog_str.split("|"):
            part = part.strip()
            if ":" in part and "m2" in part.lower():
                room_name = part.split(":")[0].strip().lower()
                try:
                    area_val = float(part.split(":")[1].strip().split("m")[0].strip().rstrip("~"))
                    d["room_areas"][room_name] = area_val
                except (ValueError, IndexError):
                    pass

    # ── Climate agent → window rules + strategies ──────────────
    clim = getattr(agent_report, "climate_out", None)
    if clim:
        if clim.recommendations:
            recs = clim.recommendations
            # Window placement rules
            for key, val in recs.items():
                kl = key.lower()
                if "window" in kl or "opening" in kl:
                    if "living" in kl:
                        d["window_rules"]["living"] = _parse_directions(str(val))
                    elif "bedroom" in kl:
                        d["window_rules"]["bedroom"] = _parse_directions(str(val))
                    elif "kitchen" in kl:
                        d["window_rules"]["kitchen"] = _parse_directions(str(val))
                # Detect west-bedroom avoidance
                if "west" in str(val).lower() and "bedroom" in str(val).lower() and "avoid" in str(val).lower():
                    d["avoid_west_bedroom"] = True
                if "never" in str(val).lower() and "w" in str(val).lower() and "bedroom" in kl:
                    d["avoid_west_bedroom"] = True
            # Passive strategies
            for key, val in recs.items():
                if "strategy" in key.lower() or "ventilation" in key.lower() or "overhang" in key.lower():
                    d["climate_strategies"].append(str(val))

    # ── Vastu agent → room direction preferences ──────────────
    vastu = getattr(agent_report, "vastu_out", None)
    if vastu and vastu.recommendations:
        recs = vastu.recommendations
        for key, val in recs.items():
            kl = key.lower()
            val_s = str(val).upper()
            if "kitchen" in kl and "placement" in kl:
                d["vastu_placement"]["kitchen"] = _parse_directions(val_s)
            elif "bedroom" in kl and "placement" in kl:
                d["vastu_placement"]["bedroom"] = _parse_directions(val_s)
            elif "living" in kl and "placement" in kl:
                d["vastu_placement"]["living"] = _parse_directions(val_s)
            elif "pooja" in kl and "placement" in kl:
                d["vastu_placement"]["pooja"] = _parse_directions(val_s)

    # ── Baker agent → courtyard recommendation ──────────────
    # v8: broadened keyword matching for courtyard detection
    baker = getattr(agent_report, "baker_out", None)
    if baker and baker.recommendations:
        for key, val in baker.recommendations.items():
            if "courtyard" in key.lower():
                val_lower = str(val).lower()
                if any(kw in val_lower for kw in ("yes", "include", "recommend", "beneficial", "traditional", "muttram")):
                    d["has_courtyard"] = True

    # ── Collect primary scores for integrated scoring ──────────
    for domain, out in [("baker", baker), ("climate", clim), ("material", getattr(agent_report, "material_out", None)),
                        ("regulatory", reg), ("vastu", vastu), ("arch", arch)]:
        if out and out.scores:
            d["agent_scores"][domain] = list(out.scores.values())[0]

    return d


def _parse_directions(text: str) -> List[str]:
    """Extract cardinal directions from a text string."""
    dirs = []
    text_u = text.upper()
    for d_name in ["NE", "NW", "SE", "SW", "N", "S", "E", "W"]:
        if d_name in text_u:
            dirs.append(d_name)
    return dirs if dirs else ["S", "E"]

# ─────────────────────────────────────────────────────────────
# TAMIL NADU CLIMATE ZONES
# ─────────────────────────────────────────────────────────────
TN_CLIMATE_ZONES = {
    "Coastal (Chennai, Pondicherry, Nagapattinam)": {
        "type": "hot_humid",
        "avg_temp_c": 30,
        "humidity_pct": 80,
        "prevailing_wind": "SE",
        "solar_radiation": "high",
        "key_challenges": ["humidity", "salt_air", "cyclone_risk"],
        "baker_response": [
            "Maximize cross-ventilation with SE-facing openings",
            "Use jali screens to filter humid sea breeze",
            "Rat-trap bond walls for thermal insulation from solar gain",
            "Deep overhangs (min 900mm) to block high sun",
            "Courtyards for natural air circulation",
            "Lime plaster over brick — resists salt corrosion",
        ],
    },
    "Inland Semi-Arid (Madurai, Salem, Trichy)": {
        "type": "hot_dry",
        "avg_temp_c": 34,
        "humidity_pct": 45,
        "prevailing_wind": "SW",
        "solar_radiation": "very_high",
        "key_challenges": ["extreme_heat", "water_scarcity", "dust"],
        "baker_response": [
            "Thick rat-trap bond walls (cavity traps hot air outside)",
            "Small, high-set windows to limit solar gain yet allow hot air escape",
            "Central courtyard as evaporative cooling engine",
            "Earth-coloured lime wash to reflect solar radiation",
            "Underground water storage integrated into foundation",
            "Sloped roof with terracotta tiles for rapid rain runoff",
        ],
    },
    "Hilly (Ooty, Kodaikanal, Yercaud)": {
        "type": "temperate_cool",
        "avg_temp_c": 16,
        "humidity_pct": 70,
        "prevailing_wind": "NE",
        "solar_radiation": "moderate",
        "key_challenges": ["cold_nights", "fog", "heavy_rain"],
        "baker_response": [
            "Maximise south-facing glazing for winter solar gain",
            "Compact floor plan to minimise heat loss surface area",
            "Thick stone or brick walls for thermal mass",
            "Sloped roof (min 35°) for heavy rainfall runoff",
            "Minimal north-facing openings to block cold NE wind",
            "Verandah as thermal buffer between outside and living spaces",
        ],
    },
    "Western Ghats Wet (Coimbatore foothills, Tirunelveli)": {
        "type": "hot_humid_wet",
        "avg_temp_c": 27,
        "humidity_pct": 75,
        "prevailing_wind": "SW",
        "solar_radiation": "moderate",
        "key_challenges": ["heavy_monsoon", "flooding", "humidity"],
        "baker_response": [
            "Elevated plinth (min 600mm) to prevent flood ingress",
            "Wide roof overhangs for monsoon protection",
            "Sloped site drainage integrated into landscape design",
            "Open verandah to dry wet clothes and footwear",
            "Terracotta roof tiles shed water quickly",
            "Courtyard with drainage channel at centre",
        ],
    },
}

BAKER_PRINCIPLES = {
    "rat_trap_bond": {
        "label": "Rat-Trap Bond Brickwork",
        "description": "Bricks laid on edge creating cavity inside wall — 25% less brick, natural insulation",
        "wall_thickness_mm": 230, "thermal_resistance": 1.8, "cost_saving_pct": 25,
        "computable_rule": "wall_thickness >= 200mm AND cavity_present == True",
    },
    "jali_screens": {
        "label": "Jali / Lattice Screens",
        "description": "Perforated brick screens allow breeze, block direct sun, ensure privacy",
        "opening_ratio": 0.4, "solar_shading_factor": 0.6,
        "computable_rule": "window_facing_west OR window_facing_southwest → add jali",
    },
    "courtyard": {
        "label": "Central Courtyard",
        "description": "Open-to-sky space drives stack ventilation, provides daylight to interior rooms",
        "min_area_sqm": 9, "ventilation_multiplier": 1.4,
        "computable_rule": "plot_area > 100sqm → include courtyard of min 9sqm",
    },
    "deep_overhangs": {
        "label": "Deep Roof Overhangs",
        "description": "Minimum 600-900mm overhangs block high summer sun, allow low winter sun",
        "min_overhang_mm": 600, "optimal_overhang_mm": 900,
        "computable_rule": "overhang = (window_height * tan(latitude_angle))",
    },
    "minimal_materials": {
        "label": "Material Minimalism",
        "description": "Use local materials: Mangalore tiles, Madurai limestone, Thanjavur brick",
        "local_materials": ["country_brick", "terracotta_tile", "lime_mortar", "granite"],
        "computable_rule": "prefer local_material over imported where structural_adequacy == True",
    },
    "natural_ventilation": {
        "label": "Natural Cross-Ventilation",
        "description": "Align rooms so prevailing wind enters one face and exits opposite face",
        "min_window_area_ratio": 0.10,
        "computable_rule": "inlet_window OPPOSITE outlet_window relative to prevailing_wind_direction",
    },
}

ROOM_COLORS = {
    "living":    "#F5E6C8",
    "dining":    "#FAF0DC",
    "kitchen":   "#FFE4B5",
    "bedroom":   "#C8D8E8",
    "bathroom":  "#D4F0F0",
    "corridor":  "#E0E0E0",
    "pooja":     "#FFF0A0",
    "courtyard": "#B8DDB8",
    "store":     "#E8D4B0",
    "verandah":  "#F0E8D0",   # entry transition — warm sand
    "utility":   "#EDE8C0",
    "entrance":  "#F0D4C0",
    "study":     "#DDE8F0",   # home office / study — light blue-grey
    "lightwell": "#E8F4E8",   # ventilation shaft — pale green
}

# ─────────────────────────────────────────────────────────────
# DATA CLASSES
# ─────────────────────────────────────────────────────────────
@dataclass
class Room:
    name: str
    room_type: str
    x: float
    y: float
    width: float
    height: float
    color: str = "#FFFFFF"
    windows: List[str] = field(default_factory=list)
    door_side: str = "S"
    adjacent_to: List[str] = field(default_factory=list)
    jali_recommended: bool = False
    has_lightwell: bool = False

    @property
    def area(self) -> float:
        return round(self.width * self.height, 2)

    @property
    def aspect_ratio(self) -> float:
        mn = min(self.width, self.height)
        return 99 if mn <= 0 else max(self.width, self.height) / mn

    @property
    def cx(self): return self.x + self.width / 2
    @property
    def cy(self): return self.y + self.height / 2
    @property
    def x2(self): return self.x + self.width
    @property
    def y2(self): return self.y + self.height


@dataclass
class FloorPlan:
    rooms: List[Room]
    plot_width: float
    plot_height: float
    climate_zone: str
    bhk_type: str
    facing: str
    has_courtyard: bool = False
    courtyard: Optional[Dict] = None
    scores: Dict = field(default_factory=dict)
    baker_features: List[str] = field(default_factory=list)
    explanations: List[str] = field(default_factory=list)
    adjacency_violations: List[str] = field(default_factory=list)
    explanation_map: Dict[str, str] = field(default_factory=dict)  # room_name → rationale
    agent_integrated: bool = False  # True when agents drove the design
    shape_warnings: List[str] = field(default_factory=list)  # from _validate_and_fix_room_shapes
    structural_grid: Optional[Any] = None  # StructuralGrid — column/row line positions


# ─────────────────────────────────────────────────────────────
# ROOM SIZE LIMITS (NBC India)  min_w, max_w, min_h, max_h
# ─────────────────────────────────────────────────────────────
ROOM_SIZE_LIMITS = {
    # (min_w, max_w, min_h, max_h) — furniture-first minimums where larger than NBC.
    # min_w / min_h = max(NBC 2016 Cl.8.1, furniture-derived minimum).
    # Source: NBC 2016 Part 3 Cl. 8.1 + IS 1209 + Neufert 4e (see furniture_sizer.py).
    #
    #   bedroom:  bed(2.0×1.8m)+clearances → 3.2m wide × 3.1m deep
    #   living:   sofa(2.2m)+sides, TV viewing dist ≥ 2.5m → 2.8m × 4.45m
    #   kitchen:  galley(2×counter+aisle=2.2m), work triangle → 2.55m wide
    #   dining:   4-seat table + chair pull-out → 2.4m × 2.55m
    #   bathroom: WC+basin+shower → 1.2m × 1.8m (NBC hard-floor governs)
    "study":     (2.4,  5.0, 2.4,  5.0),   # desk(0.9m)+chair+aisle → 2.4m NBC min
    "living":    (2.8, 12.0, 4.4, 12.0),   # furniture-first: sofa+TV clearance
    "dining":    (2.4,  8.0, 2.6,  8.0),   # furniture-first: table+chair pull-out
    "bedroom":   (3.2,  6.0, 3.1,  6.0),   # furniture-first: bed+wardrobe+clearances
    "kitchen":   (2.6,  5.0, 2.4,  5.0),   # furniture-first: galley + work triangle
    "bathroom":  (1.2,  3.5, 1.8,  4.0),   # NBC 2016 Cl.8.1 governs (IS 1172)
    "toilet":    (1.2,  3.5, 1.5,  4.0),   # NBC 2016 Cl.8.1
    "corridor":  (1.2,  3.0, 1.5, 10.0),   # furniture-first: 1.2m passage (NBC §8.5.1)
    "pooja":     (1.2,  3.0, 1.2,  3.0),
    "utility":   (1.5,  4.0, 1.8,  4.5),   # washer/dryer + sink clearance
    "store":     (1.2,  3.5, 1.2,  3.5),
    "verandah":  (1.2,  5.0, 2.0,  8.0),
    "courtyard": (2.5,  8.0, 2.5,  8.0),
    "entrance":  (1.0,  3.5, 1.0,  3.5),
}

ADJACENCY_RULES = {
    # Source: JSON adjacency spec (required_adjacent only) + NBC 2016 standard.
    # JSON §dining_room  : required_adjacent = ["kitchen"]      (living is preferred, not required)
    # JSON §kitchen      : required_adjacent = ["dining_room"]  (utility is preferred, not required)
    # JSON §master_bedroom: required_adjacent = ["bathroom"]
    # NBC 2016 Part 3 Cl.3.4.1 — bedroom must have attached bathroom (modern standard)
    "dining":  ["kitchen"],   # Dining MUST be adj to Kitchen (food-service chain)
    "kitchen": ["dining"],    # Kitchen MUST be adj to Dining (bidirectional)
    "bedroom": ["bathroom"],  # Each bedroom must have adj bathroom (NBC attached-bath std)
}

# ── Forbidden adjacencies (NBC 2016 Part 8 — hygiene and safety) ──────────
# These pairs should NEVER share a wall.
# Source: NBC 2016 Part 8 Section 1 Cl. 5.1; BIS IS:1172 Code of Practice
FORBIDDEN_ADJACENCIES = [
    # ── NBC 2016 Part 8 Cl.5.1 — legally mandated separations ───────────
    ("bathroom", "kitchen",  "NBC 2016 Part 8 Cl.5.1 — hygiene violation (odour/contamination)"),
    ("toilet",   "kitchen",  "NBC 2016 Part 8 Cl.5.1 — hygiene violation"),
    ("toilet",   "dining",   "NBC 2016 Part 8 — health hazard"),
    ("bathroom", "dining",   "NBC 2016 Part 8 — undesirable (odour risk)"),
    ("toilet",   "living",   "NBC 2016 Part 8 — odour/privacy violation (JSON §living_room)"),
    # ── JSON adjacency spec — design best-practice ───────────────────────
    # JSON §bedroom  : avoid_adjacent → kitchen, parking
    ("bedroom",  "kitchen",  "Design spec §bedroom — privacy & odour separation"),
    # JSON §utility  : avoid_adjacent → living_room
    ("utility",  "living",   "Design spec §utility — service zone must not open to living"),
    # JSON §store_room: avoid_adjacent → bathroom
    ("store",    "bathroom", "Design spec §store_room — contamination risk"),
    # JSON §kitchen  : avoid_adjacent → toilet, bathroom, master_bedroom
    ("kitchen",  "bedroom",  "Design spec §kitchen — odour intrusion to private zone"),
]

# ─────────────────────────────────────────────────────────────
# ORIENTATION SYSTEM
#
# The core idea: the floor plan is always generated with
# "entry/living at South (row 0)" in canonical coordinates.
# Then the entire layout is ROTATED to match the actual facing.
#
# Facing → rotation needed to put entry on that side:
#   North  → 180° (flip: entry moves from S to N)
#   South  → 0°   (no rotation: entry stays at S)
#   East   → 90° CCW (entry moves from S to E)
#   West   → 90° CW  (entry moves from S to W)
# ─────────────────────────────────────────────────────────────

FACING_ROTATION = {
    "South":      0,    # canonical: living/entry at South = bottom
    "North":    180,    # flip 180°: living/entry at North = top
    "East":      90,    # rotate CCW 90°: entry at East = right
    "West":     270,    # rotate CW 90°: entry at West = left
    "South-East": 45,
    "South-West": 315,
    "North-East": 135,
    "North-West": 225,
}

def _rotate_rooms(rooms: List[Room], pw: float, ph: float, facing: str) -> Tuple[List[Room], float, float]:
    """
    Rotate all room coordinates by the facing angle.
    Returns (rotated_rooms, new_plot_width, new_plot_height).
    For 90/270° rotations, plot width and height are swapped.
    """
    angle = FACING_ROTATION.get(facing, 0)

    if angle == 0:
        return rooms, pw, ph

    rotated = []
    for r in rooms:
        cx = r.x + r.width / 2
        cy = r.y + r.height / 2

        if angle == 180:
            # Mirror: new_cx = pw - cx, new_cy = ph - cy
            new_cx = pw - cx
            new_cy = ph - cy
            new_w, new_h = r.width, r.height
            new_pw, new_ph = pw, ph

        elif angle == 90:  # CCW 90°: entry goes from South→East
            # (cx, cy) → (cy, pw - cx)  for CCW rotation
            # But we want entry (was at bottom/South) to appear at East (right side)
            # CCW 90°: new_x = cy, new_y = pw - cx
            # After rotation plot becomes ph wide × pw tall → we re-normalise
            new_cx = cy
            new_cy = pw - cx
            new_w, new_h = r.height, r.width
            new_pw, new_ph = ph, pw

        elif angle == 270:  # CW 90°: entry goes from South→West
            new_cx = ph - cy
            new_cy = cx
            new_w, new_h = r.height, r.width
            new_pw, new_ph = ph, pw

        elif angle == 45:
            # Diagonal: approximate — just nudge entry toward SE corner
            # Don't actually rotate (complex), just keep canonical + note in title
            return rooms, pw, ph

        else:
            return rooms, pw, ph

        nr = Room(
            name=r.name, room_type=r.room_type,
            x=round(new_cx - new_w/2, 2),
            y=round(new_cy - new_h/2, 2),
            width=round(new_w, 2), height=round(new_h, 2),
            color=r.color,
            windows=list(r.windows),
            door_side=r.door_side,
            adjacent_to=list(r.adjacent_to),
            jali_recommended=r.jali_recommended,
            has_lightwell=r.has_lightwell,
        )
        rotated.append(nr)

    return rotated, new_pw, new_ph


# ─────────────────────────────────────────────────────────────
# BHK GRID TEMPLATES  (canonical: entry/living at South=row 0)
# cell = (room_type, col, row, col_span, row_span)
# ─────────────────────────────────────────────────────────────
BHK_LAYOUTS = {
    # ═════════════════════════════════════════════════════════════════════
    # KITCHEN-DIAGONAL PRINCIPLE (all templates v4):
    #
    #   Kitchen is always placed at (col_last, row_0) — the TOP-RIGHT cell
    #   of the canonical grid. This is the SE canonical corner = traditional
    #   Agni corner in Tamil Nadu Vastu (fire/service zone).
    #
    #   Dining is directly below Kitchen at (col_last, row_1):
    #     → Kitchen(col_last, 0) adj Dining(col_last, 1) ✓ REQUIRED
    #
    #   Bedrooms occupy (col_0..col_last-1, row_1):
    #     → Kitchen(col_last, 0) vs Bedroom(col_last-1, 1):
    #       col_diff = 1, row_diff = 1 → DIAGONAL → NOT adjacent ✓ !!
    #
    #   Bathrooms occupy (col_0..col_last-1, row_2) — directly below bedrooms:
    #     → Bedroom(col_X, row_1) adj Bathroom(col_X, row_2) ✓ REQUIRED
    #     → Kitchen(col_last, 0) vs any Bathroom(col<last, row_2):
    #       row_diff ≥ 2 → NOT adjacent ✓
    #
    #   Utility occupies (col_last, row_2) — below Kitchen/Dining stack:
    #     → Dining(col_last,1) adj Utility(col_last,2) ✓ preferred
    #     → Utility(col_last,2) adj Bathroom(col_last-1,2): same row adj col,
    #       but utility↔bath is not forbidden ✓
    #
    #   RESULT: zero bedroom↔kitchen adjacency across ALL templates ✓
    #   References: NBC 2016 Part 8 Cl.5.1; JSON adjacency spec §bedroom;
    #   HUDCO Space Standards 2012; Baker 1986 (Agni SE orientation).
    # ═════════════════════════════════════════════════════════════════════

    # ── 1 BHK (2 cols × 4 rows) ──────────────────────────────────────────
    "1BHK": {
        # Combined Living+Dining — no separate dining room.
        # Rooms: Verandah (auto-inserted), Kitchen, Living, Corridor, Bedroom, Bathroom, Utility
        #
        # Col 0: habitable  |  Col 1: service (Agni/SE canonical)
        # Row 0: Living     |  Kitchen   — Kitchen at SE corner (Agni ✓)
        # Row 1: Corridor (span=2)        — separates public from private ✓
        # Row 2: Bedroom   |  Bathroom   — Bathroom same col as Kitchen (plumbing stack ✓)
        # Row 3: Utility   |  (none)     — adj Bedroom above ✓
        #
        # Wet-wall: Kitchen(1,0) ↔ Bathroom(1,2): same col, plumbing stack ✓
        # En-suite: Bedroom(0,2) ↔ Bathroom(1,2): same row adj cols ✓
        # Kitchen(1,0) ↔ Bedroom(0,2): col_diff=1, row_diff=2 → NOT adj ✓
        # Corridor provides access from living → bedroom ✓ (NBC 2016 §8.5.1 spirit)
        "cells": [
            ("living",   0, 0, 1, 1),   # public zone (living + dining area combined)
            ("kitchen",  1, 0, 1, 1),   # SE canonical corner (Agni ✓)
            ("corridor", 0, 1, 2, 1),   # spans both cols — public↔private separator ✓
            ("bedroom",  0, 2, 1, 1),   # private zone
            ("bathroom", 1, 2, 1, 1),   # adj Bedroom ✓; same col as Kitchen (plumbing ✓)
            ("utility",  0, 3, 1, 1),   # adj Bedroom above ✓
        ],
        "col_ratios": [0.52, 0.48],      # balanced: living/bed side vs kitchen/bath side
        "row_ratios": [0.32, 0.09, 0.37, 0.22],   # 4 rows
        "has_courtyard": False,
    },

    # ── 2 BHK (3 cols × 3 rows) ──────────────────────────────────────────
    "2BHK": {
        # Row 0: Living(span 2) | Kitchen(2,0)    Kitchen at SE corner (Agni ✓)
        # Row 1: Bed1(0,1) | Bed2(1,1) | Dining(2,1)
        # Row 2: Bath1(0,2) | Bath2(1,2) | Utility(2,2)
        #
        # Kitchen(2,0) ↔ Bed2(1,1): col_diff=1, row_diff=1 → DIAGONAL ✓
        # Kitchen(2,0) ↔ Bed1(0,1): col_diff=2, row_diff=1 → NOT adj ✓
        # Kitchen(2,0) ↔ any Bath: row_diff≥2 → NOT adj ✓
        # Living(0-1,0) adj Dining(2,0)? No — adj to Kitchen(2,0) only ✓
        # Dining(2,1) adj Kitchen(2,0) ✓ REQUIRED
        "cells": [
            ("living",   0, 0, 2, 1),   # public zone, spans cols 0-1
            ("kitchen",  2, 0, 1, 1),   # SE canonical corner ✓
            ("bedroom",  0, 1, 1, 1),   # Bed 1
            ("bedroom",  1, 1, 1, 1),   # Bed 2 — diagonal to Kitchen ✓
            ("dining",   2, 1, 1, 1),   # adj Kitchen above ✓ REQUIRED
            ("bathroom", 0, 2, 1, 1),   # adj Bed1 ✓ PREFERRED
            ("bathroom", 1, 2, 1, 1),   # adj Bed2 ✓ PREFERRED
            ("utility",  2, 2, 1, 1),   # adj Dining ✓ preferred
        ],
        "col_ratios": [0.32, 0.36, 0.32],
        "row_ratios": [0.30, 0.40, 0.30],
        "has_courtyard": False,
    },

    # ── 2 BHK + Pooja (3 cols × 3 rows) ─────────────────────────────────
    "2BHK + Pooja": {
        # Pooja replaces Utility at (2,2).
        # Pooja(2,2) is 2 rows below Kitchen(2,0) → NOT adj ✓
        # Pooja(2,2) adj Dining(2,1): same col adj rows — culturally OK ✓
        "cells": [
            ("living",   0, 0, 2, 1),
            ("kitchen",  2, 0, 1, 1),   # SE corner (Agni ✓)
            ("bedroom",  0, 1, 1, 1),
            ("bedroom",  1, 1, 1, 1),
            ("dining",   2, 1, 1, 1),
            ("bathroom", 0, 2, 1, 1),
            ("bathroom", 1, 2, 1, 1),
            ("pooja",    2, 2, 1, 1),   # bottom-right; Vastu: SW in canonical = good ✓
        ],
        "col_ratios": [0.32, 0.36, 0.32],
        "row_ratios": [0.30, 0.40, 0.30],
        "has_courtyard": False,
    },

    # ── 2 BHK + Office (3 cols × 4 rows) ────────────────────────────────
    "2BHK + Office": {
        # Study added as row 3. Study(span 2) adj Bed1/Bed2 via corridors ✓
        # Study preferred_adjacent to bedroom (JSON §study_room) — row 2 rows below ✓
        "cells": [
            ("living",   0, 0, 2, 1),
            ("kitchen",  2, 0, 1, 1),
            ("bedroom",  0, 1, 1, 1),
            ("bedroom",  1, 1, 1, 1),
            ("dining",   2, 1, 1, 1),
            ("bathroom", 0, 2, 1, 1),
            ("bathroom", 1, 2, 1, 1),
            ("utility",  2, 2, 1, 1),
            ("study",    0, 3, 2, 1),   # spans cols 0-1; workspace with N/E light ✓
            ("corridor", 2, 3, 1, 1),
        ],
        "col_ratios": [0.32, 0.36, 0.32],
        "row_ratios": [0.27, 0.35, 0.22, 0.16],
        "has_courtyard": False,
    },

    # ── 3 BHK (3 cols × 4 rows) ──────────────────────────────────────────
    "3BHK": {
        # 4-row layout — all 3 beds in one private row; no overflow bed row.
        # Row 0: Living+Dining(span=2) | Kitchen(2)   ← Agni SE ✓
        # Corridor: spans all 3 cols
        # Row 2: Bed1(0) | Bed2(1) | Bed3(2)          ← all 3 beds; Bed3 at service_col ✓
        # Row 3: Bath1(0) | Bath2(1) | Utility(2)     ← Bath adj beds ✓; Utility adj Kitchen ✓
        #
        # Two bathrooms: Bath1 attached Bed1; Bath2 common for Bed2+Bed3.
        # Bed3 width = col_ratio[2] × usable_w = 0.28 × 9m = 2.52m ≥ NBC 2.4m min ✓.
        # 4 rows on 8.5m usable (12×15 TNCDBR) → avg 2.1m/row — corridor fits ≥ 0.9m ✓.
        "cells": [
            ("living",   0, 0, 2, 1),   # Living+Dining combined (span=2)
            ("kitchen",  2, 0, 1, 1),
            ("corridor", 0, 1, 3, 1),   # spanning corridor ← solver will regenerate this
            ("bedroom",  0, 2, 1, 1),   # Bed 1
            ("bedroom",  1, 2, 1, 1),   # Bed 2
            ("bedroom",  2, 2, 1, 1),   # Bed 3 — service col, adjacent to Bath2 below ✓
            ("bathroom", 0, 3, 1, 1),   # Bath 1 → adj Bed1 ✓
            ("bathroom", 1, 3, 1, 1),   # Bath 2 → adj Bed2, common for Bed3 ✓
            ("utility",  2, 3, 1, 1),   # Utility → adj Kitchen above ✓
        ],
        "col_ratios": [0.34, 0.38, 0.28],   # Bed3 col=2.52m ≥ NBC 2.4m min width ✓
        "row_ratios": [0.30, 0.11, 0.34, 0.25],
        "has_courtyard": False,
    },

    # ── 3 BHK + Pooja (3 cols × 4 rows) ─────────────────────────────────
    "3BHK + Pooja": {
        # Same 4-row structure as 3BHK; Pooja replaces Utility at service_col.
        # Row 0: Living+Dining(span=2) | Kitchen(2)
        # Corridor: spans all 3 cols
        # Row 2: Bed1(0) | Bed2(1) | Bed3(2)
        # Row 3: Bath1(0) | Bath2(1) | Pooja(2)  ← pooja adj kitchen above ✓
        "cells": [
            ("living",   0, 0, 2, 1),
            ("kitchen",  2, 0, 1, 1),
            ("corridor", 0, 1, 3, 1),
            ("bedroom",  0, 2, 1, 1),   # Bed 1
            ("bedroom",  1, 2, 1, 1),   # Bed 2
            ("bedroom",  2, 2, 1, 1),   # Bed 3 — service col ✓
            ("bathroom", 0, 3, 1, 1),   # Bath 1 → adj Bed1 ✓
            ("bathroom", 1, 3, 1, 1),   # Bath 2 → common for Bed2+Bed3 ✓
            ("pooja",    2, 3, 1, 1),   # Pooja — service col, adj kitchen above ✓
        ],
        "col_ratios": [0.34, 0.38, 0.28],
        "row_ratios": [0.30, 0.11, 0.34, 0.25],
        "has_courtyard": False,
    },

    # ── 3 BHK + Office (3 cols × 5 rows) ────────────────────────────────
    "3BHK + Office": {
        # Study in row 4 spanning 2 cols — adj to Bed3 above via corridor ✓
        # Study preferred_adjacent to bedroom corridor (JSON §study_room) ✓
        "cells": [
            ("living",   0, 0, 2, 1),
            ("kitchen",  2, 0, 1, 1),
            ("bedroom",  0, 1, 1, 1),
            ("bedroom",  1, 1, 1, 1),
            ("dining",   2, 1, 1, 1),
            ("bathroom", 0, 2, 1, 1),
            ("bathroom", 1, 2, 1, 1),
            ("utility",  2, 2, 1, 1),
            ("bedroom",  0, 3, 1, 1),   # Bed 3
            ("bathroom", 1, 3, 1, 1),   # Bath 3 adj Bed3 ✓
            ("corridor", 2, 3, 1, 1),
            ("study",    0, 4, 2, 1),   # Study spans cols 0-1 adj Bed3 above ✓ PREFERRED
            ("corridor", 2, 4, 1, 1),
        ],
        "col_ratios": [0.34, 0.38, 0.28],   # v8: wider habitable cols
        "row_ratios": [0.24, 0.27, 0.18, 0.20, 0.11],
        "has_courtyard": False,
    },

    # ── 3 BHK + Courtyard (3 cols × 5 rows) ─────────────────────────────
    "3BHK + Courtyard": {
        # Traditional Tamil Nadu muttram — courtyard as ventilation engine.
        # Baker 1986: muttram reduces cooling load 18-22%, wind-stack effect ✓
        #
        # Row 0: Living(span2) | Kitchen(2,0)   Agni SE ✓
        # Row 1: Bed1 | Bed2 | Dining           Kitchen diagonal to Bed2 ✓
        # Row 2: Bath1 | Bath2 | Utility
        # Row 3: Courtyard(span2) | Bath3(2,3)  Bath3 at service col
        # Row 4: Corridor(span2) | Bed3(2,4)    Bed3 adj Bath3 above ✓
        #
        # Kitchen(2,0) ↔ Bath3(2,3): row_diff=3 → NOT adj ✓
        # Kitchen(2,0) ↔ Bed3(2,4): row_diff=4 → NOT adj ✓
        # Courtyard adj Living (row_diff=2; ventilation benefit noted in explanations)
        "cells": [
            ("living",    0, 0, 2, 1),
            ("kitchen",   2, 0, 1, 1),   # Agni SE ✓
            ("bedroom",   0, 1, 1, 1),   # Bed 1
            ("bedroom",   1, 1, 1, 1),   # Bed 2
            ("dining",    2, 1, 1, 1),
            ("bathroom",  0, 2, 1, 1),   # Bath 1 adj Bed1 ✓
            ("bathroom",  1, 2, 1, 1),   # Bath 2 adj Bed2 ✓
            ("utility",   2, 2, 1, 1),
            ("courtyard", 0, 3, 2, 1),   # Muttram — spans cols 0-1 ✓ central sky light
            ("bathroom",  2, 3, 1, 1),   # Bath 3 — service col adj Utility ✓
            ("corridor",  0, 4, 2, 1),
            ("bedroom",   2, 4, 1, 1),   # Bed 3 adj Bath3 above ✓ PREFERRED
        ],
        "col_ratios": [0.34, 0.38, 0.28],   # v8: wider habitable cols
        "row_ratios": [0.24, 0.26, 0.18, 0.18, 0.14],
        "has_courtyard": True,
    },

    # ── 4 BHK (3 cols × 6 rows) ──────────────────────────────────────────
    "4BHK": {
        # Row 0: Living(span2) | Kitchen(2,0)
        # Row 1: Bed1 | Bed2 | Dining
        # Row 2: Bath1 | Bath2 | Utility
        # Row 3: Corridor (span=3)              ← SINGLE spine corridor ✓
        # Row 4: Bed3 | Bed4 | Pooja            Kitchen NOT adj to Bed3/4 (row_diff≥4) ✓
        # Row 5: Bath3 | Bath4 | Store          Bed3 adj Bath3 ✓, Bed4 adj Bath4 ✓
        #
        # FIX: replaced two single-cell corridor fragments (2,3)+(2,4) with one
        # full-width corridor at row 3, matching TN typology (Baker 1986 spine corridor).
        "cells": [
            ("living",   0, 0, 2, 1),
            ("kitchen",  2, 0, 1, 1),
            ("bedroom",  0, 1, 1, 1),   # Bed 1
            ("bedroom",  1, 1, 1, 1),   # Bed 2
            ("dining",   2, 1, 1, 1),
            ("bathroom", 0, 2, 1, 1),   # Bath 1 adj Bed1 ✓
            ("bathroom", 1, 2, 1, 1),   # Bath 2 adj Bed2 ✓
            ("utility",  2, 2, 1, 1),
            ("corridor", 0, 3, 3, 1),   # single spine corridor — spans all 3 cols ✓
            ("bedroom",  0, 4, 1, 1),   # Bed 3
            ("bedroom",  1, 4, 1, 1),   # Bed 4
            ("pooja",    2, 4, 1, 1),   # Pooja adj Utility above (row_diff=2 — svc col) ✓
            ("bathroom", 0, 5, 1, 1),   # Bath 3 adj Bed3 ✓
            ("bathroom", 1, 5, 1, 1),   # Bath 4 adj Bed4 ✓
            ("store",    2, 5, 1, 1),   # Store adj Pooja above ✓
        ],
        "col_ratios": [0.34, 0.38, 0.28],
        "row_ratios": [0.18, 0.21, 0.13, 0.08, 0.22, 0.18],   # 6 rows
        "has_courtyard": False,
    },

    # ── 4 BHK + Pooja (3 cols × 6 rows) ─────────────────────────────────
    "4BHK + Pooja": {
        # Pooja at (2,4) — service column row 4, adj Utility(2,2) via corridor.
        # Single spine corridor at row 3. Dedicated pooja room replaces store.
        "cells": [
            ("living",   0, 0, 2, 1),
            ("kitchen",  2, 0, 1, 1),
            ("bedroom",  0, 1, 1, 1),   # Bed 1
            ("bedroom",  1, 1, 1, 1),   # Bed 2
            ("dining",   2, 1, 1, 1),
            ("bathroom", 0, 2, 1, 1),   # Bath 1 adj Bed1 ✓
            ("bathroom", 1, 2, 1, 1),   # Bath 2 adj Bed2 ✓
            ("utility",  2, 2, 1, 1),
            ("corridor", 0, 3, 3, 1),   # single spine corridor ✓
            ("bedroom",  0, 4, 1, 1),   # Bed 3
            ("bedroom",  1, 4, 1, 1),   # Bed 4
            ("pooja",    2, 4, 1, 1),   # Pooja — Vastu SW in canonical ✓
            ("bathroom", 0, 5, 1, 1),   # Bath 3 adj Bed3 ✓
            ("bathroom", 1, 5, 1, 1),   # Bath 4 adj Bed4 ✓
            ("utility",  2, 5, 1, 1),   # second utility (laundry) adj Pooja ✓
        ],
        "col_ratios": [0.34, 0.38, 0.28],
        "row_ratios": [0.18, 0.21, 0.13, 0.08, 0.22, 0.18],   # 6 rows
        "has_courtyard": False,
    },
}


# ─────────────────────────────────────────────────────────────
# AGENT-DRIVEN RATIO ADJUSTMENT
# ─────────────────────────────────────────────────────────────
def _adjust_ratios_for_targets(
    template: Dict,
    target_areas: Dict[str, float],
    usable_w: float,
    usable_h: float,
    col_ratios: List[float],
    row_ratios: List[float],
) -> Tuple[List[float], List[float]]:
    """
    Adjust grid col/row ratios so room cells approximate the target areas
    from the Arch Agent's spatial programme.

    Strategy: For each room type in the template, compute the ratio of
    (target area / current area) and nudge the relevant row/col proportionally.
    Then re-normalise so ratios still sum to 1.0.
    """
    cells = template["cells"]
    n_cols = len(col_ratios)
    n_rows = len(row_ratios)

    # Compute current cell areas
    col_w = [usable_w * r for r in col_ratios]
    row_h = [usable_h * r for r in row_ratios]

    # Accumulate desired scale factors per col and row
    col_scale = [1.0] * n_cols
    row_scale = [1.0] * n_rows
    col_count = [0] * n_cols
    row_count = [0] * n_rows

    for (rtype, col, row, cs, rs) in cells:
        if rtype not in target_areas:
            continue
        if col >= n_cols or row >= n_rows:
            continue
        current_w = sum(col_w[col:col+cs])
        current_h = sum(row_h[row:row+rs])
        current_area = current_w * current_h
        if current_area <= 0:
            continue

        target = target_areas[rtype]
        ratio = target / current_area
        # Clamp to avoid extreme distortions
        ratio = max(0.6, min(1.8, ratio))   # v8: wider clamp for stronger agent influence

        # Distribute scale factor to both dimensions (sqrt for balanced scaling)
        import math
        scale_factor = math.sqrt(ratio)
        for c in range(col, min(col+cs, n_cols)):
            col_scale[c] += scale_factor
            col_count[c] += 1
        for r in range(row, min(row+rs, n_rows)):
            row_scale[r] += scale_factor
            row_count[r] += 1

    # Average scale factors
    new_col = []
    for i in range(n_cols):
        if col_count[i] > 0:
            avg_scale = col_scale[i] / (col_count[i] + 1)  # +1 for the initial 1.0
            new_col.append(col_ratios[i] * avg_scale)
        else:
            new_col.append(col_ratios[i])

    new_row = []
    for i in range(n_rows):
        if row_count[i] > 0:
            avg_scale = row_scale[i] / (row_count[i] + 1)
            new_row.append(row_ratios[i] * avg_scale)
        else:
            new_row.append(row_ratios[i])

    # Re-normalise
    cs_sum = sum(new_col)
    rs_sum = sum(new_row)
    new_col = [c / cs_sum for c in new_col]
    new_row = [r / rs_sum for r in new_row]

    return new_col, new_row


# ─────────────────────────────────────────────────────────────
# ROOM SHAPE VALIDATION CONSTANTS  (NBC 2016 Part 3)
# ─────────────────────────────────────────────────────────────
MIN_ROOM_WIDTH   = 1.8   # NBC absolute minimum usable width (metres)
MAX_ASPECT_RATIO = 2.8   # maximum length:width ratio before room feels like a corridor


def _validate_and_fix_room_shapes(rooms: list) -> list:
    """
    Validates every room for minimum width and aspect ratio.
    Returns a list of human-readable warning strings (empty = all OK).

    Checks:
      - min(width, height) >= MIN_ROOM_WIDTH (NBC 2016 §8.1 absolute minimum)
      - max/min <= MAX_ASPECT_RATIO          (avoids corridor-like sliver rooms)

    Note: no geometry mutation is attempted here — corrective resizing
    happens upstream in STEP 0.4x clamping.  This function is diagnostic
    only so the Report tab can surface shape issues to the user.
    """
    warnings_out: list = []

    for r in rooms:
        min_dim = min(r.width, r.height)
        max_dim = max(r.width, r.height)
        ar      = max_dim / max(min_dim, 0.01)

        if min_dim < MIN_ROOM_WIDTH:
            msg = (f"NARROW: {r.name} min_dim={min_dim:.2f}m "
                   f"< {MIN_ROOM_WIDTH}m NBC minimum")
            warnings_out.append(msg)
            logging.warning("ShapeCheck: %s", msg)

        if ar > MAX_ASPECT_RATIO:
            msg = (f"ASPECT: {r.name} ratio={ar:.1f} > {MAX_ASPECT_RATIO} "
                   f"({r.width:.2f}×{r.height:.2f}m)")
            warnings_out.append(msg)
            logging.warning("ShapeCheck: %s", msg)

    return warnings_out


# ─────────────────────────────────────────────────────────────
# MAIN GENERATOR — single variant
# ─────────────────────────────────────────────────────────────
def _build_one_plan(
    plot_width_m: float,
    plot_height_m: float,
    bhk_type: str,
    climate_zone_key: str,
    facing: str,
    seed: int,
    agent_directives: Optional[Dict[str, Any]] = None,
) -> FloorPlan:
    random.seed(seed)
    climate_info = TN_CLIMATE_ZONES[climate_zone_key]
    layout_key   = bhk_type if bhk_type in BHK_LAYOUTS else "2BHK"
    _bhk_fallback = BHK_LAYOUTS[layout_key]
    _room_types   = [rtype for (rtype, *_) in _bhk_fallback["cells"]]
    if _GRAPH_LAYOUT_AVAILABLE:
        try:
            template = build_layout_from_adjacency_graph(
                _room_types,
                plot_width_m,
                plot_height_m,
                climate_zone_key,
                facing,
                agent_directives,
            )
            # Validate 1: graph must produce every room type the template requires.
            # If any type is missing (e.g. courtyard dropped, bedroom short-counted),
            # the resulting plan has overlapping or absent rooms — fall back.
            from collections import Counter as _Ctr
            _req = _Ctr(rt for (rt, *_) in _bhk_fallback["cells"])
            _got = _Ctr(rt for (rt, *_) in template["cells"])
            if any(_got.get(rt, 0) < cnt for rt, cnt in _req.items()):
                template = _bhk_fallback
            else:
                # Validate 2: no two graph cells may overlap in grid space.
                # Overlapping grid cells produce overlapping room rectangles after
                # col_widths/row_heights expansion — always fall back if found.
                _cells = template["cells"]
                _grid_ok = True
                for _i in range(len(_cells)):
                    _rt1, _c1, _r1, _cs1, _rs1 = _cells[_i]
                    for _j in range(_i + 1, len(_cells)):
                        _rt2, _c2, _r2, _cs2, _rs2 = _cells[_j]
                        _cx = min(_c1 + _cs1, _c2 + _cs2) - max(_c1, _c2)
                        _cy = min(_r1 + _rs1, _r2 + _rs2) - max(_r1, _r2)
                        if _cx > 0 and _cy > 0:
                            _grid_ok = False
                            break
                    if not _grid_ok:
                        break
                if not _grid_ok:
                    template = _bhk_fallback
        except Exception as _exc:
            import sys
            print(
                f"[engine] graph layout failed ({type(_exc).__name__}: {_exc}); "
                f"falling back to BHK_LAYOUTS[{layout_key!r}]",
                file=sys.stderr,
            )
            template = _bhk_fallback
    else:
        template = _bhk_fallback
    has_courtyard = template["has_courtyard"]

    # ── Extract CirculationPlanner metadata (may be absent in fallback templates)
    _door_hints_from_circ: Dict[str, str] = template.get("door_hints", {})
    _circ_violations:      List[str]      = template.get("circulation_violations", [])

    ad = agent_directives or {}

    # ── Agent-driven courtyard override ─────────────────────────
    # v8: also force courtyard for large plots (≥100m²) when baker agent recommends
    _pa = plot_width_m * plot_height_m
    if ad.get("has_courtyard") and not has_courtyard and _pa >= 100:
        # Upgrade to courtyard variant if available
        courtyard_key = bhk_type.split("+")[0].strip() + " + Courtyard"
        if courtyard_key in BHK_LAYOUTS:
            layout_key = courtyard_key
            template = BHK_LAYOUTS[layout_key]
            has_courtyard = True

    # ── Agent-driven setbacks (regulatory agent) ────────────────
    sb = ad.get("setbacks")
    if sb:
        margin_left  = sb["side"]
        margin_right = sb["side"]
        margin_front = sb["front"]
        margin_rear  = sb["rear"]
    else:
        # Use TNCDBR 2019 setback rules based on actual plot area
        _plot_area = plot_width_m * plot_height_m
        _tn_sb = get_setback_for_plot(_plot_area)
        margin_front = _tn_sb["front_m"]
        margin_rear  = _tn_sb["rear_m"]
        margin_left  = _tn_sb["side_each_m"]
        margin_right = _tn_sb["side_each_m"]
        # Safety: ensure enough usable space remains (at least 50% of plot)
        if (plot_width_m - margin_left - margin_right) < plot_width_m * 0.50:
            margin_left = margin_right = 0.6  # fallback for very small plots
        if (plot_height_m - margin_front - margin_rear) < plot_height_m * 0.40:
            margin_front = max(margin_front, 1.5)
            margin_rear  = max(margin_rear, 1.0)


    usable_w = plot_width_m  - margin_left - margin_right

    # v8: adaptive verandah depth by plot area — NBC 2016 min 1.2m
    _plot_area = plot_width_m * plot_height_m
    if _plot_area < 100:
        verandah_depth = 1.2   # save space on small plots
    elif _plot_area > 250:
        verandah_depth = 2.0   # generous for large plots
    else:
        verandah_depth = 1.5   # standard
    usable_h = plot_height_m - margin_front - margin_rear - verandah_depth

    # ── Agent-driven room sizing (arch agent spatial programme) ──
    col_ratios  = list(template["col_ratios"])
    row_ratios  = list(template["row_ratios"])

    target_areas = ad.get("room_areas", {})
    if target_areas:
        col_ratios, row_ratios = _adjust_ratios_for_targets(
            template, target_areas, usable_w, usable_h, col_ratios, row_ratios
        )

    col_widths  = [usable_w * r for r in col_ratios]
    row_heights = [usable_h * r for r in row_ratios]

    # ── Enforce furniture-first minimum row heights ──────────────────
    # Uses the LARGER of NBC 2016 Part 3 minimum OR furniture-derived minimum
    # (from algorithms/furniture_sizer.py — bed+clearances, sofa+TV dist, etc.)
    # With TNCDBR setbacks, usable_h can be much smaller than expected.
    _NBC_MIN_ROW_DEPTH_BASE = {
        "bedroom":  2.4,   # NBC 2016 Part 3 §8.1.2 — min dimension 2.4m
        "bathroom": 1.8,   # NBC 2016 actual minimum: 1.8m × 1.2m = 2.16m²
        "kitchen":  2.4,   # NBC 2016 §8.1.3 — work triangle clearance
        "living":   2.8,   # NBC 2016 §8.1.1 — min for furniture + circulation
        "dining":   2.4,   # NBC 2016 §8.1.1 — table + chair pull-out clearance
        "utility":  2.0,   # functional minimum for washer/dryer + sink
        "corridor": 1.2,   # furniture-first: 1.2m passage (≥ NBC §8.5.1 0.9m)
        "verandah": 1.5,   # NBC 2016 — min sitting/transition depth
        "pooja":    2.0,   # functional minimum for ritual space
        "study":    2.4,   # matches dining (desk + circulation)
    }
    # Merge with furniture-derived minimums — take the larger value
    _NBC_MIN_ROW_DEPTH = {
        rt: max(nbc_d, FURNITURE_MIN_ROW_DEPTH.get(rt, 0.0))
        for rt, nbc_d in _NBC_MIN_ROW_DEPTH_BASE.items()
    }
    _cells_list = template["cells"]
    for idx, rh in enumerate(row_heights):
        # Find all room types in this row
        row_types = [c[0] for c in _cells_list if c[2] == idx]
        if not row_types:
            continue
        needed = max(_NBC_MIN_ROW_DEPTH.get(rt, 1.0) for rt in row_types)
        if rh < needed:
            deficit = needed - rh
            # Steal from the largest row that can afford it
            # (must exceed its own minimum by ≥ 0.5m to be a valid donor)
            best_donor = -1
            best_slack = 0.0
            for di in range(len(row_heights)):
                if di == idx:
                    continue
                di_types = [c[0] for c in _cells_list if c[2] == di]
                di_min   = max((_NBC_MIN_ROW_DEPTH.get(rt, 1.0) for rt in di_types), default=0.0)
                slack    = row_heights[di] - di_min - 0.3
                if slack > best_slack:
                    best_slack = slack
                    best_donor = di
            if best_donor >= 0:
                give = min(deficit, best_slack)
                row_heights[best_donor] -= give
                row_heights[idx] += give

    # ── Build structural grid and snap dims to bay lines ─────────────
    # Grid controls architecture: all walls must lie on column-grid lines.
    # Rooms occupy whole or half bays (bay_w/2 minimum module).
    # Source: NBC 2016 Part 6 §5.3 — RCC column spacing 3.0–6.0 m;
    #         IS 456:2000; HUDCO 3.0 m module for low-cost housing.
    _sg: Optional[Any] = None
    if _STRUCTURAL_GRID_AVAILABLE:
        _n_col_bays, _n_row_bays = choose_bay_counts(
            usable_w, usable_h,
            n_template_cols=len(col_ratios),
            n_template_rows=len(row_ratios),
        )
        _y_grid_start = margin_front + verandah_depth  # grid begins above verandah
        _sg = build_grid(
            usable_w=usable_w,
            usable_h=usable_h,
            origin_x=margin_left,
            origin_y=_y_grid_start,
            n_col_bays=_n_col_bays,
            n_row_bays=_n_row_bays,
        )
        col_widths, row_heights = snap_dims_to_grid(col_widths, row_heights, _sg)

    # Small variation per seed (applied AFTER grid snap so walls stay on grid)
    def jitter(vals, rng=0.04):
        out = [v + random.uniform(-rng, rng) * sum(vals) for v in vals]
        s = sum(out)
        return [v / s for v in out]

    if seed != 42:
        col_widths  = [usable_w * r for r in jitter(col_ratios)]
        row_heights = [usable_h * r for r in jitter(row_ratios)]
        # Re-snap after jitter to keep walls on grid
        if _STRUCTURAL_GRID_AVAILABLE and _sg is not None:
            col_widths, row_heights = snap_dims_to_grid(col_widths, row_heights, _sg)

    col_x = [margin_left]
    for w in col_widths[:-1]:
        col_x.append(col_x[-1] + w)
    row_y = [margin_front + verandah_depth]  # leave room for verandah at entry edge
    for h in row_heights[:-1]:
        row_y.append(row_y[-1] + h)

    rooms: List[Room] = []
    type_counts: Dict[str, int] = {}

    for (rtype, col, row, cs, rs) in template["cells"]:
        if col >= len(col_ratios) or row >= len(row_ratios):
            continue

        rx = col_x[col]
        ry = row_y[row]
        rw = sum(col_widths[col:col + cs])
        rh = sum(row_heights[row:row + rs])

        # Snap to boundary (no gaps on edges)
        if col + cs >= len(col_ratios):
            rw = (plot_width_m - margin_right) - rx
        if row + rs >= len(row_ratios):
            rh = (plot_height_m - margin_rear) - ry

        # Do NOT enforce NBC minimums here — expanding a room beyond its grid cell
        # boundary shifts it past the adjacent room's origin, creating overlaps.
        # NBC compliance is reported separately via check_nbc_compliance().
        # BHK_LAYOUTS row/col_ratios are sized to satisfy NBC minimums by design.

        count = type_counts.get(rtype, 0)
        type_counts[rtype] = count + 1
        label = rtype.capitalize()
        if rtype in ("bedroom", "bathroom") and count > 0:
            label = f"{rtype.capitalize()} {count + 1}"
        # In 1BHK, the living room serves as combined Living + Dining
        if rtype == "living" and layout_key == "1BHK":
            label = "Living + Dining"

        rooms.append(Room(
            name=label, room_type=rtype,
            x=round(rx, 2), y=round(ry, 2),
            width=round(rw, 2), height=round(rh, 2),
            color=ROOM_COLORS.get(rtype, "#EEEEEE"),
        ))

    # ── STEP 0.4: Insert verandah (entry transition space) ───────────
    # Verandah occupies the reserved space at the entry-facing (canonical South) edge.
    has_verandah = any(r.room_type == "verandah" for r in rooms)
    if not has_verandah:
        ver_room = Room(
            name="Verandah", room_type="verandah",
            x=round(margin_left, 2),
            y=round(margin_front, 2),
            width=round(plot_width_m - margin_left - margin_right, 2),
            height=round(verandah_depth, 2),
            color=ROOM_COLORS.get("verandah", "#F0E8D0"),
            windows=["S"],  # entry-facing (canonical)
        )
        rooms.insert(0, ver_room)  # first room = entry edge

    # ── STEP 0.45: Cap individual room widths ─────────────────────────
    # On large plots, rooms can get wider than practical limits.
    # Cap widths per room type (architectural best practice).
    # NOTE: 'corridor' is intentionally absent — a spanning corridor
    # (col_span = n_cols) must keep its full plot width (e.g. 9.0 m).
    # Its width is already computed correctly via
    #   rw = sum(col_widths[col : col + cs])
    # and must NOT be post-capped here.
    MAX_ROOM_WIDTH = {
        "living": 7.0,   # wider feels like a hall, not a room
        "bedroom": 5.0,  # NBC/HUDCO comfortable bedroom width
        "bathroom": 4.0,
        "toilet": 3.0,
        "kitchen": 6.0,
        "dining": 6.0,
        "utility": 5.0,
        "pooja": 3.5,
        "study": 5.0,
        "store": 4.0,
        "corridor": 2.0,   # v8: reduced from 3.5 to prevent oversized corridors
    }
    _right_bdy = round(plot_width_m - margin_right, 3)
    for r in rooms:
        # Skip truly spanning rooms. Corridors are skipped only if they span >= 80% of plot width.
        if r.room_type in ("verandah", "courtyard", "lightwell"):
            continue
        # Spanning corridors (full usable width) must never be capped
        if r.room_type == "corridor" and r.width >= usable_w * 0.90:
            continue
            
        max_w = MAX_ROOM_WIDTH.get(r.room_type, 8.0)
        if r.width > max_w:
            _orig_x2 = r.x2          # right edge before cap
            r.width  = round(max_w, 2)
            # If this room's right edge was at the plot boundary (boundary-snapped
            # during cell placement), maintain right-edge alignment so no gap forms
            # between the room and the exterior wall after rotation.
            if abs(_orig_x2 - _right_bdy) < 0.15:
                r.x = round(_right_bdy - r.width, 3)

    # ── STEP 0.46: Close gaps from MAX_ROOM_WIDTH capping ────────────────
    # Capping a room's width without shifting its neighbour creates a gap that
    # breaks wall-sharing detection (adjacency tol = 0.35m).  Restore adjacency
    # by extending the left room rightward to meet the right room's left edge.
    _GAP_MAX = 1.5   # close gaps up to 1.5m (jitter can produce exact 1.0m gaps missed by strict <)
    skip_types = ("verandah", "courtyard", "lightwell", "corridor")
    for r1 in rooms:
        if r1.room_type in skip_types:
            continue
        for r2 in rooms:
            if r2 is r1 or r2.room_type in skip_types:
                continue
            gap = r2.x - r1.x2
            if 0.01 < gap < _GAP_MAX:
                y_overlap = min(r1.y2, r2.y2) - max(r1.y, r2.y)
                if y_overlap > 0.10:          # same row
                    r1.width = round(r1.width + gap, 3)

    # ── STEP 0.465: Hard maximum room area + dimension caps (FIX A) ──────
    # Prevents oversized rooms on large plots (bedroom=18m², living=34m², etc.).
    # When a room exceeds its area or dimension cap:
    #   1. Clamp width  to max_w  (horizontal — safe to adjust per-room)
    #   2. Clamp height to max_d  (vertical — only when room is the sole occupant
    #      of its row height, i.e. no adjacent room would lose space)
    #   3. Distribute excess width to the nearest same-row habitable neighbour.
    # Source: HUDCO 2012 space standards; NBC 2016 Part 3 §8.1 practical maximums.
    _ROOM_MAX: Dict[str, Dict] = {
        "living":   {"max_area": 20.0, "max_w": 5.0, "max_d": 4.5},
        "dining":   {"max_area": 14.0, "max_w": 4.5, "max_d": 4.0},
        "kitchen":  {"max_area": 12.0, "max_w": 4.0, "max_d": 3.5},
        "bedroom":  {"max_area": 16.0, "max_w": 4.5, "max_d": 4.0},
        "bathroom": {"max_area":  6.0, "max_w": 3.0, "max_d": 2.5},
        "utility":  {"max_area":  6.0, "max_w": 3.0, "max_d": 2.5},
        "corridor": {"max_area": 12.0,                "max_d": 1.2},
        "pooja":    {"max_area":  6.0, "max_w": 2.5, "max_d": 2.5},
        "store":    {"max_area":  5.0, "max_w": 2.5, "max_d": 2.5},
    }
    _HABITABLE = {"living", "dining", "bedroom", "study"}
    _SKIP_MAX  = {"verandah", "courtyard", "lightwell", "corridor"}

    for r in rooms:
        if r.room_type in _SKIP_MAX:
            continue
        caps = _ROOM_MAX.get(r.room_type)
        if not caps:
            continue

        max_w = caps.get("max_w", r.width)
        max_d = caps.get("max_d", r.height)

        excess_w = max(0.0, r.width  - max_w)
        excess_d = max(0.0, r.height - max_d)

        # Clamp width
        if excess_w > 0.05:
            old_x2   = r.x2
            r.width  = round(max_w, 3)
            # Maintain right-edge alignment when room was flush with plot boundary
            if abs(old_x2 - _right_bdy) < 0.15:
                r.x = round(_right_bdy - r.width, 3)

            # Distribute excess width to the nearest habitable same-row neighbour
            for nbr in rooms:
                if nbr is r or nbr.room_type not in _HABITABLE:
                    continue
                y_ov = min(r.y2, nbr.y2) - max(r.y, nbr.y)
                if y_ov < 0.3:
                    continue  # not same row
                # Neighbour immediately to the right of r
                if abs(nbr.x - r.x2) < 0.15:
                    nbr.x     = round(nbr.x - excess_w, 3)
                    nbr.width = round(nbr.width + excess_w, 3)
                    break
                # Neighbour immediately to the left of r
                if abs(r.x - nbr.x2) < 0.15:
                    nbr.width = round(nbr.width + excess_w, 3)
                    break

        # Clamp depth (height) only when safe — i.e. no other non-service room
        # shares this exact y-band, so collapsing the row won't hurt adjacency.
        if excess_d > 0.05:
            same_band = [
                o for o in rooms
                if o is not r
                and o.room_type not in _SKIP_MAX
                and abs(o.y - r.y) < 0.15
                and abs(o.height - r.height) < 0.15
            ]
            # Only clamp depth when this room is the sole tall occupant of its band
            if not same_band:
                r.height = round(max_d, 3)

    # ── STEP 0.47: Clamp rooms to plot boundaries ────────────────────
    # Safety net: jitter + gap-close may push rooms fractionally outside the
    # plot.  Hard-clamp every dimension so no room extends past exterior walls.
    _bnd_x0 = margin_left
    _bnd_x1 = round(plot_width_m  - margin_right, 3)
    _bnd_y0 = margin_front
    _bnd_y1 = round(plot_height_m - margin_rear,  3)
    for r in rooms:
        if r.room_type in ("verandah", "courtyard", "lightwell"):
            continue
        # Clamp x
        r.x = max(r.x, _bnd_x0)
        if r.x + r.width > _bnd_x1:
            r.width = round(_bnd_x1 - r.x, 3)
        # Clamp y
        r.y = max(r.y, _bnd_y0)
        if r.y + r.height > _bnd_y1:
            r.height = round(_bnd_y1 - r.y, 3)

    # ── STEP 0.48: Enforce NBC minimum room dimensions ───────────────
    # After all clamping, check rooms against NBC_ROOM_MINIMUMS and
    # expand undersized rooms within boundary limits.
    from data.nbc_standards import NBC_ROOM_MINIMUMS
    _nbc_skip = ("verandah", "courtyard", "lightwell", "corridor")
    for r in rooms:
        if r.room_type in _nbc_skip:
            continue
        nbc_mins = NBC_ROOM_MINIMUMS.get(r.room_type, {})
        min_w = nbc_mins.get("min_width_m", 0)
        min_a = nbc_mins.get("min_area_sqm") or 0

        # Expand width if below minimum (within boundary)
        if min(r.width, r.height) < min_w:
            if r.width < r.height:
                # Width is the short side
                deficit = min_w - r.width
                new_w = min(min_w, _bnd_x1 - r.x)
                r.width = round(max(r.width, new_w), 3)
            else:
                # Height is the short side
                deficit = min_w - r.height
                new_h = min(min_w, _bnd_y1 - r.y)
                r.height = round(max(r.height, new_h), 3)

        # Expand area if below minimum (grow shorter dim proportionally)
        if min_a > 0 and r.area < min_a:  # exact NBC compliance
            scale = (min_a / max(r.area, 0.1)) * 1.02  # 2% buffer for rounding
            if r.width < r.height:
                new_w = min(r.width * scale, _bnd_x1 - r.x)
                r.width = round(max(r.width, new_w), 3)
            else:
                new_h = min(r.height * scale, _bnd_y1 - r.y)
                r.height = round(max(r.height, new_h), 3)

    # ── STEP 0.49: Borrow from oversized neighbours for undersized rooms ──
    # v8: if a room is still below NBC min_area, take width from an adjacent
    # room that exceeds its own NBC minimum by ≥10%.
    for r in rooms:
        if r.room_type in _nbc_skip:
            continue
        nbc_mins = NBC_ROOM_MINIMUMS.get(r.room_type, {})
        min_a = nbc_mins.get("min_area_sqm") or 0
        if min_a <= 0 or r.area >= min_a * 0.95:
            continue  # room is fine
        # Find horizontally adjacent donor
        for other in rooms:
            if other is r or other.room_type in _nbc_skip:
                continue
            o_min_a = (NBC_ROOM_MINIMUMS.get(other.room_type, {}).get("min_area_sqm") or 0)
            if o_min_a > 0 and other.area < o_min_a * 1.10:
                continue  # other not oversized enough
            # Check horizontal adjacency (same row band)
            y_overlap = min(r.y + r.height, other.y + other.height) - max(r.y, other.y)
            if y_overlap < 0.5:
                continue
            # How much width to donate
            deficit_area = min_a - r.area
            donate = min(deficit_area / max(r.height, 0.1),
                         other.width - max(2.4, (NBC_ROOM_MINIMUMS.get(other.room_type, {}).get("min_width_m") or 1.8) + 0.3))
            if donate < 0.10:
                continue
            donate = round(donate, 3)
            if abs(other.x - (r.x + r.width)) < 0.15:
                # other is to the RIGHT of r
                r.width = round(r.width + donate, 3)
                other.x = round(other.x + donate, 3)
                other.width = round(other.width - donate, 3)
                break
            elif abs(r.x - (other.x + other.width)) < 0.15:
                # other is to the LEFT of r
                r.x = round(r.x - donate, 3)
                r.width = round(r.width + donate, 3)
                other.width = round(other.width - donate, 3)
                break

    # ── STEP 0.495: Furniture compliance check ───────────────────────
    # Flag rooms that still fall below furniture-derived minimums after all
    # NBC enforcement steps.  These are recorded as warnings (not errors) because
    # small plots may not have enough area to meet furniture minimums in all rooms.
    furniture_violations: List[str] = []
    if _FURNITURE_SIZER_AVAILABLE:
        from algorithms.furniture_sizer import check_room_against_furniture
        for r in rooms:
            if r.room_type in ("verandah", "courtyard", "lightwell", "corridor", "entrance"):
                continue
            chk = check_room_against_furniture(r.room_type, r.width, r.height)
            if not chk["ok"]:
                msg = (
                    f"{r.room_type.upper()} {r.width:.2f}×{r.height:.2f}m — "
                    f"furniture min {chk['min_width']:.2f}×{chk['min_depth']:.2f}m "
                    f"(deficit W={chk['deficit_w']:.2f}m D={chk['deficit_d']:.2f}m)"
                )
                furniture_violations.append(msg)

    # ── STEP 0.5: Insert lightwell for interior middle-column rooms ───
    # In 3-column layouts, middle-column rooms have no exterior walls.
    # NBC 2016 Part 8 §8.7: light wells (min 1.5×1.5m) provide ventilation
    # for interior rooms. We detect interior rooms and insert a lightwell.
    # SAFETY: lightwell width is reduced or skipped if it would cause any
    # adjacent room to fall below NBC minimum area.
    n_cols_in_template = len(template["col_ratios"])
    if n_cols_in_template >= 3:
        # Find rooms with no exterior walls (interior)
        tol_lw = min(margin_left, margin_right, margin_front, margin_rear) + 0.15
        interior_rooms = []
        for r in rooms:
            on_edge = (r.y <= tol_lw or
                       r.y + r.height >= plot_height_m - tol_lw or
                       r.x <= tol_lw or
                       r.x + r.width >= plot_width_m - tol_lw)
            if not on_edge and r.room_type not in ("courtyard", "lightwell"):
                interior_rooms.append(r)

        if len(interior_rooms) >= 2:
            interior_rooms.sort(key=lambda r: r.y)
            r_top = interior_rooms[0]
            r_bot = interior_rooms[1]

            # NBC minimum area for each room type (min_w × min_h)
            def _nbc_min_area(rt):
                lim = ROOM_SIZE_LIMITS.get(rt, (1.5, 8.0, 1.5, 8.0))
                return lim[0] * lim[2]  # min_w × min_h

            # Check if a given lightwell width is safe for all interior rooms
            def _lw_safe(lw_width):
                for ir in interior_rooms:
                    new_w = ir.width - lw_width
                    new_area = new_w * ir.height
                    nbc_min = _nbc_min_area(ir.room_type)
                    if new_area < nbc_min:
                        return False
                return True

            # Try 1.5m first, then 1.0m, then skip
            lw_w = 0.0
            if _lw_safe(1.5):
                lw_w = 1.5
            elif _lw_safe(1.0):
                lw_w = 1.0
            # else: lw_w stays 0 → skip lightwell

            if lw_w > 0:
                lw_h = min(lw_w, (r_top.height + r_bot.height) * 0.25)

                # Position: right edge of top interior room, straddling boundary
                lw_x = r_top.x + r_top.width - lw_w
                boundary_y = r_top.y + r_top.height
                lw_y = boundary_y - lw_h / 2

                # Shrink room widths to make space for lightwell.
                # Do NOT shrink a room whose right edge already touches an
                # exterior-wall room — shrinking would break that adjacency
                # and create a visible gap after rotation.
                # r_top example: dining flush-right against kitchen (service col)
                # r_bot example: bedroom2 flush-right against corridor (service col)
                def _has_right_nbr(room):
                    return any(
                        abs(other.x - room.x2) < 0.05
                        and other not in interior_rooms
                        and other.room_type not in ("lightwell",)
                        for other in rooms
                    )
                _rtop_has_right_nbr = _has_right_nbr(r_top)
                _rbot_has_right_nbr = _has_right_nbr(r_bot)

                if not _rtop_has_right_nbr:
                    r_top.width = round(r_top.width - lw_w, 2)
                if r_bot.x <= r_top.x + 0.3 and not _rbot_has_right_nbr:  # same column, not flush-right
                    r_bot.width = round(r_bot.width - lw_w, 2)

                # If neither room was shrunk there is no space for the lightwell
                if _rtop_has_right_nbr and _rbot_has_right_nbr:
                    lw_w = 0   # skip insertion below
                elif _rtop_has_right_nbr or _rbot_has_right_nbr:
                    # Only one room shrunk — confine lightwell to that row
                    if _rtop_has_right_nbr:
                        lw_h = min(lw_w, r_bot.height * 0.50)
                    else:
                        lw_h = min(lw_w, r_top.height * 0.50)

                # Create lightwell room (skipped if both neighbours blocked it)
                if lw_w > 0:
                    lw_room = Room(
                        name="Light Well", room_type="lightwell",
                        x=round(lw_x, 2), y=round(lw_y, 2),
                        width=round(lw_w, 2), height=round(lw_h, 2),
                        color=ROOM_COLORS.get("lightwell", "#E8F4E8"),
                        windows=["open_sky"],
                    )
                    rooms.append(lw_room)

                # Tag ALL interior rooms as having lightwell access
                for r in interior_rooms:
                    r.has_lightwell = True

    # ── STEP 1: Assign windows in CANONICAL coordinates (South=entry)
    canonical_margin = min(margin_left, margin_right, margin_front, margin_rear)
    for room in rooms:
        room.windows   = _assign_windows_canonical(room, climate_info,
                                                   plot_width_m, plot_height_m,
                                                   canonical_margin)
        room.door_side = _assign_door_side(room, plot_width_m, plot_height_m,
                                           canonical_margin,
                                           door_hints=_door_hints_from_circ)

    # ── STEP 2: Rotate layout to actual facing direction
    rooms, final_pw, final_ph = _rotate_rooms(rooms, plot_width_m, plot_height_m, facing)

    # Rotate the structural grid to match the rooms' post-rotation coordinates
    if _STRUCTURAL_GRID_AVAILABLE and _sg is not None:
        _sg = rotate_grid(_sg, facing, plot_width_m, plot_height_m)

    # ── STEP 3: After rotation, re-assign windows based on actual exterior walls
    # Use agent-driven window rules if available
    agent_win_rules = ad.get("window_rules", {})
    avoid_west_bed  = ad.get("avoid_west_bedroom", False)
    final_margin    = canonical_margin

    # Compute building footprint from actual room positions (geometry-based exterior)
    _non_special = [r for r in rooms if r.room_type not in ("verandah",)]
    _bldg_x0 = min(r.x  for r in _non_special) if _non_special else 0.0
    _bldg_y0 = min(r.y  for r in _non_special) if _non_special else 0.0
    _bldg_x1 = max(r.x2 for r in _non_special) if _non_special else final_pw
    _bldg_y1 = max(r.y2 for r in _non_special) if _non_special else final_ph

    for room in rooms:
        room.windows = _assign_windows_final(room, climate_info,
                                             final_pw, final_ph, final_margin,
                                             agent_win_rules, avoid_west_bed,
                                             bldg_bounds=(_bldg_x0, _bldg_y0,
                                                          _bldg_x1, _bldg_y1))

    # ── STEP 3b: v8 — enforce avoid_west_bedroom post-check ──────
    if avoid_west_bed:
        for room in rooms:
            if room.room_type != "bedroom":
                continue
            wins = room.windows or []
            if "W" in wins:
                if len(wins) > 1:
                    room.windows = [w for w in wins if w != "W"]
                else:
                    # Only window is W — replace with best alternative
                    for alt in ("N", "E", "S"):
                        room.windows = [alt]
                        break

    # ── Detect adjacency (must happen BEFORE door assignment)
    _compute_adjacency(rooms)

    # ── Re-assign doors using adjacency info for interior rooms
    for room in rooms:
        room.door_side = _assign_door_side(room, final_pw, final_ph,
                                           final_margin, all_rooms=rooms,
                                           door_hints=_door_hints_from_circ)

    # ── Courtyard
    courtyard_room = next((r for r in rooms if r.room_type == "courtyard"), None)
    courtyard_dict = ({"x": courtyard_room.x, "y": courtyard_room.y,
                       "w": courtyard_room.width, "h": courtyard_room.height}
                      if courtyard_room else None)
    non_ct_rooms = [r for r in rooms if r.room_type not in ("courtyard", "lightwell")]

    # ── Scores (agent-integrated)
    agent_scores = ad.get("agent_scores", {})
    scores               = _compute_scores(non_ct_rooms, final_pw, final_ph,
                                           climate_info, has_courtyard, agent_scores)
    baker_features       = _identify_baker_features(non_ct_rooms, climate_info,
                                                    has_courtyard, final_pw * final_ph)
    special_needs = (ad or {}).get("special_needs_list", [])
    explanations         = _generate_explanations(non_ct_rooms, climate_info,
                                                  climate_zone_key, baker_features, facing,
                                                  special_needs=special_needs)
    adjacency_violations = _check_adjacency_violations(non_ct_rooms)
    # Append circulation path violations (dead-ends, zig-zag, multi-corridor)
    if _circ_violations:
        adjacency_violations = adjacency_violations + [
            f"[Circulation] {v}" for v in _circ_violations
        ]
    # Append furniture-fit warnings (rooms below furniture clearance minimums)
    if furniture_violations:
        adjacency_violations = adjacency_violations + [
            f"[Furniture] {v}" for v in furniture_violations
        ]

    # Build per-room explanation map for XAI overlay
    _exp_map: Dict[str, str] = {}
    for r in non_ct_rooms:
        parts = [f"{r.area:.1f} m²"]
        if r.windows:
            parts.append(f"windows: {', '.join(r.windows)}")
        if r.jali_recommended:
            parts.append("jali recommended")
        _exp_map[r.name] = " | ".join(parts)

    # ── Shape validation (diagnostic — surfaced in Report tab)
    _shape_warnings = _validate_and_fix_room_shapes(non_ct_rooms)

    return FloorPlan(
        rooms=non_ct_rooms,
        plot_width=final_pw,
        plot_height=final_ph,
        climate_zone=climate_zone_key,
        bhk_type=bhk_type,
        facing=facing,
        has_courtyard=has_courtyard,
        courtyard=courtyard_dict,
        scores=scores,
        baker_features=baker_features,
        explanations=explanations,
        adjacency_violations=adjacency_violations,
        explanation_map=_exp_map,
        agent_integrated=bool(ad and ad.get("agent_scores")),
        shape_warnings=_shape_warnings,
        structural_grid=_sg,   # pre-rotation grid; renderer uses room edges post-rotation
    )


# ─────────────────────────────────────────────────────────────
# PUBLIC API: generate 3 variants, return best
# ─────────────────────────────────────────────────────────────
def generate_floor_plan(
    plot_width_m: float,
    plot_height_m: float,
    bhk_type: str,
    climate_zone_key: str,
    facing: str,
    seed: int = 42,
    agent_report=None,
) -> FloorPlan:
    """Generate one floor plan (used internally)."""
    ad = _extract_agent_directives(agent_report) if agent_report else None
    return _build_one_plan(plot_width_m, plot_height_m, bhk_type,
                           climate_zone_key, facing, seed,
                           agent_directives=ad)


def generate_best_floor_plan(
    plot_width_m: float,
    plot_height_m: float,
    bhk_type: str,
    climate_zone_key: str,
    facing: str,
    agent_report=None,
    special_needs: List[str] = None,
) -> Tuple[FloorPlan, List[FloorPlan]]:
    """
    Generate 3 variants with different seeds.
    Returns (best_plan, [all_3_plans]).
    Best = highest Overall score.
    Agent report (if provided) drives room sizing, setbacks, and scoring.
    special_needs list is injected into explanations and baker features.
    """
    ad = _extract_agent_directives(agent_report) if agent_report else {}
    if special_needs:
        ad["special_needs_list"] = special_needs
    seeds = [42, 137, 271]
    variants = [
        _build_one_plan(plot_width_m, plot_height_m, bhk_type,
                        climate_zone_key, facing, s,
                        agent_directives=ad if ad else None)
        for s in seeds
    ]
    best = max(variants, key=lambda p: p.scores.get("Overall", 0))
    return best, variants


# ─────────────────────────────────────────────────────────────
# WINDOW ASSIGNMENT
# ─────────────────────────────────────────────────────────────

# Map: room type → which sides are PREFERRED for windows (relative to canonical orientation)
# In canonical: South=entry/public, North=private, East=right, West=left
ROOM_WINDOW_PREFS = {
    "living":    ["S", "E", "W"],        # public face + side light
    "dining":    ["E", "S", "W"],        # morning light preferred
    "kitchen":   ["N", "E"],             # north light (cool), east morning
    "bedroom":   ["E", "N"],             # east morning light, north is cool
    "bathroom":  ["N", "E"],             # high small window, ventilation
    "pooja":     ["E"],                  # east morning sun — auspicious
    "utility":   ["N", "E"],
    "corridor":  ["N", "E", "W"],
    "store":     ["N"],
    "verandah":  ["S", "E"],
    "courtyard": [],
}

def _assign_windows_canonical(room: Room, climate: Dict,
                               pw: float, ph: float, margin: float) -> List[str]:
    """Assign windows before rotation, in canonical South=entry coordinates."""
    tol = margin + 0.15
    on = {
        "S": room.y      <= tol,
        "N": room.y2     >= ph - tol,
        "E": room.x2     >= pw - tol,
        "W": room.x      <= tol,
    }
    exterior = [side for side, is_ext in on.items() if is_ext]

    if room.room_type == "courtyard":
        return ["open_sky"]

    prefs = ROOM_WINDOW_PREFS.get(room.room_type, ["S", "E", "N", "W"])
    windows = [p for p in prefs if p in exterior]

    # Always try to give at least one window to exterior rooms
    if not windows and exterior:
        windows = [exterior[0]]

    return windows


def _assign_windows_final(room: Room, climate: Dict,
                           pw: float, ph: float, margin: float,
                           agent_win_rules: Dict[str, List[str]] = None,
                           avoid_west_bed: bool = False,
                           bldg_bounds: tuple = None) -> List[str]:
    """
    After rotation: assign windows based on actual exterior walls + climate.

    Delegates to `algorithms.ventilation_rules.suggest_windows()` which applies
    the full TN ventilation strategy:
      - Windward inlet from prevailing wind (IMD Wind Atlas 2010)
      - Cross-ventilation outlet on opposite wall (Givoni 1976, NBC §5.3)
      - West heat gain blocking/shading (IS 3792, ECBC 2017 App. D)
      - Room-type preferences (Baker 1993, CEPT 2018)
      - NBC 2016 Part 8 §5.1 minimum opening compliance

    Agent window rules and avoid-west-bedroom overrides are applied
    AFTER the base ventilation strategy as a final refinement.
    """
    wind      = climate.get("prevailing_wind", "SE")
    zone_type = climate.get("type", "hot_humid")

    # Geometry-based exterior detection: use building footprint bounds if available.
    # This correctly handles rotated plans where rooms don't start at y=0.
    # bldg_bounds = (bx0, by0, bx1, by1) — actual min/max of all room coordinates.
    _EDGE_TOL = 0.20   # room edge must be within 0.20m of building boundary
    if bldg_bounds:
        bx0, by0, bx1, by1 = bldg_bounds
        on = {
            "S": room.y  <= by0 + _EDGE_TOL,
            "N": room.y2 >= by1 - _EDGE_TOL,
            "E": room.x2 >= bx1 - _EDGE_TOL,
            "W": room.x  <= bx0 + _EDGE_TOL,
        }
    else:
        tol = margin + 0.15
        on = {
            "S": room.y  <= tol,
            "N": room.y2 >= ph - tol,
            "E": room.x2 >= pw - tol,
            "W": room.x  <= tol,
        }
    exterior = [side for side, is_ext in on.items() if is_ext]

    # ── Delegate to ventilation rules engine ──────────────────────────────────
    if _VENT_RULES_AVAILABLE:
        windows, jali = _vent_suggest_windows(
            room=room,
            room_type=room.room_type,
            exterior=exterior,
            climate_zone=zone_type,
            prevailing_wind=wind,
            pw=pw, ph=ph, margin=margin,
        )
        room.jali_recommended = jali
    else:
        # ── Fallback: inline legacy logic (unchanged) ────────────────────────
        WIND_INLET = {
            "SE": ["S", "E"], "SW": ["S", "W"],
            "NE": ["N", "E"], "NW": ["N", "W"],
            "S":  ["S"],      "N":  ["N"],
            "E":  ["E"],      "W":  ["W"],
        }
        OPPOSITE = {"S": "N", "N": "S", "E": "W", "W": "E"}
        inlets = WIND_INLET.get(wind, ["S", "E"])

        if room.room_type in ("courtyard", "lightwell"):
            return ["open_sky"]
        if not exterior:
            if room.has_lightwell:
                return ["LW"]
            cx, cy = room.cx, room.cy
            dists = {"S": cy, "N": ph - cy, "W": cx, "E": pw - cx}
            nearest = min(dists, key=dists.get)
            return [f"vent->{nearest}"]

        windows = []
        for w in inlets:
            if w in exterior:
                windows.append(w)
        for w in list(windows):
            opp = OPPOSITE.get(w)
            if opp and opp in exterior and opp not in windows:
                windows.append(opp)
        rtype = room.room_type
        if rtype == "living":
            if zone_type == "hot_humid" and "E" in exterior and "E" not in windows:
                windows.append("E")
            if "S" in exterior and "S" not in windows:
                windows.append("S")
        elif rtype == "bedroom":
            if "E" in exterior and "E" not in windows:
                windows.append("E")
            if "N" in exterior and "N" not in windows:
                windows.append("N")
        elif rtype == "kitchen":
            kitchen_pref = ["E", "N", "SE", "S"]
            assigned = any(p in windows for p in kitchen_pref)
            if not assigned:
                for pref in kitchen_pref:
                    if pref in exterior and pref not in windows:
                        windows.append(pref)
                        break
            if not any(p in windows for p in kitchen_pref):
                if "W" in exterior and zone_type in ("hot_humid", "hot_dry"):
                    windows.append("W")
                    room.jali_recommended = True
        elif rtype == "corridor":
            return ["vent->natural"]
        elif rtype == "utility":
            for pref in ["E", "N", "SE", "S"]:
                if pref in exterior and pref not in windows:
                    windows.append(pref)
                    break
        elif rtype in ("bathroom", "toilet"):
            for pref in ["N", "E", "S"]:
                if pref in exterior and pref not in windows:
                    windows.append(pref)
                    break
            if not windows and exterior:
                windows = [exterior[0]]

        # Climate W-avoidance
        if zone_type in ("hot_humid", "hot_dry"):
            if rtype == "bedroom":
                if "W" in windows and len(windows) > 1:
                    windows.remove("W")
                elif windows == ["W"]:
                    for alt in ["E", "N", "S"]:
                        if alt in exterior:
                            windows = [alt]; break
            if rtype not in ("kitchen", "bedroom"):
                if "W" in windows and len(windows) > 1:
                    windows.remove("W")
                elif "W" in windows:
                    room.jali_recommended = True

        if not windows and exterior:
            windows = [exterior[0]]
            if windows[0] in ("W", "SW") and zone_type in ("hot_humid", "hot_dry"):
                room.jali_recommended = True

        # ── Two-window minimum for major rooms (fallback path) ─────────────
        # Mirrors Step G/H from ventilation_rules.suggest_windows().
        _MAJOR_FB = ("living", "bedroom", "dining", "kitchen", "study")
        if rtype in _MAJOR_FB and len(windows) < 2 and len(exterior) >= 2:
            _SECOND_PREF = ["N", "E", "S", "W"]
            for cand in _SECOND_PREF:
                if cand in exterior and cand not in windows:
                    if cand == "W" and zone_type in ("hot_humid", "hot_dry"):
                        # Only accept W if no other non-W exterior side is free
                        if any(s in exterior and s not in windows
                               for s in ["N", "E", "S"]):
                            continue
                    windows.append(cand)
                    if cand in ("W", "SW") and zone_type in ("hot_humid", "hot_dry"):
                        room.jali_recommended = True
                    break

        # ── West-only avoidance (fallback path) ────────────────────────────
        if windows and all(w in ("W", "SW") for w in windows):
            if zone_type in ("hot_humid", "hot_dry", "composite"):
                for alt in ["N", "E", "S"]:
                    if alt in exterior:
                        windows.insert(0, alt)
                        break
                # For bedrooms drop W entirely if we added a better window
                if rtype == "bedroom" and len(windows) > 1:
                    windows = [w for w in windows if w not in ("W", "SW")]

    # ── Agent-driven window rules override (applied after both paths) ────────
    rtype = room.room_type
    if agent_win_rules and rtype in (agent_win_rules or {}):
        preferred = agent_win_rules[rtype]
        agent_windows = [p for p in preferred if p in exterior]
        if agent_windows:
            windows = agent_windows

    # ── Agent: avoid west-facing bedrooms override ───────────────────────────
    if avoid_west_bed and rtype == "bedroom":
        if "W" in windows and len(windows) > 1:
            windows.remove("W")
        if windows == ["W"]:
            for alt in ["E", "N", "S"]:
                if alt in exterior:
                    windows = [alt]
                    break

    return windows


def _assign_door_side(room: Room, pw: float, ph: float,
                      margin: float, all_rooms=None,
                      door_hints: Dict[str, str] = None) -> str:
    """
    Determine which wall gets the door.

    Priority order:
      1. CirculationPlanner door_hints (circulation-edge alignment)
      2. Exterior wall detection
      3. Adjacency-based interior door placement

    door_hints: Dict[room_type → side] from CirculationPlanner, where
    "NONE" means the room type has no door (e.g. corridor itself).
    """
    tol = margin + 0.15

    # ── Priority 1: Circulation hint (overrides geometry for interior rooms)
    if door_hints:
        hint = door_hints.get(room.room_type)
        if hint and hint != "NONE":
            # Only apply hint to interior rooms — exterior rooms keep wall door
            is_exterior = (room.y <= tol or room.y2 >= ph - tol
                           or room.x <= tol or room.x2 >= pw - tol)
            if not is_exterior:
                return hint

    # ── Priority 2: Exterior room — place door on exterior wall ──────
    if room.y      <= tol:       return "N"
    if room.y2     >= ph - tol:  return "S"
    if room.x      <= tol:       return "E"
    if room.x2     >= pw - tol:  return "W"

    # ── Priority 3: Interior room — shared wall with preferred adjacent
    if not all_rooms:
        return "S"  # fallback

    # Priority targets by room type
    DOOR_TARGETS = {
        "bathroom":  ["bedroom", "corridor", "living"],
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
    targets = DOOR_TARGETS.get(room.room_type, ["corridor", "living"])

    # Find adjacent rooms from the list
    adj_rooms = [ar for ar in all_rooms
                 if ar.name in room.adjacent_to and ar.name != room.name]

    # Sort by priority: prefer target types first, then largest overlap
    def _sort_key(ar):
        try:
            prio = targets.index(ar.room_type)
        except ValueError:
            prio = 99
        return prio

    adj_rooms.sort(key=_sort_key)

    # Find which wall the best adjacent room shares
    adj_tol = 0.25
    for target in adj_rooms:
        # Check which side target is on
        # Target is to the NORTH of room
        if abs(target.y - room.y2) < adj_tol:
            x_overlap = min(target.x2, room.x2) - max(target.x, room.x)
            if x_overlap > 0.5:
                return "N"
        # Target is to the SOUTH
        if abs(target.y2 - room.y) < adj_tol:
            x_overlap = min(target.x2, room.x2) - max(target.x, room.x)
            if x_overlap > 0.5:
                return "S"
        # Target is to the EAST
        if abs(target.x - room.x2) < adj_tol:
            y_overlap = min(target.y2, room.y2) - max(target.y, room.y)
            if y_overlap > 0.5:
                return "E"
        # Target is to the WEST
        if abs(target.x2 - room.x) < adj_tol:
            y_overlap = min(target.y2, room.y2) - max(target.y, room.y)
            if y_overlap > 0.5:
                return "W"

    return "S"  # fallback


# ─────────────────────────────────────────────────────────────
# ADJACENCY
# ─────────────────────────────────────────────────────────────
def _compute_adjacency(rooms: List[Room]):
    tol = 0.18
    for i, r1 in enumerate(rooms):
        for j, r2 in enumerate(rooms):
            if i >= j: continue
            sv = abs(r1.x2 - r2.x) < tol or abs(r2.x2 - r1.x) < tol
            yo = min(r1.y2, r2.y2) - max(r1.y, r2.y) > 0.3
            sh = abs(r1.y2 - r2.y) < tol or abs(r2.y2 - r1.y) < tol
            xo = min(r1.x2, r2.x2) - max(r1.x, r2.x) > 0.3
            if (sv and yo) or (sh and xo):
                if r2.name not in r1.adjacent_to: r1.adjacent_to.append(r2.name)
                if r1.name not in r2.adjacent_to: r2.adjacent_to.append(r1.name)


def _check_adjacency_violations(rooms: List[Room]) -> List[str]:
    """
    Check required AND forbidden adjacencies.

    Required: rooms that MUST share a wall (HUDCO, NBC).
    Forbidden: rooms that must NEVER share a wall (NBC Part 8 hygiene).

    Deduplication via frozenset so symmetric pairs are reported once.
    Source: HUDCO 2012; NBC 2016 Part 8; Hillier & Hanson 1984.
    """
    present = {r.room_type for r in rooms}
    # Build adjacency map: room_type → set of adjacent room_types
    adj_map: Dict[str, Set[str]] = {r.room_type: set() for r in rooms}
    for r in rooms:
        for aname in r.adjacent_to:
            ar = next((x for x in rooms if x.name == aname), None)
            if ar:
                adj_map[r.room_type].add(ar.room_type)

    # ── 1. Required adjacency violations (MISSING required walls) ─────────
    violation_pairs: Set[frozenset] = set()
    for rtype, reqs in ADJACENCY_RULES.items():
        if rtype not in present:
            continue
        for req in reqs:
            if req in present and req not in adj_map.get(rtype, set()):
                violation_pairs.add(frozenset([rtype, req]))

    violations = []
    for pair in violation_pairs:
        parts = sorted(pair)
        violations.append(f"⚠️ Missing: {parts[0].capitalize()} ↔ {parts[1].capitalize()} (required)")

    # ── 2. Forbidden adjacency violations (PRESENT forbidden walls) ────────
    for rtype_a, rtype_b, ref in FORBIDDEN_ADJACENCIES:
        if rtype_a in present and rtype_b in present:
            if rtype_b in adj_map.get(rtype_a, set()):
                violations.append(
                    f"🚫 Forbidden: {rtype_a.capitalize()} ↔ {rtype_b.capitalize()} ({ref})"
                )

    return sorted(violations)


# ─────────────────────────────────────────────────────────────
# SCORING
# ─────────────────────────────────────────────────────────────
def _compute_scores(rooms, pw, ph, climate, has_courtyard,
                    agent_scores: Dict[str, float] = None):
    """
    Compute 6 design scores + overall.
    When agent_scores are available, blend geometric analysis with agent intelligence
    for more accurate Climate, Baker, and NBC scores.
    """
    from algorithms.scoring import score_circulation_quality
    agent_scores = agent_scores or {}
    plot_area  = pw * ph
    room_area  = sum(r.area for r in rooms)
    efficiency = min(room_area / (plot_area * 0.72), 1.0)

    ar_scores  = [1.0 if r.aspect_ratio <= 1.6 else
                  0.7 if r.aspect_ratio <= 2.0 else
                  0.4 if r.aspect_ratio <= 2.5 else 0.1
                  for r in rooms]
    aspect = sum(ar_scores) / len(ar_scores) if ar_scores else 0

    # Ventilation: count rooms with real exterior windows (not vent→ or via corridor)
    # LW (light well) windows count at 60% — real opening but limited airflow
    vent_score = 0.0
    for r in rooms:
        if not r.windows:
            continue
        if r.windows == ["LW"]:
            vent_score += 0.6  # light well: 60% credit
        elif not r.windows[0].startswith("vent") and r.windows != ["via corridor"]:
            vent_score += 1.0  # full exterior window
    ventilation = vent_score / len(rooms) if rooms else 0

    # Cross-ventilation: rooms with 2+ real windows
    cross = sum(1 for r in rooms
                if len([w for w in r.windows
                        if not w.startswith("vent") and w != "via corridor"]) >= 2)
    cross_ratio = cross / len(rooms) if rooms else 0

    ct = climate.get("type", "hot_humid")

    # ── Climate score: per-room orientation + cross-vent + jali + courtyard ─
    n_rooms = max(len(rooms), 1)

    # (a) Room orientation correctness (40% of geo_climate)
    # Build name→type map once for courtyard-adjacency lookups inside the loop
    room_type_by_name = {r.name: r.room_type for r in rooms}

    orient_pts = 0.0
    orient_max = 0.0
    for r in rooms:
        wins = set(w for w in r.windows
                   if not w.startswith("vent") and w != "via corridor")
        rt = r.room_type

        # Service/transition rooms — excluded entirely from orientation scoring.
        # Utility, corridor, verandah, lightwell, pooja serve a functional/ritual
        # role that does not require climate-optimised window orientation
        # (NBC / Baker service-zone principle; pooja = private devotional space).
        if rt in ("corridor", "utility", "verandah", "lightwell", "pooja"):
            continue

        # Light well rooms get 70% orient credit (real daylight, better than vent→)
        if "LW" in r.windows:
            weight = 10 if rt in ("living", "bedroom", "kitchen") else 5 if rt == "dining" else 3
            orient_max += weight
            orient_pts += weight * 0.7  # 70% credit — lightwell provides real daylight
            continue

        # Interior rooms (no exterior walls) get neutral partial credit
        is_interior = not wins and any(w.startswith("vent") for w in r.windows)
        if is_interior:
            weight = 10 if rt in ("living", "bedroom", "kitchen") else 5 if rt == "dining" else 3
            orient_max += weight
            orient_pts += weight * 0.6  # 60% credit — not penalised for grid position
            continue

        # Forced-W: rotation placed this room against the W boundary only.
        # This is a layout constraint, not a design choice — penalising it fully
        # would punish North/West-facing plots regardless of their other merits.
        # Give 40% partial credit (same as jali-mitigated rooms, per Baker §3).
        # Source: NBC 2016 Part 3 Cl.8.1 — service rooms on W acceptable with screens.
        _ext_tol = 0.75  # margin(0.60) + tolerance(0.15)
        _ext = []
        if r.x  <= _ext_tol:        _ext.append("W")
        if r.x2 >= pw - _ext_tol:   _ext.append("E")
        if r.y  <= _ext_tol:        _ext.append("S")
        if r.y2 >= ph - _ext_tol:   _ext.append("N")
        forced_w = (_ext == ["W"])
        if forced_w:
            weight = 10 if rt in ("living", "bedroom", "kitchen") else 5 if rt == "dining" else 3
            orient_max += weight
            orient_pts += weight * 0.50  # 50% partial — rotation-constrained + jali-mitigated
            continue

        if ct == "hot_humid":
            if rt == "living":
                orient_max += 10
                if wins & {"E", "SE", "S"}:
                    orient_pts += 10
                elif wins & {"N"}:
                    orient_pts += 5
            elif rt == "bedroom":
                orient_max += 10
                if "W" not in wins and wins & {"E", "N"}:
                    orient_pts += 10
                elif "W" not in wins:
                    orient_pts += 6
                elif wins & {"E", "N"}:
                    orient_pts += 3
            elif rt == "kitchen":
                orient_max += 10
                if "W" not in wins and wins & {"E", "SE", "N"}:
                    orient_pts += 10
                elif "W" not in wins:
                    orient_pts += 5
            elif rt == "dining":
                # Courtyard-adjacent dining: courtyard supplies diffuse daylight
                # and stack ventilation regardless of window azimuth.
                # Credit 70% — equivalent to a lightwell room (Baker 1986 §4).
                court_adj = any(room_type_by_name.get(n) == "courtyard"
                                for n in r.adjacent_to)
                orient_max += 5
                if court_adj:
                    orient_pts += 5 * 0.70  # courtyard_adjacent: 3.5 / 5
                elif wins & {"E", "S", "N"}:
                    orient_pts += 5
                elif "W" in wins and r.jali_recommended:
                    orient_pts += 2.5  # partial credit: W with jali mitigation
            else:
                orient_max += 3
                orient_pts += 3 if wins else 0
        elif ct == "hot_dry":
            if rt == "living":
                orient_max += 10
                orient_pts += 10 if wins & {"N", "SE"} else (7 if wins & {"E"} else 0)
            elif rt == "bedroom":
                orient_max += 10
                if "W" not in wins and wins & {"N", "E"}:
                    orient_pts += 10
                elif "W" not in wins:
                    orient_pts += 6
            elif rt == "kitchen":
                orient_max += 10
                orient_pts += 10 if ("W" not in wins and wins & {"E"}) else (5 if "W" not in wins else 0)
            elif rt == "dining":
                court_adj = any(room_type_by_name.get(n) == "courtyard"
                                for n in r.adjacent_to)
                orient_max += 5 if court_adj else 3
                if court_adj:
                    orient_pts += (5 * 0.70)   # courtyard_adjacent bonus
                elif wins & {"E", "N", "S"}:
                    orient_pts += 3
                elif wins:                     # W only — no jali, no courtyard
                    orient_pts += 1.5          # half credit (hot-dry less critical than hot-humid)
            else:
                orient_max += 3
                orient_pts += 3 if wins else 0
        elif ct == "temperate_cool":
            if rt in ("living", "bedroom"):
                orient_max += 10
                orient_pts += 10 if wins & {"S", "E"} else (8 if wins & {"SE"} else 0)
            else:
                orient_max += 3
                orient_pts += 3 if wins else 0
        else:
            orient_max += 5
            orient_pts += 5 if wins else 0
    orient_ratio = orient_pts / max(orient_max, 1)

    # (b) Cross-ventilation bonus (25% of geo_climate)
    cross_bonus = min(cross_ratio * 2.0, 1.0)

    # (c) W/SW exposure penalty / jali proxy (8% of geo_climate)
    # Rooms with jali_recommended=True are mitigated — don't penalize them.
    # Utility and corridor are excluded (service rooms — orientation irrelevant).
    # Courtyard-adjacent rooms are also exempt: the courtyard provides shading
    # and stack-driven ventilation that compensates for a west window.
    if ct in ("hot_humid", "hot_dry"):
        courtyard_adj_names = {
            r.name for r in rooms
            if any(room_type_by_name.get(n) == "courtyard" for n in r.adjacent_to)
        }
        scorable = [r for r in rooms
                    if r.room_type not in ("corridor", "utility")]
        n_scorable = max(len(scorable), 1)
        w_unmitigated = sum(
            1 for r in scorable
            if ("W" in r.windows or "SW" in r.windows)
            and not r.jali_recommended
            and r.name not in courtyard_adj_names   # courtyard adjacency = mitigated
        )
        jali_score = 1.0 - (w_unmitigated / n_scorable) * 0.8
    else:
        jali_score = 0.7

    # (d) ECBC WWR compliance proxy (12% of geo_climate)
    # window_area ≈ count × 1.2m² (standard 1.2m×1.0m window)
    # wall_area ≈ perimeter × 3.0m floor height
    total_real_wins = sum(
        len([w for w in r.windows
             if w in ("N", "S", "E", "W", "NE", "NW", "SE", "SW")])
        for r in rooms
    )
    est_window_area = total_real_wins * 1.2  # m²
    total_perimeter = sum(2 * (r.width + r.height) for r in rooms)
    est_wall_area = total_perimeter * 0.4 * 3.0  # 40% exterior fraction × 3m height
    wwr = est_window_area / max(est_wall_area, 1.0)

    # ECBC targets: hot_humid 30%, hot_dry 20%, composite 25%, temperate 35%
    ecbc_target = {"hot_humid": 0.30, "hot_dry": 0.20, "temperate_cool": 0.35,
                   "hot_humid_wet": 0.25}.get(ct, 0.25)
    if 0.10 <= wwr <= ecbc_target + 0.10:
        wwr_score = 1.0  # within acceptable range
    elif wwr < 0.10:
        wwr_score = wwr / 0.10  # too few windows
    else:
        wwr_score = max(0.3, 1.0 - (wwr - ecbc_target - 0.10) * 3)

    # (e) Courtyard bonus (8% of geo_climate)
    court_score = 1.0 if has_courtyard else 0.5

    # (f) Ventilation coverage (12% of geo_climate)
    vent_cov = ventilation  # fraction of rooms with real exterior windows

    geo_climate = (orient_ratio * 0.35 +
                   cross_bonus  * 0.20 +
                   jali_score   * 0.08 +
                   wwr_score    * 0.12 +
                   court_score  * 0.08 +
                   vent_cov     * 0.17)

    # Blend: 40% geometric + 60% agent (when agent available)
    agent_climate = agent_scores.get("climate", None)
    if agent_climate is not None:
        climate_score = (0.4 * geo_climate) + (0.6 * agent_climate / 100.0)
    else:
        climate_score = geo_climate

    # ── Baker score: 6-principle geometric evaluation + agent blend ───────
    # Each principle contributes to a weighted score (sum of weights = 1.0)
    baker_pts = 0.0

    # (1) Rat-trap bond — always recommended, base credit for adoption
    baker_pts += 0.15  # assumed adopted per Baker agent recommendation

    # (2) Cross-ventilation — Baker: 'Every room must breathe'
    # Blend actual cross-vent with single-window ventilation coverage
    cross_credit = min(cross_ratio * 2.0, 1.0) * 0.5 + ventilation * 0.5
    baker_pts += cross_credit * 0.20

    # (3) Deep overhangs — applicable for hot zones
    if ct in ("hot_humid", "hot_dry", "hot_humid_wet"):
        baker_pts += 0.12  # credited when climate demands overhangs
    else:
        baker_pts += 0.06  # partial credit for other zones

    # (4) Jali screens — reward low W/SW exposure in hot zones
    if ct in ("hot_humid", "hot_dry"):
        w_west = sum(1 for r in rooms if "W" in r.windows or "SW" in r.windows)
        jali_ratio = 1.0 - (w_west / max(len(rooms), 1))
        baker_pts += jali_ratio * 0.12
    else:
        baker_pts += 0.06

    # (5) Local materials — always applicable, Baker's core principle
    baker_pts += 0.13

    # (6) Room proportions — economical aspect ratios (AR ≤ 1.8)
    well_prop = sum(1 for r in rooms
                    if max(r.width, r.height) / max(min(r.width, r.height), 0.1) <= 1.8)
    baker_pts += (well_prop / max(len(rooms), 1)) * 0.13

    # (7) Courtyard bonus
    if has_courtyard:
        baker_pts += 0.15
    else:
        baker_pts += 0.04  # small base — courtyard not always feasible

    # (8) Bedroom ventilation quality
    bedrooms = [r for r in rooms if r.room_type == "bedroom"]
    if bedrooms:
        vent_br = 0
        for b in bedrooms:
            if any(w in ("N", "S", "E", "W", "NE", "SE", "NW", "SW") for w in b.windows):
                vent_br += 1.0  # full credit: exterior window
            elif any(w.startswith("vent") for w in b.windows):
                vent_br += 0.4  # partial: ventilation shaft
        baker_pts += (vent_br / len(bedrooms)) * 0.10
    else:
        baker_pts += 0.05

    geo_baker_norm = min(baker_pts, 1.0)

    agent_baker = agent_scores.get("baker", None)
    if agent_baker is not None:
        baker_score = (0.4 * geo_baker_norm) + (0.6 * agent_baker / 100.0)
    else:
        baker_score = geo_baker_norm

    # ── NBC score: per-room area + width compliance ────────────────────────
    # Uses NBC_ROOM_MINIMUMS from nbc_standards.py for accurate per-room check
    from data.nbc_standards import check_nbc_compliance as _nbc_check
    nbc_total = 0.0
    nbc_count = 0
    for r in rooms:
        # Use effective room type (second bedrooms have different min)
        rt_key = r.room_type
        if r.room_type == "bedroom" and "2" in r.name or "3" in r.name:
            rt_key = "bedroom_second"
        result = _nbc_check(rt_key, r.area, min(r.width, r.height))
        nbc_count += 1
        if result["compliant"]:
            nbc_total += 1.0
        else:
            # Partial credit: area OK but width short → 0.5
            if result.get("area_ok", True) and not result.get("width_ok", True):
                nbc_total += 0.5
            # Width OK but area short → 0.3 (more serious)
            elif result.get("width_ok", True) and not result.get("area_ok", True):
                nbc_total += 0.3
            # Both fail → 0
    geo_nbc = nbc_total / max(nbc_count, 1)

    agent_regulatory = agent_scores.get("regulatory", None)
    if agent_regulatory is not None:
        nbc_score = (0.5 * geo_nbc) + (0.5 * agent_regulatory / 100.0)
    else:
        nbc_score = geo_nbc


    # ── Vastu bonus when agent scores it ───────────────────────────────────
    vastu_bonus = 0.0
    agent_vastu = agent_scores.get("vastu", None)
    if agent_vastu is not None:
        vastu_bonus = agent_vastu / 100.0 * 0.05  # up to 5% bonus

    # ── Spanning corridor bonus (+3% overall) ──────────────────────────────
    # A spanning corridor (width >= 60% of plot or >= 7m) earns a bonus
    # because it properly separates public/private zones - Tamil Nadu pattern.
    corridor_rooms = [r for r in rooms if r.room_type == "corridor"]
    corridor_bonus = 0.0
    corridor_type = "none"
    if corridor_rooms:
        best_corr = max(corridor_rooms, key=lambda c: c.width)
        is_spanning = best_corr.width >= pw * 0.6 or best_corr.width >= 7.0
        passage_dim = min(best_corr.width, best_corr.height)
        if is_spanning and passage_dim >= 0.9:
            corridor_bonus = 0.03  # +3% bonus for spanning corridor
            corridor_type = "spanning"
        elif passage_dim >= 1.0:
            corridor_bonus = 0.01  # +1% for adequate corridor
            corridor_type = "adequate"
        else:
            corridor_type = "narrow"

    # ── NBC corridor width compliance ──────────────────────────────────────
    # NBC 2016 Part 3 §8.5.1: residential corridor min clear width = 0.9m
    # Penalise nbc_score if corridor passage dimension < 0.9m
    if corridor_rooms:
        best_corr = max(corridor_rooms, key=lambda c: c.width)
        passage_dim = min(best_corr.width, best_corr.height)
        if passage_dim < 0.9:
            nbc_score = max(0.0, nbc_score - 0.10)  # -10% penalty

    overall = (efficiency * 0.15 + aspect * 0.12 + ventilation * 0.18 +
               climate_score * 0.22 + baker_score * 0.13 + nbc_score * 0.15 +
               vastu_bonus + corridor_bonus) * 100
    overall = min(100.0, overall)

    circ_score = score_circulation_quality(rooms, pw, ph)

    return {
        "Space Efficiency":       round(efficiency * 100, 1),
        "Aspect Ratio Quality":   round(aspect * 100, 1),
        "Natural Ventilation":    round(ventilation * 100, 1),
        "Climate Responsiveness": round(climate_score * 100, 1),
        "Baker Compliance":       round(baker_score * 100, 1),
        "NBC Compliance":         round(nbc_score * 100, 1),
        "Circulation Quality":    round(circ_score, 1),
        "Corridor Type":          corridor_type,
        "Overall":                round(overall, 1),
    }


def _identify_baker_features(rooms, climate, has_courtyard, plot_area):
    features = []
    real_win_rooms = [r for r in rooms
                      if r.windows and not r.windows[0].startswith("vent")]
    cross = sum(1 for r in real_win_rooms
                if len([w for w in r.windows
                        if not w.startswith("vent")]) >= 2)
    n = len(rooms)
    if cross >= n * 0.4:
        features.append(f"✅ Cross-ventilation: {cross}/{n} rooms have inlet + outlet windows")
    if has_courtyard and plot_area >= 100:
        features.append("✅ Central courtyard for stack ventilation and natural daylight")
    features.append("✅ Rat-trap bond walls — saves 25% brick, thermal R-value 1.8")
    features.append("✅ Deep overhangs (900mm) on South and West facades")
    if climate.get("type") in ("hot_humid", "hot_dry"):
        features.append("✅ Jali screens on West-facing windows filter afternoon heat")
    features.append("✅ Local materials: Country brick · Mangalore tile roof · Lime mortar")
    features.append("✅ 600mm setback on all sides — boundary wall-free (Baker's rule)")
    return features


def _generate_explanations(rooms, climate_info, zone_key, baker_features, facing,
                            special_needs: List[str] = None):
    expl = []
    zone_short = zone_key.split("(")[0].strip()
    expl.append(
        f"📍 Zone: {zone_short} — {climate_info['type'].replace('_',' ').title()} "
        f"| {climate_info['avg_temp_c']}°C avg | {climate_info['humidity_pct']}% humidity"
    )
    expl.append(
        f"🌬️ Wind: {climate_info['prevailing_wind']} prevailing — "
        f"windows oriented to maximise cross-ventilation"
    )
    expl.append(
        f"🧭 Facing: {facing} — public zone (living/entry) placed at {facing} boundary. "
        f"Private zone (bedrooms) on opposite side."
    )
    for rule in climate_info["baker_response"][:3]:
        expl.append(f"🏛️ {rule}")
    for br in [r for r in rooms if r.room_type == "bedroom"]:
        win_str = ", ".join(w for w in br.windows if not w.startswith("vent")) or "interior (via corridor)"
        nbc = "✅ NBC ≥9.5m²" if br.area >= 9.5 else "⚠️ Below NBC min"
        expl.append(f"🛏️ {br.name}: {br.area:.1f} m² | windows [{win_str}] | {nbc}")

    # ── Special requirements ──────────────────────────────────────────────
    needs = special_needs or []
    if "car_parking" in needs:
        expl.append("🚗 Parking: Car parking space (min 2.7m × 5.0m) required at front setback area. "
                    "Locate adjacent to entry/gate per TNCDBR 2019 driveway rules.")
    if "accessibility_ground_floor" in needs or "elderly_accessibility" in needs:
        expl.append("♿ Accessibility: All habitable rooms on ground floor. "
                    "Doorways ≥900mm clear width (IS:11226). "
                    "No thresholds in circulation path. Grab bars in bathrooms (NBC Part 12).")
    if "home_office" in needs:
        expl.append("💼 Home Office/Study: Natural light from North or East orientation. "
                    "Separate from bedroom zone for acoustic isolation.")
    if "garden_terrace" in needs:
        expl.append("🌿 Garden/Terrace: Courtyard or rear garden integrated in layout. "
                    "Baker 1986: muttram (central open space) enhances ventilation 1.4× and "
                    "reduces cooling load by 18–22%.")

    return expl