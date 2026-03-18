"""
Base Agent — Offline Knowledge-Based Expert System
====================================================
All specialist agents inherit from BaseAgent.
NO AI API keys required — agents reason entirely from
the research data loaded from the data/ modules.

Design Philosophy:
  Each agent is a domain expert "trained" on its knowledge base:
    - Baker Agent    → data/materials_db.py + BAKER_PRINCIPLES
    - Climate Agent  → data/tn_climate_data.py + PASSIVE_STRATEGIES
    - Material Agent → data/materials_db.py + cost/thermal scoring
    - Regulatory Agent → data/nbc_standards.py + data/tn_setbacks.py
    - Vastu Agent    → data/vastu_data.py
    - Arch Agent     → multi-criteria synthesis of all agent outputs

References:
  - Russell & Norvig, "Artificial Intelligence: A Modern Approach", 4th ed.
    Chapter 7 — Knowledge-Based Agents
  - Giarratano & Riley, "Expert Systems: Principles and Programming", 4th ed.
    Chapter 3 — Rule-Based Inference Engines
  - Shortliffe & Buchanan, "MYCIN" rule-based certainty factor model (1975)
    adapted for architecture domain confidence scoring
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ── Output dataclass (replaces raw markdown strings) ─────────────────────────

@dataclass
class AgentOutput:
    """
    Structured output from a knowledge-based domain expert agent.

    Fields mirror the MYCIN certainty-factor model:
      recommendations — key findings with evidence links
      scores          — quantified confidence on 0–100 scale
      warnings        — constraint violations / flags
      reasoning_trace — step-by-step inference log (for XAI)
      references      — source citations used in this analysis
      summary         — paragraph-form summary for UI display
    """
    agent_name:      str
    domain:          str
    recommendations: Dict[str, Any]       = field(default_factory=dict)
    scores:          Dict[str, float]     = field(default_factory=dict)
    warnings:        List[str]            = field(default_factory=list)
    reasoning_trace: List[str]            = field(default_factory=list)
    references:      List[str]            = field(default_factory=list)
    summary:         str                  = ""

    def to_markdown(self) -> str:
        """
        Render the structured output as a formatted markdown string
        for display in the Streamlit 'Agent Brief' tab.
        """
        lines: List[str] = []
        lines.append(f"## {self.agent_name} — {self.domain}")
        lines.append("")

        if self.summary:
            lines.append(self.summary)
            lines.append("")

        if self.scores:
            lines.append("### Scores")
            for k, v in self.scores.items():
                filled = int(v / 10)
                bar = "█" * filled + "░" * (10 - filled)
                lines.append(f"- **{k}**: {v:.0f}/100  `{bar}`")
            lines.append("")

        if self.recommendations:
            lines.append("### Recommendations")
            for k, v in self.recommendations.items():
                lines.append(f"- **{k}**: {v}")
            lines.append("")

        if self.warnings:
            lines.append("### ⚠️ Warnings")
            for w in self.warnings:
                lines.append(f"- {w}")
            lines.append("")

        if self.references:
            lines.append("### References")
            for r in self.references:
                lines.append(f"- {r}")

        return "\n".join(lines)


# ── Base class ────────────────────────────────────────────────────────────────

class BaseAgent:
    """
    Abstract base for all offline knowledge-based expert agents.

    Subclasses must implement:
      load_knowledge() — load domain data from data/ modules
      analyse(brief, context) → AgentOutput

    Provides helper methods:
      _log(msg, ref)                — append to reasoning_trace
      _rec(key, value, reason, ref) — add recommendation
      _score(key, value)            — record a score (0–100)
      _warn(msg)                    — add a warning
      _ref(citation)                — add a source reference
    """

    def __init__(self, name: str, domain: str):
        self.name   = name
        self.domain = domain
        self._output: Optional[AgentOutput] = None
        self.load_knowledge()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def load_knowledge(self) -> None:
        """
        Load domain knowledge from data/ modules.
        Override in subclass to import and index required data.
        """
        pass

    def analyse(self, brief: Any, context: Dict[str, Any]) -> AgentOutput:
        """
        Run the expert inference engine on the client brief.
        Must be overridden by each domain agent.

        Args:
            brief:   ClientBrief instance (user input)
            context: Shared context dict (outputs from earlier agents)

        Returns:
            AgentOutput with recommendations, scores, warnings, reasoning trace
        """
        raise NotImplementedError(f"{self.name}.analyse() not implemented")

    # ── Output helpers ────────────────────────────────────────────────────────

    def _init_output(self) -> AgentOutput:
        self._output = AgentOutput(agent_name=self.name, domain=self.domain)
        return self._output

    def _log(self, msg: str, ref: Optional[str] = None) -> None:
        """Append a step to the reasoning trace."""
        entry = msg if not ref else f"{msg}  [Ref: {ref}]"
        if self._output:
            self._output.reasoning_trace.append(entry)

    def _rec(
        self,
        key: str,
        value: Any,
        reason: str = "",
        ref: Optional[str] = None,
    ) -> None:
        """Record a recommendation with optional reasoning."""
        if self._output:
            self._output.recommendations[key] = value
        if reason:
            self._log(f"REC [{key}] → {value}  ({reason})", ref)

    def _score(self, key: str, value: float) -> None:
        """Record a domain score (0–100)."""
        value = round(max(0.0, min(100.0, float(value))), 1)
        if self._output:
            self._output.scores[key] = value

    def _warn(self, msg: str) -> None:
        """Add a constraint violation or advisory warning."""
        if self._output:
            self._output.warnings.append(msg)

    def _ref(self, citation: str) -> None:
        """Add a source reference."""
        if self._output and citation not in self._output.references:
            self._output.references.append(citation)

    # ── Utility helpers ───────────────────────────────────────────────────────

    @staticmethod
    def clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))

    @staticmethod
    def linear_score(value: float, lo: float, hi: float) -> float:
        """
        Map value linearly onto [0, 100] between lo and hi.
        Returns 0 if value <= lo, 100 if value >= hi.
        """
        if hi <= lo:
            return 50.0
        return round(max(0.0, min(100.0, (value - lo) / (hi - lo) * 100)), 1)

    @staticmethod
    def grade(score: float) -> str:
        """Convert 0–100 score to letter grade."""
        if score >= 85:
            return "A (Excellent)"
        elif score >= 70:
            return "B (Good)"
        elif score >= 55:
            return "C (Satisfactory)"
        elif score >= 40:
            return "D (Below Standard)"
        else:
            return "F (Non-Compliant)"
