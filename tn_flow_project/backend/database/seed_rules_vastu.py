"""
TN-Flow Seed Script — PlotEligibilityRules & VastuGridLogic
============================================================
Populates two knowledge-base tables that drive the TN-Flow rule engine:

  1. PlotEligibilityRules  — TNCDBR 2019 dimensional constraints
  2. VastuGridLogic        — Classic Vastu Shastra room-direction mappings

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TNCDBR 2019 APPROXIMATION NOTES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The Tamil Nadu Combined Development and Building Rules 2019 (G.O.Ms.No.
78, Housing & Urban Development Dept., 11-Feb-2019) covers residential
buildings for CMDA and DTCP jurisdictions. Key approximations used here:

  §4 – Definitions: "Plot area" = gross area including setback zones.
  §6 – Setbacks scale with road width (front) and plot width (sides).
       EWS/Micro plots (<50 sqm) on lanes <4.5m are exempt from rear/
       side setbacks per Proviso to §6(1).
       Plots with width ≤5m are exempt from side setbacks per NBC 2016
       Clause 4.2.2 (adopted by TNCDBR reference).

  §7 – Height Limits:
       - Ground-only residential: ≤5.5m to top of parapet.
       - G+1 residential: ≤10.5m (TNCDBR §7(2)).
       - G+2 residential: ≤14.0m; requires structural engineer certificate.
       - Heights above 15m require Fire NOC (out of scope for Phase 1).

  §8 – FSI (Floor Space Index) and Ground Coverage:
       CMDA benefits from slightly higher permitted FSI (2.0 vs 1.5) for
       medium plots due to the 2019 amendment relaxing CMA inner-ring norms.
       DTCP FSI escalates from 1.5→2.0 only when abutting road ≥ 12m.

  §9 – Minimum road width requirements:
       - G+1 permitted ONLY if abutting road ≥ 6.0m (§9(1)).
       - G+2 permitted ONLY if abutting road ≥ 9.0m (§9(2)).
       Absence of a matching rule row in this table = not permitted.

  §10 – EWS/LIG relaxation: Micro plots (≤50 sqm) on lanes ≥3.0m may
        build Ground floor only; full zero-side-setback dispensation.

All setback values below are in metres. FSI and coverage are worst-case
conservative interpretations. Consult CMDA/DTCP for site-specific orders.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VASTU SHASTRA LOGIC NOTES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Vastu zones are ABSOLUTE compass octants, not relative to road-facing.
The Vastu Router (vastu_router.py) resolves (room_type, plot_facing) →
vastu_zone and the Geometry Engine anchors each room's polygon to that
compass quadrant of the build envelope.

  Priority 1 (is_mandatory=True)  : Hard placement rule; engine rejects
                                    layouts that cannot honour this.
  Priority 2 (is_mandatory=False) : Preferred fallback; engine uses this
                                    if P1 zone is already fully claimed.
  Priority 3 (is_mandatory=False) : Last-resort fallback; logged as a
                                    Vastu deviation in the output report.

Vastu Zone ↔ Devata (energy) reference:
  NorthEast  = Ishanya  — purity, knowledge, sacred functions
  East       = Indra    — sunrise, social energy, living
  SouthEast  = Agni     — fire, cooking, transformation
  South      = Yama     — rest, sleep, endings
  SouthWest  = Niruthi  — heavy mass, stability, earth energy
  West       = Varuna   — water, children, study, meals
  NorthWest  = Vayu     — air, movement, guests, vehicles
  North      = Kubera   — wealth, prosperity, water storage

Entrance placement is orientation-dependent (the only exception to the
absolute-zone rule) because the entrance must coincide with the plot face
that abuts the road.

Run:
    python backend/database/seed_rules_vastu.py
    python backend/database/seed_rules_vastu.py --drop   # reseed (dev)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.database.db import SessionLocal, engine
from backend.database.models import (
    Base,
    PlotEligibilityRules,
    VastuGridLogic,
    AuthorityEnum,
    FloorLevelEnum,
    VastuZoneEnum,
)


# ============================================================================
# SECTION 1 — PLOT ELIGIBILITY RULES (TNCDBR 2019)
# ============================================================================
#
# Table structure (unique key = authority + floor_level + road_width_min_m):
#
#   Constraint.py lookup algorithm:
#     SELECT * FROM plot_eligibility_rules
#      WHERE authority       = <district.authority>
#        AND floor_level     = <user.floor_level>
#        AND road_width_min_m <= <user.road_width>
#      ORDER BY road_width_min_m DESC
#      LIMIT 1
#
#   Absence of a row for a given (authority, floor_level, road_width)
#   combination means that construction type is NOT PERMITTED at that
#   road width — the Validation Gate must reject with a clear error.
#
# Road width bands used (matching common TN municipal classifications):
#   3.0m  → EWS/BPL lane (tiny gully)
#   4.5m  → Standard residential lane
#   6.0m  → Standard single-carriageway road
#   9.0m  → Medium / ward road
#   12.0m → Main / collector road
#   18.0m → Arterial road / inner ring road
# ============================================================================

# ---------------------------------------------------------------------------
# Helper — build one PlotEligibilityRules dict
# ---------------------------------------------------------------------------
def _rule(
    authority, floor_level,
    road_min, road_max,
    area_min, width_min, depth_min,
    f_setback, r_setback, sl_setback, sr_setback,
    fsi, coverage, max_h,
    ref, notes
):
    """Return a dict that maps 1-to-1 with PlotEligibilityRules fields."""
    return {
        "authority":          authority,
        "floor_level":        floor_level,
        "road_width_min_m":   road_min,
        "road_width_max_m":   road_max,
        "plot_area_min_sqm":  area_min,
        "plot_width_min_m":   width_min,
        "plot_depth_min_m":   depth_min,
        "setback_front_m":    f_setback,
        "setback_rear_m":     r_setback,
        "setback_side_left_m":  sl_setback,
        "setback_side_right_m": sr_setback,
        "fsi_value":           fsi,
        "ground_coverage_pct": coverage,
        "max_height_m":        max_h,
        "rule_reference":      ref,
        "notes":               notes,
    }


# Shorthand aliases for readability inside the data block
_C  = AuthorityEnum.CMDA
_D  = AuthorityEnum.DTCP
_G  = FloorLevelEnum.GROUND
_G1 = FloorLevelEnum.G_PLUS_1
_G2 = FloorLevelEnum.G_PLUS_2

# ---------------------------------------------------------------------------
# CMDA — Ground Floor Rules
# Six road-width bands; G+1/G+2 absent for narrow roads = not permitted.
# ---------------------------------------------------------------------------
PLOT_ELIGIBILITY_RULES: list[dict] = [

    # ── CMDA · GROUND ────────────────────────────────────────────────────────
    _rule(
        authority=_C, floor_level=_G,
        road_min=3.0,  road_max=4.49,
        area_min=27.0, width_min=3.0, depth_min=9.0,
        f_setback=1.0, r_setback=0.0, sl_setback=0.0, sr_setback=0.0,
        fsi=1.50, coverage=70.0, max_h=4.5,
        ref="TNCDBR 2019 §6(1) Proviso – EWS/Micro Plot",
        notes=(
            "EWS/BPL dispensation: plots ≤50 sqm on lanes 3–4.5m. "
            "Zero rear/side setback permitted. G+1 not allowed at this "
            "road width (§9(1) road-width prerequisite not met). "
            "Typical plot: 3×9m or 4×9m."
        ),
    ),
    _rule(
        authority=_C, floor_level=_G,
        road_min=4.5,  road_max=5.99,
        area_min=60.0, width_min=5.0, depth_min=10.0,
        f_setback=1.5, r_setback=0.5, sl_setback=0.0, sr_setback=0.0,
        fsi=1.75, coverage=65.0, max_h=5.0,
        ref="TNCDBR 2019 §6(2) – Small Residential Plot",
        notes=(
            "Side setbacks waived for plots with frontage ≤5.0m per "
            "NBC 2016 Cl.4.2.2 as referenced in TNCDBR. Rear setback "
            "0.5m minimum. Typical plot: 5×12m or 6×10m. "
            "G+1 still not permitted (road width < 6m)."
        ),
    ),
    _rule(
        authority=_C, floor_level=_G,
        road_min=6.0,  road_max=8.99,
        area_min=90.0, width_min=6.0, depth_min=12.0,
        f_setback=1.5, r_setback=1.0, sl_setback=1.0, sr_setback=1.0,
        fsi=2.00, coverage=60.0, max_h=5.5,
        ref="TNCDBR 2019 §6(2) – Standard Residential Plot (CMDA)",
        notes=(
            "Minimum 1m all-round side setbacks for plots ≥6m wide. "
            "CMDA FSI elevated to 2.0 per 2019 CMA inner-ring amendment. "
            "Typical plot: 6×12m or 7.5×12m. G+1 permitted here."
        ),
    ),
    _rule(
        authority=_C, floor_level=_G,
        road_min=9.0,  road_max=11.99,
        area_min=150.0, width_min=9.0, depth_min=15.0,
        f_setback=2.0, r_setback=1.5, sl_setback=1.5, sr_setback=1.5,
        fsi=2.00, coverage=55.0, max_h=6.0,
        ref="TNCDBR 2019 §6(3) – Medium Residential Plot (CMDA)",
        notes=(
            "Front setback increases to 2.0m for roads 9–12m. "
            "All-round 1.5m side/rear setbacks. Typical: 9×15m or 12×15m."
        ),
    ),
    _rule(
        authority=_C, floor_level=_G,
        road_min=12.0, road_max=17.99,
        area_min=200.0, width_min=12.0, depth_min=15.0,
        f_setback=3.0, r_setback=1.5, sl_setback=1.5, sr_setback=1.5,
        fsi=2.00, coverage=50.0, max_h=6.0,
        ref="TNCDBR 2019 §6(4) – Large Residential Plot (CMDA)",
        notes=(
            "Front setback 3m for main roads 12–18m. "
            "Standard 1.5m rear and side setbacks. Typical: 15×20m or 18×24m."
        ),
    ),
    _rule(
        authority=_C, floor_level=_G,
        road_min=18.0, road_max=None,
        area_min=300.0, width_min=15.0, depth_min=18.0,
        f_setback=4.5, r_setback=2.0, sl_setback=2.0, sr_setback=2.0,
        fsi=2.50, coverage=50.0, max_h=6.0,
        ref="TNCDBR 2019 §6(5) – Arterial Road Frontage (CMDA)",
        notes=(
            "Arterial / ring-road frontage: mandatory 4.5m front setback. "
            "FSI bonus to 2.5 per CMDA arterial-road incentive clause. "
            "No upper road-width bound (open category)."
        ),
    ),

    # ── CMDA · G+1 ──────────────────────────────────────────────────────────
    # G+1 is absent for roads < 6m — absence = not permitted.
    _rule(
        authority=_C, floor_level=_G1,
        road_min=6.0,  road_max=8.99,
        area_min=90.0, width_min=6.0, depth_min=12.0,
        f_setback=1.5, r_setback=1.0, sl_setback=1.0, sr_setback=1.0,
        fsi=2.00, coverage=60.0, max_h=10.5,
        ref="TNCDBR 2019 §7(2) + §9(1) – G+1 Residential (CMDA, 6m road)",
        notes=(
            "Minimum road width 6m is the gateway for G+1 (§9(1)). "
            "Height cap 10.5m includes parapet. "
            "Same setbacks as Ground category for this road band. "
            "Typical plot: 6×12m for a compact G+1."
        ),
    ),
    _rule(
        authority=_C, floor_level=_G1,
        road_min=9.0,  road_max=11.99,
        area_min=150.0, width_min=9.0, depth_min=15.0,
        f_setback=2.0, r_setback=1.5, sl_setback=1.5, sr_setback=1.5,
        fsi=2.00, coverage=55.0, max_h=10.5,
        ref="TNCDBR 2019 §7(2) – G+1 Residential (CMDA, 9m road)",
        notes=(
            "G+1 on medium plots abutting 9m roads. "
            "Increased 1.5m all-round for structural clearance."
        ),
    ),
    _rule(
        authority=_C, floor_level=_G1,
        road_min=12.0, road_max=17.99,
        area_min=200.0, width_min=12.0, depth_min=15.0,
        f_setback=3.0, r_setback=1.5, sl_setback=1.5, sr_setback=1.5,
        fsi=2.00, coverage=50.0, max_h=10.5,
        ref="TNCDBR 2019 §7(2) – G+1 Residential (CMDA, 12m road)",
        notes="G+1 on large plots; main-road 3m front setback retained.",
    ),
    _rule(
        authority=_C, floor_level=_G1,
        road_min=18.0, road_max=None,
        area_min=300.0, width_min=15.0, depth_min=18.0,
        f_setback=4.5, r_setback=2.0, sl_setback=2.0, sr_setback=2.0,
        fsi=2.50, coverage=50.0, max_h=10.5,
        ref="TNCDBR 2019 §7(2) – G+1 Residential (CMDA, ≥18m road)",
        notes="G+1 on arterial-road frontage; 4.5m front setback; FSI 2.5.",
    ),

    # ── CMDA · G+2 ──────────────────────────────────────────────────────────
    # G+2 absent for roads < 9m — absence = not permitted.
    _rule(
        authority=_C, floor_level=_G2,
        road_min=9.0,  road_max=11.99,
        area_min=200.0, width_min=10.0, depth_min=15.0,
        f_setback=2.0, r_setback=1.5, sl_setback=1.5, sr_setback=1.5,
        fsi=2.00, coverage=50.0, max_h=14.0,
        ref="TNCDBR 2019 §7(3) + §9(2) – G+2 Residential (CMDA, 9m road)",
        notes=(
            "Minimum 9m road for G+2 (§9(2)). Height 14m includes headroom, "
            "slab, and parapet. Structural engineer certificate mandatory. "
            "Minimum plot 200 sqm, width 10m."
        ),
    ),
    _rule(
        authority=_C, floor_level=_G2,
        road_min=12.0, road_max=17.99,
        area_min=250.0, width_min=12.0, depth_min=18.0,
        f_setback=3.0, r_setback=1.5, sl_setback=1.5, sr_setback=1.5,
        fsi=2.00, coverage=45.0, max_h=14.0,
        ref="TNCDBR 2019 §7(3) – G+2 Residential (CMDA, 12m road)",
        notes="G+2 on large plots; ground coverage reduced to 45% for open space.",
    ),
    _rule(
        authority=_C, floor_level=_G2,
        road_min=18.0, road_max=None,
        area_min=350.0, width_min=15.0, depth_min=20.0,
        f_setback=4.5, r_setback=2.0, sl_setback=2.0, sr_setback=2.0,
        fsi=2.50, coverage=45.0, max_h=14.0,
        ref="TNCDBR 2019 §7(3) – G+2 Residential (CMDA, ≥18m road)",
        notes="G+2 on arterial-road frontage; FSI 2.5 incentive retained.",
    ),

    # ── DTCP · GROUND ───────────────────────────────────────────────────────
    # DTCP is generally more conservative (lower FSI) than CMDA.
    # FSI 1.5 for most categories; 2.0 only on roads ≥12m.
    _rule(
        authority=_D, floor_level=_G,
        road_min=3.0,  road_max=4.49,
        area_min=27.0, width_min=3.0, depth_min=9.0,
        f_setback=1.0, r_setback=0.0, sl_setback=0.0, sr_setback=0.0,
        fsi=1.50, coverage=70.0, max_h=4.5,
        ref="TNCDBR 2019 §6(1) Proviso – EWS/Micro Plot (DTCP)",
        notes=(
            "Same EWS dispensation as CMDA but FSI capped at 1.5. "
            "Applies across all 34 DTCP-governed districts. "
            "Typical plot: 3×9m or 4×9m in town/panchayat areas."
        ),
    ),
    _rule(
        authority=_D, floor_level=_G,
        road_min=4.5,  road_max=5.99,
        area_min=60.0, width_min=5.0, depth_min=10.0,
        f_setback=1.5, r_setback=0.5, sl_setback=0.0, sr_setback=0.0,
        fsi=1.50, coverage=65.0, max_h=5.0,
        ref="TNCDBR 2019 §6(2) – Small Residential Plot (DTCP)",
        notes=(
            "Side setbacks waived for plots ≤5m wide (NBC 2016 Cl.4.2.2). "
            "0.5m rear setback minimum. DTCP FSI = 1.5 (vs CMDA 1.75)."
        ),
    ),
    _rule(
        authority=_D, floor_level=_G,
        road_min=6.0,  road_max=8.99,
        area_min=90.0, width_min=6.0, depth_min=12.0,
        f_setback=1.5, r_setback=1.0, sl_setback=1.0, sr_setback=1.0,
        fsi=1.50, coverage=60.0, max_h=5.5,
        ref="TNCDBR 2019 §6(2) – Standard Residential Plot (DTCP)",
        notes=(
            "Standard DTCP ground-floor rule for most district towns. "
            "FSI capped at 1.5 (CMDA gets 2.0 at this band due to CMA amendment)."
        ),
    ),
    _rule(
        authority=_D, floor_level=_G,
        road_min=9.0,  road_max=11.99,
        area_min=150.0, width_min=9.0, depth_min=15.0,
        f_setback=2.0, r_setback=1.5, sl_setback=1.0, sr_setback=1.0,
        fsi=1.75, coverage=55.0, max_h=6.0,
        ref="TNCDBR 2019 §6(3) – Medium Residential Plot (DTCP)",
        notes=(
            "DTCP FSI rises to 1.75 for plots on 9m+ roads. "
            "Side setback 1.0m (vs CMDA 1.5m) for district towns."
        ),
    ),
    _rule(
        authority=_D, floor_level=_G,
        road_min=12.0, road_max=17.99,
        area_min=200.0, width_min=12.0, depth_min=15.0,
        f_setback=3.0, r_setback=1.5, sl_setback=1.5, sr_setback=1.5,
        fsi=2.00, coverage=50.0, max_h=6.0,
        ref="TNCDBR 2019 §6(4) – Large Residential Plot (DTCP)",
        notes=(
            "DTCP FSI reaches 2.0 only at 12m+ main roads, "
            "aligning with CMDA values for large plot categories."
        ),
    ),
    _rule(
        authority=_D, floor_level=_G,
        road_min=18.0, road_max=None,
        area_min=300.0, width_min=15.0, depth_min=18.0,
        f_setback=3.0, r_setback=2.0, sl_setback=1.5, sr_setback=1.5,
        fsi=2.00, coverage=50.0, max_h=6.0,
        ref="TNCDBR 2019 §6(5) – Arterial Road Frontage (DTCP)",
        notes=(
            "DTCP arterial road: front setback 3.0m (CMDA gets 4.5m). "
            "No FSI bonus for DTCP (no equivalent CMA incentive clause)."
        ),
    ),

    # ── DTCP · G+1 ──────────────────────────────────────────────────────────
    _rule(
        authority=_D, floor_level=_G1,
        road_min=6.0,  road_max=8.99,
        area_min=90.0, width_min=6.0, depth_min=12.0,
        f_setback=1.5, r_setback=1.0, sl_setback=1.0, sr_setback=1.0,
        fsi=1.50, coverage=55.0, max_h=8.5,
        ref="TNCDBR 2019 §7(2) + §9(1) – G+1 Residential (DTCP, 6m road)",
        notes=(
            "G+1 minimum entry point at 6m road for DTCP. "
            "FSI 1.5; ground coverage 55% (reduced from 60% Ground). "
            "Height 8.5m accounts for lower storey-height norms in "
            "smaller DTCP towns vs CMDA."
        ),
    ),
    _rule(
        authority=_D, floor_level=_G1,
        road_min=9.0,  road_max=11.99,
        area_min=150.0, width_min=9.0, depth_min=15.0,
        f_setback=2.0, r_setback=1.5, sl_setback=1.5, sr_setback=1.5,
        fsi=1.75, coverage=50.0, max_h=10.5,
        ref="TNCDBR 2019 §7(2) – G+1 Residential (DTCP, 9m road)",
        notes="FSI 1.75 and 1.5m all-round setbacks for medium DTCP plots.",
    ),
    _rule(
        authority=_D, floor_level=_G1,
        road_min=12.0, road_max=17.99,
        area_min=200.0, width_min=12.0, depth_min=15.0,
        f_setback=3.0, r_setback=1.5, sl_setback=1.5, sr_setback=1.5,
        fsi=2.00, coverage=50.0, max_h=10.5,
        ref="TNCDBR 2019 §7(2) – G+1 Residential (DTCP, 12m road)",
        notes="DTCP FSI reaches 2.0 for G+1 on main-road large plots.",
    ),
    _rule(
        authority=_D, floor_level=_G1,
        road_min=18.0, road_max=None,
        area_min=300.0, width_min=15.0, depth_min=18.0,
        f_setback=3.0, r_setback=2.0, sl_setback=1.5, sr_setback=1.5,
        fsi=2.00, coverage=50.0, max_h=10.5,
        ref="TNCDBR 2019 §7(2) – G+1 Residential (DTCP, ≥18m road)",
        notes="G+1 on DTCP arterial road; no FSI bonus (DTCP policy).",
    ),

    # ── DTCP · G+2 ──────────────────────────────────────────────────────────
    _rule(
        authority=_D, floor_level=_G2,
        road_min=9.0,  road_max=11.99,
        area_min=200.0, width_min=10.0, depth_min=15.0,
        f_setback=2.0, r_setback=1.5, sl_setback=1.5, sr_setback=1.5,
        fsi=1.50, coverage=45.0, max_h=14.0,
        ref="TNCDBR 2019 §7(3) + §9(2) – G+2 Residential (DTCP, 9m road)",
        notes=(
            "DTCP G+2 permitted from 9m road. FSI conservative at 1.5. "
            "Ground coverage drops to 45% to provide open space. "
            "Structural certificate mandatory (TNCDBR §14)."
        ),
    ),
    _rule(
        authority=_D, floor_level=_G2,
        road_min=12.0, road_max=17.99,
        area_min=250.0, width_min=12.0, depth_min=18.0,
        f_setback=3.0, r_setback=1.5, sl_setback=1.5, sr_setback=1.5,
        fsi=2.00, coverage=45.0, max_h=14.0,
        ref="TNCDBR 2019 §7(3) – G+2 Residential (DTCP, 12m road)",
        notes="FSI reaches 2.0 for G+2 on large DTCP plots at main roads.",
    ),
    _rule(
        authority=_D, floor_level=_G2,
        road_min=18.0, road_max=None,
        area_min=350.0, width_min=15.0, depth_min=20.0,
        f_setback=3.0, r_setback=2.0, sl_setback=1.5, sr_setback=1.5,
        fsi=2.00, coverage=45.0, max_h=14.0,
        ref="TNCDBR 2019 §7(3) – G+2 Residential (DTCP, ≥18m road)",
        notes="G+2 on DTCP arterial road; max coverage 45%; FSI 2.0.",
    ),
]


# ============================================================================
# SECTION 2 — VASTU GRID LOGIC
# ============================================================================
#
# Unique key = (room_type, plot_facing, priority)
#
# Vastu zones are ABSOLUTE compass directions — NE is always NE of the plot,
# regardless of which face is the road-facing front.
# The only exception is Entrance, which must be on the road-facing side.
#
# Helper function generates the same rule for all four orientations,
# reducing repetition for rooms whose Vastu zone is orientation-agnostic.
# ============================================================================

ALL_FACINGS = ("North", "South", "East", "West")


def _vastu_all_facings(
    room_type: str,
    vastu_zone: VastuZoneEnum,
    vastu_zone_name: str,
    priority: int,
    is_mandatory: bool,
    rationale: str,
) -> list[dict]:
    """
    Return four identical Vastu rule dicts — one per plot orientation.
    Use for any room whose optimal compass zone is the same regardless
    of which face the plot abuts the road.
    """
    return [
        {
            "room_type":       room_type,
            "plot_facing":     facing,
            "vastu_zone":      vastu_zone,
            "vastu_zone_name": vastu_zone_name,
            "priority":        priority,
            "is_mandatory":    is_mandatory,
            "rationale":       rationale,
        }
        for facing in ALL_FACINGS
    ]


def _vastu_single(
    room_type: str,
    plot_facing: str,
    vastu_zone: VastuZoneEnum,
    vastu_zone_name: str,
    priority: int,
    is_mandatory: bool,
    rationale: str,
) -> dict:
    """Return one Vastu rule dict for a specific (room, facing) pair."""
    return {
        "room_type":       room_type,
        "plot_facing":     plot_facing,
        "vastu_zone":      vastu_zone,
        "vastu_zone_name": vastu_zone_name,
        "priority":        priority,
        "is_mandatory":    is_mandatory,
        "rationale":       rationale,
    }


# Shorthand enum aliases
_NE = VastuZoneEnum.NORTHEAST
_E  = VastuZoneEnum.EAST
_SE = VastuZoneEnum.SOUTHEAST
_S  = VastuZoneEnum.SOUTH
_SW = VastuZoneEnum.SOUTHWEST
_W  = VastuZoneEnum.WEST
_NW = VastuZoneEnum.NORTHWEST
_N  = VastuZoneEnum.NORTH

# ---------------------------------------------------------------------------
# Vastu rule definitions
# ---------------------------------------------------------------------------
VASTU_RULES: list[dict] = []

# ── KITCHEN ──────────────────────────────────────────────────────────────────
# Agni (fire/SE) is the classical cooking zone; NW (Vayu) is the only
# acceptable alternative. Placing a kitchen in the NE or SW is a hard
# Vastu violation and must never be generated.
VASTU_RULES += _vastu_all_facings(
    "Kitchen", _SE, "Agni",
    priority=1, is_mandatory=True,
    rationale=(
        "SE (Agni zone) is the Vastu fire corner. Aligns with morning sun "
        "for natural sterilisation and ventilation. Hard rule — NE/SW "
        "kitchen is a serious Vastu violation and structurally inadvisable."
    ),
)
VASTU_RULES += _vastu_all_facings(
    "Kitchen", _NW, "Vayu",
    priority=2, is_mandatory=False,
    rationale=(
        "NW (Vayu) is acceptable only when SE is architecturally unavailable "
        "(e.g., obstructed by stairs). Requires cross-ventilation provision."
    ),
)

# ── MASTER BEDROOM ───────────────────────────────────────────────────────────
# SW (Niruthi/earth) carries the heaviest mass/stability in Vastu.
# Sleeping with head to the South is a core Vastu sleep directive.
VASTU_RULES += _vastu_all_facings(
    "MasterBedroom", _SW, "Niruthi",
    priority=1, is_mandatory=True,
    rationale=(
        "SW (Niruthi) — earth element, heaviest load-bearing zone. "
        "Provides stability and grounding for the head of the household. "
        "Owner's head should point South while sleeping (§Vastu Sutra)."
    ),
)
VASTU_RULES += _vastu_all_facings(
    "MasterBedroom", _S, "Yama",
    priority=2, is_mandatory=False,
    rationale=(
        "South (Yama) zone accepted when SW is claimed by staircase or "
        "store. Still maintains South-head sleeping orientation."
    ),
)
VASTU_RULES += _vastu_all_facings(
    "MasterBedroom", _W, "Varuna",
    priority=3, is_mandatory=False,
    rationale=(
        "West (Varuna) — last resort for master bedroom. Acceptable on "
        "narrow plots where SW/S zones are too small for minimum NBC "
        "bedroom area (9.5 sqm for master)."
    ),
)

# ── BEDROOM 2 (Children / Guest) ─────────────────────────────────────────────
# West (Varuna — water, nurturing) is ideal for children's rooms.
VASTU_RULES += _vastu_all_facings(
    "Bedroom2", _W, "Varuna",
    priority=1, is_mandatory=True,
    rationale=(
        "West (Varuna) is the water/nurturing zone — ideal for children "
        "and guests. Afternoon shade improves sleep comfort."
    ),
)
VASTU_RULES += _vastu_all_facings(
    "Bedroom2", _NW, "Vayu",
    priority=2, is_mandatory=False,
    rationale=(
        "NW (Vayu) acceptable for Bedroom2; movement/air energy is "
        "suitable for guests. Works well in G+1 plans."
    ),
)
VASTU_RULES += _vastu_all_facings(
    "Bedroom2", _S, "Yama",
    priority=3, is_mandatory=False,
    rationale=(
        "South zone fallback for Bedroom2 when W/NW are exhausted. "
        "Acceptable rest zone per Vastu; avoid E/NE for sleeping rooms."
    ),
)

# ── BEDROOM 3 (Additional) ───────────────────────────────────────────────────
# For 3BHK layouts; South is used after SW is taken by master.
VASTU_RULES += _vastu_all_facings(
    "Bedroom3", _S, "Yama",
    priority=1, is_mandatory=False,
    rationale=(
        "South (Yama) is the secondary rest zone after SW. "
        "For 3BHK plans where SW is MasterBedroom and W is Bedroom2."
    ),
)
VASTU_RULES += _vastu_all_facings(
    "Bedroom3", _W, "Varuna",
    priority=2, is_mandatory=False,
    rationale=(
        "West accepted if S is unavailable; avoid NE/E for sleeping rooms."
    ),
)
VASTU_RULES += _vastu_all_facings(
    "Bedroom3", _NW, "Vayu",
    priority=3, is_mandatory=False,
    rationale=(
        "NW last resort for third bedroom; acceptable in G+1 layouts "
        "where upper floor has more NW space."
    ),
)

# ── POOJA (Prayer Room) ───────────────────────────────────────────────────────
# NE (Ishanya) is the most sacred zone in Vastu — divine/pure energy.
# Placing the prayer room here is a near-absolute rule.
VASTU_RULES += _vastu_all_facings(
    "Pooja", _NE, "Ishanya",
    priority=1, is_mandatory=True,
    rationale=(
        "NE (Ishanya) — the sacred northeast corner. Divine energy, "
        "morning sun (purifying effect), closest to celestial north. "
        "Pooja room in NE is considered the most important Vastu rule "
        "in South Indian residential design."
    ),
)
VASTU_RULES += _vastu_all_facings(
    "Pooja", _E, "Indra",
    priority=2, is_mandatory=False,
    rationale=(
        "East (Indra) — sunrise zone; acceptable for Pooja if NE is "
        "occupied by entrance on East-facing plots."
    ),
)

# ── TOILET / BATHROOM ─────────────────────────────────────────────────────────
# NW (Vayu) is ideal — air movement aids ventilation. Must NEVER be NE/N/E.
VASTU_RULES += _vastu_all_facings(
    "Toilet", _NW, "Vayu",
    priority=1, is_mandatory=True,
    rationale=(
        "NW (Vayu) — air/movement zone. Natural ventilation for sanitary "
        "spaces. Attached bathrooms on NW allow easy waste-pipe routing "
        "to the street/drainage side. Absolute prohibition: never NE."
    ),
)
VASTU_RULES += _vastu_all_facings(
    "Toilet", _W, "Varuna",
    priority=2, is_mandatory=False,
    rationale=(
        "West (Varuna — water) is an acceptable toilet location; water "
        "element aligns with sanitary function."
    ),
)
VASTU_RULES += _vastu_all_facings(
    "Toilet", _S, "Yama",
    priority=3, is_mandatory=False,
    rationale=(
        "South zone — last resort toilet placement. Acceptable per "
        "practical plumbing constraints on south-facing plots. "
        "Never use N, NE, or E for toilets."
    ),
)

# ── HALL / LIVING ROOM ────────────────────────────────────────────────────────
# East (Indra — social energy, sunrise) is ideal. NE is also excellent.
VASTU_RULES += _vastu_all_facings(
    "Hall", _E, "Indra",
    priority=1, is_mandatory=False,
    rationale=(
        "East (Indra) — sunrise/social energy zone. Hall in the east "
        "receives morning light, promoting activity and positivity. "
        "Optimal for receiving guests and family gatherings."
    ),
)
VASTU_RULES += _vastu_all_facings(
    "Hall", _NE, "Ishanya",
    priority=2, is_mandatory=False,
    rationale=(
        "NE acceptable for Hall when east is occupied by entrance. "
        "Light and airy; works well for North-facing plot layouts."
    ),
)
VASTU_RULES += _vastu_all_facings(
    "Hall", _N, "Kubera",
    priority=3, is_mandatory=False,
    rationale=(
        "North (Kubera — wealth/prosperity) as a fallback living zone. "
        "Used for North-facing plots where the entrance occupies the NE "
        "and the hall naturally flows south from it."
    ),
)

# ── DINING ROOM ───────────────────────────────────────────────────────────────
# West (Varuna — meals, nourishment) is traditional. North also acceptable.
VASTU_RULES += _vastu_all_facings(
    "Dining", _W, "Varuna",
    priority=1, is_mandatory=False,
    rationale=(
        "West (Varuna — water/nourishment zone). Dining in the west "
        "aligns meals with the setting sun, promoting calm digestion. "
        "Convenient adjacency to Kitchen (SE) via a central circulation zone."
    ),
)
VASTU_RULES += _vastu_all_facings(
    "Dining", _N, "Kubera",
    priority=2, is_mandatory=False,
    rationale=(
        "North (Kubera) acceptable for dining — abundance energy. "
        "Works well in North-facing plots where north zone is large."
    ),
)
VASTU_RULES += _vastu_all_facings(
    "Dining", _E, "Indra",
    priority=3, is_mandatory=False,
    rationale=(
        "East fallback for Dining in compact plots. Acceptable when "
        "Kitchen (SE) and Dining are combined in an open layout."
    ),
)

# ── STAIRCASE ─────────────────────────────────────────────────────────────────
# SW (Niruthi — heavy/stable) is the preferred staircase zone;
# competes with MasterBedroom — engine resolves by giving SW to bedroom
# and using S or SE for stairs.
VASTU_RULES += _vastu_all_facings(
    "Staircase", _SW, "Niruthi",
    priority=1, is_mandatory=False,
    rationale=(
        "SW (Niruthi) — earth/stability zone; ideal structural load for "
        "staircase. However, conflict with MasterBedroom P1 is common; "
        "engine assigns SW to bedroom and moves stairs to P2/P3."
    ),
)
VASTU_RULES += _vastu_all_facings(
    "Staircase", _S, "Yama",
    priority=2, is_mandatory=False,
    rationale=(
        "South zone practical fallback for staircase; structural loads "
        "on the south wall are Vastu-neutral."
    ),
)
VASTU_RULES += _vastu_all_facings(
    "Staircase", _SE, "Agni",
    priority=3, is_mandatory=False,
    rationale=(
        "SE last resort for staircase. Competes with Kitchen priority; "
        "engine logs a Vastu deviation note in the output report."
    ),
)

# ── STORE / UTILITY ROOM ──────────────────────────────────────────────────────
# W/SW for heavy storage; S also acceptable.
VASTU_RULES += _vastu_all_facings(
    "StoreRoom", _W, "Varuna",
    priority=1, is_mandatory=False,
    rationale=(
        "West (Varuna) is ideal for storage — shade, stable temperature. "
        "Good for grain, provisions, and utility items."
    ),
)
VASTU_RULES += _vastu_all_facings(
    "StoreRoom", _SW, "Niruthi",
    priority=2, is_mandatory=False,
    rationale=(
        "SW acceptable for store — heavy/stable energy. Used when SW is "
        "not taken by MasterBedroom or Staircase."
    ),
)
VASTU_RULES += _vastu_all_facings(
    "StoreRoom", _S, "Yama",
    priority=3, is_mandatory=False,
    rationale="South fallback for utility/store room.",
)

# ── ENTRANCE (ORIENTATION-DEPENDENT) ─────────────────────────────────────────
# The entrance door must be on the road-facing side.
# Within that face, Vastu prescribes a preferred Pada (sector).
#
# Classical Vastu Pada mapping for entrance (simplified for 4-octant model):
#   North-facing  → NE sector of north face is the most auspicious pada
#   East-facing   → NE sector of east face (Mukhya pada)
#   South-facing  → SE sector of south face (Grihapati pada — SE is
#                   the most Vastu-neutral entry on a south-facing plot)
#   West-facing   → NW sector of west face (Sugriva pada)

# --- North-facing entrance ---
VASTU_RULES.append(_vastu_single(
    "Entrance", "North", _NE, "Ishanya",
    priority=1, is_mandatory=True,
    rationale=(
        "North-facing plot: entrance in NE sector (Ishanya pada). "
        "Most auspicious entry on a north-facing plot per Vastu Sutra."
    ),
))
VASTU_RULES.append(_vastu_single(
    "Entrance", "North", _N, "Kubera",
    priority=2, is_mandatory=False,
    rationale=(
        "North entry at the Kubera sector — acceptable fallback when "
        "NE is occupied by Pooja room alcove or utility niche."
    ),
))

# --- East-facing entrance ---
VASTU_RULES.append(_vastu_single(
    "Entrance", "East", _NE, "Ishanya",
    priority=1, is_mandatory=True,
    rationale=(
        "East-facing plot: entrance in NE sector (Mukhya pada). "
        "Classic auspicious east-entry; morning sun greets the threshold."
    ),
))
VASTU_RULES.append(_vastu_single(
    "Entrance", "East", _E, "Indra",
    priority=2, is_mandatory=False,
    rationale=(
        "East entry at the Indra (central east) sector — acceptable "
        "fallback when plot width constrains NE sector placement."
    ),
))

# --- South-facing entrance ---
VASTU_RULES.append(_vastu_single(
    "Entrance", "South", _SE, "Agni",
    priority=1, is_mandatory=True,
    rationale=(
        "South-facing plot: entrance in SE sector (Grihapati pada). "
        "South entries at the SE pada are considered acceptable in Tamil "
        "Vastu tradition; direct south-centre entry is inauspicious. "
        "SE placement also avoids conflict with Kitchen (SE zone)."
    ),
))
VASTU_RULES.append(_vastu_single(
    "Entrance", "South", _S, "Yama",
    priority=2, is_mandatory=False,
    rationale=(
        "South-centre entry as fallback when SE sector is obstructed. "
        "Engine must log a Vastu deviation warning in the output report."
    ),
))

# --- West-facing entrance ---
VASTU_RULES.append(_vastu_single(
    "Entrance", "West", _NW, "Vayu",
    priority=1, is_mandatory=True,
    rationale=(
        "West-facing plot: entrance in NW sector (Sugriva pada). "
        "NW entry on west-facing plots channels Vayu energy inward."
    ),
))
VASTU_RULES.append(_vastu_single(
    "Entrance", "West", _W, "Varuna",
    priority=2, is_mandatory=False,
    rationale=(
        "West-centre entry as fallback for narrow plots where NW sector "
        "is too shallow for a standard door opening."
    ),
))


# ============================================================================
# SECTION 3 — VALIDATION
# ============================================================================

def _validate_plot_rules(rules: list[dict]) -> None:
    """Fail fast on dataset inconsistencies before hitting the DB."""
    total = len(rules)
    # 13 CMDA rows (6 Ground + 4 G+1 + 3 G+2) +
    # 13 DTCP rows (6 Ground + 4 G+1 + 3 G+2) = 26 total
    assert total == 26, f"Expected 26 PlotEligibilityRules rows, got {total}."

    # Check unique constraint: (authority, floor_level, road_width_min_m)
    seen_keys: set[tuple] = set()
    for r in rules:
        key = (r["authority"], r["floor_level"], r["road_width_min_m"])
        assert key not in seen_keys, f"Duplicate rule key: {key}"
        seen_keys.add(key)

    # Road-width gate enforcement: no G+1 rows below 6m, no G+2 rows below 9m
    for r in rules:
        if r["floor_level"] == FloorLevelEnum.G_PLUS_1:
            assert r["road_width_min_m"] >= 6.0, (
                f"G+1 rule found with road_min < 6m: {r}"
            )
        if r["floor_level"] == FloorLevelEnum.G_PLUS_2:
            assert r["road_width_min_m"] >= 9.0, (
                f"G+2 rule found with road_min < 9m: {r}"
            )

    # FSI must be positive; coverage 0–100
    for r in rules:
        assert r["fsi_value"] > 0,           f"Invalid FSI in: {r}"
        assert 0 < r["ground_coverage_pct"] <= 100, f"Invalid coverage in: {r}"
        assert r["setback_front_m"] >= 0,    f"Negative front setback in: {r}"

    print(f"[Validation] PlotEligibilityRules: {total} rows — OK.")


def _validate_vastu_rules(rules: list[dict]) -> None:
    """Fail fast on Vastu dataset inconsistencies."""
    total = len(rules)

    # Check unique constraint: (room_type, plot_facing, priority)
    seen_keys: set[tuple] = set()
    for r in rules:
        key = (r["room_type"], r["plot_facing"], r["priority"])
        assert key not in seen_keys, f"Duplicate Vastu key: {key}"
        seen_keys.add(key)

    # Validate enums
    valid_facings = {"North", "South", "East", "West"}
    valid_priorities = {1, 2, 3}
    for r in rules:
        assert r["plot_facing"] in valid_facings, (
            f"Invalid plot_facing '{r['plot_facing']}'"
        )
        assert r["priority"] in valid_priorities, (
            f"Invalid priority {r['priority']} for {r['room_type']}"
        )
        assert isinstance(r["vastu_zone"], VastuZoneEnum), (
            f"vastu_zone must be VastuZoneEnum: {r}"
        )

    # Entrance must have entries for all 4 orientations at P1 and P2
    entrance_facings_p1 = {
        r["plot_facing"] for r in rules
        if r["room_type"] == "Entrance" and r["priority"] == 1
    }
    assert entrance_facings_p1 == {"North", "South", "East", "West"}, (
        f"Entrance missing P1 for some orientations: {entrance_facings_p1}"
    )

    # Critical safety checks: Kitchen must NOT be placed in NE/N/E at P1
    for r in rules:
        if r["room_type"] == "Kitchen" and r["priority"] == 1:
            assert r["vastu_zone"] == VastuZoneEnum.SOUTHEAST, (
                f"Kitchen P1 must always be SE (Agni). Got: {r['vastu_zone']}"
            )

    # Pooja must NOT be placed outside NE at P1
    for r in rules:
        if r["room_type"] == "Pooja" and r["priority"] == 1:
            assert r["vastu_zone"] == VastuZoneEnum.NORTHEAST, (
                f"Pooja P1 must always be NE (Ishanya). Got: {r['vastu_zone']}"
            )

    print(f"[Validation] VastuGridLogic: {total} rows — OK.")


# ============================================================================
# SECTION 4 — SEED FUNCTIONS
# ============================================================================

def seed_plot_eligibility_rules(db) -> int:
    """
    Insert PlotEligibilityRules rows into an already-open session.
    Caller is responsible for commit/rollback. Returns row count inserted.
    Tables must already exist (call Base.metadata.create_all before this).
    """
    existing = db.query(PlotEligibilityRules).count()
    if existing > 0:
        print(
            f"[Seed] PlotEligibilityRules skipped — "
            f"{existing} rows already present. Pass --drop to reseed."
        )
        return 0
    rows = [PlotEligibilityRules(**r) for r in PLOT_ELIGIBILITY_RULES]
    db.bulk_save_objects(rows)
    print(f"[Seed] Queued {len(rows)} PlotEligibilityRules rows.")
    return len(rows)


def seed_vastu_grid_logic(db) -> int:
    """
    Insert VastuGridLogic rows into an already-open session.
    Caller is responsible for commit/rollback. Returns row count inserted.
    Tables must already exist (call Base.metadata.create_all before this).
    """
    existing = db.query(VastuGridLogic).count()
    if existing > 0:
        print(
            f"[Seed] VastuGridLogic skipped — "
            f"{existing} rows already present. Pass --drop to reseed."
        )
        return 0
    rows = [VastuGridLogic(**r) for r in VASTU_RULES]
    db.bulk_save_objects(rows)
    print(f"[Seed] Queued {len(rows)} VastuGridLogic rows.")
    return len(rows)


def seed_all(drop_existing: bool = False) -> None:
    """
    Validate datasets, manage DDL, then seed both tables atomically.

    Design: ALL DDL (DROP / CREATE) happens BEFORE the session opens.
    This avoids the SQLite single-writer lock that occurs when a DROP
    is issued via engine while a session holds an open write transaction.

    Flow:
      1. Validate in-memory datasets (no DB I/O).
      2. If --drop: DROP both tables via engine outside any session.
      3. CREATE all tables (idempotent).
      4. Open ONE session, insert all rows, commit in a single transaction.
    """
    # ── Step 1: validate datasets (pure Python, no DB) ──────────────────────
    _validate_plot_rules(PLOT_ELIGIBILITY_RULES)
    _validate_vastu_rules(VASTU_RULES)

    # ── Step 2: DDL — drops outside session (avoids SQLite lock) ────────────
    if drop_existing:
        # Drop in reverse dependency order; checkfirst=True is safe to repeat.
        with engine.begin() as conn:
            VastuGridLogic.__table__.drop(conn, checkfirst=True)
            PlotEligibilityRules.__table__.drop(conn, checkfirst=True)
        print("[DB] Dropped plot_eligibility_rules and vastu_grid_logic tables.")

    # ── Step 3: CREATE (idempotent) ──────────────────────────────────────────
    Base.metadata.create_all(bind=engine)
    print("[DB] Tables verified / created.")

    # ── Step 4: open ONE session, insert, commit atomically ─────────────────
    db = SessionLocal()
    try:
        plot_count  = seed_plot_eligibility_rules(db)
        vastu_count = seed_vastu_grid_logic(db)
        db.commit()
        if plot_count + vastu_count > 0:
            print(
                f"[Seed] Committed — "
                f"{plot_count} rule rows + {vastu_count} Vastu rows."
            )
        else:
            print("[Seed] Nothing committed (both tables already populated).")
    except Exception as exc:
        db.rollback()
        print(f"[Seed] ERROR — full rollback. Reason: {exc}")
        raise
    finally:
        db.close()


# ============================================================================
# SECTION 5 — CLI ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Seed PlotEligibilityRules (TNCDBR 2019) and VastuGridLogic "
            "tables for the TN-Flow engine."
        )
    )
    parser.add_argument(
        "--drop",
        action="store_true",
        help="Drop and recreate both tables before seeding (dev only).",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print a summary report of all seeded rules after completion.",
    )
    args = parser.parse_args()

    seed_all(drop_existing=args.drop)

    if args.report:
        db = SessionLocal()
        try:
            print("\n=== PlotEligibilityRules Summary ===========================")
            rules = db.query(PlotEligibilityRules).order_by(
                PlotEligibilityRules.authority,
                PlotEligibilityRules.floor_level,
                PlotEligibilityRules.road_width_min_m,
            ).all()
            print(
                f"{'Auth':<6} {'Floor':<8} {'Road>=':>6}  "
                f"{'AreaMin':>8}  {'F':>4} {'R':>4} {'SL':>4} {'SR':>4}  "
                f"{'FSI':>4}  {'Cov%':>5}  {'MaxH':>5}"
            )
            print("-" * 75)
            for r in rules:
                print(
                    f"{r.authority.value:<6} {r.floor_level.value:<8} "
                    f"{r.road_width_min_m:>5.1f}m  "
                    f"{r.plot_area_min_sqm:>7.0f}sqm  "
                    f"{r.setback_front_m:>3.1f} "
                    f"{r.setback_rear_m:>3.1f} "
                    f"{r.setback_side_left_m:>3.1f} "
                    f"{r.setback_side_right_m:>3.1f}  "
                    f"{r.fsi_value:>4.2f}  "
                    f"{r.ground_coverage_pct:>4.0f}%  "
                    f"{(str(r.max_height_m)+'m') if r.max_height_m else 'N/A':>5}"
                )

            print(f"\n=== VastuGridLogic Summary =================================")
            vastu = db.query(VastuGridLogic).order_by(
                VastuGridLogic.room_type,
                VastuGridLogic.plot_facing,
                VastuGridLogic.priority,
            ).all()
            print(
                f"{'Room':<15} {'Facing':<7} {'P':>2}  "
                f"{'Zone':<12} {'Devata':<12} {'Mandatory'}"
            )
            print("-" * 62)
            for v in vastu:
                print(
                    f"{v.room_type:<15} {v.plot_facing:<7} {v.priority:>2}  "
                    f"{v.vastu_zone.value:<12} {v.vastu_zone_name:<12} "
                    f"{'YES' if v.is_mandatory else 'no'}"
                )
        finally:
            db.close()
