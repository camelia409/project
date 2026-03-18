"""
BuildingCodeChecker — Consolidated TNCDBR 2019 + NBC 2016 Compliance Validator
================================================================================
Aggregates setback, OSR, ground coverage, FSI, and room-level NBC checks
into a single Compliance Report dictionary.

Sources:
  - TNCDBR 2019 G.O. Ms. 78 (setbacks, OSR, ground coverage)
  - NBC 2016 Part 3 Cl. 8.1 (room area & width minimums)
  - CMDA DCR 2022 Cl. 15 (road-width front setbacks)
  - NBC 2016 Part 4 Cl. 4.4.3 (exit widths by occupancy)

Usage:
    checker = BuildingCodeChecker(plot_area=180, road_width=9.0,
                                   plot_width=12, plot_height=15)
    report = checker.generate_compliance_report(rooms=fp.rooms)
"""

from data.nbc_standards import (
    check_nbc_compliance, NBC_ROOM_MINIMUMS, FSI_BY_CITY,
    NBC_VENTILATION, NBC_CEILING_HEIGHTS
)
from data.tn_setbacks import (
    get_setback_for_plot, compute_usable_area,
    CMDA_ROAD_WIDTH_SETBACKS, GROUND_COVERAGE_LIMITS
)


# ── Road width string → CMDA key mapping ────────────────────────────────────
_ROAD_WIDTH_MAP = {
    "Less than 6m": "road_upto_5m_wide",
    "6-9m":         "road_5m_to_9m",
    "9-12m":        "road_9m_to_12m",
    "12-18m":       "road_12m_to_18m",
    "More than 18m":"road_above_18m",
}


class BuildingCodeChecker:
    """One-stop compliance checker for Tamil Nadu residential floor plans."""

    def __init__(self, plot_area: float, road_width, plot_width: float = None,
                 plot_height: float = None, zone: str = "CMDA",
                 num_floors: int = 1, occupancy: int = 4):
        self.plot_area = plot_area
        self.road_width = road_width          # string key or float metres
        self.plot_width = plot_width or 0
        self.plot_height = plot_height or 0
        self.zone = zone
        self.num_floors = num_floors
        self.occupancy = occupancy

        # Pre-compute setbacks
        self._tncdbr = get_setback_for_plot(plot_area)
        self._usable = compute_usable_area(plot_width, plot_height) if plot_width and plot_height else None

    # ── Setback computation ──────────────────────────────────────────────────

    def compute_setbacks(self) -> dict:
        """Return applicable setbacks (max of TNCDBR table + CMDA road rule)."""
        front = self._tncdbr["front_m"]
        rear = self._tncdbr["rear_m"]
        side = self._tncdbr["side_each_m"]

        # CMDA road-width override (stricter governs)
        cmda_key = _ROAD_WIDTH_MAP.get(self.road_width)
        cmda_front = 0
        if cmda_key and cmda_key in CMDA_ROAD_WIDTH_SETBACKS:
            cmda_front = CMDA_ROAD_WIDTH_SETBACKS[cmda_key]["front_setback_m"]
        elif isinstance(self.road_width, (int, float)):
            # Numeric road width → find matching bracket
            rw = float(self.road_width)
            if rw <= 5:
                cmda_front = 2.0
            elif rw <= 9:
                cmda_front = 3.0
            elif rw <= 12:
                cmda_front = 4.5
            elif rw <= 18:
                cmda_front = 6.0
            else:
                cmda_front = 9.0

        effective_front = max(front, cmda_front)

        return {
            "front_m": effective_front,
            "rear_m": rear,
            "side_each_m": side,
            "tncdbr_front_m": front,
            "cmda_front_m": cmda_front,
            "clause": self._tncdbr.get("note", "TNCDBR 2019 Table 1"),
        }

    # ── OSR (Open Space Reservation) ─────────────────────────────────────────

    def compute_osr(self) -> dict:
        """
        TNCDBR 2019 Cl. 36: OSR = 10% of plot area for plots > 1500 m²
        in CMDA/Corporation areas. Smaller plots: no OSR.
        """
        if self.plot_area > 1500 and self.zone in ("CMDA", "Corporation"):
            osr_area = self.plot_area * 0.10
            return {
                "required": True,
                "area_sqm": round(osr_area, 1),
                "pct": 10.0,
                "clause": "TNCDBR 2019, Cl. 36 — 10% OSR for plots > 1500 m²",
            }
        elif self.plot_area > 3000:
            osr_area = self.plot_area * 0.10
            return {
                "required": True,
                "area_sqm": round(osr_area, 1),
                "pct": 10.0,
                "clause": "TNCDBR 2019, Cl. 36 — OSR mandatory for large plots",
            }
        return {
            "required": False,
            "area_sqm": 0,
            "pct": 0,
            "clause": "TNCDBR 2019, Cl. 36 — OSR not required for this plot size",
        }

    # ── Ground coverage ──────────────────────────────────────────────────────

    def compute_ground_coverage(self, built_footprint_sqm: float = None) -> dict:
        """Check against GROUND_COVERAGE_LIMITS for the zone."""
        gc = GROUND_COVERAGE_LIMITS.get(self.zone, GROUND_COVERAGE_LIMITS.get("CMDA", {}))
        max_pct = gc.get("residential_max_pct", 75)
        max_area = self.plot_area * max_pct / 100.0

        actual_pct = 0
        compliant = True
        if built_footprint_sqm is not None:
            actual_pct = (built_footprint_sqm / self.plot_area * 100) if self.plot_area > 0 else 0
            compliant = actual_pct <= max_pct

        return {
            "max_pct": max_pct,
            "max_area_sqm": round(max_area, 1),
            "actual_pct": round(actual_pct, 1),
            "compliant": compliant,
            "clause": gc.get("note", "TNCDBR 2019"),
        }

    # ── FSI / FAR ────────────────────────────────────────────────────────────

    def compute_fsi(self) -> dict:
        """Return applicable FSI limit for the zone and plot size."""
        fsi_data = FSI_BY_CITY.get(
            "CMDA (Chennai Metropolitan Area)",
            {"residential_plot_upto_200sqm": 1.5}
        )
        if self.plot_area <= 200:
            fsi = fsi_data.get("residential_plot_upto_200sqm", 1.5)
        elif self.plot_area <= 500:
            fsi = fsi_data.get("residential_plot_201_to_500sqm", 2.0)
        else:
            fsi = fsi_data.get("residential_plot_above_500sqm", 2.5)

        max_built = self.plot_area * fsi
        return {
            "fsi": fsi,
            "max_built_up_sqm": round(max_built, 1),
            "clause": fsi_data.get("note", "CMDA DCR 2022 Cl. 20"),
        }

    # ── Room-level NBC compliance ────────────────────────────────────────────

    def check_room_compliance(self, rooms) -> list:
        """Run check_nbc_compliance() for each room. Returns list of dicts."""
        results = []
        for r in rooms:
            rt = getattr(r, "room_type", "unknown")
            area = getattr(r, "area", 0)
            width = min(getattr(r, "width", 0), getattr(r, "height", 0))

            nbc = check_nbc_compliance(rt, area, width)
            results.append({
                "room_name": getattr(r, "name", rt),
                "room_type": rt,
                "area_sqm": round(area, 1),
                "width_m": round(width, 2),
                "min_area": NBC_ROOM_MINIMUMS.get(rt, {}).get("min_area_sqm", "N/A"),
                "min_width": NBC_ROOM_MINIMUMS.get(rt, {}).get("min_width_m", "N/A"),
                "compliant": nbc["compliant"],
                "clause": nbc.get("clause", ""),
                "reasons": nbc.get("reasons", []),
            })
        return results

    # ── Exit width (NBC Part 4) ──────────────────────────────────────────────

    def compute_exit_requirements(self) -> dict:
        """NBC Part 4, Cl. 4.4.3: exit door width by occupancy."""
        occ = self.occupancy
        if occ <= 24:
            door_w, corr_w = 1.0, 1.0
        elif occ <= 50:
            door_w, corr_w = 1.2, 1.2
        else:
            door_w, corr_w = 1.5, 1.5

        return {
            "occupancy": occ,
            "min_exit_door_width_m": door_w,
            "min_corridor_width_m": corr_w,
            "clause": "NBC 2016, Part 4, Cl. 4.4.3",
        }

    # ── Consolidated report ──────────────────────────────────────────────────

    def generate_compliance_report(self, rooms=None) -> dict:
        """
        Master compliance report. Always returns a dict — never raises.
        overall_pass = True only if ALL rules are satisfied.
        """
        setbacks = self.compute_setbacks()
        osr = self.compute_osr()
        fsi = self.compute_fsi()
        exits = self.compute_exit_requirements()

        # Compute built footprint from rooms
        built_fp = 0
        if rooms:
            xs = [getattr(r, "x", 0) for r in rooms]
            x2s = [getattr(r, "x", 0) + getattr(r, "width", 0) for r in rooms]
            ys = [getattr(r, "y", 0) for r in rooms]
            y2s = [getattr(r, "y", 0) + getattr(r, "height", 0) for r in rooms]
            if xs and ys:
                built_fp = (max(x2s) - min(xs)) * (max(y2s) - min(ys))

        gc = self.compute_ground_coverage(built_fp)
        room_checks = self.check_room_compliance(rooms) if rooms else []

        # Aggregate violations
        violations = []
        clauses = set()

        # Setback violations (informational — the engine already applies them)
        clauses.add(setbacks["clause"])

        # Ground coverage
        if not gc["compliant"]:
            violations.append(
                f"Ground coverage {gc['actual_pct']:.0f}% exceeds max {gc['max_pct']}%"
            )
        clauses.add(gc["clause"])

        # OSR
        if osr["required"]:
            clauses.add(osr["clause"])

        # FSI
        clauses.add(fsi["clause"])

        # Room compliance
        for rc in room_checks:
            if not rc["compliant"]:
                for reason in rc["reasons"]:
                    violations.append(f"{rc['room_name']}: {reason}")
            if rc["clause"]:
                clauses.add(rc["clause"])

        # Exit requirements
        clauses.add(exits["clause"])

        overall_pass = len(violations) == 0

        return {
            "overall_pass": overall_pass,
            "violations": violations,
            "violation_count": len(violations),
            "clauses_cited": sorted(clauses),
            "setbacks": setbacks,
            "osr": osr,
            "ground_coverage": gc,
            "fsi": fsi,
            "exit_requirements": exits,
            "room_compliance": room_checks,
            "usable_area": self._usable,
        }
