"""
ZonePlanner — Architectural Zoning Pre-Pass
============================================
Divides the usable plot depth into three ordered bands BEFORE room cells
are assigned, enforcing the canonical Tamil Nadu spatial hierarchy:

    Entry (high-y)
    ─────────────────────────────────
    PUBLIC BAND      verandah · living
    ─────────────────────────────────
    SEMI-PRIVATE     dining · kitchen · corridor
    ─────────────────────────────────
    PRIVATE BAND     bedroom(s) · bathroom(s) · pooja · study
    ─────────────────────────────────
    Rear  (low-y)

Hard rules enforced before placement:
  H1 — No bedroom in public band
  H2 — Kitchen always in same or adjacent band to dining
  H3 — Each bathroom must be assigned to the same band as a bedroom
  H4 — Bands are contiguous and non-overlapping

Soft rules (produce warnings, not failures):
  S1 — Verandah on entry side
  S2 — Kitchen not sharing a band with bedrooms
  S3 — Corridor at public/private boundary (depth fraction 0.35–0.55)

Usage (in adjacency_solver.py):

    from algorithms.zone_planner import ZonePlanner

    planner = ZonePlanner(plot_width, plot_depth, facing)
    zp      = planner.build(room_types)   # raises ZoneError on H-violations
    # then pass zp.public / zp.semi / zp.private to layout functions

Source: Hillier & Hanson "The Social Logic of Space" 1984 — justified graph;
        HUDCO 2012 housing typologies; TNCDBR 2019 room sequence norms.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional

# ── Zone membership (three-zone model used by ZonePlanner) ────────────────────
# Note: existing solver uses public/private/service — we reclassify here into
# public / semi_private / private for the depth-hierarchy enforcement.
ZONE_3: Dict[str, str] = {
    # Public — directly accessible from entry
    "verandah":  "public",
    "living":    "public",
    "entrance":  "public",
    "courtyard": "public",
    # Semi-private — functional support, not guest-sleeping
    "dining":    "semi",
    "kitchen":   "semi",
    "corridor":  "semi",
    "utility":   "semi",
    "store":     "semi",
    "office":    "semi",
    # Private — sleeping, devotion, hygiene
    "bedroom":   "private",
    "bathroom":  "private",
    "toilet":    "private",
    "pooja":     "private",
    "study":     "private",
    "lightwell": "private",
}

# Canonical depth fractions from entry wall (high-y = 0.0, rear = 1.0)
# These are the DEFAULT band boundaries; ZonePlanner adjusts them to the
# actual room counts so that each band has enough height for its rooms.
_DEFAULT_BAND_FRACTIONS: Dict[str, Tuple[float, float]] = {
    "public":  (0.00, 0.32),   # ~32% of usable depth for public zone
    "semi":    (0.32, 0.55),   # ~23% for semi-private (kitchen, dining, corridor)
    "private": (0.55, 1.00),   # ~45% for bedrooms + bathrooms
}

# NBC 2016 minimum depths per zone to ensure each band is tall enough
_MIN_ZONE_DEPTH_M: Dict[str, float] = {
    "public":  3.0,   # living ≥ 3.0m depth (NBC Part 3 §8.1.1)
    "semi":    2.2,   # kitchen ≥ 2.2m depth (NBC Part 3 §8.1.3)
    "private": 2.4,   # bedroom ≥ 2.4m depth (NBC Part 3 §8.1.2)
}


class ZoneError(ValueError):
    """Raised when a hard zoning constraint cannot be satisfied."""


@dataclass
class ZoneBand:
    """One horizontal depth band in the layout."""
    name: str           # "public" | "semi" | "private"
    depth_start: float  # normalised from entry (0.0 = entry wall)
    depth_end: float    # normalised
    rooms: List[str] = field(default_factory=list)  # room types assigned here

    @property
    def depth_fraction(self) -> float:
        return self.depth_end - self.depth_start

    def depth_m(self, plot_depth: float) -> float:
        return self.depth_fraction * plot_depth


@dataclass
class ZonePlan:
    """Output of ZonePlanner.build() — the zoning blueprint."""
    public:  ZoneBand
    semi:    ZoneBand
    private: ZoneBand

    # Flattened per-solver-zone lists (maps onto existing solver interface)
    public_rooms:  List[str] = field(default_factory=list)
    semi_rooms:    List[str] = field(default_factory=list)
    private_rooms: List[str] = field(default_factory=list)

    # Back-compat aliases for existing solver (service = semi + bathrooms)
    @property
    def service_rooms(self) -> List[str]:
        """Return semi + bathroom/toilet/utility — matches solver's service_rooms."""
        svc_types = {"kitchen", "utility", "bathroom", "toilet", "corridor", "store"}
        return [r for r in self.semi_rooms + self.private_rooms if r in svc_types]

    violations: List[str] = field(default_factory=list)   # H-rule failures
    warnings:   List[str] = field(default_factory=list)   # S-rule notes

    def has_hard_violations(self) -> bool:
        return len(self.violations) > 0

    # Convenience: col_ratios / row_ratios guidance
    row_depth_fractions: List[float] = field(default_factory=list)
    # [public_fraction, semi_fraction, private_fraction] — sum = 1.0


class ZonePlanner:
    """
    Computes the three-band zoning blueprint for a floor plan.

    Parameters
    ----------
    plot_width : float
        Usable plot width in metres (post-setback).
    plot_depth : float
        Usable plot depth in metres (post-setback + verandah).
    facing : str
        Entry direction — "North" | "South" | "East" | "West" | ...
    """

    def __init__(self, plot_width: float, plot_depth: float, facing: str = "North"):
        self.plot_width  = plot_width
        self.plot_depth  = plot_depth
        self.facing      = facing

    # ─────────────────────────────────────────────────────────────────────────
    def build(self, room_types: List[str]) -> ZonePlan:
        """
        Assign each room type to its correct zone band and compute depth
        fractions.  Raises ZoneError if any hard rule is violated.

        Parameters
        ----------
        room_types : List[str]
            Flat list with repetitions, e.g. ["living","bedroom","bedroom",
            "kitchen","bathroom","bathroom","corridor","utility"].

        Returns
        -------
        ZonePlan
            Band definitions + per-zone room lists + violation/warning lists.
        """
        # ── Step 1: Initial zone assignment ─────────────────────────────────
        pub, semi, priv = self._initial_assignment(room_types)

        # ── Step 2: Enforce hard rules (may reassign rooms) ──────────────────
        violations: List[str] = []
        warnings:   List[str] = []
        pub, semi, priv = self._enforce_hard_rules(pub, semi, priv, violations, room_types)

        # ── Step 3: Check soft rules ─────────────────────────────────────────
        self._check_soft_rules(pub, semi, priv, warnings)

        # ── Step 4: Compute depth fractions ──────────────────────────────────
        fractions = self._compute_depth_fractions(pub, semi, priv)

        # ── Step 5: Build band objects ────────────────────────────────────────
        pub_band = ZoneBand(
            name="public",
            depth_start=0.0,
            depth_end=fractions[0],
            rooms=pub,
        )
        semi_band = ZoneBand(
            name="semi",
            depth_start=fractions[0],
            depth_end=fractions[0] + fractions[1],
            rooms=semi,
        )
        priv_band = ZoneBand(
            name="private",
            depth_start=fractions[0] + fractions[1],
            depth_end=1.0,
            rooms=priv,
        )

        # Validate minimum band depths (H4) — warn if shallow, hard-fail only if
        # band fraction is degenerate (< 5% of depth, i.e. unusable)
        for band, zone in [(pub_band, "public"), (semi_band, "semi"), (priv_band, "private")]:
            actual_d = band.depth_m(self.plot_depth)
            min_d    = _MIN_ZONE_DEPTH_M[zone]
            if actual_d < 0.5:                       # truly degenerate
                violations.append(
                    f"H4: {zone} band depth {actual_d:.2f}m is degenerate (< 0.5m)"
                )
            elif actual_d < min_d - 0.1:             # soft warn only
                warnings.append(
                    f"H4: {zone} band depth {actual_d:.2f}m below recommended {min_d:.1f}m"
                )

        if violations:
            raise ZoneError(
                f"ZonePlanner: {len(violations)} hard rule violation(s) — "
                + "; ".join(violations)
            )

        # ── Step 6: Build back-compat solver lists ────────────────────────────
        # public_rooms → living/verandah/courtyard
        # semi_rooms   → kitchen/dining/corridor/utility
        # private_rooms→ bedroom/bathroom/pooja/study
        return ZonePlan(
            public=pub_band,
            semi=semi_band,
            private=priv_band,
            public_rooms=list(pub),
            semi_rooms=list(semi),
            private_rooms=list(priv),
            violations=violations,
            warnings=warnings,
            row_depth_fractions=list(fractions),
        )

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 1 — Initial zone assignment from ZONE_3 lookup
    # ─────────────────────────────────────────────────────────────────────────
    def _initial_assignment(
        self, room_types: List[str]
    ) -> Tuple[List[str], List[str], List[str]]:
        pub:  List[str] = []
        semi: List[str] = []
        priv: List[str] = []
        for rt in room_types:
            zone = ZONE_3.get(rt, "semi")
            if zone == "public":
                pub.append(rt)
            elif zone == "semi":
                semi.append(rt)
            else:
                priv.append(rt)
        return pub, semi, priv

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 2 — Hard rules enforcement
    # ─────────────────────────────────────────────────────────────────────────
    def _enforce_hard_rules(
        self,
        pub:  List[str],
        semi: List[str],
        priv: List[str],
        violations: List[str],
        room_types: Optional[List[str]] = None,
    ) -> Tuple[List[str], List[str], List[str]]:
        """
        H1 — Bedrooms must NOT appear in the public band.
        H2 — Kitchen and dining must share a band or be in adjacent bands.
        H3 — Each bathroom must be co-zoned with at least one bedroom.
        """
        pub  = list(pub)
        semi = list(semi)
        priv = list(priv)

        # ── H1: Bedrooms out of public band ──────────────────────────────────
        beds_in_pub = [r for r in pub if r == "bedroom"]
        if beds_in_pub:
            violations.append(
                f"H1: {len(beds_in_pub)} bedroom(s) in public band — "
                "moved to private band"
            )
            for r in beds_in_pub:
                pub.remove(r)
                priv.append(r)

        # ── H2: Kitchen–dining co-location ───────────────────────────────────
        has_kitchen_semi  = "kitchen" in semi
        has_dining_semi   = "dining"  in semi
        has_kitchen_priv  = "kitchen" in priv
        has_dining_pub    = "dining"  in pub
        has_dining_priv   = "dining"  in priv

        # Dining in public band → move it to semi (it's semi-private, not public)
        while "dining" in pub:
            pub.remove("dining")
            semi.append("dining")

        # Kitchen in private band → move to semi
        while "kitchen" in priv:
            priv.remove("kitchen")
            semi.append("kitchen")

        # Verify kitchen + dining co-location — only flag when dining actually exists
        _rt = room_types or []
        has_dining_anywhere = ("dining" in pub or "dining" in semi
                               or "dining" in priv or "dining" in _rt)
        if "kitchen" in semi and "dining" not in semi and has_dining_anywhere:
            violations.append(
                "H2: Kitchen in semi band but dining not in adjacent band — "
                "check template has explicit dining room"
            )

        # ── H3: Bathrooms co-zoned with bedrooms ─────────────────────────────
        n_beds  = priv.count("bedroom")
        n_baths = priv.count("bathroom") + priv.count("toilet")
        baths_in_semi = semi.count("bathroom") + semi.count("toilet")

        if baths_in_semi > 0:
            # Move bathrooms from semi to private (they must attach to bedrooms)
            for rt in ["bathroom", "toilet"]:
                while rt in semi:
                    semi.remove(rt)
                    priv.append(rt)

        if n_beds == 0 and n_baths > 0:
            violations.append(
                f"H3: {n_baths} bathroom(s) in private band but no bedrooms found"
            )

        return pub, semi, priv

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 3 — Soft rule checks (warnings only)
    # ─────────────────────────────────────────────────────────────────────────
    def _check_soft_rules(
        self,
        pub:  List[str],
        semi: List[str],
        priv: List[str],
        warnings: List[str],
    ) -> None:
        # S1 — Verandah should exist in public band
        if "verandah" not in pub and "entrance" not in pub:
            warnings.append("S1: No verandah/entrance in public band — entry buffer missing")

        # S2 — Kitchen should NOT share band with bedrooms
        if "kitchen" in priv:
            warnings.append("S2: Kitchen co-zoned with bedrooms — cooking odour risk")

        # S3 — Corridor should be in semi band at zone boundary
        if "corridor" in pub:
            warnings.append("S3: Corridor in public band — should be at public/private boundary")
        if "corridor" in priv:
            warnings.append("S3: Corridor in private band — should be at public/private boundary")

        # S4 — Pooja should be in private band (inner sanctum principle)
        if "pooja" in pub or "pooja" in semi:
            warnings.append("S4: Pooja room not in private band — Vastu prefers interior placement")

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 4 — Compute depth fractions proportional to room count in each band
    # ─────────────────────────────────────────────────────────────────────────
    def _compute_depth_fractions(
        self,
        pub:  List[str],
        semi: List[str],
        priv: List[str],
    ) -> List[float]:
        """
        Return [pub_frac, semi_frac, priv_frac] summing to 1.0.

        Basis: each room type contributes its NBC minimum depth to its band.
        Final fractions are normalised and clamped so each band >= its minimum.
        """
        # NBC minimum depths per room type
        _ROOM_DEPTH: Dict[str, float] = {
            "living":    3.6,  "verandah": 1.5,  "entrance": 1.5,
            "courtyard": 3.0,  "dining":   2.7,  "kitchen":  2.8,
            "corridor":  1.1,  "utility":  1.5,  "store":    1.2,
            "bedroom":   3.0,  "bathroom": 2.0,  "toilet":   1.8,
            "pooja":     1.4,  "study":    2.4,  "office":   2.4,
            "lightwell": 1.5,
        }

        def _band_raw(rooms: List[str]) -> float:
            if not rooms:
                return 0.0
            # Max room depth in band (rooms stack, so tallest row defines band height)
            # Use max of the dominant room type per band
            return max(_ROOM_DEPTH.get(rt, 2.0) for rt in rooms)

        raw_pub  = max(_band_raw(pub),  _MIN_ZONE_DEPTH_M["public"])
        raw_semi = max(_band_raw(semi), _MIN_ZONE_DEPTH_M["semi"])
        raw_priv = max(_band_raw(priv), _MIN_ZONE_DEPTH_M["private"])

        # Private band has multiple rows (beds + baths) — add row depth for beds
        n_bed_rows = max(1, _count_private_rows(priv))
        raw_priv   = max(raw_priv * n_bed_rows, _MIN_ZONE_DEPTH_M["private"])

        total = raw_pub + raw_semi + raw_priv
        if total <= 0:
            return [0.32, 0.23, 0.45]

        fracs = [
            round(raw_pub  / total, 4),
            round(raw_semi / total, 4),
            round(raw_priv / total, 4),
        ]
        # Fix rounding so fracs sum to 1.0
        fracs[2] = round(1.0 - fracs[0] - fracs[1], 4)
        return fracs


def _count_private_rows(priv: List[str]) -> int:
    """Estimate number of stacked rows in the private band.
    Bedrooms and bathrooms pair into rows; corridor adds 1 row.
    """
    n_beds  = priv.count("bedroom")
    n_baths = priv.count("bathroom") + priv.count("toilet")
    # Each bed+bath pair = 1 row; remaining beds = 1 row; remaining baths = 1 row
    bed_bath_pairs = min(n_beds, n_baths)
    remaining_beds = n_beds - bed_bath_pairs
    remaining_baths = n_baths - bed_bath_pairs
    rows = bed_bath_pairs + remaining_beds + remaining_baths
    return max(1, rows)


# ─────────────────────────────────────────────────────────────────────────────
# CONVENIENCE WRAPPER
# ─────────────────────────────────────────────────────────────────────────────

def plan_zones(
    room_types: List[str],
    plot_width: float,
    plot_depth: float,
    facing: str = "North",
    strict: bool = False,
) -> ZonePlan:
    """
    One-call wrapper.  Returns a ZonePlan or raises ZoneError if strict=True
    and hard constraints fail.  With strict=False (default), violations are
    stored in ZonePlan.violations but no exception is raised.

    Parameters
    ----------
    room_types : flat list of room type strings (may have duplicates)
    plot_width : usable width in metres
    plot_depth : usable depth in metres
    facing     : entry direction string
    strict     : if True, raise ZoneError on hard constraint failures

    Returns
    -------
    ZonePlan
    """
    planner = ZonePlanner(plot_width, plot_depth, facing)
    if strict:
        return planner.build(room_types)
    # Non-strict: catch ZoneError, still return a best-effort plan
    try:
        return planner.build(room_types)
    except ZoneError as e:
        # Return a degraded plan with violations recorded
        pub, semi, priv = planner._initial_assignment(room_types)
        fracs = planner._compute_depth_fractions(pub, semi, priv)
        return ZonePlan(
            public  = ZoneBand("public",  0.0,         fracs[0], pub),
            semi    = ZoneBand("semi",    fracs[0],    fracs[0]+fracs[1], semi),
            private = ZoneBand("private", fracs[0]+fracs[1], 1.0, priv),
            public_rooms=pub, semi_rooms=semi, private_rooms=priv,
            violations=[str(e)],
            warnings=[],
            row_depth_fractions=fracs,
        )
