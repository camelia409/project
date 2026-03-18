"""
furniture_sizer.py — Furniture-first minimum room dimension calculator
=======================================================================
Room sizes are derived from the minimum footprint needed to fit required
furniture WITH proper circulation clearances, not from area-first allocation.

Sources:
  - IS 1209 : 1978 (Furniture dimensions for Indian households)
  - NBC 2016 Part 3 §8 (minimum room dimensions)
  - HUDCO 2012 (space standards for EWS/LIG/MIG housing)
  - Neufert Architects' Data 4e (furniture clearance standards)

Usage:
  from algorithms.furniture_sizer import FURNITURE_MIN_DIMS, compute_min_room_dims

  min_w, min_d = compute_min_room_dims("bedroom")
  min_w, min_d = compute_min_room_dims("living")
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional

# ─── Furniture piece dimensions (metres) ────────────────────────────────────
# Format: (width_m, depth_m)  — "depth" = dimension perpendicular to the wall

FURNITURE_PIECES: Dict[str, Dict[str, Tuple[float, float]]] = {
    "bedroom": {
        # Queen-size bed (IS 1209: 1900×1520mm → rounded to 2.0×1.8m incl. frame)
        "bed":           (2.00, 1.80),
        # Wardrobe — 3-door sliding (IS 7088: 1200mm wide, 600mm deep min)
        "wardrobe":      (1.20, 0.60),
        # Side table (bedside)
        "sidetable":     (0.50, 0.45),
    },
    "living": {
        # 3-seater sofa (IS 1209: 1800–2200mm long, 850mm deep)
        "sofa_3s":       (2.20, 0.90),
        # Coffee table
        "coffee_table":  (1.10, 0.55),
        # TV unit / media cabinet
        "tv_unit":       (1.40, 0.45),
    },
    "kitchen": {
        # Base counter (standard depth: 600mm)
        "counter":       (0.60, 0.60),  # per linear metre
        # Refrigerator (typical Indian 250L–350L: 600×650mm)
        "refrigerator":  (0.60, 0.65),
    },
    "dining": {
        # 4-seater dining table (1200×900mm)
        "table_4":       (1.20, 0.90),
        # Dining chair (seat width 450mm, pulled-out depth 700mm)
        "chair":         (0.45, 0.70),
    },
    "bathroom": {
        # WC pan (IS 2556: 700×370mm; with cistern+space = 750×500mm)
        "wc":            (0.75, 0.50),
        # Wash basin (IS 2548: 550×430mm; with plumbing = 600×500mm)
        "washbasin":     (0.60, 0.50),
        # Shower enclosure (minimum 900×900mm)
        "shower":        (0.90, 0.90),
    },
}

# ─── Clearance standards (metres) ────────────────────────────────────────────
# Source: Neufert 4e + NBC 2016 Part 3 + Indian ergonomic practice

CLEARANCES = {
    # Bedroom
    "bed_side_primary":   0.60,   # one side of bed (dressing + making bed)
    "bed_side_secondary": 0.45,   # wall side / secondary side (minimum access)
    "bed_foot":           0.90,   # end of bed to wardrobe / wall
    "wardrobe_door":      0.60,   # swing clearance in front of wardrobe doors

    # Living
    "sofa_back":          0.60,   # sofa back to wall (circulation aisle)
    "sofa_side":          0.30,   # sofa end to side wall
    "tv_min_distance":    3.00,   # min distance from TV face to sofa back
                                  # (approx 1.5× screen diagonal for 40"–55" TV)
    "tv_unit_depth":      0.45,   # TV cabinet / wall unit depth
    "coffee_table_gap":   0.45,   # sofa edge to coffee table

    # Kitchen
    "work_aisle":         1.00,   # clear aisle between facing counters (NBC §8.1.3)
    "counter_depth":      0.60,   # standard counter depth (base cabinet + worktop)
    "single_counter":     0.60,   # single-wall counter depth

    # Dining
    "chair_pullout":      0.60,   # space behind chair when pulled out
    "aisle_behind_chair": 0.45,   # passage behind pushed-in chairs (tight)

    # Bathroom
    "wc_front":           0.60,   # clearance in front of WC (NBC IS 1172)
    "wc_side":            0.20,   # side clearance beside WC
    "basin_front":        0.70,   # clearance in front of washbasin
    "shower_front":       0.60,   # clearance to exit shower
}


# ─── Derive minimum room dimensions from furniture layout ────────────────────

@dataclass
class FurnitureLayout:
    """Minimum room dimensions derived from a specific furniture arrangement."""
    room_type:   str
    min_width:   float   # metres (short dimension of the room)
    min_depth:   float   # metres (long dimension, perpendicular to entry wall)
    rationale:   str
    pieces:      List[str] = field(default_factory=list)


def _bedroom_layout(n_occupants: int = 2) -> FurnitureLayout:
    """
    Derive minimum bedroom dimensions for a double-occupancy room.

    Arrangement:
      - Bed centred against the head wall
      - Wardrobe on the side or opposite wall
      - Entry door on the foot wall

    Width calculation:
      sidetable + bed_side_primary_clearance + bed + bed_side_secondary_clearance
      = 0.50 + 0.60 + 2.00 + 0.45 = 3.55 → vs wardrobe+door = 1.20+0.60 = 1.80
      → width = max(3.55, 1.80) → rounded to 3.2m with walls

    Depth calculation:
      wardrobe_depth + wardrobe_door_clearance + bed_foot_clearance + bed_width
      = 0.60 + 0.60 + 0.90 + 1.80 = 3.90 → practical: 3.2m (wardrobe alongside)

    Practical layout (wardrobe on side wall, bed against head wall):
      - depth = bed_width + bed_foot_clearance + door_swing = 1.80 + 0.90 + 0.30 = 3.0m
      - width = bed_length + 2×bed_side_clearances + margin = 2.00+0.60+0.45+0.15 = 3.2m
    """
    c = CLEARANCES
    fp = FURNITURE_PIECES["bedroom"]

    bed_w, bed_d = fp["bed"]           # 2.00 × 1.80
    war_w, war_d = fp["wardrobe"]      # 1.20 × 0.60

    # Width: bed length + side clearances (both sides)
    width_from_bed = (c["bed_side_primary"] + bed_w + c["bed_side_secondary"])
    # Wardrobe + opening clearance — fits alongside or on end wall
    width_from_wardrobe = war_w + c["wardrobe_door"]

    min_width = max(width_from_bed, width_from_wardrobe)
    min_width = round(min_width + 0.15, 2)   # 0.15m wall/margin tolerance

    # Depth: bed width + foot clearance + door swing buffer
    min_depth = bed_d + c["bed_foot"] + 0.30   # 1.80 + 0.90 + 0.30 = 3.00m
    min_depth = round(min_depth + 0.10, 2)      # wall tolerance

    return FurnitureLayout(
        room_type="bedroom",
        min_width=min_width,
        min_depth=min_depth,
        rationale=(
            f"Bed({bed_w}×{bed_d}m) + side clearances({c['bed_side_primary']}/"
            f"{c['bed_side_secondary']}m) + foot({c['bed_foot']}m) + "
            f"wardrobe({war_w}×{war_d}m) + door clearance({c['wardrobe_door']}m)"
        ),
        pieces=["bed", "wardrobe", "sidetable"],
    )


def _living_layout() -> FurnitureLayout:
    """
    Derive minimum living room dimensions.

    Arrangement:
      - Sofa against the wall opposite the TV
      - TV unit on the far wall
      - Min viewing distance (sofa back to TV face) ≥ 3.0m

    Width: sofa length + side clearances = 2.20 + 0.30 + 0.30 = 2.80m → 3.0m with walls
    Depth: sofa_depth + circulation behind sofa + viewing_distance + tv_unit_depth
         = 0.90 + 0.60 + 3.00 + 0.45 = 4.95m → practical 3.8m

    Practical: The 3.0m TV viewing distance counts from sofa BACK, but sofa back
    is 0.60m from wall → effective room depth = sofa_back_wall + sofa_depth +
    viewing_dist + tv_unit_depth = 0.60 + 0.90 + 3.00 + 0.45 = 4.95m.

    For Indian MIG housing, acceptable viewing distances start at 2.5m (32" TV).
    We use 2.5m as practical minimum.
    """
    c = CLEARANCES
    fp = FURNITURE_PIECES["living"]

    sofa_w, sofa_d = fp["sofa_3s"]      # 2.20 × 0.90
    tv_d           = c["tv_unit_depth"]  # 0.45

    min_width = sofa_w + 2 * c["sofa_side"] + 0.20  # walls
    min_width = round(min_width, 2)

    # Practical minimum: 2.5m viewing distance (32"–40" TV)
    effective_view_dist = 2.50
    min_depth = (c["sofa_back"] + sofa_d + effective_view_dist + tv_d + 0.10)
    min_depth = round(min_depth, 2)

    return FurnitureLayout(
        room_type="living",
        min_width=min_width,
        min_depth=min_depth,
        rationale=(
            f"Sofa({sofa_w}×{sofa_d}m) + back clearance({c['sofa_back']}m) + "
            f"TV viewing distance({effective_view_dist}m) + "
            f"TV unit depth({tv_d}m)"
        ),
        pieces=["sofa_3s", "coffee_table", "tv_unit"],
    )


def _kitchen_layout() -> FurnitureLayout:
    """
    Derive minimum kitchen dimensions.

    Arrangement: parallel counter (galley kitchen) or L-shape.
    - Parallel: two counters 0.60m deep, work aisle ≥ 1.0m between them
      → depth = 0.60 + 1.00 + 0.60 = 2.20m; width for work triangle ≥ 2.4m
    - L-shape (preferred): one counter along length + short counter perpendicular
      → Width = counter_depth + aisle + wall = 0.60 + 1.00 + 0.15 = 1.75m
      → Depth = minimum for sink-hob-fridge triangle = 2.4m

    NBC 2016 §8.1.3 mandates 2.4m minimum. Furniture-derived is 2.2m parallel,
    so NBC governs for depth. Width: 2.4m for triangle reach.
    """
    c = CLEARANCES

    # Galley / parallel kitchen (most space-efficient)
    min_width_galley = 2 * c["counter_depth"] + c["work_aisle"]  # 0.60+1.00+0.60=2.20
    # Work triangle minimum width (sink to hob distance ≥ 1.2m, hob to fridge ≥ 1.2m)
    min_width_triangle = 2.40

    min_width = round(max(min_width_galley, min_width_triangle) + 0.15, 2)
    min_depth = 2.40   # NBC 2016 §8.1.3 governs (matches furniture layout)

    return FurnitureLayout(
        room_type="kitchen",
        min_width=min_width,
        min_depth=min_depth,
        rationale=(
            f"Galley: 2×counter({c['counter_depth']}m) + work aisle({c['work_aisle']}m) "
            f"= {min_width_galley:.2f}m; work triangle min = {min_width_triangle}m"
        ),
        pieces=["counter", "refrigerator"],
    )


def _dining_layout(seats: int = 4) -> FurnitureLayout:
    """
    Derive minimum dining room dimensions for a 4-seater (default).

    Table: 1200×900mm (4-seater), with chairs pulled out on both long sides.
    Width = table_width + 2×chair_pullout = 1.20 + 2×0.60 = 2.40m
    Depth = table_depth + 2×chair_pullout = 0.90 + 2×0.60 = 2.10m
    With passage aisle (one side): add 0.45m → depth = 2.55m
    """
    c = CLEARANCES
    fp = FURNITURE_PIECES["dining"]

    t_w, t_d = fp["table_4"]   # 1.20 × 0.90

    min_width = t_w + 2 * c["chair_pullout"] + 0.20   # both long sides + walls
    min_depth = t_d + 2 * c["chair_pullout"] + c["aisle_behind_chair"]
    min_width = round(min_width, 2)
    min_depth = round(min_depth, 2)

    return FurnitureLayout(
        room_type="dining",
        min_width=min_width,
        min_depth=min_depth,
        rationale=(
            f"Table({t_w}×{t_d}m) + chair pull-out({c['chair_pullout']}m) "
            f"on both long sides + passage aisle"
        ),
        pieces=["table_4", "chair"],
    )


def _bathroom_layout() -> FurnitureLayout:
    """
    Derive minimum bathroom dimensions.

    Arrangement (linear): door on short side, WC at far end, basin + shower.
    Width = max(WC width + side_clearance×2, shower width) = max(0.75+0.40, 0.90) = 1.15m
    Depth = basin_depth + basin_front_clearance + shower_depth + threshold =
            0.50 + 0.70 + 0.90 + 0.30 = 2.40m (exceeds NBC min of 1.8m)

    Practical minimum (wet-dry combined):
    Width  = 1.20m (NBC IS 1172 minimum: 1.2m × 1.8m)
    Depth  = 1.80m (NBC minimum; with shower 2.10m is standard)
    """
    c = CLEARANCES
    fp = FURNITURE_PIECES["bathroom"]

    wc_w, wc_d     = fp["wc"]
    basin_w, bas_d = fp["washbasin"]
    sh_w, sh_d     = fp["shower"]

    # Width: WC + side clearances
    width_from_wc = wc_w + 2 * c["wc_side"] + 0.15
    # Or shower width (0.90m)
    min_width = max(width_from_wc, sh_w + 0.15)
    min_width = round(max(min_width, 1.20), 2)   # NBC hard floor

    # Depth: basin + clearance + (shower or WC in line)
    min_depth = bas_d + c["basin_front"] + wc_d + c["wc_front"]
    min_depth = round(max(min_depth, 1.80), 2)   # NBC hard floor

    return FurnitureLayout(
        room_type="bathroom",
        min_width=min_width,
        min_depth=min_depth,
        rationale=(
            f"WC({wc_w}×{wc_d}m) + basin({basin_w}×{bas_d}m) + "
            f"shower({sh_w}×{sh_d}m); NBC IS 1172 hard-floor 1.2×1.8m"
        ),
        pieces=["wc", "washbasin", "shower"],
    )


# ─── Master minimum dimensions table ────────────────────────────────────────

def _build_furniture_min_dims() -> Dict[str, Tuple[float, float]]:
    """
    Build the canonical furniture-derived minimum (width, depth) table.
    'width' = shorter plan dimension; 'depth' = longer plan dimension.
    These are the MINIMUMS — actual rooms will typically be larger.
    """
    bed   = _bedroom_layout()
    liv   = _living_layout()
    kit   = _kitchen_layout()
    din   = _dining_layout()
    bath  = _bathroom_layout()

    return {
        "bedroom":   (bed.min_width,  bed.min_depth),   # ≈ (3.20, 3.10)
        "living":    (liv.min_width,  liv.min_depth),   # ≈ (2.80, 4.45)
        "kitchen":   (kit.min_width,  kit.min_depth),   # ≈ (2.55, 2.40)
        "dining":    (din.min_width,  din.min_depth),   # ≈ (2.40, 2.55)
        "bathroom":  (bath.min_width, bath.min_depth),  # ≈ (1.20, 1.80)
        # Remaining types: use NBC-only values (no furniture fit needed)
        "toilet":    (1.20, 1.50),
        "corridor":  (1.20, 1.50),
        "utility":   (1.50, 1.80),
        "verandah":  (1.20, 1.50),
        "pooja":     (1.20, 1.20),
        "study":     (2.40, 2.40),
        "store":     (1.20, 1.20),
        "courtyard": (2.50, 2.50),
        "office":    (2.40, 2.40),
    }


# Singleton — computed once at module load
FURNITURE_MIN_DIMS: Dict[str, Tuple[float, float]] = _build_furniture_min_dims()

# Convenience: minimum ROW DEPTH (the dimension a row must have to
# accommodate the deepest room it contains).  Used by engine.py.
FURNITURE_MIN_ROW_DEPTH: Dict[str, float] = {
    rt: max(w, d) for rt, (w, d) in FURNITURE_MIN_DIMS.items()
}


def compute_min_room_dims(
    room_type: str,
    n_occupants: int = 2,
    seats: int = 4,
) -> Tuple[float, float]:
    """
    Return (min_width_m, min_depth_m) for *room_type*, derived from the
    minimum footprint required to fit the room's standard furniture with
    proper circulation clearances.

    Parameters
    ----------
    room_type   : str  — one of bedroom, living, kitchen, dining, bathroom, …
    n_occupants : int  — number of bedroom occupants (default 2 = double room)
    seats       : int  — dining seats (default 4)

    Returns
    -------
    (min_width, min_depth) in metres
    """
    if room_type == "bedroom":
        layout = _bedroom_layout(n_occupants)
        return layout.min_width, layout.min_depth
    if room_type == "living":
        layout = _living_layout()
        return layout.min_width, layout.min_depth
    if room_type == "kitchen":
        layout = _kitchen_layout()
        return layout.min_width, layout.min_depth
    if room_type == "dining":
        layout = _dining_layout(seats)
        return layout.min_width, layout.min_depth
    if room_type == "bathroom":
        layout = _bathroom_layout()
        return layout.min_width, layout.min_depth

    # Fall back to table lookup for all other types
    return FURNITURE_MIN_DIMS.get(room_type, (1.2, 1.2))


def get_furniture_layout_details(room_type: str) -> Optional[FurnitureLayout]:
    """Return the detailed FurnitureLayout object for a given room type."""
    _builders = {
        "bedroom":  lambda: _bedroom_layout(),
        "living":   _living_layout,
        "kitchen":  _kitchen_layout,
        "dining":   _dining_layout,
        "bathroom": _bathroom_layout,
    }
    builder = _builders.get(room_type)
    return builder() if builder else None


# ─── Validation helper ───────────────────────────────────────────────────────

def check_room_against_furniture(
    room_type: str,
    actual_width: float,
    actual_depth: float,
) -> Dict:
    """
    Check whether an actual room dimension satisfies furniture-derived minimums.

    Returns a dict with:
      ok        — bool, True if both dimensions meet minimum
      min_width — required minimum width
      min_depth — required minimum depth
      deficit_w — shortfall in width (0 if ok)
      deficit_d — shortfall in depth (0 if ok)
    """
    min_w, min_d = compute_min_room_dims(room_type)
    # The room's short dim maps to min_width; long dim maps to min_depth
    short = min(actual_width, actual_depth)
    long_  = max(actual_width, actual_depth)
    return {
        "ok":        short >= min_w and long_ >= min_d,
        "min_width": min_w,
        "min_depth": min_d,
        "deficit_w": round(max(0.0, min_w - short), 3),
        "deficit_d": round(max(0.0, min_d - long_), 3),
    }
