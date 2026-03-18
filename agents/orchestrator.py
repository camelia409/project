"""
Orchestrator — Offline Multi-Agent Pipeline Coordinator
========================================================
Coordinates all 6 knowledge-based expert agents in sequence.
NO AI API keys required — all agents reason from data/ modules.

Pipeline order:
  1. Baker Agent      — sustainability + cost-effectiveness
  2. Climate Agent    — passive design + ECBC compliance
  3. Material Agent   — local sourcing + embodied carbon
  4. Regulatory Agent — NBC 2016 + TNCDBR 2019 compliance
  5. Vastu Agent      — Vastu Shastra spatial analysis
  6. Arch Agent       — MCDM synthesis of all agent outputs

Design:
  - ClientBrief dataclass: collects structured user input from UI
  - AgentReport dataclass: holds all AgentOutput objects
  - run_pipeline(): sequential execution with status callbacks

References:
  - Russell & Norvig, "AI: A Modern Approach" 4th ed. — multi-agent systems
  - Giarratano & Riley, "Expert Systems" 4th ed. — pipeline architecture
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from agents.base_agent import AgentOutput
from agents.baker_agent import analyze_baker
from agents.climate_agent import analyze_climate
from agents.material_agent import analyze_materials
from agents.regulatory_agent import analyze_regulatory
from agents.vastu_agent import analyze_vastu
from agents.arch_agent import synthesize_design_brief


# ── Client Brief dataclass ───────────────────────────────────────────────────

@dataclass
class ClientBrief:
    """
    Structured client brief collected from the Pre-Design form in the UI.
    Passed to every agent as the primary input.
    """
    family_size:   int
    family_type:   str           # "Nuclear" | "Joint" | "Elderly included"
    bhk:           str           # "1BHK" | "2BHK" | "3BHK" | "4BHK"
    plot_area:     float         # m2
    district:      str           # Tamil Nadu district name
    climate_zone:  str           # "hot_humid" | "hot_dry" | "composite" | "temperate"
    facing:        str           # "N" | "NE" | "E" | "SE" | "S" | "SW" | "W" | "NW"
    budget_tier:   str           # "Economy" | "Standard" | "Premium"
    special_needs: List[str]     = field(default_factory=list)
    vastu_required:bool          = False
    accessibility: bool          = False
    wants_courtyard: bool        = False
    cooking_style: str           = "Traditional South Indian"
    road_width:    Optional[str] = None
    local_body:    Optional[str] = None
    num_floors:    Optional[str] = None
    special_zone:  Optional[str] = None

    def to_dict(self) -> dict:
        """Backward-compatible dict for any code that expects a dict brief."""
        return {
            "family_size":    self.family_size,
            "family_type":    self.family_type,
            "bhk":            self.bhk,
            "plot_area":      self.plot_area,
            "built_up_area":  self.plot_area * 0.6,
            "district":       self.district,
            "climate_zone":   self.climate_zone,
            "facing":         self.facing,
            "budget_tier":    self.budget_tier,
            "special_needs":  self.special_needs,
            "vastu_required": self.vastu_required,
            "accessibility":  self.accessibility,
            "wants_courtyard":self.wants_courtyard,
            "cooking_style":  self.cooking_style,
            "road_width":     self.road_width or "Not specified",
            "local_body":     self.local_body or "Municipality (DTCP)",
            "num_floors":     self.num_floors or "G+1",
            "special_zone":   self.special_zone or "None",
        }


# ── Agent Report dataclass ───────────────────────────────────────────────────

@dataclass
class AgentReport:
    """
    Collected structured outputs from all 6 knowledge-based agents.

    Each field holds an AgentOutput object (not a raw string).
    Use .to_markdown() on each field for display.

    Legacy string fields (baker_str etc.) provided for backward compatibility
    with any code that still expects string outputs.
    """
    brief:          ClientBrief
    baker_out:      Optional[AgentOutput] = None
    climate_out:    Optional[AgentOutput] = None
    material_out:   Optional[AgentOutput] = None
    regulatory_out: Optional[AgentOutput] = None
    vastu_out:      Optional[AgentOutput] = None
    arch_out:       Optional[AgentOutput] = None
    error:          Optional[str]         = None

    # ── Legacy string properties (backward compat) ────────────────────────────
    @property
    def baker(self) -> str:
        return self.baker_out.to_markdown() if self.baker_out else ""

    @property
    def climate(self) -> str:
        return self.climate_out.to_markdown() if self.climate_out else ""

    @property
    def material(self) -> str:
        return self.material_out.to_markdown() if self.material_out else ""

    @property
    def regulatory(self) -> str:
        return self.regulatory_out.to_markdown() if self.regulatory_out else ""

    @property
    def vastu(self) -> str:
        return self.vastu_out.to_markdown() if self.vastu_out else ""

    @property
    def arch_synthesis(self) -> str:
        return self.arch_out.to_markdown() if self.arch_out else ""

    def all_outputs(self) -> List[AgentOutput]:
        """Return all non-None AgentOutputs in pipeline order."""
        outs = [self.baker_out, self.climate_out, self.material_out,
                self.regulatory_out, self.vastu_out, self.arch_out]
        return [o for o in outs if o is not None]

    def combined_warnings(self) -> List[str]:
        """Aggregate all warnings from all agents."""
        warnings = []
        for out in self.all_outputs():
            warnings.extend(out.warnings)
        return warnings

    def combined_scores(self) -> Dict[str, float]:
        """Aggregate all scores from all agents (prefixed by agent name)."""
        scores = {}
        for out in self.all_outputs():
            for k, v in out.scores.items():
                scores[f"{out.agent_name} / {k}"] = v
        return scores


# ── Pipeline runner ──────────────────────────────────────────────────────────

def run_pipeline(
    brief: ClientBrief,
    status_callback: Optional[Callable[[str], None]] = None,
) -> AgentReport:
    """
    Run all 6 knowledge-based agents in sequence.

    Args:
        brief:           ClientBrief with user input
        status_callback: Optional callable(agent_name) for UI progress updates

    Returns:
        AgentReport with structured outputs from all agents
    """
    report = AgentReport(brief=brief)
    context: Dict[str, AgentOutput] = {}

    try:
        # ── Stage 1: Baker (sustainability) ───────────────────────────────────
        if status_callback:
            status_callback("Baker Agent — Sustainability Analysis")
        report.baker_out = analyze_baker(brief, context)
        context["baker"] = report.baker_out

        # ── Stage 2: Climate (passive design) ─────────────────────────────────
        if status_callback:
            status_callback("Climate Agent — Passive Design Analysis")
        report.climate_out = analyze_climate(brief, context)
        context["climate"] = report.climate_out

        # ── Stage 3: Material (local sourcing) ────────────────────────────────
        if status_callback:
            status_callback("Material Agent — Material Selection")
        report.material_out = analyze_materials(brief, context)
        context["material"] = report.material_out

        # ── Stage 4: Regulatory (NBC + TNCDBR) ───────────────────────────────
        if status_callback:
            status_callback("Regulatory Agent — Compliance Check")
        report.regulatory_out = analyze_regulatory(brief, context)
        context["regulatory"] = report.regulatory_out

        # ── Stage 5: Vastu (spatial analysis) ────────────────────────────────
        if status_callback:
            status_callback("Vastu Agent — Vastu Analysis")
        report.vastu_out = analyze_vastu(brief, context)
        context["vastu"] = report.vastu_out

        # ── Stage 6: Arch synthesis (MCDM) ───────────────────────────────────
        if status_callback:
            status_callback("Arch Agent — Synthesizing All Inputs (MCDM)")
        report.arch_out = synthesize_design_brief(brief, context=context)
        context["arch"] = report.arch_out

    except Exception as e:
        import traceback
        report.error = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"

    return report
