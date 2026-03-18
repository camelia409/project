"""
Vastu Agent — Offline Vastu Shastra Expert System
==================================================
Applies traditional Vastu Shastra principles to evaluate room placement,
entrance direction, and spatial organisation using the vastu_data knowledge base.

Knowledge Base:
  - data/vastu_data.py (VASTU_ROOM_DIRECTION_SCORES, VASTU_FACING_SCORES, VASTU_ZONES)
  - Manasara (6th-7th century CE) — Vastu Vidya foundational text
  - Mayamata (11th century CE) — South Indian Vastu treatise
  - Subramanian K., "Vastu Vidya for Modern Homes" (2018)
  - Nitschke, "Indian Architecture and the Production of a Postcolonial Past" (2013)

Agent Type: Rule-based expert system using Vastu zone scoring
"""

from typing import Any, Dict, List
from agents.base_agent import BaseAgent, AgentOutput

# ── Vastu Facing Scores (entrance direction) ──────────────────────────────────
# Source: Manasara; Mayamata; Subramanian 2018
VASTU_FACING = {
    "N":  {"score": 90, "deity": "Kubera (wealth)", "element": "Water",
           "interpretation": "Auspicious — Kubera governs north, brings prosperity. Good for offices/commercial.",
           "suitable_rooms": ["living", "dining", "entrance"]},
    "NE": {"score": 85, "deity": "Ishanya (Shiva)", "element": "Water+Earth",
           "interpretation": "Highly auspicious — Ishanya corner, spiritual energy. Best for pooja room entrance.",
           "suitable_rooms": ["pooja", "entrance", "living"]},
    "E":  {"score": 95, "deity": "Indra (rain/prosperity)", "element": "Fire+Air",
           "interpretation": "Most auspicious — morning sunlight, Indra governs east. Best for all residential.",
           "suitable_rooms": ["entrance", "living", "pooja", "bedroom"]},
    "SE": {"score": 50, "deity": "Agni (fire)", "element": "Fire",
           "interpretation": "Moderate — Agni corner, good for kitchen entrance only. Avoid for main door.",
           "suitable_rooms": ["kitchen"]},
    "S":  {"score": 40, "deity": "Yama (death)", "element": "Earth",
           "interpretation": "Inauspicious for main entrance — Yama governs south. Can be used with remediation.",
           "suitable_rooms": []},
    "SW": {"score": 30, "deity": "Nirriti (poverty)", "element": "Earth",
           "interpretation": "Very inauspicious — Nirriti corner, causes financial loss. Avoid as main entrance.",
           "suitable_rooms": []},
    "W":  {"score": 55, "deity": "Varuna (water)", "element": "Water",
           "interpretation": "Moderate — Varuna governs west. Acceptable for secondary entrance.",
           "suitable_rooms": ["bathroom", "utility"]},
    "NW": {"score": 65, "deity": "Vayu (wind)", "element": "Air",
           "interpretation": "Good — Vayu brings movement and change. Acceptable for residential entrance.",
           "suitable_rooms": ["bedroom", "corridor", "utility"]},
}

# ── Vastu Room Direction Scores ───────────────────────────────────────────────
# Matrix: room_type → direction → score (0-100)
VASTU_ROOMS = {
    "pooja": {
        "NE": 100, "E": 90, "N": 75, "NW": 50, "W": 40, "SW": 20, "S": 15, "SE": 30,
        "rationale": "NE (Ishanya) — divine corner per Manasara; E for morning sun during prayer",
    },
    "living": {
        "N": 90, "NE": 85, "E": 80, "NW": 70, "W": 60, "SW": 40, "S": 50, "SE": 55,
        "rationale": "N and NE — prosperity energy; E — morning social energy",
    },
    "bedroom": {
        "SW": 85, "S": 75, "NW": 70, "W": 65, "N": 60, "NE": 50, "E": 55, "SE": 40,
        "rationale": "SW — stability and deep sleep; master bedroom should be heaviest corner",
    },
    "kitchen": {
        "SE": 100, "E": 80, "S": 60, "NW": 50, "W": 40, "N": 30, "NE": 15, "SW": 10,
        "rationale": "SE — Agni (fire) corner per Mayamata; E for morning sun. NE strictly forbidden.",
    },
    "dining": {
        "W": 90, "E": 85, "N": 75, "NW": 70, "S": 65, "NE": 60, "SE": 55, "SW": 40,
        "rationale": "W — Varuna blesses food; E — morning meal with sunlight",
    },
    "bathroom": {
        "NW": 90, "W": 85, "N": 70, "E": 60, "NE": 30, "SE": 40, "SW": 20, "S": 50,
        "rationale": "NW — Vayu removes impurities; W — Varuna (water). Avoid NE and SW.",
    },
    "store": {
        "SW": 85, "W": 75, "NW": 70, "S": 65, "N": 60, "E": 50, "SE": 45, "NE": 40,
        "rationale": "SW — heavy objects anchor the SW zone for stability",
    },
    "utility": {
        "NW": 90, "W": 80, "SE": 70, "N": 60, "S": 55, "E": 50, "NE": 30, "SW": 25,
        "rationale": "NW — Vayu drives movement (washing machines, water flow)",
    },
}

# ── Vastu compass zones ───────────────────────────────────────────────────────
VASTU_ZONES = {
    "N":  {"deity": "Kubera", "element": "Water", "quality": "Wealth, prosperity"},
    "NE": {"deity": "Ishanya/Shiva", "element": "Water+Earth", "quality": "Divinity, wisdom"},
    "E":  {"deity": "Indra", "element": "Fire+Air", "quality": "Health, vitality"},
    "SE": {"deity": "Agni", "element": "Fire", "quality": "Energy, cooking, transformation"},
    "S":  {"deity": "Yama", "element": "Earth", "quality": "Stability (heavy), death (entrance)"},
    "SW": {"deity": "Nirriti", "element": "Earth", "quality": "Weight, stability for master BR"},
    "W":  {"deity": "Varuna", "element": "Water", "quality": "Social spaces, water elements"},
    "NW": {"deity": "Vayu", "element": "Air", "quality": "Movement, change, service areas"},
}


class VastuAgent(BaseAgent):
    """Offline Vastu Shastra expert using traditional zone-scoring inference."""

    def __init__(self):
        super().__init__(
            name="Vastu Agent",
            domain="Vastu Shastra Spatial Analysis",
        )

    def load_knowledge(self):
        try:
            from data.vastu_data import VASTU_FACING_SCORES, VASTU_ROOM_DIRECTION_SCORES, VASTU_ZONES
            self._facing = VASTU_FACING_SCORES
            self._room_scores = VASTU_ROOM_DIRECTION_SCORES
            self._zones = VASTU_ZONES
        except ImportError:
            self._facing = VASTU_FACING
            self._room_scores = VASTU_ROOMS
            self._zones = VASTU_ZONES

    def analyse(self, brief: Any, context: Dict[str, Any]) -> AgentOutput:
        out = self._init_output()
        self._ref("Manasara (6th-7th CE) — Vastu Vidya foundational text")
        self._ref("Mayamata (11th CE) — South Indian Vastu treatise")
        self._ref("Subramanian K., 'Vastu Vidya for Modern Homes' (2018)")

        facing = brief.facing
        vastu_required = getattr(brief, "vastu_required", False)
        bhk = brief.bhk
        plot_area = brief.plot_area

        if not vastu_required:
            self._log("Vastu analysis requested but not mandatory — providing advisory report")

        # 1. Entrance direction analysis
        self._log(f"Analysing entrance direction: {facing}")
        facing_data = VASTU_FACING.get(facing, VASTU_FACING["E"])
        facing_score = facing_data["score"]

        self._log(f"  Facing: {facing} | Deity: {facing_data['deity']} | Score: {facing_score}/100")
        self._rec("Plot Facing", facing, f"Main entrance faces {facing}", "Manasara; Mayamata")
        self._rec(
            "Facing Interpretation",
            f"{facing_data['interpretation']} (Score: {facing_score}/100)",
            f"Deity: {facing_data['deity']}, Element: {facing_data['element']}",
            "Manasara; Subramanian 2018",
        )

        if facing_score < 50:
            self._warn(
                f"Facing direction {facing} is inauspicious per Vastu (score {facing_score}/100). "
                f"Remediation: Place Vastu yantra at entrance, or shift main door 2ft to {self._get_better_direction(facing)}."
            )
        elif facing_score >= 85:
            self._log(f"  Facing {facing} is highly auspicious — no remediation needed.")

        self._score("Entrance Direction Score", facing_score)

        # 2. Room placement recommendations
        self._log("Computing optimal room placements per Vastu Shastra")
        rooms_by_bhk = {
            "1BHK": ["living", "kitchen", "bedroom", "bathroom"],
            "2BHK": ["living", "dining", "kitchen", "bedroom", "bathroom", "pooja"],
            "3BHK": ["living", "dining", "kitchen", "bedroom", "bathroom", "pooja", "utility"],
            "4BHK": ["living", "dining", "kitchen", "bedroom", "bathroom", "pooja", "utility", "store"],
        }
        rooms = rooms_by_bhk.get(bhk, rooms_by_bhk["2BHK"])
        total_vastu_score = 0
        room_count = 0

        for room in rooms:
            room_data = VASTU_ROOMS.get(room, {})
            if not room_data:
                continue
            # Best direction for this room
            best_dir = max(
                (k for k in room_data if k not in ("rationale",)),
                key=lambda d: room_data.get(d, 0),
            )
            best_score = room_data.get(best_dir, 50)
            rationale = room_data.get("rationale", "Traditional Vastu positioning")

            self._log(f"  {room.capitalize()}: best direction {best_dir} (score {best_score}) — {rationale}")
            self._rec(
                f"Optimal Zone: {room.capitalize()}",
                f"{best_dir} sector — {rationale}",
                f"Vastu score {best_score}/100",
                "Manasara; Mayamata",
            )
            total_vastu_score += best_score
            room_count += 1

        avg_vastu = round(total_vastu_score / room_count, 1) if room_count else 50.0
        self._score("Room Placement Compliance", avg_vastu)
        self._log(f"Average Vastu room placement score: {avg_vastu}/100")

        # 3. Critical rules
        critical_rules = [
            ("Kitchen in NE", "kitchen", "NE", "bad",
             "Kitchen in NE is strictly forbidden — Agni conflicts with Ishanya (divine energy). Risk: illness."),
            ("Bathroom in NE", "bathroom", "NE", "bad",
             "Bathroom in NE pollutes the sacred Ishanya corner. Risk: spiritual loss."),
            ("Master bedroom in SW", "bedroom", "SW", "good",
             "SW is optimal for master bedroom — heavy, stable energy for deep sleep."),
            ("Pooja in NE", "pooja", "NE", "good",
             "NE (Ishanya) is the divine corner — best location for prayer room."),
        ]
        for label, room, direction, quality, note in critical_rules:
            if quality == "bad":
                self._warn(f"VASTU CRITICAL: {label} — {note}")
            else:
                self._rec(f"Vastu Best Practice: {label}", note, "", "Manasara; Mayamata")
            self._log(f"  Rule: {label} [{quality.upper()}] — {note}")

        # 4. Vastu zones summary
        self._log("Vastu zone mapping for 8 directions:")
        for direction, zdata in VASTU_ZONES.items():
            self._log(f"  {direction}: {zdata['deity']} ({zdata['element']}) — {zdata['quality']}")

        self._rec(
            "Vastu Zone Map",
            "N=Kubera(Wealth) | NE=Ishanya(Divine) | E=Indra(Health) | SE=Agni(Fire) | "
            "S=Yama(Stability) | SW=Nirriti(Weight) | W=Varuna(Water) | NW=Vayu(Movement)",
            "8-direction compass per Manasara",
            "Manasara; Mayamata",
        )

        # 5. Climate vs Vastu conflicts
        climate = getattr(brief, "climate_zone", "hot_humid")
        conflicts = []
        if climate in ("hot_humid", "hot_dry") and facing in ("W", "SW"):
            conflicts.append(
                f"West/SW entrance: Vastu score {facing_score} is already low, AND west entry "
                "means afternoon sun directly into living room (heat load). Double conflict."
            )
        if climate == "hot_dry" and facing == "S":
            conflicts.append(
                "South entrance in hot-dry climate: Vastu inauspicious AND maximum afternoon solar gain."
            )

        for c in conflicts:
            self._warn(f"VASTU-CLIMATE CONFLICT: {c}")

        # 6. Overall Vastu score
        overall = (facing_score * 0.4 + avg_vastu * 0.6)
        self._score("Overall Vastu Compliance", overall)
        self._log(f"Overall Vastu score: {overall:.1f}/100 (facing 40% + rooms 60%)")

        req_status = "mandatory" if vastu_required else "advisory"
        out.summary = (
            f"Vastu analysis ({req_status}) for {bhk}, facing {facing}: "
            f"Entrance score {facing_score}/100 ({facing_data['deity']} zone). "
            f"Average room placement score {avg_vastu}/100 for {room_count} rooms. "
            f"Overall Vastu compliance: {overall:.0f}/100. "
            f"Critical rule: Kitchen must be SE (Agni zone), never NE. "
            f"Master bedroom in SW for best sleep quality. "
            f"Pooja room: NE corner (Ishanya — divine zone per Manasara)."
        )
        return out

    @staticmethod
    def _get_better_direction(facing: str) -> str:
        """Suggest the nearest auspicious direction."""
        better = {"S": "SE or E", "SW": "W or NW", "SE": "E or NE", "W": "NW or N"}
        return better.get(facing, "N or E")


_agent_instance = None


def _get_agent() -> VastuAgent:
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = VastuAgent()
    return _agent_instance


def analyze_vastu(brief, context=None):
    """Entry point called by orchestrator."""
    return _get_agent().analyse(brief, context or {})
