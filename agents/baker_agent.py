"""
Baker Agent — Offline Laurie Baker Expert System
=================================================
Evaluates designs against Laurie Baker's principles of economical,
sustainable, and climate-responsive architecture.

Knowledge Base:
  - Baker L., "Cost Effective Architecture" (COSTFORD, 1986) — 6 core principles
  - Baker L., "Homes for the Masses" (COSTFORD, 1993)
  - Baker L., "Brick as a Building Material", COSTFORD Bulletin 12 (1984)
  - Baker L., "The Jali as Climate Modifier", Architecture+Design (1996)
  - CBRI Technical Report on Rat-Trap Bond Masonry (2008)
  - CEPT University, "Thermal Performance of Traditional Indian Walling Materials" (2014)
  - PWD Tamil Nadu Schedule of Rates 2023-24

Agent Type: Rule-based expert system (no API dependency)
"""

from typing import Any, Dict
from agents.base_agent import BaseAgent, AgentOutput

# Baker's Six Core Principles (Baker COSTFORD 1986 pp.34-78)
BAKER_PRINCIPLES = {
    "rat_trap_bond": {
        "label": "Rat-Trap Bond Brickwork",
        "condition": lambda b: True,
        "score_boost": 25,
        "detail": (
            "Bricks laid on edge create a hollow cavity — 25% fewer bricks vs solid 230mm wall. "
            "U-value: 1.8 W/m²K vs 3.5 for solid brick (reduces heat conduction ~30%). "
            "Cost: Rs.850/m2 plastered (PWD SoR 2023-24). CBRI confirms R=1.8 m2K/W."
        ),
        "ref": "Baker 1986 pp.34-41; CBRI 2008; PWD SoR 2023-24",
    },
    "jali_screen": {
        "label": "Brick Jali / Lattice Screen",
        "condition": lambda b: b.climate_zone in ("hot_humid", "composite"),
        "score_boost": 15,
        "detail": (
            "Perforated brick jali on W/SW elevations: 60% solar shading while preserving breeze. "
            "Cost: Rs.1,100/m2. Baker: 'A jali is cheaper than a curtain and lasts forever.' "
            "(COSTFORD Bulletin 3, 1981). Reduces indoor temp by 2-3 degC."
        ),
        "ref": "Baker 1996; COSTFORD Bulletin 3, 1981; CBRI 2008",
    },
    "central_courtyard": {
        "label": "Central Courtyard (Muttram)",
        "condition": lambda b: b.plot_area > 100,
        "score_boost": 20 if True else 20,  # full/partial credit logic in analyse()
        "detail": (
            "Open-to-sky muttram drives stack ventilation. Minimum 9m2 for ventilation effect. "
            "Ventilation multiplier: 1.4x vs corridor-plan house (CEPT 2014). "
            "Traditional: Chettinad, Agraharam typology (INTACH 2004)."
        ),
        "ref": "Baker 1986; CEPT 2014; Meenakshi Rm., INTACH 2004",
    },
    "deep_overhangs": {
        "label": "Deep Roof Overhangs (600-900mm)",
        "condition": lambda b: b.climate_zone in ("hot_humid", "hot_dry", "composite"),
        "score_boost": 10,
        "detail": (
            "600-900mm overhang blocks high summer sun. "
            "Formula: projection = window_height x tan(latitude). "
            "Chennai (13N): 820mm for 2m window. Reduces cooling load 15-20%."
        ),
        "ref": "Baker 1986; CEPT Passive Cooling Guide 2018",
    },
    "local_materials": {
        "label": "Local Material Minimalism",
        "condition": lambda b: True,
        "score_boost": 15,
        "detail": (
            "Baker: 'Import nothing that can be made here.' Country brick (Ariyalur): Rs.5/brick. "
            "Mangalore tile: Rs.450/m2 vs RCC slab Rs.1,800/m2. "
            "Lime plaster (Ariyalur lime): Rs.320/m2 vs cement plaster Rs.420/m2."
        ),
        "ref": "Baker 1993 'Homes for the Masses'; PWD SoR 2023-24",
    },
    "cross_ventilation": {
        "label": "Natural Cross-Ventilation",
        "condition": lambda b: True,
        "score_boost": 15,
        "detail": (
            "Align inlet opposite outlet relative to prevailing wind. "
            "Baker: 'Every room must breathe on its own.' "
            "NBC 2016 Part 8 Cl. 5.1 requires window area >= 10% of floor area."
        ),
        "ref": "Baker 1986; NBC 2016 Part 8 Sec 1 Cl. 5.1",
    },
}

BAKER_COST_SAVINGS = {
    "rat_trap_vs_solid": 0.25,
    "mangalore_vs_rcc_roof": 0.72,
    "lime_vs_cement_plaster": 0.24,
    "total_min_pct": 0.30,
    "total_max_pct": 0.42,
}

BUDGET_TIER_SQFT = {
    "Economy":  {"low": 1200, "high": 1600},
    "Standard": {"low": 1600, "high": 2200},
    "Premium":  {"low": 2200, "high": 3500},
}


class BakerAgent(BaseAgent):
    """Offline expert system embodying Laurie Baker's design philosophy."""

    def __init__(self):
        super().__init__(
            name="Baker Agent",
            domain="Sustainable Construction & Cost-Effective Architecture",
        )

    def load_knowledge(self):
        try:
            from data.materials_db import MATERIALS_DATABASE
            self._materials = MATERIALS_DATABASE
        except ImportError:
            self._materials = {}

    def analyse(self, brief: Any, context: Dict[str, Any]) -> AgentOutput:
        out = self._init_output()
        self._ref("Baker L., 'Cost Effective Architecture' (COSTFORD, 1986)")
        self._ref("CBRI Technical Report on Rat-Trap Bond Masonry (2008)")
        self._ref("PWD Tamil Nadu Schedule of Rates 2023-24")
        self._ref("CEPT, 'Thermal Performance of Walling Materials' (2014)")

        # 1. Evaluate each principle
        self._log("Evaluating Baker's 6 core principles against client brief")
        applicable_score = 0
        max_score = sum(p["score_boost"] for p in BAKER_PRINCIPLES.values())

        for key, principle in BAKER_PRINCIPLES.items():
            applies = principle["condition"](brief)
            if applies:
                # Courtyard: partial credit if recommended but not selected
                if key == "central_courtyard" and not brief.wants_courtyard:
                    partial = 8  # 8 out of 20 — Baker recommends but user didn't select
                    applicable_score += partial
                    self._rec(principle["label"],
                              principle["detail"] + " (Recommended but not selected — partial credit)",
                              f"Applicable: plot={brief.plot_area}m2 qualifies, courtyard recommended",
                              principle["ref"])
                    self._log(f"  PARTIAL {principle['label']} (+{partial}/{principle['score_boost']} pts — no courtyard selected)")
                else:
                    applicable_score += principle["score_boost"]
                    self._rec(principle["label"], principle["detail"],
                              f"Applicable: climate={brief.climate_zone}, plot={brief.plot_area}m2",
                              principle["ref"])
                    self._log(f"  PASS {principle['label']} (+{principle['score_boost']} pts)", principle["ref"])
            else:
                self._log(f"  SKIP {principle['label']} (condition not met for this brief)")

        baker_score = round(applicable_score / max_score * 100, 1) if max_score else 50.0
        self._score("Baker Principles Score", baker_score)
        self._log(f"Baker principle score: {baker_score}/100 ({applicable_score}/{max_score} pts)")

        # 2. Cost impact
        self._log("Computing cost savings vs conventional RCC construction")
        plot_area = brief.plot_area
        built_up_sqft = plot_area * 0.55 * 10.764  # m2 -> sqft, 55% coverage

        tier = BUDGET_TIER_SQFT.get(brief.budget_tier, {"low": 1600, "high": 2200})
        conv_total = tier["high"] * built_up_sqft
        baker_total = tier["low"] * (1 - BAKER_COST_SAVINGS["total_min_pct"]) * built_up_sqft
        saving = conv_total - baker_total

        self._score("Cost Efficiency", min(100, baker_score * 0.9 + 10))
        self._rec(
            "Estimated Cost Saving",
            f"Rs.{saving:,.0f} ({int(BAKER_COST_SAVINGS['total_min_pct']*100)}-"
            f"{int(BAKER_COST_SAVINGS['total_max_pct']*100)}% vs conventional RCC)",
            f"Built-up ~{built_up_sqft/10.764:.0f}m2 at Rs.{tier['high']}/sqft conventional",
            "PWD SoR 2023-24; Baker 1986",
        )

        # 3. Material recommendations by climate
        climate = brief.climate_zone
        if climate == "hot_dry":
            walling = "Compressed Earth Block (CEB) — lowest embodied CO2 (8 kg/m2)"
        elif climate == "temperate":
            walling = "Granite rubble masonry (Salem/Namakkal source)"
        else:
            walling = "Rat-Trap Bond (country brick, Ariyalur source) — U=1.8 W/m2K"

        roof = ("Stone slab + lime plaster" if climate == "temperate"
                else "Mangalore Clay Tile on timber rafter (Rs.450/m2 vs RCC Rs.1,800/m2)")

        self._rec("Walling System", walling, "Baker-preferred for climate zone", "Baker 1986; CEPT 2014")
        self._rec("Roofing System", roof, "75% cheaper than RCC slab", "Baker 1989; TERI 2018")
        self._rec("Flooring", "Athangudi handmade tile (Sivagangai) for living areas; Kota stone for wet areas",
                  "Stays cool, local GI-tagged product", "Baker 1986; GI Tag Athangudi Tile 2020")
        self._rec("Mortar/Plaster", "Hydraulic lime-sand 1:3 (Ariyalur lime)",
                  "Breathable — prevents salt efflorescence", "Baker Bulletin 12, 1984")

        # 4. Challenges
        if brief.budget_tier == "Premium":
            self._warn("Baker would challenge premium finishes — redirect budget to courtyard/roof quality instead.")
        if not brief.wants_courtyard and brief.plot_area > 100:
            self._warn(
                f"Plot {brief.plot_area}m2 is large enough for a muttram (min 9m2). "
                "Baker would insist on a courtyard for stack ventilation (CEPT 1.4x multiplier)."
            )
        if climate in ("hot_humid", "hot_dry"):
            self._warn(
                "Eliminate ALL west-facing bedroom windows. Afternoon solar heat gain "
                "makes west bedrooms uninhabitable. (CEPT Passive Cooling Guide 2018)"
            )

        # 5. Sustainability score
        courtyard_bonus = 20 if brief.wants_courtyard else 0
        sustainability = min(100, baker_score * 0.7 + courtyard_bonus + 10)
        self._score("Sustainability Rating", sustainability)

        principle_count = sum(1 for p in BAKER_PRINCIPLES.values() if p["condition"](brief))
        out.summary = (
            f"Baker assessment for {brief.bhk}, {brief.plot_area}m2, {brief.district}: "
            f"{principle_count}/6 Baker principles applicable. "
            f"Adopting rat-trap bond + local materials can save Rs.{saving:,.0f} "
            f"({int(BAKER_COST_SAVINGS['total_min_pct']*100)}-{int(BAKER_COST_SAVINGS['total_max_pct']*100)}%) "
            f"vs conventional RCC. Key walling: {walling}. Baker score: {baker_score}/100."
        )
        return out


_agent_instance = None


def _get_agent() -> BakerAgent:
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = BakerAgent()
    return _agent_instance


def analyze_baker(brief, context=None):
    """Entry point called by orchestrator."""
    return _get_agent().analyse(brief, context or {})
