"""
ventilation_rules.py — Tamil Nadu Residential Ventilation Strategy
==================================================================
A rule-based engine for cross-ventilation, wind-directed window placement,
and west-heat-gain avoidance, calibrated to Tamil Nadu's four ECBC climate
zones (Hot & Dry, Warm & Humid, Composite, Temperate).

Source References
-----------------
  NBC 2016 Part 8 Section 1
    § 5.1   — ventilation openings ≥ 1/6 floor area (habitable rooms)
    § 5.1.2 — opening location: inlet low windward, outlet high leeward
    § 5.3   — cross-ventilation required when room depth > 2.5× ceiling ht

  ECBC 2017
    Table 4.3  — maximum Window-to-Wall Ratio by climate zone
    Appendix D — shading depth for west/southwest facade

  Givoni B., "Man, Climate and Architecture", 2nd ed., 1976
    Ch. 9 — outlet area ≥ 1.25 × inlet area for maximum air velocity
    Ch. 10 — wind pressure coefficient: Cp_windward ≈ +0.6, Cp_leeward ≈ −0.3

  IMD Wind Atlas of India 2010
    Seasonal wind rose data for TN stations (Chennai, Madurai, Coimbatore)

  CEPT Research, "Passive Cooling Strategies", 2018
    Thermal buffer zoning (utility/store on west wall)
    Stack ventilation via courtyard (ΔT ≈ 2–4 °C between courtyard and room)

  Baker L., "Mud and Man", COSTFORD 1993, § 6.2
    "Every room must breathe" — paired openings for through-ventilation

  IS 3792 : 1978 — Guide for heat insulation of non-industrial buildings
    West wall solar heat gain factor ≈ 1.6× east wall (for latitude 8–13°N)

  ASHRAE Handbook — Fundamentals 2017, Ch. 16
    Wind pressure coefficients for low-rise rectangular buildings

  Olgyay V., "Design with Climate", 1963
    Bioclimatic chart methodology adapted for tropical India

Public API
----------
  VENT_RULES           — master rule table (dict of RuleID → VentRule)
  suggest_windows()    — optimal window sides for a room
  evaluate_room()      — per-room ventilation adequacy check
  evaluate_plan()      — plan-level ventilation score + violations
  west_buffer_rooms()  — identify rooms that should buffer west heat
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

__all__ = [
    "VentRule", "RoomVentResult", "PlanVentResult",
    "VENT_RULES", "ZONE_PARAMS",
    "suggest_windows", "evaluate_room", "evaluate_plan",
    "west_buffer_rooms", "wind_sides",
]


# ═══════════════════════════════════════════════════════════════════════════════
#  1. CONSTANTS & DATA TABLES
# ═══════════════════════════════════════════════════════════════════════════════

# Wind direction → which cardinal walls it reaches first (inlet) and last (outlet)
# For oblique winds (SE, SW, NE, NW), both adjacent cardinals are inlet walls.
_WIND_INLET: Dict[str, List[str]] = {
    "N":  ["N"],       "S":  ["S"],       "E":  ["E"],       "W":  ["W"],
    "NE": ["N", "E"],  "NW": ["N", "W"],  "SE": ["S", "E"],  "SW": ["S", "W"],
}

OPPOSITE: Dict[str, str] = {"N": "S", "S": "N", "E": "W", "W": "E"}

# Wind pressure coefficients — ASHRAE 2017 Ch. 16 (low-rise rectangular bldg)
# Cp_windward ≈ +0.6, Cp_side ≈ −0.35, Cp_leeward ≈ −0.3
CP_WINDWARD  =  0.60
CP_SIDE      = -0.35
CP_LEEWARD   = -0.30

# Minimum ventilation opening areas — NBC 2016 Part 8 § 5.1
NBC_MIN_VENT_RATIO = 1 / 6          # opening area ≥ 1/6 floor area (habitable)
NBC_MIN_VENT_RATIO_WET = 1 / 10     # bathroom/toilet/utility: ≥ 1/10 floor area
NBC_CROSS_VENT_DEPTH = 2.5          # room depth > 2.5 × ceiling ht → cross-vent needed

# Outlet-to-inlet area ratio for optimal airflow — Givoni 1976 Ch. 9
OUTLET_INLET_RATIO = 1.25

# West wall heat gain multiplier vs east wall — IS 3792 : 1978, latitude 8–13°N
WEST_HEAT_GAIN_FACTOR = 1.6

# Assumed floor-to-ceiling height for cross-vent depth check
ASSUMED_CEILING_HT = 3.0   # metres (standard TN residential)


# ── Climate zone parameters ──────────────────────────────────────────────────
# Keys match ECBC 2017 / tn_climate_data.py zone_type strings.

@dataclass(frozen=True)
class ZoneParams:
    """Climate-zone-specific ventilation design parameters."""
    zone_key:        str
    wwr_max:         float   # max window-to-wall ratio (ECBC Table 4.3)
    wwr_target:      float   # design target (mid-range)
    cross_vent:      str     # "required" | "recommended" | "seasonal"
    west_policy:     str     # "block" | "shade_1.2m" | "reduce" | "allow"
    min_air_speed:   float   # m/s — ASHRAE comfort air speed
    night_vent:      bool    # night purge ventilation beneficial?
    stack_vent:      bool    # courtyard stack-effect beneficial?
    inlet_pref:      str     # "large" (hot-humid) | "small" (hot-dry) | "moderate"
    avoid_sides:     Tuple[str, ...]   # wall orientations to avoid glazing on
    buffer_west:     bool    # should non-habitable rooms buffer the west wall?
    shading_depth_m: float   # recommended overhang projection (metres)

ZONE_PARAMS: Dict[str, ZoneParams] = {
    "hot_humid": ZoneParams(
        zone_key="hot_humid",
        wwr_max=0.30, wwr_target=0.25,
        cross_vent="required",
        west_policy="block",        # no habitable W windows (Baker / ECBC)
        min_air_speed=0.5,
        night_vent=False,           # humidity too high at night
        stack_vent=True,            # courtyard muttram is effective
        inlet_pref="large",         # maximise cross-vent airflow
        avoid_sides=("W", "SW"),
        buffer_west=True,
        shading_depth_m=0.9,
    ),
    "hot_dry": ZoneParams(
        zone_key="hot_dry",
        wwr_max=0.20, wwr_target=0.15,
        cross_vent="seasonal",       # close during hot day, open at night
        west_policy="shade_1.2m",    # allowed with deep shading
        min_air_speed=0.3,
        night_vent=True,             # night purge: Δ15 °C diurnal range
        stack_vent=True,
        inlet_pref="small",          # minimise daytime hot-air entry
        avoid_sides=("W",),
        buffer_west=True,
        shading_depth_m=1.2,
    ),
    "composite": ZoneParams(
        zone_key="composite",
        wwr_max=0.25, wwr_target=0.20,
        cross_vent="recommended",
        west_policy="reduce",
        min_air_speed=0.4,
        night_vent=True,
        stack_vent=True,
        inlet_pref="moderate",
        avoid_sides=("W",),
        buffer_west=True,
        shading_depth_m=1.0,
    ),
    "temperate_cool": ZoneParams(
        zone_key="temperate_cool",
        wwr_max=0.35, wwr_target=0.20,
        cross_vent="seasonal",
        west_policy="allow",         # no heat penalty at altitude
        min_air_speed=0.1,
        night_vent=False,
        stack_vent=False,
        inlet_pref="moderate",
        avoid_sides=(),
        buffer_west=False,
        shading_depth_m=0.5,
    ),
}


# ═══════════════════════════════════════════════════════════════════════════════
#  2. RULE DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class VentRule:
    """A single ventilation rule with applicability conditions."""
    rule_id:     str
    title:       str
    source:      str               # reference citation
    applies_to:  Tuple[str, ...]   # room types ("living", "bedroom", …) or ("*",)
    zones:       Tuple[str, ...]   # climate zones or ("*",)
    severity:    str               # "mandatory" | "recommended"
    description: str


VENT_RULES: Dict[str, VentRule] = {
    # ── R1: Cross-ventilation (inlet + outlet on opposite walls) ─────────────
    "R1_CROSS_VENT": VentRule(
        rule_id="R1_CROSS_VENT",
        title="Cross-ventilation: inlet + outlet on opposite walls",
        source="NBC 2016 Part 8 §5.3; Baker COSTFORD 1993 §6.2; Givoni 1976 Ch. 9",
        applies_to=("living", "bedroom", "dining"),
        zones=("hot_humid", "composite"),
        severity="mandatory",
        description=(
            "Habitable rooms in hot-humid and composite zones must have openings "
            "on two opposite walls for through-ventilation. The windward wall "
            "opening (inlet) admits breeze; the leeward opening (outlet) "
            "creates negative pressure for airflow. Outlet area should be "
            "≥ 1.25× inlet area for maximum indoor air velocity (Givoni 1976)."
        ),
    ),
    "R1b_CROSS_VENT_DRY": VentRule(
        rule_id="R1b_CROSS_VENT_DRY",
        title="Night cross-ventilation for hot-dry zones",
        source="CEPT 2018; Olgyay 1963; NBC 2016 Part 8 §5.1",
        applies_to=("living", "bedroom"),
        zones=("hot_dry",),
        severity="recommended",
        description=(
            "In hot-dry zones, cross-ventilation is recommended for night "
            "purge cooling (15 °C diurnal temperature swing). Daytime openings "
            "should be minimised; night-time openings on opposite walls flush "
            "stored heat from thermal mass."
        ),
    ),

    # ── R2: Windward inlet window placement ──────────────────────────────────
    "R2_WIND_INLET": VentRule(
        rule_id="R2_WIND_INLET",
        title="Window on prevailing-wind wall (windward inlet)",
        source="IMD Wind Atlas 2010; ASHRAE 2017 Ch. 16; NBC 2016 Part 8 §5.1.2",
        applies_to=("living", "bedroom", "dining", "kitchen"),
        zones=("*",),
        severity="mandatory",
        description=(
            "At least one window must face the prevailing wind direction "
            "(windward wall, Cp ≈ +0.6). For Tamil Nadu: SE in Chennai, "
            "SW in Madurai/Coimbatore, NE in Ooty. Inlet should be at "
            "low-to-mid height on the windward face."
        ),
    ),

    # ── R3: Leeward outlet window ────────────────────────────────────────────
    "R3_WIND_OUTLET": VentRule(
        rule_id="R3_WIND_OUTLET",
        title="Outlet window on leeward wall (opposite to wind)",
        source="Givoni 1976 Ch. 9; ASHRAE 2017 Ch. 16",
        applies_to=("living", "bedroom"),
        zones=("hot_humid", "composite"),
        severity="recommended",
        description=(
            "A window on the wall opposite to prevailing wind creates a "
            "negative-pressure outlet (Cp ≈ −0.3). This pressure differential "
            "drives airflow through the room. Outlet area ≥ 1.25× inlet area "
            "maximises indoor air velocity."
        ),
    ),

    # ── R4: NBC minimum ventilation opening area ─────────────────────────────
    "R4_NBC_MIN_OPENING": VentRule(
        rule_id="R4_NBC_MIN_OPENING",
        title="Minimum ventilation opening ≥ 1/6 floor area",
        source="NBC 2016 Part 8 §5.1",
        applies_to=("living", "bedroom", "dining", "kitchen"),
        zones=("*",),
        severity="mandatory",
        description=(
            "Every habitable room shall have ventilation openings with "
            "aggregate area ≥ 1/6 of the floor area of the room. Wet rooms "
            "(bathroom, toilet, utility) require ≥ 1/10 of floor area."
        ),
    ),

    # ── R5: West heat gain avoidance ─────────────────────────────────────────
    "R5_WEST_BLOCK": VentRule(
        rule_id="R5_WEST_BLOCK",
        title="Block/shade west-facing windows in hot zones",
        source="IS 3792:1978; ECBC 2017 Appendix D; Baker COSTFORD 1993",
        applies_to=("living", "bedroom", "kitchen", "dining"),
        zones=("hot_humid", "hot_dry", "composite"),
        severity="mandatory",
        description=(
            "West-facing walls receive 1.6× the solar heat gain of east "
            "walls (IS 3792, latitude 8–13°N). In hot-humid zones, west "
            "windows on habitable rooms are prohibited. In hot-dry zones, "
            "west windows require external shading ≥ 1.2 m projection. "
            "Non-habitable rooms (utility, store, bathroom) should buffer "
            "the west facade."
        ),
    ),

    # ── R6: Thermal buffer on west wall ──────────────────────────────────────
    "R6_WEST_BUFFER": VentRule(
        rule_id="R6_WEST_BUFFER",
        title="Non-habitable buffer rooms on west facade",
        source="CEPT 2018; Baker 1986",
        applies_to=("*",),
        zones=("hot_humid", "hot_dry", "composite"),
        severity="recommended",
        description=(
            "Place non-habitable rooms (utility, store, staircase, bathroom) "
            "along the west wall as thermal buffers. This shields bedrooms "
            "and living spaces from afternoon solar heat gain."
        ),
    ),

    # ── R7: Kitchen stack ventilation ────────────────────────────────────────
    "R7_KITCHEN_EXHAUST": VentRule(
        rule_id="R7_KITCHEN_EXHAUST",
        title="Kitchen: leeward exhaust + east/north inlet",
        source="NBC 2016 Part 8 §5.1; Baker 1993 §6.2",
        applies_to=("kitchen",),
        zones=("*",),
        severity="mandatory",
        description=(
            "Kitchen must have at least one window (preferably east for "
            "morning light or north for cool diffuse light). In hot zones, "
            "west kitchen windows are strongly penalised. A high-level "
            "exhaust opening on the leeward side removes cooking heat "
            "by stack effect."
        ),
    ),

    # ── R8: Bathroom exhaust-side window ─────────────────────────────────────
    "R8_BATHROOM_VENT": VentRule(
        rule_id="R8_BATHROOM_VENT",
        title="Bathroom window on leeward/north wall",
        source="NBC 2016 Part 8 §5.1; Baker 1993",
        applies_to=("bathroom", "toilet"),
        zones=("*",),
        severity="mandatory",
        description=(
            "Bathrooms require a ventilation opening ≥ 1/10 of floor area "
            "(NBC §5.1). Window on north or leeward wall preferred for "
            "privacy + exhaust airflow. Corner bathrooms with 2 exterior "
            "walls should have openings for cross-ventilation."
        ),
    ),

    # ── R9: Bedroom morning light + cross-vent ───────────────────────────────
    "R9_BEDROOM_ORIENT": VentRule(
        rule_id="R9_BEDROOM_ORIENT",
        title="Bedroom: east morning light + cross-ventilation",
        source="Baker 1986; CEPT 2018; NBC 2016 Part 8",
        applies_to=("bedroom",),
        zones=("*",),
        severity="recommended",
        description=(
            "Bedrooms should have an east-facing window for beneficial "
            "morning light (Baker principle). In hot-humid/composite zones, "
            "a second window on the opposite wall (typically west or north) "
            "provides cross-ventilation. West windows are removed in hot "
            "zones; north is preferred as the cross-vent outlet."
        ),
    ),

    # ── R10: Living room — primary inlet on windward face ────────────────────
    "R10_LIVING_ORIENT": VentRule(
        rule_id="R10_LIVING_ORIENT",
        title="Living room: windward inlet, public-face outlook",
        source="Baker 1993 §4.1; NBC 2016 Part 8; ECBC 2017",
        applies_to=("living",),
        zones=("*",),
        severity="mandatory",
        description=(
            "Living room must have its primary window on the prevailing-wind "
            "wall for natural ventilation. In Chennai (SE wind), this means "
            "S or E. In Madurai/Coimbatore (SW wind), this means S or W — "
            "but W is blocked in hot zones so S is preferred. A second "
            "window on the opposite wall completes cross-ventilation."
        ),
    ),

    # ── R11: ECBC WWR compliance ─────────────────────────────────────────────
    "R11_WWR_LIMIT": VentRule(
        rule_id="R11_WWR_LIMIT",
        title="Window-to-wall ratio within ECBC zone limits",
        source="ECBC 2017 Table 4.3",
        applies_to=("*",),
        zones=("*",),
        severity="recommended",
        description=(
            "Total glazing area should not exceed the ECBC maximum WWR "
            "for the climate zone: 30% hot-humid, 20% hot-dry, 25% "
            "composite, 35% temperate. Exceeding WWR increases cooling "
            "load; too-low WWR reduces daylight and ventilation."
        ),
    ),
}


# ═══════════════════════════════════════════════════════════════════════════════
#  3. HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def wind_sides(prevailing: str) -> Dict[str, str]:
    """
    Classify each cardinal wall as 'windward', 'leeward', or 'side'
    given the prevailing wind direction.

    Returns {"N": "windward"|"leeward"|"side", "S": ..., "E": ..., "W": ...}
    """
    inlets = set(_WIND_INLET.get(prevailing, ["S", "E"]))
    outlets = {OPPOSITE[d] for d in inlets if d in OPPOSITE}
    result: Dict[str, str] = {}
    for card in ("N", "S", "E", "W"):
        if card in inlets:
            result[card] = "windward"
        elif card in outlets:
            result[card] = "leeward"
        else:
            result[card] = "side"
    return result


def _exterior_sides(room: Any, pw: float, ph: float, margin: float,
                    all_rooms: Optional[List[Any]] = None) -> List[str]:
    """
    Return which cardinal sides of *room* are on the building perimeter.

    Uses geometry-based detection (room edge ≈ building footprint edge) when
    all_rooms is provided, avoiding margin-threshold errors after rotation.
    Falls back to margin-based detection otherwise.
    """
    _EDGE_TOL = 0.20   # room edge within 0.20m of building boundary = exterior
    if all_rooms:
        non_special = [r for r in all_rooms if getattr(r, "room_type", "") not in ("verandah",)]
        if non_special:
            bx0 = min(r.x for r in non_special)
            by0 = min(r.y for r in non_special)
            bx1 = max(r.x + r.width  for r in non_special)
            by1 = max(r.y + r.height for r in non_special)
            on = {
                "S": room.y             <= by0 + _EDGE_TOL,
                "N": room.y + room.height >= by1 - _EDGE_TOL,
                "E": room.x + room.width  >= bx1 - _EDGE_TOL,
                "W": room.x             <= bx0 + _EDGE_TOL,
            }
            return [s for s, v in on.items() if v]
    # Fallback: margin-based
    tol = margin + 0.15
    on = {
        "S": room.y      <= tol,
        "N": (room.y + room.height) >= ph - tol,
        "E": (room.x + room.width)  >= pw - tol,
        "W": room.x      <= tol,
    }
    return [s for s, v in on.items() if v]


def _has_cross_vent(windows: List[str]) -> bool:
    """True if windows list contains at least one inlet-outlet pair."""
    wset = set(windows)
    return (
        ("N" in wset and "S" in wset) or
        ("E" in wset and "W" in wset)
    )


def _nbc_min_opening_m2(room_type: str, floor_area: float) -> float:
    """Minimum required ventilation opening area (m²) per NBC 2016 Part 8 §5.1."""
    wet = ("bathroom", "toilet", "utility")
    ratio = NBC_MIN_VENT_RATIO_WET if room_type in wet else NBC_MIN_VENT_RATIO
    return floor_area * ratio


def _est_window_area(n_windows: int, room_width: float,
                     room_height: float) -> float:
    """
    Estimate total window opening area from number of windows.
    Standard TN residential window: 1.2 m wide × 1.2 m high = 1.44 m²
    For tight rooms (< 3 m wide), use 0.9 × 1.0 = 0.90 m².
    """
    if min(room_width, room_height) < 3.0:
        per_win = 0.90
    else:
        per_win = 1.44
    return n_windows * per_win


# ═══════════════════════════════════════════════════════════════════════════════
#  4. WINDOW SUGGESTION (replaces engine logic)
# ═══════════════════════════════════════════════════════════════════════════════

# Room-type window-side preference table (independent of climate — overridden below)
_BASE_PREFS: Dict[str, List[str]] = {
    "living":    ["S", "E", "N", "W"],
    "dining":    ["E", "S", "N", "W"],
    "kitchen":   ["E", "N", "SE", "S"],
    "bedroom":   ["E", "N", "S", "W"],
    "bathroom":  ["N", "E", "S", "W"],
    "toilet":    ["N", "E", "S", "W"],
    "utility":   ["E", "N", "S", "W"],
    "pooja":     ["E", "N", "S"],
    "study":     ["N", "E", "S"],
    "store":     ["N", "E"],
    "corridor":  [],
    "verandah":  ["S", "E"],
    "courtyard": [],
}


def suggest_windows(
    room: Any,
    room_type: str,
    exterior: List[str],
    climate_zone: str,
    prevailing_wind: str,
    pw: float,
    ph: float,
    margin: float,
    all_rooms: Optional[List[Any]] = None,
) -> Tuple[List[str], bool]:
    """
    Return (window_sides, jali_recommended) for a room based on the full
    ventilation strategy: wind direction, climate zone rules, room-type
    preferences, cross-ventilation requirements, and west-heat-gain avoidance.

    Parameters
    ----------
    room           : Room object (needs .x, .y, .width, .height, .room_type)
    room_type      : e.g., "living", "bedroom"
    exterior       : list of exterior cardinal sides (e.g., ["S", "E"])
    climate_zone   : one of "hot_humid", "hot_dry", "composite", "temperate_cool"
    prevailing_wind: dominant wind direction (e.g., "SE", "SW", "NE")
    pw, ph         : plot width and height (metres)
    margin         : plot setback margin (metres)
    all_rooms      : optional list of all rooms (for buffer-zone detection)

    Returns
    -------
    (windows, jali_recommended)
    """
    if room_type in ("courtyard", "lightwell"):
        return (["open_sky"], False)

    if room_type == "corridor":
        return (["vent->natural"], False)

    zp = ZONE_PARAMS.get(climate_zone, ZONE_PARAMS["hot_humid"])
    ws = wind_sides(prevailing_wind)
    jali = False

    # If interior room (no exterior walls)
    if not exterior:
        has_lw = getattr(room, "has_lightwell", False)
        if has_lw:
            return (["LW"], False)
        # Find nearest exterior direction for vent shaft
        cx = room.x + room.width / 2
        cy = room.y + room.height / 2
        dists = {"S": cy, "N": ph - cy, "W": cx, "E": pw - cx}
        nearest = min(dists, key=dists.get)
        return ([f"vent->{nearest}"], False)

    windows: List[str] = []

    # ── Step A: Windward inlet (highest priority) ────────────────────────────
    inlets = _WIND_INLET.get(prevailing_wind, ["S", "E"])
    for d in inlets:
        if d in exterior and d not in zp.avoid_sides:
            windows.append(d)
    # If no windward side available, pick best exterior that's not avoided
    if not windows:
        prefs = _BASE_PREFS.get(room_type, ["E", "N", "S", "W"])
        for p in prefs:
            if p in exterior and p not in zp.avoid_sides:
                windows.append(p)
                break

    # ── Step B: Cross-ventilation outlet (opposite to inlet) ─────────────────
    habitable = room_type in ("living", "bedroom", "dining")
    needs_cross = (
        (zp.cross_vent == "required" and habitable) or
        (zp.cross_vent == "recommended" and habitable)
    )
    if needs_cross:
        for w in list(windows):
            opp = OPPOSITE.get(w)
            if opp and opp in exterior and opp not in windows:
                # In hot zones, skip W/SW as outlet
                if opp in zp.avoid_sides:
                    continue
                windows.append(opp)

    # ── Step C: Room-type specific additions ─────────────────────────────────
    if room_type == "living":
        # Ensure south-face light if available
        if "S" in exterior and "S" not in windows and "S" not in zp.avoid_sides:
            windows.append("S")
        # Hot-humid: prioritise E (sea breeze inlet for Chennai)
        if climate_zone == "hot_humid" and "E" in exterior and "E" not in windows:
            windows.append("E")

    elif room_type == "bedroom":
        # East morning light (Baker principle)
        if "E" in exterior and "E" not in windows:
            windows.append("E")
        # North cool diffuse light for cross-vent outlet
        if needs_cross and "N" in exterior and "N" not in windows:
            windows.append("N")

    elif room_type == "kitchen":
        # Priority: E > N > SE > S; avoid W
        kitchen_prefs = ["E", "N", "SE", "S"]
        if not any(p in windows for p in kitchen_prefs):
            for p in kitchen_prefs:
                if p in exterior and p not in windows:
                    windows.append(p)
                    break

    elif room_type in ("bathroom", "toilet"):
        # Leeward/north preferred for exhaust + privacy
        bath_prefs = ["N", "E", "S"]
        if not windows:
            for p in bath_prefs:
                if p in exterior:
                    windows.append(p)
                    break

    elif room_type == "utility":
        util_prefs = ["E", "N", "S"]
        if not windows:
            for p in util_prefs:
                if p in exterior:
                    windows.append(p)
                    break

    # ── Step D: West heat gain enforcement ───────────────────────────────────
    if zp.west_policy == "block":
        # Remove W/SW from habitable rooms entirely
        if room_type in ("living", "bedroom", "dining", "kitchen"):
            before = len(windows)
            windows = [w for w in windows if w not in ("W", "SW")]
            if not windows and before > 0:
                # All windows were west — fallback to best non-west exterior
                for alt in ["E", "N", "S"]:
                    if alt in exterior:
                        windows = [alt]
                        break
            if not windows and exterior:
                # Truly only W available — allow with jali
                windows = [exterior[0]]
                jali = True

    elif zp.west_policy == "shade_1.2m":
        # Allow W with shading tag (jali)
        if any(w in ("W", "SW") for w in windows):
            jali = True

    elif zp.west_policy == "reduce":
        # Remove W if alternatives exist
        if any(w in ("W", "SW") for w in windows) and len(windows) > 1:
            windows = [w for w in windows if w not in ("W", "SW")]

    # ── Step E: Ensure at least one window ───────────────────────────────────
    if not windows and exterior:
        fallback = exterior[0]
        windows = [fallback]
        if fallback in ("W", "SW") and climate_zone in ("hot_humid", "hot_dry"):
            jali = True

    # ── Step F: If only W/SW window remains in hot zone, tag jali ────────────
    if (climate_zone in ("hot_humid", "hot_dry", "composite") and
            len(windows) == 1 and windows[0] in ("W", "SW")):
        jali = True

    # ── Step G: Two-window minimum for major habitable rooms ─────────────────
    # Every living room, bedroom, dining, kitchen, study must have ≥ 2 windows
    # on different walls.  Preference order for the second window: N > E > S > W.
    # West is only added as a last resort (tagged jali in hot zones).
    _MAJOR_ROOMS = ("living", "bedroom", "dining", "kitchen", "study")
    if room_type in _MAJOR_ROOMS and len(windows) < 2 and len(exterior) >= 2:
        _SECOND_WIN_PREF = ["N", "E", "S", "W"]
        for cand in _SECOND_WIN_PREF:
            if cand in exterior and cand not in windows:
                # In hot zones don't add W unless it's the only choice
                if cand == "W" and zp.west_policy == "block":
                    # Only add if no other exterior side remains
                    other_ext = [s for s in exterior if s not in windows and s != "W"]
                    if other_ext:
                        continue   # skip W, try next
                windows.append(cand)
                if cand in ("W", "SW") and climate_zone in ("hot_humid", "hot_dry"):
                    jali = True
                break

    # ── Step H: West-only avoidance — replace or supplement ──────────────────
    # If all assigned windows are west-facing in a hot zone, force at least one
    # non-west window (N or E preferred) so the room isn't west-only.
    if windows and all(w in ("W", "SW") for w in windows):
        if climate_zone in ("hot_humid", "hot_dry", "composite"):
            for alt in ["N", "E", "S"]:
                if alt in exterior:
                    windows.insert(0, alt)   # prepend preferred window
                    break
            # If we managed to add a better window and have >1, drop W if
            # west_policy == block (habitable rooms)
            if (zp.west_policy == "block" and len(windows) > 1
                    and room_type in ("living", "bedroom", "dining", "kitchen")):
                windows = [w for w in windows if w not in ("W", "SW")]

    return (windows, jali)


# ═══════════════════════════════════════════════════════════════════════════════
#  5. PER-ROOM EVALUATION
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class RoomVentResult:
    """Ventilation evaluation for a single room."""
    room_name:       str
    room_type:       str
    score:           float          # 0–100
    has_cross_vent:  bool
    has_wind_inlet:  bool
    nbc_opening_ok:  bool
    west_compliant:  bool
    violations:      List[str] = field(default_factory=list)
    suggestions:     List[str] = field(default_factory=list)


def evaluate_room(
    room: Any,
    climate_zone: str,
    prevailing_wind: str,
    pw: float,
    ph: float,
    margin: float,
) -> RoomVentResult:
    """
    Evaluate a single room against all applicable ventilation rules.
    Returns a RoomVentResult with score (0–100) and any violations.
    """
    rtype = room.room_type
    windows = list(getattr(room, "windows", []))
    zp = ZONE_PARAMS.get(climate_zone, ZONE_PARAMS["hot_humid"])
    ws = wind_sides(prevailing_wind)
    exterior = _exterior_sides(room, pw, ph, margin)

    violations: List[str] = []
    suggestions: List[str] = []
    score = 100.0

    # Skip non-standard rooms
    if rtype in ("courtyard", "lightwell", "verandah", "corridor"):
        return RoomVentResult(
            room_name=getattr(room, "name", rtype),
            room_type=rtype, score=100.0,
            has_cross_vent=False, has_wind_inlet=False,
            nbc_opening_ok=True, west_compliant=True,
        )

    # Filter to real windows (not vent->, LW, via corridor, open_sky)
    real_wins = [w for w in windows
                 if w in ("N", "S", "E", "W", "NE", "NW", "SE", "SW")]

    # ── R1: Cross-ventilation ────────────────────────────────────────────────
    has_cross = _has_cross_vent(real_wins)
    habitable = rtype in ("living", "bedroom", "dining")
    r1_applies = habitable and zp.cross_vent in ("required", "recommended")

    if r1_applies and not has_cross:
        penalty = 15.0 if zp.cross_vent == "required" else 8.0
        score -= penalty
        violations.append("R1: No cross-ventilation (missing opposite-wall outlet)")
        # Suggest the best outlet
        for w in real_wins:
            opp = OPPOSITE.get(w)
            if opp and opp in exterior and opp not in real_wins:
                suggestions.append(f"Add {opp} window for cross-ventilation outlet")
                break

    # ── R2: Windward inlet ───────────────────────────────────────────────────
    inlets = _WIND_INLET.get(prevailing_wind, ["S", "E"])
    has_inlet = any(w in inlets for w in real_wins)

    if habitable and not has_inlet:
        score -= 10.0
        violations.append(f"R2: No windward inlet (prevailing wind = {prevailing_wind})")
        available_inlets = [d for d in inlets if d in exterior]
        if available_inlets:
            suggestions.append(f"Add window on {available_inlets[0]} (windward)")

    # ── R4: NBC minimum opening area ─────────────────────────────────────────
    floor_area = room.width * room.height
    min_area = _nbc_min_opening_m2(rtype, floor_area)
    est_area = _est_window_area(len(real_wins), room.width, room.height)
    nbc_ok = est_area >= min_area

    if not nbc_ok and real_wins:
        score -= 8.0
        violations.append(
            f"R4: Est. opening {est_area:.1f} m2 < NBC min {min_area:.1f} m2"
        )
    elif not real_wins and exterior:
        score -= 12.0
        violations.append("R4: No ventilation openings on exterior room")

    # ── R5: West heat gain ───────────────────────────────────────────────────
    has_west = any(w in ("W", "SW") for w in real_wins)
    west_ok = True

    if has_west and zp.west_policy == "block" and habitable:
        west_ok = False
        score -= 15.0
        violations.append(
            "R5: West-facing window on habitable room in hot zone "
            f"(heat gain factor {WEST_HEAT_GAIN_FACTOR}x)"
        )
        alts = [d for d in ("E", "N", "S") if d in exterior]
        if alts:
            suggestions.append(f"Replace W window with {alts[0]}")

    elif has_west and zp.west_policy == "shade_1.2m":
        jali_tagged = getattr(room, "jali_recommended", False)
        if not jali_tagged:
            score -= 5.0
            violations.append("R5: West window needs shading depth >= 1.2 m")

    elif has_west and zp.west_policy == "reduce":
        if len(real_wins) > 1:
            score -= 3.0
            suggestions.append("Consider removing west window (alternatives exist)")

    # ── R7/R8: Kitchen and bathroom specifics ────────────────────────────────
    if rtype == "kitchen":
        if real_wins and all(w in ("W", "SW") for w in real_wins):
            score -= 10.0
            violations.append("R7: Kitchen has only west-facing window")

    if rtype in ("bathroom", "toilet"):
        if not real_wins and exterior:
            score -= 10.0
            violations.append("R8: Bathroom has no ventilation opening")

    # ── R9: Bedroom morning light ────────────────────────────────────────────
    if rtype == "bedroom":
        if "E" in exterior and "E" not in real_wins:
            score -= 3.0
            suggestions.append("R9: East window recommended for morning light")

    # Clamp
    score = max(0.0, min(100.0, score))

    return RoomVentResult(
        room_name=getattr(room, "name", rtype),
        room_type=rtype,
        score=round(score, 1),
        has_cross_vent=has_cross,
        has_wind_inlet=has_inlet,
        nbc_opening_ok=nbc_ok,
        west_compliant=west_ok,
        violations=violations,
        suggestions=suggestions,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  6. PLAN-LEVEL EVALUATION
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class PlanVentResult:
    """Aggregated ventilation evaluation for an entire floor plan."""
    overall_score:      float
    cross_vent_pct:     float          # fraction of habitable rooms with cross-vent
    wind_inlet_pct:     float          # fraction of habitable rooms with windward inlet
    nbc_opening_pct:    float          # fraction of rooms meeting NBC opening area
    west_compliant_pct: float          # fraction of rooms with no west-heat violation
    room_results:       List[RoomVentResult] = field(default_factory=list)
    plan_violations:    List[str] = field(default_factory=list)


def evaluate_plan(
    rooms: List[Any],
    climate_zone: str,
    prevailing_wind: str,
    pw: float,
    ph: float,
    margin: float,
) -> PlanVentResult:
    """
    Evaluate the entire floor plan's ventilation strategy.
    Returns aggregate scores and per-room detail.
    """
    zp = ZONE_PARAMS.get(climate_zone, ZONE_PARAMS["hot_humid"])
    results: List[RoomVentResult] = []

    skip_types = {"courtyard", "lightwell", "verandah", "corridor"}
    eval_rooms = [r for r in rooms if r.room_type not in skip_types]

    for r in eval_rooms:
        rr = evaluate_room(r, climate_zone, prevailing_wind, pw, ph, margin)
        results.append(rr)

    habitable = [rr for rr in results
                 if rr.room_type in ("living", "bedroom", "dining")]
    n_hab = max(len(habitable), 1)
    n_all = max(len(results), 1)

    cross_pct  = sum(1 for rr in habitable if rr.has_cross_vent)  / n_hab
    inlet_pct  = sum(1 for rr in habitable if rr.has_wind_inlet)  / n_hab
    nbc_pct    = sum(1 for rr in results   if rr.nbc_opening_ok)  / n_all
    west_pct   = sum(1 for rr in results   if rr.west_compliant)  / n_all

    # Plan-level violations
    plan_violations: List[str] = []
    if cross_pct < 0.5 and zp.cross_vent == "required":
        plan_violations.append(
            f"< 50% habitable rooms have cross-ventilation ({cross_pct:.0%})"
        )
    if inlet_pct < 0.5:
        plan_violations.append(
            f"< 50% habitable rooms face prevailing wind ({inlet_pct:.0%})"
        )

    # R6: West buffer check
    if zp.buffer_west:
        west_exterior = [
            r for r in rooms
            if r.x <= margin + 0.15 and r.room_type in
               ("living", "bedroom", "dining", "kitchen")
        ]
        if west_exterior:
            plan_violations.append(
                f"R6: {len(west_exterior)} habitable room(s) on west facade "
                "without thermal buffer"
            )

    # R11: WWR estimate
    total_windows = sum(
        len([w for w in r.windows
             if w in ("N", "S", "E", "W", "NE", "NW", "SE", "SW")])
        for r in rooms
    )
    est_window_area = total_windows * 1.2
    perimeter = 2 * (pw + ph)
    wall_area = perimeter * ASSUMED_CEILING_HT
    wwr = est_window_area / max(wall_area, 1.0)
    if wwr > zp.wwr_max:
        plan_violations.append(
            f"R11: WWR {wwr:.0%} exceeds ECBC max {zp.wwr_max:.0%}"
        )

    # Weighted overall
    room_avg = sum(rr.score for rr in results) / n_all if results else 50.0
    plan_penalty = len(plan_violations) * 5.0
    overall = max(0.0, min(100.0, room_avg - plan_penalty))

    return PlanVentResult(
        overall_score=round(overall, 1),
        cross_vent_pct=round(cross_pct, 3),
        wind_inlet_pct=round(inlet_pct, 3),
        nbc_opening_pct=round(nbc_pct, 3),
        west_compliant_pct=round(west_pct, 3),
        room_results=results,
        plan_violations=plan_violations,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  7. WEST BUFFER ROOM HELPER
# ═══════════════════════════════════════════════════════════════════════════════

# Room types suitable as west-wall thermal buffers (non-habitable, lower
# thermal-comfort requirement)
_BUFFER_TYPES = frozenset({"utility", "store", "bathroom", "toilet", "staircase"})


def west_buffer_rooms(
    rooms: List[Any],
    pw: float,
    margin: float,
) -> List[str]:
    """
    Identify rooms on the west facade suitable as thermal buffers.
    Returns list of room names that ARE on the west wall and ARE buffer-type.
    """
    tol = margin + 0.15
    return [
        r.name for r in rooms
        if r.x <= tol and r.room_type in _BUFFER_TYPES
    ]
