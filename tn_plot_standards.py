"""
Tamil Nadu Standard Plot Sizes & Validation
============================================
Source References:
  - NBC 2016 Part 3 §5.1 — Minimum plot dimensions for residential use
  - TNCDBR 2019 §4 — Plot sub-division rules, minimum frontage 6m
  - CMDA 2022 Development Regulations — standard plot configurations
  - Tamil Nadu Housing Board (TNHB) standard plot allotment sizes
  - DTCP (Directorate of Town and Country Planning) approved layouts
"""

import math
from typing import List, Tuple

# ── Standard Tamil Nadu Plot Sizes ────────────────────────────────────────────
# Format: (width_m, depth_m)
# Sources: TNHB allotment registers, DTCP approved layout patterns,
#          CMDA standard subdivisions, field survey of built stock.
TN_STANDARD_PLOTS: List[Tuple[float, float]] = [
    # Economy / EWS / LIG tier  (< 100 m²)
    (6.0,  9.0),    # 54 m²  — EWS minimum; TNHB scheme plots
    (6.0,  18.0),   # 108 m² — narrow deep; common in dense urban fabric
    (6.0,  20.0),   # 120 m² — narrow deep extended
    (7.5,  10.0),   # 75 m²  — LIG TNHB; Indira Awaas Yojana standard
    (7.5,  18.0),   # 135 m² — narrow mid-depth
    (8.0,  20.0),   # 160 m² — semi-urban subdivision
    # MIG tier  (100 – 200 m²)
    (9.0,  12.0),   # 108 m² — most common MIG subdivision
    (9.0,  15.0),   # 135 m² — MIG extended; Salem / Coimbatore layouts
    (10.0, 12.0),   # 120 m² — semi-standard MIG
    (12.0, 12.0),   # 144 m² — square MIG; common in Madurai / Trichy
    # HIG / standard residential tier  (200 – 300 m²)
    (12.0, 15.0),   # 180 m² — most common HIG in Chennai suburbs
    (12.0, 18.0),   # 216 m² — HIG extended
    (15.0, 15.0),   # 225 m² — square HIG; CMDA approved
    (15.0, 18.0),   # 270 m² — HIG extended depth
    # Premium / Group Housing tier  (> 300 m²)
    (15.0, 24.0),   # 360 m² — premium residential
    (18.0, 18.0),   # 324 m² — square premium
    (20.0, 15.0),   # 300 m² — wide premium
    (24.0, 15.0),   # 360 m² — wide premium extended
]

# ── Absolute limits (NBC 2016 Part 3 §5.1 + TNCDBR 2019 §4) ─────────────────
MIN_PLOT_WIDTH = 6.0    # m — NBC 2016 absolute residential minimum frontage
MIN_PLOT_DEPTH = 9.0    # m — NBC 2016 absolute residential minimum depth
MAX_PLOT_WIDTH = 30.0   # m — beyond this, G+1 structural framing expected
MAX_PLOT_DEPTH = 30.0   # m — beyond this, internal courtyard typically needed


def snap_to_nearest_tn_plot(
    width: float, depth: float
) -> Tuple[float, float, bool]:
    """
    Snap entered plot dimensions to the nearest Tamil Nadu standard plot size.

    Returns (snapped_width, snapped_depth, was_snapped).

    Algorithm:
      - If (width, depth) is already within 0.5 m of any standard plot,
        return the matched standard size with was_snapped=False.
      - Otherwise find the closest standard plot in normalised Euclidean space
        (w/MAX_PLOT_WIDTH, d/MAX_PLOT_DEPTH) so width and depth contribute
        equally regardless of absolute magnitude, and return was_snapped=True.

    Source: TNCDBR 2019 §4 standard subdivision table.
    """
    MATCH_TOL = 0.5   # metres — within this = already standard

    best_dist  = math.inf
    best_plot  = (width, depth)

    for (sw, sd) in TN_STANDARD_PLOTS:
        # Normalise both axes to [0, 1] so neither dominates
        dw = (width  - sw) / MAX_PLOT_WIDTH
        dd = (depth  - sd) / MAX_PLOT_DEPTH
        dist = math.sqrt(dw * dw + dd * dd)

        if dist < best_dist:
            best_dist = dist
            best_plot = (sw, sd)

        # Exact match within tolerance → treat as standard, no snapping message
        if abs(width - sw) <= MATCH_TOL and abs(depth - sd) <= MATCH_TOL:
            return (sw, sd, False)

    return (best_plot[0], best_plot[1], True)


def validate_bhk_for_plot(
    width: float, depth: float, bhk_config: str
) -> Tuple[bool, str]:
    """
    Validate whether the requested BHK configuration is appropriate for the
    given plot area.

    Returns (is_valid, warning_message).  is_valid=True means no warning.

    Area thresholds:
      < 75 m²     → 1BHK only
      75 – 135 m² → 1BHK or 2BHK
      135 – 200 m²→ 2BHK or 3BHK
      200 – 300 m²→ 3BHK or 4BHK
      > 300 m²    → 4BHK or Courtyard layout recommended

    Special rules (NBC 2016 Part 3 + HUDCO 2012 space standards):
      3BHK + Courtyard → minimum 200 m²
      4BHK             → minimum 250 m²

    bhk_config: full key string, e.g. "2BHK", "3BHK + Pooja", "4BHK + Courtyard"
    BHK count extracted from first character of string.
    """
    area = width * depth

    # Extract numeric BHK count
    try:
        n_bhk = int(bhk_config[0])
    except (ValueError, IndexError):
        return (True, "")   # unrecognised format — skip validation

    has_courtyard = "courtyard" in bhk_config.lower()

    # ── Special minimum-area rules ────────────────────────────────────────────
    if has_courtyard and n_bhk >= 3 and area < 200:
        return (
            False,
            f"3BHK+Courtyard needs ≥ 200 m² (plot area: {area:.0f} m²). "
            f"Consider 2BHK for this plot size.",
        )
    if n_bhk >= 4 and area < 250:
        return (
            False,
            f"4BHK needs ≥ 250 m² (plot area: {area:.0f} m²). "
            f"3BHK is recommended for this plot.",
        )

    # ── General area-band checks ──────────────────────────────────────────────
    if area < 75:
        if n_bhk > 1:
            return (
                False,
                f"Plot area {area:.0f} m² is suitable for 1BHK only "
                f"(NBC 2016 §5.1 minimum habitable area per room: 9.5 m²).",
            )
    elif area < 135:
        if n_bhk > 2:
            return (
                False,
                f"Plot area {area:.0f} m² is suitable for 1–2BHK. "
                f"{n_bhk}BHK rooms will be below NBC minimum sizes.",
            )
    elif area < 200:
        if n_bhk > 3:
            return (
                False,
                f"Plot area {area:.0f} m² is suitable for 2–3BHK. "
                f"4BHK on this plot will produce very cramped rooms.",
            )
    elif area < 300:
        if n_bhk > 4:
            return (
                False,
                f"Plot area {area:.0f} m² is suitable for 3–4BHK. "
                f"Consider a courtyard layout instead.",
            )
    # area ≥ 300 → all configurations acceptable

    return (True, "")
