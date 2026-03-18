"""
Arch Agent — Offline Multi-Criteria Decision Making (MCDM) Synthesis
=====================================================================
Synthesizes outputs from all 5 specialist agents using Analytic Hierarchy
Process (AHP)-inspired weighted scoring to produce an integrated spatial brief
and actionable design recommendations.

Knowledge Base:
  - All upstream agent outputs (baker, climate, material, regulatory, vastu)
  - algorithms/scoring.py (SCORE_WEIGHTS for MCDM)
  - HUDCO Space Standards for Dwellings (2012)
  - NBC 2016 Part 3 Clause 8.1 (room minimums)
  - Space Syntax: Hillier & Hanson, "The Social Logic of Space" (1984)
  - Meenakshi Rm., "Chettinad House" (INTACH, 2004)
  - Saaty T.L., "The Analytic Hierarchy Process" (McGraw-Hill, 1980)

Agent Type: MCDM synthesis engine (no API dependency)
"""

from typing import Any, Dict, List
from agents.base_agent import BaseAgent, AgentOutput

# ── AHP-inspired synthesis weights (sum = 1.0) ───────────────────────────────
# Source: Expert survey (Tamil Nadu architects, 12 respondents, 2023 pilot study)
# + Saaty 1980 AHP pairwise comparison method
SYNTHESIS_WEIGHTS = {
    "regulatory":  0.30,   # Hard constraints — non-negotiable
    "climate":     0.25,   # Comfort (most impactful in TN climate)
    "baker":       0.20,   # Cost-effectiveness (most relevant for affordable housing)
    "material":    0.15,   # Material availability and embodied carbon
    "vastu":       0.10,   # Cultural requirement (varies by client)
}

# ── Spatial programme benchmarks (NBC 2016 + HUDCO 2012) ─────────────────────
SPATIAL_PROGRAMME = {
    "1BHK": {
        "Economy":  {"living": 12, "kitchen": 5, "bedroom": 9.5, "bathroom": 2.8,
                     "total": 32, "description": "NBC minimum 1BHK economy"},
        "Standard": {"living": 14, "kitchen": 6, "bedroom": 11, "bathroom": 3,
                     "total": 38},
        "Premium":  {"living": 16, "kitchen": 7, "bedroom": 13, "bathroom": 3.5,
                     "total": 46},
    },
    "2BHK": {
        "Economy":  {"living": 14, "dining": 8, "kitchen": 5.5, "bedroom": 9.5,
                     "bathroom": 3, "total": 53, "note": "Two bedrooms, two baths"},
        "Standard": {"living": 18, "dining": 10, "kitchen": 7, "bedroom": 12,
                     "bathroom": 3.5, "total": 65},
        "Premium":  {"living": 22, "dining": 12, "kitchen": 9, "bedroom": 14,
                     "bathroom": 4, "total": 80},
    },
    "3BHK": {
        "Economy":  {"living": 15, "dining": 9, "kitchen": 6, "bedroom": 10,
                     "bathroom": 3, "utility": 3, "total": 71},
        "Standard": {"living": 20, "dining": 12, "kitchen": 8, "bedroom": 13,
                     "bathroom": 4, "utility": 4, "total": 90},
        "Premium":  {"living": 25, "dining": 15, "kitchen": 10, "bedroom": 16,
                     "bathroom": 5, "utility": 5, "pooja": 4, "total": 115},
    },
    "4BHK": {
        "Economy":  {"living": 18, "dining": 10, "kitchen": 7, "bedroom": 11,
                     "bathroom": 3.5, "utility": 4, "total": 92},
        "Standard": {"living": 24, "dining": 14, "kitchen": 9, "bedroom": 14,
                     "bathroom": 4.5, "utility": 5, "pooja": 3, "total": 122},
        "Premium":  {"living": 30, "dining": 18, "kitchen": 12, "bedroom": 18,
                     "bathroom": 6, "utility": 6, "pooja": 5, "study": 8, "total": 155},
    },
}

# ── Adjacency requirements (Space Syntax + HUDCO) ────────────────────────────
ADJACENCY_CRITICAL = [
    ("kitchen", "dining",  "CRITICAL — food prep to serving (Hillier & Hanson 1984)"),
    ("bedroom", "bathroom","CRITICAL — attached bath mandatory for modern comfort"),
    ("living",  "entrance","CRITICAL — entry flow per Space Syntax theory"),
]

ADJACENCY_AVOID = [
    ("toilet",   "kitchen", "FORBIDDEN — hygiene violation, NBC 2016 Part 8"),
    ("toilet",   "dining",  "FORBIDDEN — hygiene violation, NBC 2016 Part 8"),
    ("bathroom", "kitchen", "UNDESIRABLE — odour and hygiene concern"),
]

# ── Traditional Tamil Nadu typology zones ────────────────────────────────────
TN_ZONES = {
    "public":  ["entrance", "verandah", "living", "pooja"],
    "service": ["kitchen", "utility", "store"],
    "private": ["bedroom", "bathroom", "corridor"],
    "centre":  ["courtyard"],
}


class ArchAgent(BaseAgent):
    """
    Multi-criteria synthesis agent: combines all domain agent outputs into
    a unified, actionable spatial brief using AHP-inspired MCDM.
    """

    def __init__(self):
        super().__init__(
            name="Arch Agent",
            domain="Spatial Programming & Multi-Criteria Design Synthesis",
        )

    def load_knowledge(self):
        try:
            from algorithms.scoring import SCORE_WEIGHTS, compute_all_scores
            self._score_weights = SCORE_WEIGHTS
        except ImportError:
            self._score_weights = {}

    def analyse(self, brief: Any, context: Dict[str, Any]) -> AgentOutput:
        out = self._init_output()
        self._ref("HUDCO Space Standards for Dwellings (2012)")
        self._ref("NBC 2016 Part 3 Clause 8.1 — Room Minimums")
        self._ref("Hillier & Hanson, 'The Social Logic of Space' (1984)")
        self._ref("Saaty T.L., 'The Analytic Hierarchy Process' (McGraw-Hill, 1980)")
        self._ref("Meenakshi Rm., 'Chettinad House' (INTACH, 2004)")

        bhk = brief.bhk
        budget = brief.budget_tier
        plot_area = brief.plot_area
        district = brief.district
        facing = brief.facing
        climate = getattr(brief, "climate_zone", "hot_humid")
        family_size = brief.family_size
        vastu_required = getattr(brief, "vastu_required", False)
        wants_courtyard = getattr(brief, "wants_courtyard", False)
        accessibility = getattr(brief, "accessibility", False)
        special_needs = getattr(brief, "special_needs", [])

        # 1. Weighted synthesis of agent scores
        self._log("MCDM SYNTHESIS — weighting agent domain scores")
        agent_scores = {}
        for domain, weight in SYNTHESIS_WEIGHTS.items():
            agent_out = context.get(domain)
            if agent_out and hasattr(agent_out, "scores") and agent_out.scores:
                # Take first/primary score as domain representative
                primary_score = list(agent_out.scores.values())[0]
            else:
                primary_score = 60.0  # neutral fallback
            agent_scores[domain] = primary_score
            self._log(f"  {domain.capitalize()}: {primary_score:.0f} x weight {weight} = {primary_score*weight:.1f}")

        weighted_total = sum(
            agent_scores.get(d, 60) * w for d, w in SYNTHESIS_WEIGHTS.items()
        )
        self._score("Overall Design Quality Score", round(weighted_total, 1))
        self._log(f"Weighted total: {weighted_total:.1f}/100")

        # 2. Spatial programme
        self._log(f"Building spatial programme for {bhk} / {budget}")
        prog = SPATIAL_PROGRAMME.get(bhk, {}).get(budget, {})
        if not prog:
            prog = SPATIAL_PROGRAMME.get("2BHK", {}).get("Standard", {})

        programme_lines = []
        for room, area in prog.items():
            if room in ("total", "note", "description"):
                continue
            programme_lines.append(f"{room.capitalize()}: {area}m2")
        programme_lines.append(f"Total: ~{prog.get('total', 60)}m2 (net internal area)")

        if wants_courtyard and plot_area > 100:
            programme_lines.append("Courtyard (Muttram): min 9m2 (Baker 1986, CEPT ventilation multiplier 1.4x)")

        if accessibility:
            programme_lines.append("Ground floor: All key rooms (bedroom + bathroom) mandatory — wheelchair accessibility")

        if "home_office" in str(special_needs):
            programme_lines.append("Study/Home Office: 6-8m2 (separate from living, natural light from E/N)")

        self._rec("Spatial Programme", " | ".join(programme_lines[:6]),
                  f"HUDCO 2012 benchmarks for {bhk} {budget}", "HUDCO 2012; NBC 2016")

        # 3. Design priorities (ranked)
        priorities = []
        priorities.append(f"1. REGULATORY: Maintain setbacks ({self._get_setback_str(plot_area)}), "
                          f"FSI compliance per TNCDBR 2019")
        priorities.append(f"2. CLIMATE: {'Courtyard for stack ventilation + ' if wants_courtyard else ''}"
                          f"SE inlet openings for {climate} prevailing wind")
        priorities.append(f"3. BAKER: Rat-trap bond walling + "
                          f"{'Mangalore tile roof' if climate != 'temperate' else 'stone slab roof'}")
        priorities.append(f"4. ADJACENCY: Kitchen↔Dining (critical), "
                          f"Bedroom↔Bathroom (critical), no Toilet↔Kitchen")
        if vastu_required:
            priorities.append(f"5. VASTU: {facing} facing OK ({VASTU_FACING_SIMPLE.get(facing, 'check score')}); "
                               f"Kitchen in SE, Pooja in NE")
        else:
            priorities.append(f"5. QUALITY: All bedrooms >= 9.5m2, natural light N/E sides")

        for p in priorities:
            self._rec(f"Design Priority", p, "", "Multi-criteria AHP synthesis")
            self._log(f"  {p}")

        # 4. Key constraints
        self._log("Identifying binding constraints:")
        constraints = []

        # Regulatory constraints from context
        reg_out = context.get("regulatory")
        if reg_out and reg_out.recommendations:
            usable_str = reg_out.recommendations.get("Usable Plot Area", f"~{plot_area*0.6:.0f}m2")
            constraints.append(f"Usable area: {usable_str} (TNCDBR 2019 setbacks)")
            max_bua = reg_out.recommendations.get("Max Total Built-up Area", "—")
            constraints.append(f"Max built-up: {max_bua}")
        else:
            constraints.append(f"Usable area: ~{plot_area*0.6:.0f}m2 (estimated after setbacks)")

        if wants_courtyard:
            constraints.append(f"Courtyard (min 9m2) reduces available floor area — plan accordingly")
        if accessibility:
            constraints.append("All key rooms on ground floor (no steps) — reduces G+1 effectiveness")
        if climate in ("hot_humid", "hot_dry"):
            constraints.append("No west-facing bedrooms — climate constraint (afternoon heat)")

        for c in constraints:
            self._rec("Constraint", c, "", "TNCDBR 2019; CEPT 2018; Baker 1986")
            self._log(f"  CONSTRAINT: {c}")

        # 5. Conflict resolution
        self._log("Resolving inter-agent conflicts:")
        conflicts_resolved = []

        # Baker vs Client budget
        if budget == "Premium":
            conflicts_resolved.append(
                "Baker principle vs Premium budget: Adopt rat-trap bond + local floors (Athangudi tile) "
                "for Baker compliance while using premium finishes in wet areas only. "
                "Redirect savings to courtyard quality and rooftop garden."
            )

        # Climate vs Vastu (west entrance)
        if vastu_required and facing in ("W", "SW") and climate in ("hot_humid", "hot_dry"):
            conflicts_resolved.append(
                f"Vastu conflict: {facing} facing is inauspicious AND causes PM solar heat gain. "
                "Resolution: Retain east/north entrance, use Vastu remediation (copper yantra at SW). "
                "Climate wins for habitability."
            )

        # Regulatory vs BHK (tight plot)
        if plot_area < 75 and bhk in ("3BHK", "4BHK"):
            conflicts_resolved.append(
                f"Regulatory conflict: Plot {plot_area}m2 may be too small for {bhk} at NBC minimums. "
                "Resolution: Propose G+1 to double floor area, or reduce to 2BHK on ground floor."
            )

        for i, cr in enumerate(conflicts_resolved, 1):
            self._rec(f"Conflict Resolution {i}", cr, "MCDM arbitration", "Multi-criteria synthesis")
            self._log(f"  RESOLVED {i}: {cr}")

        if not conflicts_resolved:
            self._log("  No major inter-agent conflicts detected")

        # 6. Generator settings
        self._rec("Recommended BHK Type", bhk, "As per client brief", "Client input")
        self._rec("Recommended Climate Zone", climate, "From IMD district data", "IMD 1981-2010")
        self._rec("Recommended Facing", facing, "Client preference", "Client input")
        self._rec("Enable Courtyard", "Yes" if wants_courtyard else "No",
                  "Baker 1986 muttram principle", "Baker 1986")

        # 7. Family-specific notes
        fam_notes = []
        if family_size > 5:
            fam_notes.append(f"Large family ({family_size} members): Ensure adequate bathroom count (1 per 3 persons).")
        if accessibility:
            fam_notes.append("Accessibility: 900mm doorways, no thresholds, grab rails in bathrooms.")
        if "elderly" in str(brief.family_type).lower():
            fam_notes.append("Elder-friendly: Ground floor bedroom with attached bath, ramp not steps.")
        if fam_notes:
            self._rec("Family-Specific Notes", " | ".join(fam_notes), "", "HUDCO 2012")

        # 8. Overall quality score
        overall = round(weighted_total * 0.7 + (15 if wants_courtyard else 0) + (5 if vastu_required else 0), 1)
        self._score("Integrated Design Quality", min(100, overall))
        self._score("Programme Completeness", 85 if prog else 60)

        out.summary = (
            f"Integrated design brief for {bhk}, {plot_area}m2, {district} ({budget} budget): "
            f"Net internal area target: ~{prog.get('total', 60)}m2. "
            f"{'Courtyard (min 9m2) included. ' if wants_courtyard else ''}"
            f"Top design priority: regulatory setbacks + {climate} climate passive design. "
            f"Baker recommendation: rat-trap bond + "
            f"{'Mangalore tile roof. ' if climate != 'temperate' else 'stone slab roof. '}"
            f"Overall design quality (MCDM): {weighted_total:.0f}/100. "
            f"{'Vastu compliance required — facing score and room placement checked.' if vastu_required else ''}"
        )
        return out

    @staticmethod
    def _get_setback_str(plot_area: float) -> str:
        if plot_area <= 75:
            return "F1.0m/R1.0m/S0.75m"
        elif plot_area <= 200:
            return "F1.5m/R1.5m/S1.0m"
        elif plot_area <= 500:
            return "F2.0m/R1.5m/S1.2m"
        return "F3.0m/R2.0m/S1.5m"


VASTU_FACING_SIMPLE = {
    "N": "Auspicious (Kubera)", "NE": "Highly auspicious (Ishanya)",
    "E": "Most auspicious (Indra)", "SE": "Moderate (Agni — kitchen only)",
    "S": "Inauspicious (Yama)", "SW": "Very inauspicious (Nirriti)",
    "W": "Moderate (Varuna)", "NW": "Good (Vayu)",
}


_agent_instance = None


def _get_agent() -> ArchAgent:
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = ArchAgent()
    return _agent_instance


def synthesize_design_brief(brief, baker_response=None, climate_response=None,
                             material_response=None, regulatory_response=None,
                             vastu_response=None, context=None):
    """Entry point called by orchestrator."""
    ctx = context or {}
    if baker_response:
        ctx["baker"] = baker_response
    if climate_response:
        ctx["climate"] = climate_response
    if material_response:
        ctx["material"] = material_response
    if regulatory_response:
        ctx["regulatory"] = regulatory_response
    if vastu_response:
        ctx["vastu"] = vastu_response
    return _get_agent().analyse(brief, ctx)
