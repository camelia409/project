"""
Material Agent — Offline Tamil Nadu Local Materials Expert System
=================================================================
Recommends locally sourced building materials by district, climate zone,
and budget tier using the MATERIALS_DATABASE knowledge base.

Knowledge Base:
  - data/materials_db.py (MATERIALS_DATABASE — thermal + cost data)
  - PWD Tamil Nadu Schedule of Rates 2023-24
  - CEPT "Thermal Performance of Traditional Indian Walling Materials" (2014)
  - TERI "Energy Efficiency in South Indian Homes" (2018)
  - Baker L., "Cost Effective Architecture" (COSTFORD, 1986)
  - GI Tag documentation: Athangudi Tile (TN), 2020
  - NIRD "Low-Cost Housing Technologies" (2015)

Agent Type: Rule-based expert system with scored material selection
"""

from typing import Any, Dict, List
from agents.base_agent import BaseAgent, AgentOutput

# ── District-level material sourcing map ──────────────────────────────────────
# Source: Madurai Institute of Architecture field survey 2023-24; PWD SoR 2023-24
DISTRICT_SOURCING = {
    "ariyalur":     ["country brick (cheapest TN source)", "lime"],
    "sivagangai":   ["athangudi handmade tile (exclusive)"],
    "salem":        ["granite rubble", "rough stone"],
    "namakkal":     ["granite rubble"],
    "trichy":       ["country brick", "flat clay tile"],
    "thanjavur":    ["flat clay tile", "country brick"],
    "tirunelveli":  ["stabilised mud block (SMB)", "laterite"],
    "coimbatore":   ["CEB (machines available)", "western ghats stone"],
    "madurai":      ["limestone", "country brick"],
    "chennai":      ["all materials (15-25% transport premium)"],
    "vellore":      ["granite", "country brick"],
    "dharmapuri":   ["granite", "SMB"],
}

# ── Walling material options (keyed from MATERIALS_DATABASE) ─────────────────
WALLING_OPTIONS = {
    "hot_humid": [
        ("rat_trap_bond_brick", 1, "Primary — thermal cavity + breathable lime plaster"),
        ("fly_ash_brick",       2, "Alternative — recycled industrial waste, good strength"),
        ("aac_block",           3, "Only if AC-cooled building is planned"),
    ],
    "hot_dry": [
        ("rat_trap_bond_brick",       1, "Preferred — thermal cavity reduces peak temp in hot-dry zone"),
        ("country_brick_solid_115mm", 2, "Fallback — widely available if rat-trap not possible"),
    ],
    "composite": [
        ("rat_trap_bond_brick", 1, "Best all-round for Tamil Nadu composite zone"),
        ("fly_ash_brick",       2, "Good alternative, recycled content"),
    ],
    "temperate": [
        ("rat_trap_bond_brick", 1, "With lime plaster for moisture management"),
    ],
}

# ── Roofing by climate ────────────────────────────────────────────────────────
ROOFING_OPTIONS = {
    "hot_humid":   ("mangalore_tile_timber_roof",         "Traditional — self-ventilating, Rs.450/m2 vs RCC Rs.1,800/m2"),
    "hot_dry":     ("rcc_flat_roof_inverted_insulation",  "RCC+XPS insulation needed — CDD 2,920 requires ECBC U<=0.33"),
    "composite":   ("mangalore_tile_timber_roof",         "Preferred — monsoon shedding + ventilation"),
    "temperate":   ("rcc_flat_roof_inverted_insulation",  "Sloped RCC with insulation — cold nights require U<=0.80"),
}

# ── Flooring by budget tier ───────────────────────────────────────────────────
FLOORING_OPTIONS = {
    "Economy":  {"living": "kota_stone (Rs.420/m2)", "wet": "ceramic tile (Rs.280/m2)"},
    "Standard": {"living": "athangudi_tile (Rs.550/m2 — Sivagangai GI tag)", "wet": "kota_stone"},
    "Premium":  {"living": "athangudi_tile custom pattern (Rs.800/m2+)", "wet": "kota_stone or marble"},
}

# ── Embodied CO2 benchmarks (kg/m2 wall) ─────────────────────────────────────
CO2_BENCHMARK = {
    "rat_trap_bond_brick":        28,
    "fly_ash_brick":              18,
    "aac_block":                  35,
    "country_brick_solid_115mm":  42,
    "conventional_rcc":           85,
}


class MaterialAgent(BaseAgent):
    """Offline expert system for locally sourced Tamil Nadu building materials."""

    def __init__(self):
        super().__init__(
            name="Material Agent",
            domain="Local Materials Selection & Embodied Carbon Analysis",
        )

    def load_knowledge(self):
        try:
            from data.materials_db import MATERIALS_DATABASE, get_materials_for_climate
            self._db = MATERIALS_DATABASE
            self._get_by_climate = get_materials_for_climate
        except ImportError:
            self._db = {}
            self._get_by_climate = lambda x: []

    def analyse(self, brief: Any, context: Dict[str, Any]) -> AgentOutput:
        out = self._init_output()
        self._ref("PWD Tamil Nadu Schedule of Rates 2023-24")
        self._ref("CEPT, 'Thermal Performance of Traditional Indian Walling Materials' (2014)")
        self._ref("TERI, 'Energy Efficiency in South Indian Homes' (2018)")
        self._ref("Baker L., 'Cost Effective Architecture' (COSTFORD, 1986)")
        self._ref("ECBC 2017 — Material thermal property appendix")

        climate = getattr(brief, "climate_zone", "hot_humid")
        district = brief.district.lower()
        budget = brief.budget_tier
        plot_area = brief.plot_area
        built_up_m2 = plot_area * 0.55  # typical 55% ground coverage

        # 1. Local sourcing opportunities
        self._log(f"Checking local material sources for district: {district}")
        local_sources = []
        for d_key, materials in DISTRICT_SOURCING.items():
            if d_key in district or district in d_key:
                local_sources = materials
                break
        if not local_sources:
            local_sources = ["country brick (from nearest Ariyalur belt)", "lime mortar"]
        self._log(f"  Local sources identified: {', '.join(local_sources)}")
        self._rec("Local Material Sources", ", ".join(local_sources),
                  "Field survey data: MIA 2023-24", "PWD SoR 2023-24; MIA 2023-24")

        # 2. Walling selection
        self._log(f"Selecting walling system for climate zone: {climate}")
        walling_opts = WALLING_OPTIONS.get(climate, WALLING_OPTIONS["hot_dry"])
        primary_wall_key, _, wall_reason = walling_opts[0]
        wall_data = self._db.get(primary_wall_key, {})

        wall_u = wall_data.get("u_value_w_m2k", 1.8)
        wall_cost = wall_data.get("cost_per_sqm_inr_2024", 850)
        wall_co2 = wall_data.get("co2_kg_per_m2_wall", 28)
        wall_name = wall_data.get("full_name", primary_wall_key.replace("_", " ").title())

        self._log(f"  Primary walling: {wall_name}")
        self._log(f"  U-value: {wall_u} W/m2K | Cost: Rs.{wall_cost}/m2 | CO2: {wall_co2} kg/m2")
        self._rec("Primary Walling System", f"{wall_name} — Rs.{wall_cost}/m2, U={wall_u} W/m2K",
                  wall_reason, "CEPT 2014; ECBC 2017")

        # 3. Roofing selection
        self._log(f"Selecting roofing for climate zone: {climate}")
        roof_key, roof_reason = ROOFING_OPTIONS.get(climate, ROOFING_OPTIONS["hot_humid"])
        roof_data = self._db.get(roof_key, {})
        roof_u = roof_data.get("u_value_w_m2k", 1.4)
        roof_cost = roof_data.get("cost_per_sqm_inr_2024", 900)
        roof_name = roof_data.get("full_name", roof_key.replace("_", " ").title())

        self._log(f"  Roofing: {roof_name}")
        self._log(f"  U-value: {roof_u} W/m2K | Cost: Rs.{roof_cost}/m2")
        self._rec("Roofing System", f"{roof_name} — Rs.{roof_cost}/m2, U={roof_u} W/m2K",
                  roof_reason, "TERI 2018; Baker 1989; ECBC 2017")

        # 4. Flooring selection
        floor_opts = FLOORING_OPTIONS.get(budget, FLOORING_OPTIONS["Standard"])
        self._rec("Living Area Flooring", floor_opts["living"], "Budget-appropriate local material",
                  "Baker 1986; GI Tag Athangudi Tile 2020")
        self._rec("Wet Area Flooring", floor_opts["wet"], "Durable, slip-resistant", "Baker 1986")

        # 5. Mortar & plaster
        self._rec(
            "Mortar & Plaster",
            "Hydraulic lime-sand 1:3 (Ariyalur lime) — Rs.320/m2 (24% cheaper than cement plaster)",
            "Breathable — prevents salt efflorescence. Baker mandates over OPC cement.",
            "Baker Bulletin 12, 1984; IS 712",
        )

        # 6. Jali screen (climate-specific)
        if climate in ("hot_humid", "composite"):
            jali_data = self._db.get("jali_screen_brick", {})
            jali_cost = jali_data.get("cost_per_sqm_inr_2024", 1100)
            self._rec("Ventilation Element", f"Brick Jali Screen — Rs.{jali_cost}/m2 (W/SW elevations only)",
                      "85% open area for airflow, 75% solar shading coefficient",
                      "Baker 1996; CBRI 2008")

        # 7. Embodied carbon analysis
        self._log("Computing embodied carbon vs conventional RCC construction")
        conv_co2 = CO2_BENCHMARK["conventional_rcc"]
        actual_co2 = wall_co2
        co2_saving_pct = round((conv_co2 - actual_co2) / conv_co2 * 100, 1)

        wall_area_m2 = 2 * (built_up_m2 ** 0.5) * 3.0 * 4  # rough perimeter * height
        total_co2_saved = (conv_co2 - actual_co2) * wall_area_m2
        self._rec(
            "Embodied Carbon Reduction",
            f"{co2_saving_pct}% less CO2 vs solid RCC ({actual_co2} vs {conv_co2} kg/m2)",
            f"Approx. {total_co2_saved:,.0f} kg CO2 saved for this project",
            "ECBC 2017 Annex; CEPT 2014",
        )
        self._log(f"  CO2 saving: {co2_saving_pct}% ({total_co2_saved:,.0f} kg for project)")

        # 8. Cost estimate
        walling_total = wall_cost * wall_area_m2
        roofing_total = roof_cost * built_up_m2
        flooring_total = 500 * built_up_m2  # avg flooring
        material_total = walling_total + roofing_total + flooring_total
        self._log(f"  Material cost estimate: Rs.{material_total:,.0f}")
        self._rec(
            "Estimated Material Cost",
            f"Rs.{material_total:,.0f} (wall+roof+floor for ~{built_up_m2:.0f}m2)",
            "Walling + Roofing + Flooring totals",
            "PWD SoR 2023-24",
        )

        # 9. What to avoid
        avoid_list = []
        if climate in ("hot_humid", "hot_dry"):
            avoid_list.append("AAC blocks without AC — low thermal mass causes extreme indoor temp swings")
        if "chennai" in district or "coast" in district:
            avoid_list.append("Stabilised Mud Block (SMB) — salt ingress within 5km of coast")
        avoid_list.append("RCC flat slab without insulation — U=3.8 W/m2K, ECBC non-compliant")
        for a in avoid_list:
            self._warn(f"AVOID: {a}")

        # 10. Scores
        u_score = max(0, min(100, (3.5 - wall_u) / (3.5 - 0.5) * 100))
        cost_score = max(0, min(100, (2000 - wall_cost) / (2000 - 350) * 100))
        co2_score = max(0, min(100, co2_saving_pct * 1.5))
        self._score("Thermal Performance", u_score)
        self._score("Cost Efficiency", cost_score)
        self._score("Embodied Carbon", co2_score)
        self._score("Local Sourcing", 80 if local_sources else 50)

        out.summary = (
            f"Material package for {brief.district} ({climate}, {budget} budget): "
            f"Walling: {wall_name} (U={wall_u} W/m2K, Rs.{wall_cost}/m2). "
            f"Roofing: {roof_name} (U={roof_u} W/m2K, Rs.{roof_cost}/m2). "
            f"Embodied carbon {co2_saving_pct}% below conventional RCC. "
            f"Total estimated material cost: Rs.{material_total:,.0f} for {built_up_m2:.0f}m2 built-up area."
        )
        return out


_agent_instance = None


def _get_agent() -> MaterialAgent:
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = MaterialAgent()
    return _agent_instance


def analyze_materials(brief, context=None):
    """Entry point called by orchestrator."""
    return _get_agent().analyse(brief, context or {})
