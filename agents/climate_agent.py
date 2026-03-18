"""
Climate Agent — Offline Tamil Nadu Passive Design Expert System
================================================================
Analyses district-level IMD climate data and derives passive design
strategies, window placement rules, and ECBC compliance targets.

Knowledge Base:
  - IMD Climatological Normals 1981-2010 (station data)
  - ECBC 2017 (Energy Conservation Building Code)
  - ISHRAE Climatic Data Handbook 2016
  - CEPT Passive Cooling Guide 2018
  - Olgyay V., "Design with Climate" (Princeton, 1963)
  - NBC 2016 Part 8 Section 1 — Natural Ventilation

Agent Type: Rule-based expert system (no API dependency)
"""

import math
from typing import Any, Dict
from agents.base_agent import BaseAgent, AgentOutput

# ── IMD 1981-2010 station data + ECBC zone mapping ───────────────────────────
CLIMATE_DATA = {
    "hot_humid": {
        "label": "Hot & Humid (ECBC Zone 2)",
        "districts": [
            "Chennai", "Pondicherry", "Nagapattinam", "Cuddalore", "Thanjavur",
            "Tiruvarur", "Kanyakumari coast", "Rameswaram",
        ],
        "design_db_c": 38,   # dry-bulb degC (IMD 99th percentile)
        "design_wb_c": 28,   # wet-bulb degC
        "rh_pct": 82,        # avg RH %
        "prevailing_wind": "SE",
        "cdd": 1980,         # Cooling Degree Days (base 18C, Chennai IMD)
        "ecbc_wall_u": 0.75, # W/m2K max
        "ecbc_roof_u": 0.40,
        "ecbc_wwr": 0.30,    # Window-to-Wall Ratio max
        "primary_challenge": "Humidity, salt air, monsoon flooding",
        "passive_strategies": [
            "Cross-ventilation SE inlet openings (prevailing wind: SE)",
            "Brick jali screens on W/SW elevations (60% shading, full airflow)",
            "Deep roof overhangs 900mm (Chennai lat 13N: tan(13)=0.23, for 2m window)",
            "Rat-trap bond brickwork (U=1.8 W/m2K — 49% better than solid brick)",
            "High-level ventilation outlets near ridge for stack effect",
            "Avoid west-facing bedrooms — PM sun angle 50-60 deg causes max heat gain",
        ],
        "window_rules": {
            "living":  "SE or S (inlet), large openings >=15% floor area",
            "bedroom": "E (morning) or N (diffuse). NEVER W (afternoon heat).",
            "kitchen": "E or SE — morning sun only, exhaust on opposite wall",
            "bathroom": "N or NW — privacy + diffuse light",
        },
        "risk_flags": [
            "Nagapattinam/Cuddalore: Very High cyclone risk — NBC wind speed 50 m/s design",
            "Low-lying coastal areas: Require 600-900mm plinth above flood level",
            "Salt air within 5km of coast: Avoid CEB, use lime-plastered rat-trap bond",
        ],
    },
    "hot_dry": {
        "label": "Hot & Dry (ECBC Zone 1)",
        "districts": [
            "Madurai", "Trichy", "Salem", "Vellore", "Dindigul",
            "Erode", "Namakkal", "Dharmapuri", "Krishnagiri",
        ],
        "design_db_c": 41,
        "design_wb_c": 27,
        "rh_pct": 42,
        "prevailing_wind": "SW",
        "cdd": 2920,
        "ecbc_wall_u": 0.40,
        "ecbc_roof_u": 0.33,
        "ecbc_wwr": 0.20,
        "primary_challenge": "Extreme afternoon heat, dust, water scarcity",
        "passive_strategies": [
            "Courtyard (muttram) as evaporative cooling engine — mandatory >100m2 plot",
            "Small, high windows on W elevation (clerestory only, min 2.1m sill height)",
            "Thick walls: CEB 300mm or rat-trap bond 230mm — minimum thermal mass 200 kJ/m2K",
            "Earth-colour lime wash on exterior — albedo 0.5 reflects solar radiation",
            "Underground water storage (sump): natural cooling, no pump energy",
            "Roof: terracotta tile or RCC+XPS insulation (U<=0.33 W/m2K per ECBC)",
        ],
        "window_rules": {
            "living":  "N (diffuse light, no direct sun) or SE (morning only)",
            "bedroom": "N or E — NEVER W. Madurai afternoon temp reaches 43 degC.",
            "kitchen": "E — morning sun, chimney/exhaust W side",
            "bathroom": "N — privacy and diffuse light",
        },
        "risk_flags": [
            "Dharmapuri: hottest district (DB up to 43C) — courtyard MANDATORY",
            "Salem/Erode: frequent dust events — seal western openings",
            "Water scarcity: design rainwater harvesting from day one",
        ],
    },
    "composite": {
        "label": "Composite (ECBC Zone 4)",
        "districts": [
            "Coimbatore", "Tirunelveli", "Nagercoil", "Thoothukudi", "Virudhunagar",
        ],
        "design_db_c": 38,
        "design_wb_c": 26,
        "rh_pct": 75,
        "prevailing_wind": "SW",
        "cdd": 2100,
        "ecbc_wall_u": 0.75,
        "ecbc_roof_u": 0.50,
        "ecbc_wwr": 0.25,
        "primary_challenge": "Hot-dry Dec-May, hot-humid Jun-Nov (split strategy needed)",
        "passive_strategies": [
            "Elevated plinth 600mm minimum (Coimbatore: SW monsoon 1,200mm/yr)",
            "Wide overhangs 750mm for monsoon rain deflection",
            "Courtyard with verandah on all four sides for seasonal adaptation",
            "Slope drainage integrated into landscape — integrate with courtyard",
            "Open verandah on SW and NW for drying area in humid season",
            "Both jali screens (humid months) and opaque W wall (dry months) desirable",
        ],
        "window_rules": {
            "living":  "SW (prevailing wind) or S",
            "bedroom": "E or N — avoid W and SW in dry season",
            "kitchen": "E or SE with chimney exhaust",
            "bathroom": "N or NW",
        },
        "risk_flags": [
            "Coimbatore split personality — design for composite (worst of both)",
            "Tirunelveli/Nagercoil: high rainfall — elevated plinth critical",
        ],
    },
    "temperate": {
        "label": "Temperate / Highland (ECBC Zone 5)",
        "districts": ["Nilgiris (Ooty)", "Kodaikanal (Dindigul)", "Yercaud (Salem)"],
        "design_db_c": 27,
        "design_wb_c": 20,
        "rh_pct": 72,
        "prevailing_wind": "NE",
        "cdd": 180,
        "ecbc_wall_u": 1.50,  # thermal mass more important
        "ecbc_roof_u": 0.80,
        "ecbc_wwr": 0.35,     # more glazing for solar gain
        "primary_challenge": "Cold nights (5-10C), fog, heavy rain, frost at high elevation",
        "passive_strategies": [
            "South-facing glazing (35% of south wall) for passive solar winter gain",
            "Compact plan — minimise surface area to volume ratio to reduce heat loss",
            "Thick stone walls 450mm (Salem granite) for thermal mass — stabilises temp",
            "35-deg sloped roof — rain/snow shedding, traditional TN hill aesthetic",
            "Minimal N-facing openings — cold NE wind in winter",
            "Double-glazed windows or secondary shutters for cold nights",
        ],
        "window_rules": {
            "living":  "S (max solar gain in winter) and E for morning warmth",
            "bedroom": "E (morning sun, warming) — avoid N (cold wind)",
            "kitchen": "E or SE — morning sun, warmth for cooking",
            "bathroom": "E or S — warmer for bathing",
        },
        "risk_flags": [
            "TNHDB hill station rules: FAR 1.0, max 50% ground coverage",
            "Frost risk >2,000m ASL — avoid exposed water pipes on N walls",
            "Heavy fog: ensure natural light (wider E/S windows) not blocked by trees",
        ],
    },
}

DISTRICT_TO_CLIMATE = {}
for ctype, cdata in CLIMATE_DATA.items():
    for d in cdata["districts"]:
        DISTRICT_TO_CLIMATE[d.lower()] = ctype


def _get_climate_type(district: str) -> str:
    d = district.lower().strip()
    for k, v in DISTRICT_TO_CLIMATE.items():
        if k in d or d in k:
            return v
    # Default heuristic
    if any(x in d for x in ["coast", "port", "nagai", "cudda", "pudi", "karai"]):
        return "hot_humid"
    if any(x in d for x in ["ooty", "nilgi", "koda", "yerca", "kolli"]):
        return "temperate"
    if any(x in d for x in ["coim", "tirun", "nager", "virud"]):
        return "composite"
    return "hot_dry"  # interior TN default


class ClimateAgent(BaseAgent):
    """Offline climate expert: IMD data + ECBC rules + passive design inference."""

    def __init__(self):
        super().__init__(
            name="Climate Agent",
            domain="Passive Design & Climate-Responsive Architecture",
        )

    def load_knowledge(self):
        try:
            from data.tn_climate_data import STATION_CLIMATE, PASSIVE_STRATEGIES
            self._station_data = STATION_CLIMATE
            self._passive = PASSIVE_STRATEGIES
        except ImportError:
            self._station_data = {}
            self._passive = {}

    def analyse(self, brief: Any, context: Dict[str, Any]) -> AgentOutput:
        out = self._init_output()
        self._ref("IMD Climatological Normals 1981-2010")
        self._ref("ECBC 2017 (Energy Conservation Building Code)")
        self._ref("ISHRAE Climatic Data Handbook 2016")
        self._ref("CEPT University, Passive Cooling Guide 2018")
        self._ref("NBC 2016 Part 8 Section 1 — Natural Ventilation")

        # 1. Identify climate type
        # brief.climate_zone may be the short type key ("hot_humid") used by CLIMATE_DATA,
        # OR the full TN zone key ("Coastal (Chennai, Pondicherry, Nagapattinam)") used by
        # TN_CLIMATE_ZONES in engine.py. Only the short key matches CLIMATE_DATA — when the
        # full key is passed, fall back to district-level lookup via _get_climate_type().
        district = brief.district
        raw_zone = getattr(brief, "climate_zone", None)
        climate_type = raw_zone if (raw_zone and raw_zone in CLIMATE_DATA) \
                       else _get_climate_type(district)
        cdata = CLIMATE_DATA.get(climate_type, CLIMATE_DATA["hot_dry"])

        self._log(f"District: {district} → Climate zone: {cdata['label']}")
        self._log(f"IMD design conditions: DB={cdata['design_db_c']}C, RH={cdata['rh_pct']}%")
        self._log(f"Prevailing wind: {cdata['prevailing_wind']} | CDD: {cdata['cdd']}")

        self._rec("Climate Zone", cdata["label"], "Classified from IMD district data", "IMD 1981-2010")
        self._rec("Design DB Temperature", f"{cdata['design_db_c']}°C", "IMD 99th percentile", "IMD 1981-2010")
        self._rec("Design Relative Humidity", f"{cdata['rh_pct']}%", "IMD average", "IMD 1981-2010")
        self._rec("Prevailing Wind Direction", cdata["prevailing_wind"], "", "IMD 1981-2010; ISHRAE 2016")
        self._rec("Cooling Degree Days", str(cdata["cdd"]), "Base 18C", "ISHRAE 2016")

        # 2. ECBC compliance targets
        self._log("ECBC 2017 compliance targets for this zone:")
        self._log(f"  Wall U-value: <= {cdata['ecbc_wall_u']} W/m2K")
        self._log(f"  Roof U-value: <= {cdata['ecbc_roof_u']} W/m2K")
        self._log(f"  Window-to-Wall Ratio: <= {cdata['ecbc_wwr']*100:.0f}%")

        self._rec("ECBC Max Wall U-value", f"{cdata['ecbc_wall_u']} W/m2K", "ECBC 2017 zone requirement", "ECBC 2017")
        self._rec("ECBC Max Roof U-value", f"{cdata['ecbc_roof_u']} W/m2K", "ECBC 2017", "ECBC 2017")
        self._rec("Max Window-to-Wall Ratio", f"{cdata['ecbc_wwr']*100:.0f}%", "ECBC 2017", "ECBC 2017")

        # 3. Overhang calculation
        lat_deg = {"hot_humid": 13, "hot_dry": 10, "composite": 11, "temperate": 11.5}.get(climate_type, 12)
        window_h = 1.8  # standard window height
        overhang = round(window_h * math.tan(math.radians(lat_deg)), 2)
        self._log(f"Overhang calc: lat={lat_deg}N, tan({lat_deg})={math.tan(math.radians(lat_deg)):.3f}, "
                  f"for {window_h}m window = {overhang}m projection")
        self._rec(
            "Recommended Roof Overhang",
            f"{overhang*1000:.0f}mm (for {window_h}m window height, lat {lat_deg}N)",
            "Baker overhang formula: projection = H x tan(latitude)",
            "Baker 1986; CEPT 2018",
        )

        # 4. Passive strategies
        self._log("Applicable passive design strategies:")
        for i, strat in enumerate(cdata["passive_strategies"], 1):
            self._log(f"  {i}. {strat}")

        self._rec(
            "Passive Design Strategies",
            " | ".join(cdata["passive_strategies"][:4]),
            "Top 4 strategies for this climate",
            "CEPT 2018; Baker 1986",
        )

        # 5. Window placement by room
        self._log("Room-level window placement rules:")
        for room, rule in cdata["window_rules"].items():
            self._rec(f"Window: {room.capitalize()}", rule, "Passive design rule", "CEPT 2018; NBC 2016")
            self._log(f"  {room}: {rule}")

        # 6. Risk flags
        for flag in cdata.get("risk_flags", []):
            self._warn(flag)
            self._log(f"  RISK: {flag}")

        # 7. Scores
        # (a) Base passive design potential: higher CDD = harder to achieve passive comfort
        # Formula: 100 − ((CDD − 200) × 0.015), floored at 40
        # hot_humid CDD=1980 → 73.3 | hot_dry CDD=2920 → 59.2 | composite CDD=2100 → 71.5
        base_passive = max(40, 100 - (cdata["cdd"] - 200) * 0.015)

        # (b) Courtyard bonus: adds passive cooling engine (+15 per COSTFORD 1993)
        courtyard_bonus = 15 if brief.wants_courtyard else 0

        # (c) Facing alignment with prevailing wind (IMD 1981-2010 wind rose data)
        # Plots whose entry face aligns with the prevailing wind inlet can achieve
        # better cross-ventilation without complex room rearrangement.
        # hot_humid SE wind: SE/S-facing optimal; W-facing worst (forces rooms against W wall).
        # hot_dry   SW wind: S-facing optimal (courtyard shades afternoon W sun).
        # Temperate  NE wind: S-facing maximises winter solar gain.
        _FACING_BONUS = {
            "hot_humid": {"SE": 5, "S": 3, "E": 0, "NE": -2, "N": 0,  "SW": -2, "NW": -3, "W": -5},
            "hot_dry":   {"S": 5, "SE": 3, "N": 2, "E": 2,   "NE": 0, "SW": 0,  "NW": -3, "W": -8},
            "composite": {"S": 4, "SE": 3, "SW": 0, "E": 0,  "N": -2, "NE": -2, "NW": -4, "W": -6},
            "temperate": {"S": 8, "SE": 5, "E": 2, "SW": 0,  "N": -6, "NE": -4, "NW": -6, "W": -8},
        }
        # Normalise facing string: "North" → "N", "Northeast" → "NE", etc.
        facing_raw = str(getattr(brief, "facing", "S")).strip().upper()
        _NORM = {"NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W",
                 "NORTHEAST": "NE", "NORTHWEST": "NW", "SOUTHEAST": "SE", "SOUTHWEST": "SW"}
        for full, abbr in _NORM.items():
            if facing_raw.startswith(full[:4]):
                facing_raw = abbr
                break
        facing_delta = _FACING_BONUS.get(climate_type, {}).get(facing_raw, 0)

        passive_score = min(100, base_passive + courtyard_bonus + facing_delta)
        self._score("Passive Design Potential", passive_score)

        self._log(f"Passive score: base={base_passive:.1f} + courtyard={courtyard_bonus} "
                  f"+ facing({facing_raw})={facing_delta:+d} = {passive_score:.1f}/100")
        self._rec("Facing Alignment", f"{facing_raw} ({facing_delta:+d} pts vs prevailing {cdata['prevailing_wind']} wind)",
                  "Facing-wind alignment affects cross-ventilation potential", "IMD 1981-2010; ISHRAE 2016")

        # (d) ECBC compliance likelihood — zone-specific, based on achievable U-values
        # with common TN construction: rat-trap bond (U=1.8 W/m²K) + tile/RCC roof.
        # hot_humid target: wall U≤0.75 — not met with plain rat-trap; needs insulated cavity.
        #   Roof tile (U~0.5) meets ≤0.40 target if well laid. Approx compliance 68%.
        # hot_dry: thick CEB/rat-trap (U~0.9 after cavity) + tile roof → ~72%.
        # composite: mixed — ~70%. temperate: stone walls + slate roof → ~78%.
        _ECBC_LIKELIHOOD = {"hot_humid": 68, "hot_dry": 72, "composite": 70, "temperate": 78}
        ecbc_score = _ECBC_LIKELIHOOD.get(climate_type, 70)
        self._score("ECBC Compliance Likelihood", ecbc_score)

        # (e) Climate severity (informational — lower = harder for passive design)
        self._score("Climate Severity (lower=harder)", max(20, 100 - cdata["cdd"] * 0.025))

        # 8. Summary
        out.summary = (
            f"Climate analysis for {district} ({cdata['label']}): "
            f"Design DB {cdata['design_db_c']}C, RH {cdata['rh_pct']}%, "
            f"prevailing wind {cdata['prevailing_wind']}. "
            f"Plot facing {facing_raw} ({facing_delta:+d} pts vs prevailing wind). "
            f"Primary challenge: {cdata['primary_challenge']}. "
            f"ECBC 2017 requires: wall U<={cdata['ecbc_wall_u']} W/m2K, "
            f"roof U<={cdata['ecbc_roof_u']} W/m2K, WWR<={cdata['ecbc_wwr']*100:.0f}%. "
            f"Recommended overhang: {overhang*1000:.0f}mm. "
            f"Passive design potential score: {passive_score:.0f}/100."
        )
        return out


_agent_instance = None


def _get_agent() -> ClimateAgent:
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = ClimateAgent()
    return _agent_instance


def analyze_climate(brief, context=None):
    """Entry point called by orchestrator."""
    return _get_agent().analyse(brief, context or {})
