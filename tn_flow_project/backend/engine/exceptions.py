"""
TN-Flow Engine — Custom Exception Hierarchy
============================================
Defines structured, context-carrying exceptions for every failure mode
the engine can produce. Callers (FastAPI routes, CLI tools, tests) catch
specific subclasses to return well-formed error responses.

Hierarchy:

  TNFlowBaseError                       (root — never catch this in production)
  ├── TNCDBRValidationError              (plot/building-rule violations)
  │   ├── RoadWidthInsufficientError     (no rule exists for road+floor combo)
  │   ├── PlotTooSmallError              (plot dimensions below rule minimums)
  │   ├── FloorLevelNotPermittedError    (G+1/G+2 on a road too narrow)
  │   ├── SetbackExceedsPlotError        (setbacks leave zero build area)
  │   └── InsufficientBuildEnvelopeError (envelope exists but unusably small)
  └── VastuRoutingError                  (Vastu room-placement failures)
      ├── UnresolvableRoomPlacementError (mandatory room has no valid zone)
      └── VastuZoneUnavailableError      (specific zone has insufficient area)
"""


# ── Root ──────────────────────────────────────────────────────────────────────

class TNFlowBaseError(Exception):
    """
    Root exception for all TN-Flow engine errors.

    All subclasses accept a human-readable `message` as the first positional
    argument, plus arbitrary **context keyword arguments that are stored on
    the exception and included in its string representation.

    Usage::

        raise PlotTooSmallError(
            "Plot area 25m² is below the 27m² minimum.",
            plot_area=25.0,
            required_area=27.0,
            authority="DTCP",
        )

        # Caller can inspect structured data:
        except PlotTooSmallError as exc:
            print(exc.context["plot_area"])   # 25.0
    """

    def __init__(self, message: str, **context):
        super().__init__(message)
        self.message = message
        # Arbitrary key-value pairs for structured logging / API error bodies
        self.context: dict = context

    def __str__(self) -> str:
        if not self.context:
            return self.message
        ctx = ", ".join(f"{k}={v!r}" for k, v in self.context.items())
        return f"{self.message}  [context: {ctx}]"

    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dict (for FastAPI error responses)."""
        return {
            "error_type": type(self).__name__,
            "message":    self.message,
            "context":    {k: str(v) for k, v in self.context.items()},
        }


# ── TNCDBR Validation Errors ──────────────────────────────────────────────────

class TNCDBRValidationError(TNFlowBaseError):
    """
    Raised when a user's input configuration violates TNCDBR 2019 regulations
    or NBC 2016 minimum dimensional standards.

    The Validation Gate (constraint.py) raises subclasses of this error before
    any polygon geometry is calculated, preventing wasted computation.

    Typical HTTP mapping: 422 Unprocessable Entity.
    """


class RoadWidthInsufficientError(TNCDBRValidationError):
    """
    Raised when no PlotEligibilityRules row exists for the combination of
    (authority, floor_level, road_width).

    This means the requested floor level is simply not permitted on a road of
    the given width, per TNCDBR 2019 §9.

    Expected context keys:
      - authority    : 'CMDA' or 'DTCP'
      - floor_level  : 'Ground', 'G+1', or 'G+2'
      - road_width_m : the actual road width supplied by the user (float)

    Example:
        "G+1 construction is not permitted on a 4.5m road (DTCP).
         Minimum road width for G+1 is 6.0m (TNCDBR 2019 §9(1))."
    """


class PlotTooSmallError(TNCDBRValidationError):
    """
    Raised when the plot's area, frontage width, or run depth falls below the
    minimum values stipulated in the matched PlotEligibilityRules row.

    Expected context keys:
      - dimension    : 'area', 'frontage_width', or 'run_depth'
      - actual_value : float (the user's dimension)
      - minimum      : float (the rule minimum)
      - rule_ref     : str  (e.g., 'TNCDBR 2019 §6(2)')

    Example:
        "Plot frontage 5.0m is below the 6.0m minimum required for G+1
         construction on a 6m road (CMDA). [TNCDBR 2019 §6(2)]"
    """


class FloorLevelNotPermittedError(TNCDBRValidationError):
    """
    Raised when the requested floor level is explicitly not allowed for the
    plot configuration (a more specific subclass of RoadWidthInsufficientError
    used when the floor level is known to be the root cause).

    Expected context keys:
      - floor_level        : 'G+1' or 'G+2'
      - min_road_required  : float (e.g., 6.0 for G+1, 9.0 for G+2)
      - actual_road_width  : float

    Example:
        "G+2 is not permitted — minimum road width is 9.0m but the plot
         abuts a 6.0m road. (TNCDBR 2019 §9(2))"
    """


class SetbackExceedsPlotError(TNCDBRValidationError):
    """
    Raised when the setbacks mandated by the matched rule eliminate ALL usable
    build area, resulting in a zero-area or negative-dimension envelope.

    This typically indicates an unusually narrow plot where even the minimum
    side setbacks consume the entire width.

    Expected context keys:
      - envelope_width_m : float (computed envelope X-span, may be ≤ 0)
      - envelope_depth_m : float (computed envelope Y-span, may be ≤ 0)
      - setback_front_m  : float
      - setback_rear_m   : float
      - setback_side_m   : float

    Example:
        "After applying 1.0m side setbacks, a 2.0m-wide plot has 0.0m usable
         width. Minimum usable width after setbacks is 1.5m."
    """


class InsufficientBuildEnvelopeError(TNCDBRValidationError):
    """
    Raised when the build envelope exists (positive dimensions) but is too
    small to accommodate even the smallest meaningful floor plan per NBC 2016.

    Expected context keys:
      - envelope_area_sqm : float
      - minimum_sqm       : float (the threshold below which we reject)

    Example:
        "Build envelope area 8.2m² is below the minimum viable floor plan
         threshold of 10.0m²."
    """


# ── Vastu Routing Errors ──────────────────────────────────────────────────────

class VastuRoutingError(TNFlowBaseError):
    """
    Raised when the Vastu Router cannot resolve the compass-zone assignment
    for one or more rooms.

    Typical HTTP mapping: 409 Conflict (the layout is geometrically possible
    but Vastu constraints cannot all be satisfied simultaneously).
    """


class UnresolvableRoomPlacementError(VastuRoutingError):
    """
    Raised when a mandatory room (is_mandatory=True, priority=1) has no valid
    Vastu zone available across all three priority levels.

    This indicates a degenerate layout: the build envelope is so small that
    even the fallback zone for a critical room has insufficient area.

    Expected context keys:
      - room_type    : str  (e.g., 'Kitchen', 'Pooja')
      - plot_facing  : str
      - tried_zones  : list[str] (all zones tried, P1→P2→P3)

    Example:
        "Cannot place Pooja room — NorthEast and East zones have area 0.0m²
         on this 3×9m plot. Minimum required is 2.0m²."
    """


class VastuZoneUnavailableError(VastuRoutingError):
    """
    Raised when a specific Vastu zone is required but the corresponding grid
    cell has insufficient usable area (below NBC 2016 minimum for the room).

    Unlike UnresolvableRoomPlacementError (which indicates ALL zones failed),
    this error is used when only a specific zone is needed (e.g., during
    conflict resolution in the allocator).

    Expected context keys:
      - room_type    : str
      - zone         : str  (e.g., 'SouthEast')
      - cell_area    : float (actual available area in the zone)
      - required_min : float (NBC minimum for the room type)
    """
