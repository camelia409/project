"""
Vastu Shastra Data — Room Placement & Orientation Guidelines
=============================================================
Source References:
  - Vastu Vidya (ancient Indian architectural science), codified in:
    Manasara (6th–7th century CE) — Chapters 7–14 on residential design
    Mayamata — Chapters 18–21 on dwelling (griha)
    Vishwakarma Prakash — room orientation tables
  - Contemporary References:
    P.K. Acharya, "Architecture of Manasara" (Oxford, 1933, repr. 2010)
    Dr. Ganapati Sthapati, "Building Architecture of Sthapatya Veda", 2006
    B.B. Puri, "Vastu Shastra Vol. 1: Hindu Science of Architecture", 2003
    Subramanian K., "Scientific Vastu Shastra", Emerald Publishers, Chennai, 2018

Note on scientific basis:
  Many Vastu prescriptions align with passive design principles (e.g.,
  kitchen in SE = cooking fire faces sunrise; NE open = cross-ventilation;
  SW bedrooms = afternoon heat beneficial for sleep). These correlations
  are noted where applicable.
"""

# ── Ideal room placement by compass direction ─────────────────────────────────
# Scale: 1 (least preferred) to 5 (most preferred)
# Source: Manasara Chapters 9–11, Mayamata Chapter 20, updated per Subramanian 2018

VASTU_ROOM_DIRECTION_SCORES = {
    # room_type: {direction: score (1–5), reason}
    "living": {
        "NE": (5, "North-East — auspicious, divine light, cross-ventilation inlet"),
        "N":  (4, "North — Kubera (wealth) direction, good for social spaces"),
        "NW": (3, "North-West — acceptable; Vayu direction aids ventilation"),
        "E":  (4, "East — sunrise light, positive energy, welcoming"),
        "SE": (2, "South-East — Agni (fire) corner; not ideal for living"),
        "S":  (2, "South — Yama direction; avoided for main living"),
        "SW": (1, "South-West — Nirutti, heavy energy; best only for master bedroom"),
        "W":  (3, "West — Varuna; acceptable for living, afternoon light"),
    },
    "master_bedroom": {
        "SW": (5, "South-West — Nirutti, grounding energy; head of family stability"),
        "S":  (4, "South — Yama; restful, less activity; good for sleep"),
        "NW": (3, "North-West — Vayu; promotes movement, not ideal for master"),
        "W":  (3, "West — acceptable; sunset light aids restful sleep"),
        "SE": (2, "South-East — Agni; active energy, disturbs sleep"),
        "NE": (1, "North-East — sacred corner; not for sleeping"),
        "N":  (2, "North — Kubera; associated with wealth, not sleep"),
        "E":  (3, "East — sunrise energy; some texts approve for younger occupants"),
    },
    "bedroom": {
        "S":  (5, "South — recommended for secondary bedrooms; restful"),
        "SW": (4, "South-West — stable energy; acceptable for guest/child room"),
        "NW": (4, "North-West — Vayu; good for children, promotes movement"),
        "W":  (3, "West — acceptable for children's room"),
        "E":  (3, "East — sunrise beneficial for children studying"),
        "N":  (2, "North — Kubera; some texts recommend for unmarried children"),
        "SE": (2, "South-East — Agni; less preferred for bedrooms"),
        "NE": (1, "North-East — sacred; not for sleeping per Manasara"),
    },
    "kitchen": {
        "SE": (5, "South-East — Agni (fire) corner; cooking fire should face East/SE. "
                  "Scientific: morning sun reaches kitchen naturally"),
        "NW": (4, "North-West — secondary option; Vayu assists cooking fire"),
        "E":  (3, "East — acceptable; morning light in kitchen"),
        "S":  (2, "South — less preferred; afternoon heat increases in kitchen"),
        "N":  (1, "North — opposite of Agni; strongly avoided per Manasara"),
        "NE": (1, "North-East — sacred corner; avoid for fire/cooking"),
        "W":  (2, "West — afternoon heat compounds cooking heat"),
        "SW": (1, "South-West — Nirutti; very inauspicious for fire"),
    },
    "pooja": {
        "NE": (5, "North-East — Ishanya (divine) corner; mandatory for prayer room. "
                  "Scientific: morning sun from NE reaches the deity"),
        "E":  (4, "East — secondary best; sunrise faces devotee during prayer"),
        "N":  (3, "North — Kubera direction; acceptable"),
        "NW": (2, "North-West — less preferred"),
        "SE": (1, "South-East — Agni; not for prayer"),
        "S":  (1, "South — Yama direction; not auspicious"),
        "SW": (1, "South-West — Nirutti; inauspicious for sacred space"),
        "W":  (2, "West — not ideal; devotee faces East preferred"),
    },
    "bathroom": {
        "NW": (5, "North-West — Vayu (air) direction; ideal for water + ventilation"),
        "W":  (4, "West — Varuna (water deity); acceptable"),
        "E":  (3, "East — morning light and ventilation; acceptable"),
        "SE": (2, "South-East — Agni; mixing fire and water not recommended"),
        "NE": (1, "North-East — sacred corner; strictly avoid bathroom"),
        "SW": (1, "South-West — Nirutti; avoid bathroom here"),
        "S":  (3, "South — less preferred; some texts allow"),
        "N":  (3, "North — acceptable if NW not available"),
    },
    "dining": {
        "W":  (5, "West — Varuna; food and water; enjoyable westward view at sunset"),
        "E":  (4, "East — morning meals face sunrise; positive"),
        "N":  (4, "North — Kubera/prosperity; meals in north direction auspicious"),
        "NW": (3, "North-West — Vayu; promotes quick eating (practical for busy families)"),
        "SE": (2, "South-East — Agni; fire zone; heat near dining less comfortable"),
        "S":  (2, "South — Yama; less preferred for meals"),
        "SW": (1, "South-West — Nirutti; avoid for dining"),
        "NE": (3, "North-East — acceptable; some texts allow dining here"),
    },
    "entrance": {
        "N":  (5, "North — Kubera (wealth) direction; most auspicious entrance"),
        "NE": (5, "North-East — Ishanya; second-most auspicious entry"),
        "E":  (5, "East — sunrise; welcoming, traditional in Tamil Nadu"),
        "NW": (3, "North-West — Vayu; acceptable entry"),
        "W":  (2, "West — Varuna; less common but acceptable"),
        "SE": (2, "South-East — Agni; not ideal as main entry"),
        "S":  (1, "South — Yama direction; strongly avoided as main entrance"),
        "SW": (1, "South-West — Nirutti; inauspicious; must avoid"),
    },
    "store": {
        "SW": (5, "South-West — heavy, grounding energy suits storage"),
        "S":  (4, "South — good for storage; low activity zone"),
        "NW": (3, "North-West — Vayu; acceptable for dry storage"),
        "W":  (3, "West — acceptable"),
        "SE": (2, "South-East — fire zone; not for flammable storage"),
        "NE": (1, "North-East — sacred; no storage here"),
        "N":  (2, "North — Kubera; not for storage"),
        "E":  (2, "East — not preferred for storage"),
    },
    "utility": {
        "NW": (5, "North-West — Vayu; washing/laundry benefits from air flow"),
        "SE": (4, "South-East — Agni; fire zone good for service activities"),
        "W":  (3, "West — acceptable"),
        "SW": (2, "South-West — avoid heavy machinery in SW"),
        "NE": (1, "North-East — sacred; no service area"),
    },
    "courtyard": {
        "NE": (5, "North-East — Brahmasthana; open courtyard in NE/centre captures divine light"),
        "centre": (5, "Centre — Brahmasthan; traditional Tamil Nadu central courtyard (Muttram)"),
        "N":  (4, "North — acceptable; open to sky in north"),
        "E":  (4, "East — sunrise into courtyard; positive"),
        "SE": (2, "South-East — Agni; avoid open courtyard"),
        "SW": (1, "South-West — inauspicious open space"),
    },
}

# ── Facing direction scores for main entrance ─────────────────────────────────
VASTU_FACING_SCORES = {
    "North":      {"score": 90, "reason": "Kubera (wealth/prosperity); highly recommended"},
    "North-East": {"score": 95, "reason": "Ishanya (divine); best possible facing"},
    "East":       {"score": 90, "reason": "Indra (power/sunrise); traditional & auspicious"},
    "North-West": {"score": 65, "reason": "Vayu (air/movement); moderately acceptable"},
    "West":       {"score": 60, "reason": "Varuna (water); neutral to slightly unfavorable"},
    "South-East": {"score": 40, "reason": "Agni (fire); less favorable as main entry"},
    "South":      {"score": 25, "reason": "Yama (death); generally avoided in Vastu"},
    "South-West": {"score": 15, "reason": "Nirutti (decay); most inauspicious facing"},
}

# ── Vastu zones of the Vastu Purusha Mandala (16 zones) ──────────────────────
# Source: Manasara, Chapter 10 — Vastupurushamandala
VASTU_ZONES = {
    "NE": {"deity": "Ishanya",  "element": "Water+Ether", "energy": "Divine, pure",     "ideal_use": ["pooja", "meditation", "open courtyard"]},
    "E":  {"deity": "Indra",    "element": "Air",          "energy": "Active, powerful", "ideal_use": ["living", "entrance", "verandah"]},
    "SE": {"deity": "Agni",     "element": "Fire",         "energy": "Transformative",   "ideal_use": ["kitchen", "generator", "utility"]},
    "S":  {"deity": "Yama",     "element": "Earth",        "energy": "Grounding, heavy", "ideal_use": ["master_bedroom", "store"]},
    "SW": {"deity": "Nirutti",  "element": "Earth",        "energy": "Heavy, stable",    "ideal_use": ["master_bedroom", "store", "treasury"]},
    "W":  {"deity": "Varuna",   "element": "Water",        "energy": "Balanced",         "ideal_use": ["dining", "bathroom", "children_bedroom"]},
    "NW": {"deity": "Vayu",     "element": "Air",          "energy": "Moving, change",   "ideal_use": ["bathroom", "utility", "guest_room", "garage"]},
    "N":  {"deity": "Kubera",   "element": "Water",        "energy": "Prosperity",       "ideal_use": ["living", "entrance", "locker_room"]},
    "C":  {"deity": "Brahma",   "element": "Space/Ether",  "energy": "Central cosmic",   "ideal_use": ["courtyard", "open_sky", "brahmasthan — keep free"]},
}

# ── Room adjacency from Vastu perspective ─────────────────────────────────────
# Rooms that should be adjacent/connected per Vastu
VASTU_ADJACENCY = {
    "kitchen":        ["dining", "utility"],       # food prep → serving
    "pooja":          ["living"],                  # prayer opens to main gathering
    "master_bedroom": ["bathroom"],                # attached bath
    "living":         ["dining", "entrance"],      # social flow
    "dining":         ["kitchen"],                 # cooking → eating
    "entrance":       ["living", "verandah"],      # entry → welcome
}

def score_layout_vastu(rooms_with_directions: list) -> dict:
    """
    Score a list of {room_type, direction} dicts against Vastu guidelines.
    Returns overall score (0–100) and per-room breakdown.
    """
    if not rooms_with_directions:
        return {"overall": 50, "rooms": []}

    room_scores = []
    for r in rooms_with_directions:
        rtype = r.get("room_type", "")
        direction = r.get("direction", "N")
        scores_map = VASTU_ROOM_DIRECTION_SCORES.get(rtype, {})
        if direction in scores_map:
            score_5, reason = scores_map[direction]
            score_100 = score_5 * 20  # convert 1–5 to 0–100
        else:
            score_100, reason = 50, "Direction not specifically rated"
        room_scores.append({"room": r.get("name", rtype), "score": score_100, "reason": reason})

    overall = sum(r["score"] for r in room_scores) / len(room_scores) if room_scores else 50
    return {"overall": round(overall, 1), "rooms": room_scores}
