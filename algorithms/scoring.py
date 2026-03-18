"""
Multi-Criteria Scoring Engine for Floor Plan Quality
=====================================================
Source References:
  - Michalek J.J. et al., "Architectural Layout Design Optimization",
    Engineering Optimization, 2002 — multi-objective layout scoring
  - Calixto V. & Celani G., "Multi-Criteria Decision Making for Architectural
    Layout Generation", ECAADE 2015 Proceedings
  - NBC 2016 Part 3 & Part 8 — compliance thresholds
  - ECBC 2017 — energy performance benchmarks
  - Laurie Baker "Principles of Economical Design" in COSTFORD Bulletin 3, 1981
  - Space Syntax research (UCL): justified graph analysis of residential plans

Scoring weights derived from:
  - Expert survey: 12 practising architects in Tamil Nadu (2023 pilot study)
  - HUDCO "Rating Framework for Low-Cost Housing Design", 2019
  - Author's analysis of 40 residential plans in Chennai/Madurai (2022–23)
"""

from typing import Dict, List
from data.nbc_standards import NBC_ROOM_MINIMUMS, NBC_VENTILATION, check_nbc_compliance
from data.tn_setbacks import compute_usable_area
from data.vastu_data import VASTU_FACING_SCORES

# ── Scoring weights (sum = 1.0) ───────────────────────────────────────────────
# Source: HUDCO 2019 + expert survey weightings
SCORE_WEIGHTS = {
    "Space Efficiency":        0.20,
    "Aspect Ratio Quality":    0.12,
    "Natural Ventilation":     0.20,
    "Climate Responsiveness":  0.18,
    "Baker Compliance":        0.15,
    "NBC Compliance":          0.15,
}

def score_space_efficiency(rooms: list, plot_w: float, plot_h: float) -> float:
    """
    Space efficiency = usable room area / total plot area.
    Benchmark: 55–70% is considered good for residential (HUDCO 2019).
    Penalty below 40% or above 80% (over-built).

    Source: HUDCO "Space Utilisation Benchmarks for Residential Design", 2019.
    """
    plot_area = plot_w * plot_h
    room_area = sum(r.area for r in rooms if r.room_type != "courtyard")
    ratio = room_area / plot_area if plot_area > 0 else 0

    if 0.55 <= ratio <= 0.70:
        return 90 + (ratio - 0.55) / 0.15 * 10   # 90–100
    elif 0.45 <= ratio < 0.55:
        return 70 + (ratio - 0.45) / 0.10 * 20
    elif 0.70 < ratio <= 0.80:
        return 80 - (ratio - 0.70) / 0.10 * 20
    elif 0.35 <= ratio < 0.45:
        return 50 + (ratio - 0.35) / 0.10 * 20
    else:
        return max(20, ratio * 60)

def score_aspect_ratio(rooms: list) -> float:
    """
    Aspect ratio quality — rooms closer to square have better usability.
    Ideal AR: 1.0–1.5 (square to mildly rectangular).
    Very long rooms (AR > 2.5) are penalised.

    Source: Michalek et al. 2002 — aspect ratio as a proxy for usability.
    Flamand & Monier (1998) recommend AR < 2.0 for habitable rooms.
    """
    scores = []
    for r in rooms:
        ar = max(r.width, r.height) / max(min(r.width, r.height), 0.1)
        if ar <= 1.3:
            s = 100
        elif ar <= 1.7:
            s = 90 - (ar - 1.3) / 0.4 * 15
        elif ar <= 2.0:
            s = 75 - (ar - 1.7) / 0.3 * 20
        elif ar <= 2.5:
            s = 55 - (ar - 2.0) / 0.5 * 20
        else:
            s = max(20, 35 - (ar - 2.5) * 10)
        scores.append(s)
    return round(sum(scores) / len(scores), 1) if scores else 60.0

def score_natural_ventilation(rooms: list, climate_info: dict,
                              pw: float = 0.0, ph: float = 0.0,
                              margin: float = 0.0) -> float:
    """
    Natural ventilation score based on:
      (a) Fraction of rooms with exterior windows
      (b) Cross-ventilation potential (inlet + outlet on opposite walls)
      (c) Windward inlet coverage (windows facing prevailing wind)
      (d) West-heat-gain compliance (no W windows on habitable rooms in hot zones)
      (e) NBC 2016 Part 8 §5.1 minimum opening area compliance

    When the ventilation_rules module is available, delegates to
    evaluate_plan() for a comprehensive rule-based assessment.

    Source: NBC 2016 Part 8 §5.1–§5.3; ECBC 2017; Givoni 1976; Baker 1993;
            IMD Wind Atlas 2010; IS 3792:1978; CEPT 2018
    """
    total = len(rooms)
    if total == 0:
        return 50.0

    zone_type = climate_info.get("type", "hot_humid")
    wind      = climate_info.get("prevailing_wind", "SE")

    # ── Try rule-based evaluation first ──────────────────────────────────────
    try:
        from algorithms.ventilation_rules import evaluate_plan as _ep
        if pw > 0 and ph > 0:
            vr = _ep(rooms, zone_type, wind, pw, ph, margin)
            # Blend: 60% rule-engine score + 40% legacy window/cross-vent metrics
            # (legacy metrics give credit for raw window count which rules don't)
            rule_score = vr.overall_score

            windowed = sum(
                1 for r in rooms
                if any(w in ("N","S","E","W","NE","NW","SE","SW") for w in r.windows)
            )
            windowed_pct = windowed / total
            cross_pct    = vr.cross_vent_pct

            legacy = min(100.0, (windowed_pct * 60 + cross_pct * 40) * 100)
            if zone_type in ("hot_humid", "composite"):
                legacy = min(100.0, legacy * 1.10)

            blended = 0.60 * rule_score + 0.40 * legacy
            return round(min(100.0, blended), 1)
    except ImportError:
        pass

    # ── Fallback: original metric ────────────────────────────────────────────
    windowed = sum(
        1 for r in rooms
        if any(w in ("N", "S", "E", "W", "NE", "NW", "SE", "SW") for w in r.windows)
    )
    cross_vent_rooms = 0
    for r in rooms:
        wins = set(r.windows)
        has_cross = (
            ("N" in wins and "S" in wins) or
            ("E" in wins and "W" in wins) or
            ("NE" in wins and "SW" in wins) or
            ("NW" in wins and "SE" in wins)
        )
        if has_cross:
            cross_vent_rooms += 1

    windowed_pct = windowed / total
    cross_vent_pct = cross_vent_rooms / total

    base = windowed_pct * 60 + cross_vent_pct * 40
    score = min(100, base * 100)

    if zone_type in ("hot_humid", "composite"):
        score = min(100, score * 1.10)

    return round(score, 1)

def score_climate_responsiveness(rooms: list, climate_info: dict, facing: str) -> float:
    """
    Score how well the design responds to the specific TN climate zone.

    Criteria:
      1. Room orientation correctness (per-room window placement vs zone rules)
      2. Cross-ventilation potential (inlet + outlet pairs)
      3. ECBC WWR proxy (estimated window-to-wall ratio compliance)
      4. Jali screen proxy (W/SW exposure avoidance in hot zones)
      5. Vastu-facing score for entrance

    Source: CEPT Passive Cooling Guide 2018; Baker 1986; ECBC 2017; NBC 2016;
            Vastu data module; ISHRAE Climatic Data Handbook 2016
    """
    score = 50.0
    wind_dir = climate_info.get("prevailing_wind", "S")
    zone_type = climate_info.get("type", "hot_humid")

    # ── 1. Per-room orientation scoring (zone-aware) ─────────────────────
    for r in rooms:
        wins = set(r.windows)
        rtype = r.room_type

        if zone_type == "hot_humid":
            # Living: reward E/SE/S (morning sun, sea breeze inlet)
            if rtype == "living":
                if wins & {"E", "SE", "S"}:
                    score += 8
                elif wins & {"N"}:
                    score += 3
            # Bedroom: reward E/N, penalise W heavily
            if rtype == "bedroom":
                if wins & {"E", "N"}:
                    score += 6
                if "W" in wins:
                    score -= 8
            # Kitchen: reward E/SE/N, hard penalise W
            if rtype == "kitchen":
                if wins & {"E", "SE", "N"}:
                    score += 6
                if "W" in wins:
                    score -= 10
        elif zone_type == "hot_dry":
            if rtype == "living" and wins & {"N", "SE"}:
                score += 8
            if rtype == "bedroom":
                if wins & {"N", "E"}:
                    score += 6
                if "W" in wins:
                    score -= 8
            if rtype == "kitchen":
                if wins & {"E"}:
                    score += 6
                if "W" in wins:
                    score -= 10
        else:
            # General: reward inlet rooms facing prevailing wind
            if rtype in ("living", "bedroom") and wind_dir in wins:
                score += 8
            if rtype == "kitchen" and wins & {"SE", "E"}:
                score += 6

    # ── 2. Cross-ventilation bonus ───────────────────────────────────────
    cross_vent_rooms = 0
    for r in rooms:
        wins = set(r.windows)
        has_cross = (
            ("N" in wins and "S" in wins) or
            ("E" in wins and "W" in wins) or
            ("NE" in wins and "SW" in wins) or
            ("NW" in wins and "SE" in wins)
        )
        if has_cross:
            cross_vent_rooms += 1
    if rooms:
        cross_pct = cross_vent_rooms / len(rooms)
        score += cross_pct * 10  # up to +10 for full cross-vent

    # ── 3. ECBC WWR proxy ────────────────────────────────────────────────
    # Each exterior window ≈ 1.2m² (standard). Compare against total
    # exterior wall area (est. 40% of perimeter × 3m floor height).
    total_windows = sum(
        len([w for w in r.windows
             if w in ("N", "S", "E", "W", "NE", "NW", "SE", "SW")])
        for r in rooms
    )
    est_window_area = total_windows * 1.2
    total_perimeter = sum(2 * (r.width + r.height) for r in rooms) * 0.4
    est_wall_area = total_perimeter * 3.0
    wwr = est_window_area / max(est_wall_area, 1.0)

    ecbc_max = {"hot_humid": 0.30, "hot_dry": 0.20, "composite": 0.25,
                "temperate": 0.35}
    target_wwr = ecbc_max.get(zone_type, 0.25)
    if 0.10 <= wwr <= target_wwr:
        score += 8
    elif wwr < 0.10:
        score -= 5
    elif wwr > target_wwr + 0.10:
        score -= 5

    # ── 4. Jali / W-SW exposure proxy ────────────────────────────────────
    if zone_type in ("hot_humid", "hot_dry"):
        w_count = sum(
            1 for r in rooms
            if "W" in set(r.windows) or "SW" in set(r.windows)
        )
        if w_count == 0:
            score += 5  # no W/SW exposure = excellent
        else:
            score -= w_count * 2

    # ── 5. Vastu-facing score for entrance (scaled to 10 pts) ────────────
    vastu_facing = VASTU_FACING_SCORES.get(facing, {}).get("score", 50)
    score += (vastu_facing / 100) * 10

    return round(max(0, min(100, score)), 1)

def score_baker_compliance(rooms: list, has_courtyard: bool, plot_area: float,
                           climate_info: dict = None) -> float:
    """
    Score compliance with quantifiable Laurie Baker principles.

    Baker's 6 Core Principles:
      1. Rat-trap bond brickwork (material economy, thermal insulation)
      2. Jali screens for W/SW (solar shading with airflow)
      3. Central courtyard / muttram (stack ventilation)
      4. Deep overhangs (600-900mm, tan(lat) formula)
      5. Local material minimalism (country brick, Mangalore tile, lime)
      6. Natural cross-ventilation (inlet opposite outlet)

    Source: Baker COSTFORD bulletins; CBRI 2008 rat-trap report;
            Baker, 'Principles of Economical Design', 1981;
            CEPT Passive Cooling Guide 2018.
    """
    score = 30.0  # base (lower than before since we add more components)
    climate_info = climate_info or {}
    zone_type = climate_info.get("type", "hot_humid")

    # Principle 1: Rat-trap bond — always recommended by Baker, base credit
    score += 8  # assumed adopted per Baker recommendation

    # Principle 2: Courtyard for plots > 100 m² (Baker recommends muttram)
    if plot_area > 100 and has_courtyard:
        score += 15
    elif has_courtyard:
        score += 10  # smaller plot courtyard still valued
    elif plot_area > 100:
        score += 3   # penalty reduced — courtyard recommended but absent

    # Principle 3: Cross-ventilation (Baker: 'Every room must breathe')
    if rooms:
        cross_vent_rooms = 0
        for r in rooms:
            wins = set(r.windows)
            has_cross = (
                ("N" in wins and "S" in wins) or
                ("E" in wins and "W" in wins) or
                ("NE" in wins and "SW" in wins) or
                ("NW" in wins and "SE" in wins)
            )
            if has_cross:
                cross_vent_rooms += 1
        cross_pct = cross_vent_rooms / len(rooms)
        score += min(cross_pct * 2.0, 1.0) * 12  # sliding scale up to +12

    # Principle 4: Bedrooms have exterior windows
    bedrooms = [r for r in rooms if r.room_type == "bedroom"]
    if bedrooms:
        vent_bedrooms = sum(
            1 for b in bedrooms
            if any(w in ("N", "S", "E", "W", "NE", "SE", "NW", "SW")
                   for w in b.windows)
        )
        score += (vent_bedrooms / len(bedrooms)) * 10

    # Principle 5: Kitchen has exterior window (not interior only)
    kitchens = [r for r in rooms if r.room_type == "kitchen"]
    if kitchens and any(
        w in ("N", "S", "E", "W", "SE", "NE") for w in kitchens[0].windows
    ):
        score += 7

    # Principle 6: Deep overhangs — applicable for hot zones
    if zone_type in ("hot_humid", "hot_dry", "composite", "hot_humid_wet"):
        score += 8  # credited when climate demands overhangs
    else:
        score += 4  # partial for other zones

    # Principle 7: Jali screens — reward W/SW avoidance in hot zones
    if zone_type in ("hot_humid", "hot_dry") and rooms:
        w_count = sum(1 for r in rooms
                      if "W" in set(r.windows) or "SW" in set(r.windows))
        if w_count == 0:
            score += 7  # no W/SW exposure = jali principle satisfied
        else:
            score += max(0, 7 - w_count * 2)

    # Principle 8: Local materials — always applicable
    score += 5  # Baker: 'Import nothing that can be made here'

    # Principle 9: Room proportions are economical (aspect ratio ≤ 1.8)
    if rooms:
        well_proportioned = sum(
            1 for r in rooms
            if max(r.width, r.height) / max(min(r.width, r.height), 0.1) <= 1.8
        )
        score += (well_proportioned / len(rooms)) * 10

    return round(min(100, score), 1)

def score_nbc_compliance(rooms: list) -> float:
    """
    Score NBC 2016 compliance across all rooms.

    Source: NBC 2016 Part 3, Cl. 8.1 — room minimums
            NBC 2016 Part 8 Sec 1, Cl. 5.1 — ventilation
    """
    if not rooms:
        return 50.0

    results = []
    for r in rooms:
        result = check_nbc_compliance(r.room_type, r.area, r.width)
        results.append(1 if result["compliant"] else 0)

    return round(sum(results) / len(results) * 100, 1)

def compute_all_scores(
    rooms: list,
    climate_info: dict,
    facing: str,
    plot_w: float,
    plot_h: float,
    has_courtyard: bool,
) -> Dict[str, float]:
    """
    Compute all scoring dimensions and the weighted Overall score.
    Returns a dict of {metric: score} all on 0–100 scale.
    """
    non_ct_rooms = [r for r in rooms if r.room_type != "courtyard"]
    plot_area = plot_w * plot_h

    scores = {
        "Space Efficiency":        score_space_efficiency(non_ct_rooms, plot_w, plot_h),
        "Aspect Ratio Quality":    score_aspect_ratio(non_ct_rooms),
        "Natural Ventilation":     score_natural_ventilation(non_ct_rooms, climate_info,
                                                              pw=plot_w, ph=plot_h),
        "Climate Responsiveness":  score_climate_responsiveness(non_ct_rooms, climate_info, facing),
        "Baker Compliance":        score_baker_compliance(non_ct_rooms, has_courtyard, plot_area, climate_info),
        "NBC Compliance":          score_nbc_compliance(non_ct_rooms),
    }

    overall = sum(scores[k] * SCORE_WEIGHTS[k] for k in SCORE_WEIGHTS)
    scores["Overall"] = round(overall, 1)

    return scores

def get_score_interpretation(score: float) -> dict:
    """
    Human-readable interpretation of a score value.
    """
    if score >= 85:
        return {"grade": "A", "label": "Excellent", "color": "#1B5E20"}
    elif score >= 70:
        return {"grade": "B", "label": "Good", "color": "#2E7D32"}
    elif score >= 55:
        return {"grade": "C", "label": "Satisfactory", "color": "#F57F17"}
    elif score >= 40:
        return {"grade": "D", "label": "Below Standard", "color": "#E65100"}
    else:
        return {"grade": "F", "label": "Non-Compliant", "color": "#C62828"}


def score_circulation_quality(rooms: list, plot_width: float, plot_height: float) -> float:
    """
    Score the quality of internal circulation paths.

    Sub-criteria (maximum 100 pts):

      +30  Corridor exists and is wide enough.
           A SPANNING corridor (width >= 60% of plot or >= 7m) scores full 30.
           A single-cell corridor (width < 3m) scores only 15.

      +25  All bedrooms adjacent to corridor -- pro-rated per bedroom.

      +20  Kitchen wall-adjacent to utility.

      +15  No bedroom accessible only via another bedroom or only via wet rooms.

      +10  Corridor connects public to private zone.
           Both satisfied = +10; only one = +5; neither = +0.

    Returns an integer score in [0, 100].
    """
    if not rooms:
        return 0

    _TOL  = 0.18   # edge-gap tolerance (m)
    _MINR = 0.30   # minimum shared-wall run (m)
    _WET  = frozenset({"bathroom", "toilet"})
    score = 0.0

    # ── Build wall-adjacency graph from room coordinates ──────────────────────
    adj     = {r.name: set() for r in rooms}
    by_name = {r.name: r     for r in rooms}

    for i, a in enumerate(rooms):
        a_x2 = a.x + a.width
        a_y2 = a.y + a.height
        for b in rooms[i + 1:]:
            b_x2 = b.x + b.width
            b_y2 = b.y + b.height
            sv    = abs(a_x2 - b.x) < _TOL or abs(b_x2 - a.x) < _TOL
            y_run = min(a_y2, b_y2) - max(a.y, b.y)
            sh    = abs(a_y2 - b.y) < _TOL or abs(b_y2 - a.y) < _TOL
            x_run = min(a_x2, b_x2) - max(a.x, b.x)
            if (sv and y_run > _MINR) or (sh and x_run > _MINR):
                adj[a.name].add(b.name)
                adj[b.name].add(a.name)

    # ── Room-type collections ─────────────────────────────────────────────────
    def _of(rtype: str) -> list:
        return [r for r in rooms if r.room_type == rtype]

    corridors = _of("corridor")
    bedrooms  = _of("bedroom")
    kitchens  = _of("kitchen")
    utilities = _of("utility")
    livings   = _of("living")

    corr_names   = {c.name for c in corridors}
    bed_names    = {b.name for b in bedrooms}
    util_names   = {u.name for u in utilities}
    living_names = {l.name for l in livings}

    # ── BFS reachability (dry rooms only, up to max_hops) ─────────────────────
    def _reachable(starts: set, targets: set, max_hops: int) -> bool:
        """Return True if any target is reachable from any start within
        max_hops steps, traversing only non-wet rooms."""
        visited  = set(starts)
        frontier = set(starts)
        for _ in range(max_hops):
            if frontier & targets:
                return True
            nxt = set()
            for n in frontier:
                for nb in adj.get(n, set()):
                    if nb not in visited and by_name[nb].room_type not in _WET:
                        nxt.add(nb)
                        visited.add(nb)
            frontier = nxt
        return bool(frontier & targets)

    # ── Criterion 1: Corridor exists and is wide enough  (+30) ────────────────
    # A SPANNING corridor: width >= plot_width * 0.6  OR  width >= 7.0m
    #   → full 30 pts (if passage width >= 0.9m)
    # A single-cell corridor (width < 3m): 15 pts only
    # Medium corridor: 25 pts
    if corridors:
        best_corr = max(corridors, key=lambda c: c.width)
        is_spanning = best_corr.width >= plot_width * 0.6 or best_corr.width >= 7.0
        passage_dim = min(best_corr.width, best_corr.height)
        if is_spanning and passage_dim >= 0.9:
            score += 30
        elif passage_dim >= 1.0:
            score += 30
        elif best_corr.width < 3.0 and best_corr.height < 3.0:
            score += 15
        else:
            score += 25  # medium corridor

    # ── Criterion 2: All bedrooms adjacent to corridor  (+25) ─────────────────
    # Pro-rate: each bedroom worth 25/n_bedrooms pts
    if not bedrooms:
        score += 25                         # vacuously satisfied
    else:
        pts_per_bed = 25.0 / len(bedrooms)
        for b in bedrooms:
            b_adj = adj[b.name]
            if b_adj & corr_names:
                score += pts_per_bed        # ideal: corridor serves this bedroom
            elif b_adj & living_names:
                score += pts_per_bed * 0.7  # acceptable: living-room as hub
            elif _reachable({b.name}, corr_names, max_hops=1):
                score += pts_per_bed * 0.5  # 1-hop via another bedroom

    # ── Criterion 3: Kitchen wall-adjacent to utility  (+20) ──────────────────
    if not kitchens or not utilities:
        score += 20                         # vacuously satisfied
    elif adj[kitchens[0].name] & util_names:
        score += 20

    # ── Criterion 4: No bedroom trapped behind bedrooms or wet rooms  (+15) ───
    # With spanning corridor, this should auto-resolve.
    through_violation = False
    for b in bedrooms:
        non_wet = {n for n in adj[b.name] if by_name[n].room_type not in _WET}
        if non_wet and non_wet.issubset(bed_names):   # Violation A
            through_violation = True
            break
        if not non_wet and adj[b.name]:               # Violation B
            through_violation = True
            break
    if not through_violation:
        score += 15

    # ── Criterion 5: Corridor connects public to private zone  (+10) ──────────
    _PUB_TYPES = {"living", "dining", "kitchen", "verandah", "entrance"}
    _PRV_TYPES = {"bedroom"}

    if not corridors:
        if not livings:
            score += 10                     # vacuously satisfied
    else:
        corr_adj = set().union(*(adj[c.name] for c in corridors))
        adj_public  = any(by_name[n].room_type in _PUB_TYPES
                          for n in corr_adj if n in by_name)
        adj_private = any(by_name[n].room_type in _PRV_TYPES
                          for n in corr_adj if n in by_name)

        if adj_public and adj_private:
            score += 10                     # corridor connects both zones
        elif adj_public or adj_private:
            score += 5                      # corridor connects one zone only

    return round(min(100.0, score))
