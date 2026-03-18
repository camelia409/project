"""
Tamil Nadu Building Setback & Site Coverage Rules
===================================================
Source References:
  - Tamil Nadu Combined Development and Building Rules (TNCDBR) 2019
    G.O. Ms. No. 78, Housing and Urban Development Dept., 12.06.2019
  - CMDA Development Control Regulations 2022, Part II — Development Regulations
  - Tamil Nadu Town and Country Planning Act, 1971 (as amended 2019)
  - NBC 2016, Part 3 — Development Control Rules, Clause 6 (Setbacks)
  - Madurai Corporation Building Rules 2019
  - Coimbatore City Municipal Corporation Bye-laws 2020

Setback Definition:
  - Front Setback: from front property boundary (road side) to building face
  - Rear Setback:  from rear property boundary to building back face
  - Side Setback:  from side property boundary to building side face
"""

# ── Setback rules by plot area — TNCDBR 2019 ─────────────────────────────────
# Source: TNCDBR 2019, Table 1 (Cl. 4.5) — Residential buildings
TNCDBR_SETBACKS_BY_PLOT_AREA = {
    "upto_50sqm": {
        "front_m": 1.5,
        "rear_m":  1.0,
        "side_each_m": 0.0,   # no side setback for very small plots
        "applicable_zones": ["Panchayat", "Town Panchayat"],
        "note": "TNCDBR 2019, Table 1, Row 1 — plots ≤ 50 m²; front 1.5 m; no sides required",
    },
    "51_to_100sqm": {
        "front_m": 2.5,
        "rear_m":  1.5,
        "side_each_m": 1.0,
        "applicable_zones": ["Town Panchayat", "Municipality"],
        "note": "TNCDBR 2019, Table 1, Row 2 — plots 51–100 m²",
    },
    "101_to_200sqm": {
        "front_m": 3.0,
        "rear_m":  2.0,
        "side_each_m": 1.5,
        "applicable_zones": ["Municipality", "Corporation", "CMDA"],
        "note": "TNCDBR 2019, Table 1, Row 3 — most common residential category",
    },
    "201_to_500sqm": {
        "front_m": 4.5,
        "rear_m":  3.0,
        "side_each_m": 2.0,
        "applicable_zones": ["Corporation", "CMDA"],
        "note": "TNCDBR 2019, Table 1, Row 4 — medium plots",
    },
    "501_to_1000sqm": {
        "front_m": 6.0,
        "rear_m":  4.5,
        "side_each_m": 3.0,
        "applicable_zones": ["CMDA", "Special Planning Authority"],
        "note": "TNCDBR 2019, Table 1, Row 5 — large residential plots",
    },
    "above_1000sqm": {
        "front_m": 7.5,
        "rear_m":  6.0,
        "side_each_m": 4.5,
        "applicable_zones": ["CMDA", "Special Planning Authority"],
        "note": "TNCDBR 2019, Table 1, Row 6 — very large / group housing",
    },
}

# ── Road-width-based front setback (CMDA-specific) ───────────────────────────
# Source: CMDA Development Control Regulations 2022, Cl. 15
CMDA_ROAD_WIDTH_SETBACKS = {
    "road_upto_5m_wide": {
        "front_setback_m": 2.0,
        "note": "CMDA 2022, Cl. 15(a): roads ≤ 5 m → setback 2.0 m",
    },
    "road_5m_to_9m": {
        "front_setback_m": 3.0,
        "note": "CMDA 2022, Cl. 15(b): roads 5–9 m → setback 3.0 m",
    },
    "road_9m_to_12m": {
        "front_setback_m": 4.5,
        "note": "CMDA 2022, Cl. 15(c): roads 9–12 m → setback 4.5 m",
    },
    "road_12m_to_18m": {
        "front_setback_m": 6.0,
        "note": "CMDA 2022, Cl. 15(d): roads 12–18 m (arterial) → setback 6.0 m",
    },
    "road_above_18m": {
        "front_setback_m": 9.0,
        "note": "CMDA 2022, Cl. 15(e): roads > 18 m (major roads) → setback 9.0 m",
    },
}

# ── Ground coverage limits by city/authority ─────────────────────────────────
GROUND_COVERAGE_LIMITS = {
    "CMDA": {
        "residential_max_pct": 75,
        "commercial_max_pct": 80,
        "note": "CMDA DCR 2022, Cl. 20 — ground coverage for residential"
    },
    "Madurai Corporation": {
        "residential_max_pct": 70,
        "note": "Madurai Corp Bldg Rules 2019, Rule 16"
    },
    "Coimbatore Corporation": {
        "residential_max_pct": 70,
        "note": "Coimbatore Corp Bye-laws 2020, Cl. 18"
    },
    "Other Municipality": {
        "residential_max_pct": 65,
        "note": "TN Municipal Building Rules (general), Cl. 12"
    },
    "Town Panchayat": {
        "residential_max_pct": 60,
        "note": "TNCDBR 2019 default"
    },
    "Village Panchayat": {
        "residential_max_pct": 50,
        "note": "TNCDBR 2019 rural norms"
    },
}

# ── Height restrictions ───────────────────────────────────────────────────────
# Source: NBC 2016 Part 3, Cl. 6.5; TNCDBR 2019 Cl. 4.8
HEIGHT_RESTRICTIONS = {
    "G+1 (ground + 1 floor)": {
        "max_height_m": 10.5,
        "fire_noc_required": False,
        "lift_required": False,
        "note": "NBC 2016, Part 3, Cl. 6.5.1 — low-rise residential"
    },
    "G+2 (ground + 2 floors)": {
        "max_height_m": 13.5,
        "fire_noc_required": False,
        "lift_required": False,
        "note": "NBC 2016 — mid-rise; fire safety provisions apply"
    },
    "G+3 and above": {
        "max_height_m": "as approved",
        "fire_noc_required": True,
        "lift_required": True,
        "note": "NBC 2016, Part 4 — fire NOC mandatory; lift if > 4 floors"
    },
    "Near airport (Chennai)": {
        "max_height_m": "as per AAI NOC",
        "note": "Airports Authority of India restriction — varies by proximity"
    },
}

# ── Setback for specific plot orientations ────────────────────────────────────
# Corner plots (two-road-facing) get relaxation on one side setback
CORNER_PLOT_RELAXATION = {
    "description": (
        "TNCDBR 2019, Cl. 4.5 Note 2: For plots abutting two roads, "
        "the longer road side is treated as front. The secondary road side "
        "setback = 50% of standard front setback."
    ),
    "secondary_front_factor": 0.5,
}

def get_setback_for_plot(plot_area_sqm: float) -> dict:
    """
    Returns applicable TNCDBR setback rules for a given plot area.
    """
    if plot_area_sqm <= 50:
        key = "upto_50sqm"
    elif plot_area_sqm <= 100:
        key = "51_to_100sqm"
    elif plot_area_sqm <= 200:
        key = "101_to_200sqm"
    elif plot_area_sqm <= 500:
        key = "201_to_500sqm"
    elif plot_area_sqm <= 1000:
        key = "501_to_1000sqm"
    else:
        key = "above_1000sqm"
    return TNCDBR_SETBACKS_BY_PLOT_AREA[key]

def compute_usable_area(plot_w: float, plot_h: float) -> dict:
    """
    Compute usable (after setback) area and ground coverage stats.
    """
    plot_area = plot_w * plot_h
    setbacks = get_setback_for_plot(plot_area)

    front = setbacks["front_m"]
    rear  = setbacks["rear_m"]
    side  = setbacks["side_each_m"]

    usable_w = max(0.0, plot_w - 2 * side)
    usable_h = max(0.0, plot_h - front - rear)
    usable_area = usable_w * usable_h

    return {
        "plot_area_sqm": round(plot_area, 1),
        "setbacks": setbacks,
        "usable_width_m": round(usable_w, 2),
        "usable_depth_m": round(usable_h, 2),
        "max_footprint_sqm": round(usable_area, 1),
        "max_footprint_pct": round(usable_area / plot_area * 100, 1) if plot_area > 0 else 0,
        "front_setback_m": front,
        "rear_setback_m": rear,
        "side_setback_m": side,
    }
