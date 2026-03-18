"""
Regulatory Agent — Offline Tamil Nadu Building Regulations Expert System
=========================================================================
Applies TNCDBR 2019, NBC 2016, CMDA 2022, and local body rules
to compute setbacks, room minima, FSI, and flag compliance issues.

Knowledge Base:
  - data/nbc_standards.py (NBC_ROOM_MINIMUMS, NBC_VENTILATION)
  - data/tn_setbacks.py (TNCDBR_SETBACKS_BY_PLOT_AREA, compute_usable_area)
  - NBC 2016 Part 3 Cl. 8.1 — Room Minimums
  - TNCDBR 2019 G.O. Ms. No. 78 — Setbacks Schedule I
  - CMDA Development Control Regulations 2022
  - Tamil Nadu Town and Country Planning Act 1971 (as amended 2019)

Agent Type: Rule-based constraint checking system
"""

from typing import Any, Dict, List, Tuple
from agents.base_agent import BaseAgent, AgentOutput

# ── NBC 2016 Room Minimums (Part 3, Clause 8.1) ───────────────────────────────
NBC_MINIMUMS = {
    "living":   {"area": 12.0, "width": 3.0,  "ref": "NBC 2016 Part 3 Cl. 8.1.a"},
    "bedroom":  {"area": 9.5,  "width": 2.4,  "ref": "NBC 2016 Part 3 Cl. 8.1.b (principal)"},
    "kitchen":  {"area": 5.0,  "width": 1.8,  "ref": "NBC 2016 Part 3 Cl. 8.1.c"},
    "bathroom": {"area": 2.8,  "width": 1.2,  "ref": "NBC 2016 Part 3 Cl. 8.1.d"},
    "toilet":   {"area": 1.2,  "width": 0.9,  "ref": "NBC 2016 Part 3 Cl. 8.1.e"},
    "utility":  {"area": 2.5,  "width": 1.2,  "ref": "NBC 2016 Part 3 Cl. 8.1 (ancillary)"},
    "store":    {"area": 0.0,  "width": 0.0,  "ref": "NBC 2016 — no minimum specified"},
    "pooja":    {"area": 0.0,  "width": 0.0,  "ref": "NBC 2016 — treated as store"},
    "corridor": {"area": 0.0,  "width": 0.9,  "ref": "NBC 2016 — min 900mm width"},
    "verandah": {"area": 0.0,  "width": 1.2,  "ref": "NBC 2016 — min 1.2m depth"},
    "dining":   {"area": 7.5,  "width": 2.4,  "ref": "NBC 2016 (recommended, not mandatory)"},
}

# ── TNCDBR 2019 Setbacks (G.O. Ms. No. 78, Schedule I) ───────────────────────
TNCDBR_SETBACKS = [
    (75,   {"front": 1.0, "rear": 1.0, "side": 0.75}),   # plot < 75m2
    (200,  {"front": 1.5, "rear": 1.5, "side": 1.0}),    # 75-200m2
    (500,  {"front": 2.0, "rear": 1.5, "side": 1.2}),    # 200-500m2
    (1000, {"front": 3.0, "rear": 2.0, "side": 1.5}),    # 500-1000m2
    (9999, {"front": 4.5, "rear": 3.0, "side": 2.0}),    # >1000m2
]

# ── FSI by local body ─────────────────────────────────────────────────────────
FSI_RULES = {
    "CMDA (inside ring road)":   {"far": 2.0, "ground_coverage": 0.70},
    "CMDA (outside ring road)":  {"far": 1.5, "ground_coverage": 0.70},
    "Municipal Corporation":     {"far": 1.5, "ground_coverage": 0.75},
    "Municipality (DTCP)":       {"far": 1.5, "ground_coverage": 0.75},
    "Town Panchayat":            {"far": 1.5, "ground_coverage": 0.75},
    "Village Panchayat":         {"far": 1.5, "ground_coverage": 0.75},
    "Hill Station (TNHDB)":      {"far": 1.0, "ground_coverage": 0.50},
}

# ── CMDA road setbacks (DCR 2022, Rule 12) ───────────────────────────────────
CMDA_ROAD_SETBACKS = [
    (6,  1.0),   # road < 6m
    (9,  1.5),   # 6-9m
    (12, 2.0),   # 9-12m
    (18, 3.0),   # 12-18m
    (30, 4.5),   # 18-30m
    (99, 6.0),   # >30m
]

# ── BHK typical room counts ───────────────────────────────────────────────────
BHK_ROOMS = {
    "1BHK": {"living": 1, "kitchen": 1, "bedroom": 1, "bathroom": 1},
    "2BHK": {"living": 1, "dining": 1, "kitchen": 1, "bedroom": 2, "bathroom": 2},
    "3BHK": {"living": 1, "dining": 1, "kitchen": 1, "bedroom": 3, "bathroom": 2,
              "utility": 1, "corridor": 1},
    "4BHK": {"living": 1, "dining": 1, "kitchen": 1, "bedroom": 4, "bathroom": 3,
              "utility": 1, "corridor": 1},
}


def _get_setbacks(plot_area: float) -> Dict:
    for threshold, setbacks in TNCDBR_SETBACKS:
        if plot_area <= threshold:
            return setbacks
    return TNCDBR_SETBACKS[-1][1]


def _usable_area(plot_w: float, plot_h: float, setbacks: Dict) -> Tuple[float, float, float]:
    usable_w = max(0, plot_w - setbacks["side"] * 2)
    usable_h = max(0, plot_h - setbacks["front"] - setbacks["rear"])
    usable_area = usable_w * usable_h
    return usable_w, usable_h, usable_area


class RegulatoryAgent(BaseAgent):
    """Offline building regulations expert: TNCDBR 2019 + NBC 2016 + CMDA 2022."""

    def __init__(self):
        super().__init__(
            name="Regulatory Agent",
            domain="NBC 2016 & TNCDBR 2019 Compliance Analysis",
        )

    def load_knowledge(self):
        try:
            from data.nbc_standards import NBC_ROOM_MINIMUMS, check_nbc_compliance
            from data.tn_setbacks import get_setback_for_plot, compute_usable_area
            self._check_nbc = check_nbc_compliance
            self._get_setback = get_setback_for_plot
            self._usable_fn = compute_usable_area
            self._nbc_db = NBC_ROOM_MINIMUMS
        except ImportError:
            self._check_nbc = None
            self._get_setback = None
            self._usable_fn = None
            self._nbc_db = NBC_MINIMUMS

    def analyse(self, brief: Any, context: Dict[str, Any]) -> AgentOutput:
        out = self._init_output()
        self._ref("NBC 2016 Part 3 Clause 8.1 — Room Size Minimums")
        self._ref("NBC 2016 Part 8 Section 1 Clause 5.1 — Ventilation")
        self._ref("TNCDBR 2019 G.O. Ms. No. 78, Housing and Urban Development Dept.")
        self._ref("CMDA Development Control Regulations 2022")

        plot_area = brief.plot_area
        bhk = brief.bhk
        district = brief.district
        num_floors = getattr(brief, "num_floors", "G+1")
        local_body = getattr(brief, "local_body", "Municipality (DTCP)")
        road_width = getattr(brief, "road_width", None)
        special_zone = getattr(brief, "special_zone", None)

        # 1. Setbacks
        self._log(f"Computing TNCDBR 2019 setbacks for plot area: {plot_area}m2")
        setbacks = _get_setbacks(plot_area)
        self._log(f"  Setbacks: front={setbacks['front']}m, rear={setbacks['rear']}m, "
                  f"side={setbacks['side']}m each")

        self._rec("Front Setback", f"{setbacks['front']}m",
                  f"TNCDBR 2019 Schedule I for plot {plot_area}m2",
                  "TNCDBR 2019 G.O. Ms. No. 78")
        self._rec("Rear Setback", f"{setbacks['rear']}m",
                  "TNCDBR 2019", "TNCDBR 2019 G.O. Ms. No. 78")
        self._rec("Side Setbacks", f"{setbacks['side']}m each side",
                  "TNCDBR 2019", "TNCDBR 2019 G.O. Ms. No. 78")

        # Road setback override check
        if road_width:
            try:
                rw = float(str(road_width).replace("m", "").strip())
                for threshold, road_sb in CMDA_ROAD_SETBACKS:
                    if rw <= threshold:
                        if road_sb > setbacks["front"]:
                            self._warn(
                                f"Road width {rw}m triggers CMDA DCR front setback of {road_sb}m "
                                f"(overrides TNCDBR {setbacks['front']}m). Use {road_sb}m."
                            )
                            setbacks["front"] = road_sb
                        break
            except ValueError:
                pass

        # Usable plot dimensions (square approximation)
        import math
        side = math.sqrt(plot_area)
        plot_w, plot_h = side, side
        usable_w, usable_h, usable = _usable_area(plot_w, plot_h, setbacks)
        usable_sqft = usable * 10.764

        self._log(f"  Usable plot: {usable_w:.1f}m x {usable_h:.1f}m = {usable:.1f}m2 ({usable_sqft:.0f}sqft)")
        self._rec(
            "Usable Plot Area",
            f"{usable:.1f}m2 ({usable_sqft:.0f} sqft) after setbacks",
            f"From {plot_area}m2 plot minus {setbacks['front']+setbacks['rear']}m front+rear, "
            f"{setbacks['side']*2}m both sides",
            "TNCDBR 2019",
        )

        # 2. FSI / FAR limits
        fsi_rule = FSI_RULES.get(local_body, FSI_RULES["Municipality (DTCP)"])
        far = fsi_rule["far"]
        gc = fsi_rule["ground_coverage"]
        max_ground = usable * gc
        max_total = plot_area * far

        self._log(f"  FSI/FAR: {far} | Ground coverage max: {gc*100:.0f}%")
        self._log(f"  Max ground coverage: {max_ground:.0f}m2 | Max total built-up: {max_total:.0f}m2")

        self._rec("Floor Space Index (FSI/FAR)", str(far),
                  f"For {local_body}", "CMDA DCR 2022 / TNCDBR 2019")
        self._rec("Max Ground Coverage", f"{max_ground:.0f}m2 ({gc*100:.0f}% of usable area)",
                  "Ground floor footprint limit", "TNCDBR 2019")
        self._rec("Max Total Built-up Area",
                  f"{max_total:.0f}m2 ({max_total*10.764:.0f} sqft)",
                  f"FSI {far} x plot area {plot_area}m2", "TNCDBR 2019")

        # 3. Height limits
        height_map = {
            "G+0": (5.0, False),
            "G+1": (8.5, False),
            "G+2": (11.5, True),
            "G+3": (14.5, True),
        }
        max_h, fire_noc = height_map.get(num_floors, (8.5, False))
        self._rec("Maximum Building Height", f"{max_h}m ({num_floors})",
                  "NBC Part 4 fire regulations", "NBC 2016 Part 4; CMDA DCR 2022")
        if fire_noc:
            self._warn(f"Fire NOC required for {num_floors} — submit to Tamil Nadu Fire & Rescue Services.")

        # 4. NBC room-by-room compliance check
        self._log(f"Checking NBC 2016 room minimums for {bhk}")
        room_counts = BHK_ROOMS.get(bhk, BHK_ROOMS["2BHK"])
        violations: List[str] = []
        total_min_area = 0.0

        for room_type, count in room_counts.items():
            nbc = NBC_MINIMUMS.get(room_type, {"area": 0, "width": 0, "ref": "—"})
            min_area = nbc["area"]
            min_width = nbc["width"]
            total_min_area += min_area * count

            if min_area > 0:
                self._log(f"  {room_type.capitalize()} x{count}: min {min_area}m2, min width {min_width}m "
                          f"[{nbc['ref']}]")
                self._rec(
                    f"NBC Min: {room_type.capitalize()} (x{count})",
                    f"{min_area}m2 area, {min_width}m width",
                    f"Required per unit", nbc["ref"],
                )
            else:
                self._log(f"  {room_type.capitalize()}: no NBC minimum")

        self._log(f"  Total minimum area for {bhk}: {total_min_area:.1f}m2")
        self._rec("Minimum Total Room Area",
                  f"{total_min_area:.1f}m2 (NBC 2016 mandatory minimums)",
                  f"Sum of all room minimums for {bhk}",
                  "NBC 2016 Part 3 Cl. 8.1")

        if total_min_area > usable:
            self._warn(
                f"WARNING: Minimum room area ({total_min_area:.1f}m2) EXCEEDS usable plot area "
                f"({usable:.1f}m2). Consider G+1 to double floor area, or reduce BHK type."
            )

        # 5. NBC ventilation
        self._log("NBC 2016 ventilation requirements:")
        self._rec("Ventilation Rule", "Window area >= 10% of floor area per habitable room",
                  "Mandatory per NBC 2016 Part 8 Cl. 5.1",
                  "NBC 2016 Part 8 Sec 1 Cl. 5.1")
        self._rec("Min Openable Window", ">=50% of window area must be openable",
                  "NBC 2016 Cl. 5.1", "NBC 2016 Part 8 Sec 1 Cl. 5.1")
        self._rec("Dedicated Kitchen Exhaust", "Exhaust opening or chimney mandatory",
                  "NBC 2016 Cl. 5.1", "NBC 2016 Part 8 Sec 1 Cl. 5.1")

        # 6. Special zones
        coastal_districts = ["nagapattinam", "cuddalore", "chennai", "pondicherry",
                              "thanjavur", "tiruvarur", "kanyakumari", "ramanathapuram"]
        hill_districts = ["nilgiris", "ooty", "kodaikanal", "yercaud"]
        dist_lower = district.lower()

        is_coastal = any(d in dist_lower for d in coastal_districts)
        is_hill = any(d in dist_lower for d in hill_districts)

        if is_coastal:
            self._warn("CRZ COMPLIANCE REQUIRED: Check for CRZ-I (500m HTL), CRZ-II, or CRZ-III (200m HTL) designation.")
            self._warn("High cyclone risk: NBC wind design speed 50 m/s minimum (Very High Damage Risk Zone).")
            self._warn("Plinth minimum 600mm above finished road level for flood protection.")
            self._rec("CRZ Check", "Required — consult TNCZMA before submitting plan",
                      "Coastal Regulation Zone (MoEFCC)", "CRZ Notification 2019; TNCZMA")

        if is_hill:
            self._warn("Hill station rules apply: FAR 1.0, max 50% ground coverage (TNHDB Rules).")
            self._warn("Slope stability assessment required for plots on gradients > 1:4.")

        if special_zone and special_zone.lower() != "none":
            self._warn(f"Special zone declared: {special_zone} — check with local authority for additional restrictions.")

        # 7. Approval pathway
        approval_body = "CMDA" if "chennai" in dist_lower or "cmda" in (local_body or "").lower() else "Local Panchayat / Municipality (DTCP)"
        self._rec("Approval Authority", approval_body, "Based on district and local body type", "TNCDBR 2019")
        self._rec(
            "Approval Timeline",
            "45–90 days (online via TN DIGI-APAS portal for CMDA areas)",
            "Required steps: Plan submission → Site inspection → Commencement certificate",
            "Tamil Nadu DIGI-APAS; TNCDBR 2019",
        )

        # 8. Scores
        feasibility = 100
        if total_min_area > usable:
            feasibility -= 40
        if is_coastal:
            feasibility -= 15
        if fire_noc:
            feasibility -= 5

        self._score("Regulatory Feasibility", max(30, feasibility))
        self._score("NBC Compliance Likelihood", 80 if total_min_area <= usable * 0.85 else 50)
        self._score("Setback Compliance", 90)  # setbacks are deterministic from tables

        out.summary = (
            f"Regulatory brief for {bhk}, {plot_area}m2 plot in {district}: "
            f"Setbacks — front {setbacks['front']}m, rear {setbacks['rear']}m, sides {setbacks['side']}m. "
            f"Usable area: {usable:.1f}m2. FSI {far} allows max {max_total:.0f}m2 built-up. "
            f"NBC minimum room area: {total_min_area:.1f}m2 "
            f"({'OK' if total_min_area <= usable else 'EXCEEDS usable — consider G+1'}). "
            f"Max height: {max_h}m ({num_floors}). "
            f"{'Coastal CRZ check required. ' if is_coastal else ''}"
            f"Regulatory feasibility: {max(30, feasibility)}/100."
        )
        return out


_agent_instance = None


def _get_agent() -> RegulatoryAgent:
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = RegulatoryAgent()
    return _agent_instance


def analyze_regulatory(brief, context=None):
    """Entry point called by orchestrator."""
    return _get_agent().analyse(brief, context or {})
