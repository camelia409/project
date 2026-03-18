"""
Design Decision Tree — Maps input combinations to concrete design parameters
=============================================================================
Translates user inputs (facing, soil, occupancy, budget, climate) into
derived architectural decisions used by the engine and renderer.

Sources:
  - IS 1904:1986 (Foundation design by soil type)
  - NBC 2016 Part 4 Cl. 4.4.3 (Exit widths)
  - ECBC 2017 (Solar orientation strategies)
  - COSTFORD 1986 (Baker material selection)
"""

from data.vastu_data import VASTU_FACING_SCORES
from data.tn_climate_data import SUN_ANGLES, PASSIVE_STRATEGIES, WIND_ROSE


# ── Soil → Foundation mapping (IS 1904:1986) ─────────────────────────────────

SOIL_FOUNDATION = {
    "Black Cotton": {
        "foundation_type": "Raft / Pile",
        "depth_m": 1.5,
        "bearing_capacity_kpa": 50,
        "note": "IS 1904 Cl. 7.2 — expansive soil; under-reamed piles or raft mandatory",
        "cost_factor": 1.4,
    },
    "Sandy": {
        "foundation_type": "Strip Foundation",
        "depth_m": 1.0,
        "bearing_capacity_kpa": 100,
        "note": "IS 1904 Cl. 6.3 — granular soil; strip footing adequate for G+1",
        "cost_factor": 1.0,
    },
    "Laterite": {
        "foundation_type": "Spread Footing",
        "depth_m": 0.9,
        "bearing_capacity_kpa": 150,
        "note": "IS 1904 Cl. 6.5 — laterite/murrum; spread footing with rubble masonry",
        "cost_factor": 0.9,
    },
    "Red/Alluvial": {
        "foundation_type": "Strip Foundation",
        "depth_m": 0.8,
        "bearing_capacity_kpa": 120,
        "note": "IS 1904 Cl. 6.3 — alluvial soil; standard strip with PCC bed",
        "cost_factor": 0.95,
    },
    "Rocky": {
        "foundation_type": "Shallow Footing",
        "depth_m": 0.6,
        "bearing_capacity_kpa": 300,
        "note": "IS 1904 Cl. 6.1 — rock bed; shallow footing sufficient",
        "cost_factor": 0.8,
    },
}


# ── Budget → Material strategy ───────────────────────────────────────────────

BUDGET_MATERIALS = {
    "Economy": {
        "wall_material": "Rat-trap bond brick (230mm)",
        "wall_finish": "Exposed brick / lime wash",
        "window_type": "Jali lattice + timber frame",
        "roofing": "Mangalore tile on timber truss",
        "flooring": "Athangudi tile / oxide finish",
        "plinth": "Rubble masonry",
        "baker_level": "Full Baker",
        "cost_per_sqft": "Rs. 1,200–1,500",
        "note": "COSTFORD 1986 — 30-42% saving vs conventional RCC",
    },
    "Standard": {
        "wall_material": "Rat-trap bond brick (230mm)",
        "wall_finish": "Cement plaster + emulsion paint",
        "window_type": "UPVC / timber with glass",
        "roofing": "RCC slab + Mangalore tile (hybrid)",
        "flooring": "Vitrified tile",
        "plinth": "RCC plinth beam",
        "baker_level": "Partial Baker",
        "cost_per_sqft": "Rs. 1,800–2,200",
        "note": "Rat-trap bond retained for thermal benefit; conventional finish",
    },
    "Premium": {
        "wall_material": "AAC block / RCC frame + brick infill",
        "wall_finish": "Texture paint / stone cladding",
        "window_type": "Aluminium / uPVC with DGU glass",
        "roofing": "RCC flat slab + waterproofing + insulation",
        "flooring": "Italian marble / engineered wood",
        "plinth": "RCC with damp-proof course",
        "baker_level": "Minimal Baker",
        "cost_per_sqft": "Rs. 2,800–3,500",
        "note": "Conventional construction; Baker principles advisory only",
    },
}


# ── Facing → Solar/Overhang strategy ────────────────────────────────────────

def _solar_strategy(facing: str, climate_zone: str) -> dict:
    """Derive solar orientation strategy from facing + climate."""
    # Which walls get maximum/minimum glazing
    _avoid_glazing = {"North": "S", "South": "N", "East": "W", "West": "E",
                      "North-East": "SW", "North-West": "SE",
                      "South-East": "NW", "South-West": "NE"}

    _preferred_glazing = {"North": "N", "South": "S", "East": "E", "West": "W",
                          "North-East": "NE", "North-West": "NW",
                          "South-East": "SE", "South-West": "SW"}

    # Overhang sides (always on sun-exposed faces)
    overhang_sides = []
    if climate_zone in ("hot_humid", "hot_dry", "composite"):
        overhang_sides = ["W", "S", "SW"]
    elif climate_zone == "temperate":
        overhang_sides = ["W"]  # minimal overhangs in temperate

    # Prevailing wind for ventilation
    wind_dir = "SE"  # default
    for station, data in WIND_ROSE.items():
        if climate_zone in str(data):
            break

    vastu_score = VASTU_FACING_SCORES.get(facing, {}).get("score", 50)

    return {
        "preferred_glazing_wall": _preferred_glazing.get(facing, "N"),
        "avoid_glazing_wall": _avoid_glazing.get(facing, "W"),
        "overhang_sides": overhang_sides,
        "vastu_facing_score": vastu_score,
        "ventilation_inlet": wind_dir,
    }


# ── Main decision tree ───────────────────────────────────────────────────────

def compute_design_decisions(facing: str, soil_type: str, occupancy: int,
                              budget: str, climate_zone: str,
                              plot_area: float) -> dict:
    """
    Master decision tree: maps all input combinations to design parameters.

    Parameters
    ----------
    facing : str — "North", "South", "East", "West", etc.
    soil_type : str — key from SOIL_FOUNDATION
    occupancy : int — number of persons
    budget : str — "Economy", "Standard", "Premium"
    climate_zone : str — "hot_humid", "hot_dry", "composite", "temperate"
    plot_area : float — in m²

    Returns
    -------
    dict with all derived design parameters
    """
    # Foundation
    foundation = SOIL_FOUNDATION.get(soil_type, SOIL_FOUNDATION["Red/Alluvial"])

    # Exit requirements (NBC Part 4 Cl. 4.4.3)
    if occupancy <= 24:
        exit_door_w, corridor_w = 1.0, 1.0
    elif occupancy <= 50:
        exit_door_w, corridor_w = 1.2, 1.2
    else:
        exit_door_w, corridor_w = 1.5, 1.5

    # Materials from budget
    materials = BUDGET_MATERIALS.get(budget, BUDGET_MATERIALS["Standard"])

    # Solar strategy
    solar = _solar_strategy(facing, climate_zone)

    # Passive strategies from climate
    passive = PASSIVE_STRATEGIES.get(climate_zone, {})

    return {
        # Foundation
        "foundation_type": foundation["foundation_type"],
        "foundation_depth_m": foundation["depth_m"],
        "bearing_capacity_kpa": foundation["bearing_capacity_kpa"],
        "foundation_note": foundation["note"],
        "foundation_cost_factor": foundation["cost_factor"],

        # Exit / circulation
        "exit_door_width_m": exit_door_w,
        "corridor_width_m": corridor_w,
        "occupancy": occupancy,

        # Materials
        "wall_material": materials["wall_material"],
        "wall_finish": materials["wall_finish"],
        "window_type": materials["window_type"],
        "roofing": materials["roofing"],
        "flooring": materials["flooring"],
        "baker_level": materials["baker_level"],
        "cost_per_sqft": materials["cost_per_sqft"],
        "material_note": materials["note"],

        # Solar / orientation
        "preferred_glazing_wall": solar["preferred_glazing_wall"],
        "avoid_glazing_wall": solar["avoid_glazing_wall"],
        "overhang_sides": solar["overhang_sides"],
        "vastu_facing_score": solar["vastu_facing_score"],
        "ventilation_inlet": solar["ventilation_inlet"],

        # Passive strategies (from climate data)
        "passive_primary": passive.get("primary", []),
        "passive_secondary": passive.get("secondary", []),
        "wall_u_target": passive.get("wall_u_value_target", "N/A"),
        "roof_u_target": passive.get("roof_u_value_target", "N/A"),
        "wwr_max": passive.get("window_to_wall_ratio", "N/A"),
    }
