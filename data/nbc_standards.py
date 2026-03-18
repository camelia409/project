"""
National Building Code of India 2016 — Residential Standards
=============================================================
Source References:
  - National Building Code of India 2016, Volume 1 & 2
    Bureau of Indian Standards (BIS), New Delhi
    IS: SP 7 (Part 3) — Group 1: Lighting & Ventilation
    IS: SP 7 (Part 4) — Group 1: Fire & Life Safety
  - Tamil Nadu Combined Development and Building Rules (TNCDBR) 2019
  - CMDA Development Control Regulations 2022 (Chennai Metropolitan Area)
  - Tamil Nadu District Municipalities Act, 1920 (as amended)
  - Ministry of Housing and Urban Affairs, Model Building Bye-laws 2016

Key NBC Sections Referenced:
  Part 3: Development Control Rules and General Building Requirements
  Part 8 Section 1: Lighting and Ventilation
  Part 4: Fire and Life Safety
"""

# ── Minimum room dimensions — NBC Part 3, Clause 8.1 ──────────────────────────
# All areas in square metres, dimensions in metres
NBC_ROOM_MINIMUMS = {
    "living": {
        "min_area_sqm": 12.0,
        "min_width_m": 3.0,
        "nbc_clause": "NBC 2016, Part 3, Cl. 8.1.1",
        "description": "Habitable room (living/drawing) — minimum area 12.0 m², width 3.0 m"
    },
    "bedroom": {
        "min_area_sqm": 9.5,
        "min_width_m": 2.4,
        "nbc_clause": "NBC 2016, Part 3, Cl. 8.1.2",
        "description": "Principal bedroom ≥ 9.5 m²; second bedroom ≥ 7.5 m²; min width 2.4 m"
    },
    "bedroom_second": {
        "min_area_sqm": 7.5,
        "min_width_m": 2.4,
        "nbc_clause": "NBC 2016, Part 3, Cl. 8.1.2",
        "description": "Secondary bedroom — minimum area 7.5 m²"
    },
    "kitchen": {
        "min_area_sqm": 5.0,
        "min_width_m": 1.8,
        "nbc_clause": "NBC 2016, Part 3, Cl. 8.1.3",
        "description": "Kitchen ≥ 5.0 m²; width ≥ 1.8 m; cooking alcove ≥ 2.5 m²"
    },
    "bathroom": {
        "min_area_sqm": 2.8,
        "min_width_m": 1.2,
        "nbc_clause": "NBC 2016, Part 3, Cl. 8.1.4",
        "description": "Bathroom (combined WC) ≥ 2.8 m²; separate WC ≥ 1.1 m²"
    },
    "toilet": {
        "min_area_sqm": 1.1,
        "min_width_m": 0.9,
        "nbc_clause": "NBC 2016, Part 3, Cl. 8.1.4",
        "description": "Separate WC/toilet — minimum 1.1 m²"
    },
    "corridor": {
        "min_width_m": 1.0,
        "min_area_sqm": None,
        "nbc_clause": "NBC 2016, Part 3, Cl. 8.1.6",
        "description": "Internal passage/corridor — minimum width 1.0 m"
    },
    "staircase": {
        "min_width_m": 1.0,
        "min_tread_mm": 250,
        "max_riser_mm": 190,
        "nbc_clause": "NBC 2016, Part 4, Cl. 4.3",
        "description": "Internal stairs: width ≥ 1.0 m; tread ≥ 250 mm; riser ≤ 190 mm"
    },
    "pooja": {
        "min_area_sqm": 1.5,
        "min_width_m": 1.0,
        "nbc_clause": "TNCDBR 2019, Cl. 4.12",
        "description": "Prayer/pooja room — no NBC minimum; TNCDBR recommends ≥ 1.5 m²"
    },
    "dining": {
        "min_area_sqm": 7.0,
        "min_width_m": 2.5,
        "nbc_clause": "NBC 2016, Part 3, Cl. 8.1.1 (read with habitable room)",
        "description": "Dining treated as habitable — recommended ≥ 7.0 m², 2.5 m wide"
    },
    "utility": {
        "min_area_sqm": 2.0,
        "min_width_m": 1.2,
        "nbc_clause": "NBC 2016, Part 3, Cl. 8.1.5",
        "description": "Service/utility — no statutory minimum; 2.0 m² recommended"
    },
    "verandah": {
        "min_width_m": 1.2,
        "min_area_sqm": None,
        "nbc_clause": "TNCDBR 2019, Cl. 4.9",
        "description": "Verandah/sit-out — minimum width 1.2 m"
    },
}

# ── Ceiling heights — NBC Part 3, Clause 8.2 ─────────────────────────────────
NBC_CEILING_HEIGHTS = {
    "habitable_room_min_m": 2.75,   # NBC Cl. 8.2.1
    "habitable_room_ac_min_m": 2.40, # with air conditioning
    "bathroom_min_m": 2.20,
    "corridor_min_m": 2.20,
    "kitchen_min_m": 2.75,
    "mezzanine_min_m": 2.20,
    "note": "NBC 2016, Part 3, Cl. 8.2 — habitable rooms ≥ 2.75 m; AC rooms ≥ 2.40 m",
}

# ── Ventilation requirements — NBC Part 8 Section 1 ─────────────────────────
NBC_VENTILATION = {
    "window_area_as_fraction_of_floor": 0.10,     # 10% of floor area (NBC Cl. 8.3.1)
    "openable_fraction_of_window": 0.50,          # 50% of window must be openable
    "min_ventilation_opening_sqm": 0.30,          # absolute minimum per room
    "cross_ventilation_required": True,           # NBC recommendation for tropical zones
    "note": (
        "NBC 2016 Part 8 Sec 1, Cl. 5.1: Every habitable room shall have "
        "window/ventilator area ≥ 1/10 of floor area; at least 50% openable. "
        "ECBC 2017 recommends cross-ventilation for Warm & Humid and Hot & Dry zones."
    ),
}

# ── Natural lighting — NBC Part 8 Section 1 ──────────────────────────────────
NBC_DAYLIGHTING = {
    "daylight_factor_habitable_min_pct": 2.0,     # 2% DF for habitable rooms
    "daylight_factor_kitchen_min_pct": 2.0,
    "sky_component_min_pct": 1.0,
    "window_area_fraction_of_floor": 0.10,        # Cl. 5.1
    "note": "NBC 2016, Part 8 Sec 1, Cl. 3.1 & 5.1: DF ≥ 2% for habitable areas",
}

# ── FSI / FAR by city — Tamil Nadu specific ───────────────────────────────────
# Source: TNCDBR 2019, CMDA 2022, respective local body bye-laws
FSI_BY_CITY = {
    "CMDA (Chennai Metropolitan Area)": {
        "residential_plot_upto_200sqm": 1.5,
        "residential_plot_201_to_500sqm": 2.0,
        "residential_plot_above_500sqm": 2.5,
        "ground_coverage_max_pct": 75,
        "note": "CMDA Development Control Regulations 2022, Cl. 20"
    },
    "Madurai Corporation": {
        "residential": 2.0,
        "ground_coverage_max_pct": 70,
        "note": "Madurai Corporation Building Rules 2019"
    },
    "Coimbatore Corporation": {
        "residential_upto_200sqm": 1.75,
        "residential_above_200sqm": 2.0,
        "ground_coverage_max_pct": 70,
        "note": "Coimbatore City Municipal Corporation Building Rules 2020"
    },
    "Town Panchayat (general)": {
        "residential": 1.5,
        "ground_coverage_max_pct": 60,
        "note": "TNCDBR 2019 default for town panchayat jurisdiction"
    },
    "Village Panchayat": {
        "residential": 1.0,
        "ground_coverage_max_pct": 50,
        "note": "TNCDBR 2019 rural norms"
    },
}

# ── NBC Compliance scoring weights ────────────────────────────────────────────
NBC_COMPLIANCE_WEIGHTS = {
    "room_area":        0.30,   # 30% — most critical
    "ventilation":      0.25,   # 25%
    "ceiling_height":   0.20,   # 20%
    "corridor_width":   0.10,   # 10%
    "bathroom_count":   0.15,   # 15%
}

def check_nbc_compliance(room_type: str, area_sqm: float, width_m: float) -> dict:
    """
    Returns an NBC compliance result for a given room.
    """
    mins = NBC_ROOM_MINIMUMS.get(room_type)
    if not mins:
        return {"compliant": True, "reason": "No NBC minimum defined for this room type"}

    area_ok = (mins.get("min_area_sqm") is None) or (area_sqm >= mins["min_area_sqm"])
    width_ok = (mins.get("min_width_m") is None) or (width_m >= mins["min_width_m"])

    reasons = []
    if not area_ok:
        reasons.append(
            f"Area {area_sqm:.1f} m² < NBC minimum {mins['min_area_sqm']} m²"
        )
    if not width_ok:
        reasons.append(
            f"Width {width_m:.1f} m < NBC minimum {mins['min_width_m']} m"
        )

    return {
        "compliant": area_ok and width_ok,
        "area_ok": area_ok,
        "width_ok": width_ok,
        "clause": mins.get("nbc_clause", "—"),
        "description": mins.get("description", ""),
        "reasons": reasons,
    }
