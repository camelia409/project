"""
TN-Flow Geometry Engine — geometry.py
======================================
Applies physical wall mass to the abstract base polygons produced by the
Spatial Allocator (allocator.py), converting them into legally compliant
room polygons with true clear carpet areas.

Wall-Centric Model
──────────────────
Every room polygon output by the allocator is a BASE polygon — it represents
the gross extents of the room including the surrounding wall thickness.
This module subtracts wall mass from all four sides of each base polygon to
produce a CLEAR polygon whose area is the legally measurable carpet area
(RERA definition: distance between inner faces of walls).

Two wall categories (TNCDBR 2019 / NBC 2016):

  External wall (230mm / 0.230m):
    Applied to any room face that lies on the boundary of the build envelope.
    These walls face the setback zone (open air or road) and carry external
    loads.  Per NBC 2016 Cl. 4.1.1, load-bearing external brick walls must
    be ≥ 230mm.

  Internal / Party wall (115mm / 0.115m total, 57.5mm per face):
    Applied to any room face that is SHARED with an adjacent room or corridor.
    The full 115mm partition wall is split evenly: each room's base polygon
    is inset by 57.5mm on its internal face.  This ensures that when two
    adjacent clear polygons are constructed, there is exactly 115mm of wall
    mass between their inner faces.

Edge Classification algorithm:
  For a rectangular room base polygon with bounds (min_x, min_y, max_x, max_y):
    if abs(face_coordinate − envelope_boundary) < TOLERANCE:
        → EXTERNAL face → inset by EXT_WALL_T (0.230m)
    else:
        → INTERNAL face → inset by INT_WALL_HALF (0.0575m)

  The tolerance is set at 1e-4 m (0.1mm) to absorb floating-point drift
  accumulated during the Shapely subdivision operations in allocator.py.

Shapely operations used:
  box(x1, y1, x2, y2)  — construct axis-aligned rectangle from two corners
  polygon.bounds        — extract (min_x, min_y, max_x, max_y) for rectangles
  polygon.intersection(other) — future-proofing for non-rectangular rooms
  polygon.area          — compute carpet area of the clear polygon

Primary public API:
  apply_wall_thickness(allocated_rooms, build_envelope)
                        → FloorPlanMap

  FloorPlanMap = {
      room_name: {
          "clear_polygon":   Polygon,       # Shapely polygon of carpeted area
          "carpet_area_sqm": float,         # area of clear_polygon (m²)
          "dimensions":      (float, float) # (clear_width_m, clear_depth_m)
      }
  }

NBC 2016 Clear Carpet Area Minimums enforced:
  Kitchen:       5.0 m²  (problem brief requirement)
  MasterBedroom: 9.5 m²  (NBC 2016 Cl.4.2.1)
  Bedroom2/3:    7.5 m²  (NBC 2016 Cl.4.2.1)
  Hall:          9.5 m²  (NBC 2016 Cl.4.2.2)
  Dining:        6.0 m²  (NBC 2016 Cl.4.2.3)
  Toilet:        1.5 m²  (NBC 2016 Cl.4.2.6, practical minimum)
  Pooja:         2.0 m²  (no NBC clause; practical minimum)
  Staircase:     4.5 m²  (practical dog-leg stair minimum)
  StoreRoom:     1.5 m²  (utility minimum)
  Entrance:      1.0 m²  (foyer minimum)
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from shapely.geometry import box, Polygon

from backend.engine.exceptions import SpaceDeficitError


# ── Wall Thickness Constants ──────────────────────────────────────────────────

EXT_WALL_T: float = 0.230
"""
External wall thickness: 230mm.

Composed of:
  115mm  burnt clay brick / fly-ash brick
 +  12mm  cement-sand plaster (external face)
 +  12mm  cement-sand plaster (internal face)
 +  10mm  construction tolerance
 ≈ 149mm (structural) → rounded to 230mm for a standard brick module
   (actual: one full brick + double plaster is 230mm per IS 2212).

Applied to every room face that abuts the build envelope boundary
(i.e., faces the setback zone).
"""

INT_WALL_T: float = 0.115
"""
Internal / party wall thickness: 115mm (half-brick partition).

Composed of:
   90mm  half-brick laid on flat (half-brick = 90mm per IS 1905)
 + 12mm  plaster both faces
 = 114mm → rounded to 115mm.

Each room contributes 57.5mm (half of 115mm) of inset on its
shared face.  When two adjacent rooms are placed side-by-side,
there is exactly 115mm of wall mass between their clear areas.
"""

INT_WALL_HALF: float = INT_WALL_T / 2
"""57.5mm — inset applied PER FACE on internal/shared edges."""

EDGE_TOLERANCE: float = 1e-4
"""
0.1mm floating-point tolerance for edge-on-boundary detection.

Shapely subdivision operations in allocator.py accumulate tiny floating-point
errors (~1e-15 m level).  A 0.1mm tolerance comfortably absorbs these while
being five orders of magnitude below the smallest dimension change that matters
in architectural drawings (1mm = 0.001m).
"""


# ── NBC 2016 Clear Carpet Area Minimums ───────────────────────────────────────
#
# These are MINIMUM CLEAR CARPET AREAS (post-wall-deduction) per room.
# If a room's clear_polygon.area < NBC_CARPET_MINIMUMS[room_type], the engine
# raises SpaceDeficitError, indicating the plot is too small for the BHK type.
#
# References:
#   NBC 2016 Cl.4.2.1 — habitable rooms: 9.5m² (master), 7.5m² (secondary)
#   NBC 2016 Cl.4.2.2 — living / lounge: 9.5m²
#   NBC 2016 Cl.4.2.3 — dining space: 6.0m²
#   NBC 2016 Cl.4.2.4 — kitchen: 5.0m² (as per problem brief; NBC gives 4.5m²)
#   NBC 2016 Cl.4.2.6 — bathroom / toilet: 1.2m² (1.5m² practical)
#   No NBC clause for Pooja, StoreRoom, Entrance — practical minimums used.
#
NBC_CARPET_MINIMUMS: dict[str, float] = {
    "MasterBedroom": 9.5,
    "Bedroom2":      7.5,
    "Bedroom3":      7.5,
    "Kitchen":       5.0,
    "Hall":          9.5,
    "Toilet":        1.5,
    "Pooja":         2.0,
    "Dining":        6.0,
    "Staircase":     4.5,
    "StoreRoom":     1.5,
    "Entrance":      1.0,
}

# Fallback for room types not listed above.
_DEFAULT_NBC_MIN: float = 1.5

# Type aliases
AllocatedRoomMap = Dict[str, Polygon]
FloorPlanMap = Dict[str, Dict]


# ── Private Helpers ───────────────────────────────────────────────────────────

def _classify_wall_thicknesses(
    base_poly:      Polygon,
    build_envelope: Polygon,
) -> Tuple[float, float, float, float]:
    """
    Determine the wall inset thickness for each of the four sides of a
    rectangular room base polygon.

    Edge Classification Logic:
    ──────────────────────────
    For each face of ``base_poly``, compare the face's coordinate to the
    corresponding face of ``build_envelope``:

        Left face   (x = min_x):  external if min_x ≈ env.min_x
        Right face  (x = max_x):  external if max_x ≈ env.max_x
        Bottom face (y = min_y):  external if min_y ≈ env.min_y
        Top face    (y = max_y):  external if max_y ≈ env.max_y

    "≈" means within EDGE_TOLERANCE (0.1mm) to absorb float arithmetic drift.

    External faces receive EXT_WALL_T (0.230m).
    Internal faces receive INT_WALL_HALF (0.0575m).

    Visual model for a North-facing SW cell (MasterBedroom at bottom-left):

        Envelope boundary (SW corner)
          │
          ├──[EXT 230mm]──┬──[INT 57.5mm]──
          │               │
          │  Master       │  [next room
          │  Bedroom      │   to the East]
          │  clear area   │
          │               │
          ├──[EXT 230mm]──┴──[INT 57.5mm]──
          │
          Envelope boundary (South face)

    Args:
        base_poly:      Rectangular base polygon from allocator.py.
        build_envelope: Build envelope polygon from constraint.py.

    Returns:
        (left_t, right_t, bottom_t, top_t) — inset distances in metres.
    """
    r_minx, r_miny, r_maxx, r_maxy = base_poly.bounds
    e_minx, e_miny, e_maxx, e_maxy = build_envelope.bounds

    def _t(face_coord: float, env_coord: float) -> float:
        """Return external thickness if face is on the envelope boundary."""
        return EXT_WALL_T if abs(face_coord - env_coord) < EDGE_TOLERANCE else INT_WALL_HALF

    left_t   = _t(r_minx, e_minx)
    right_t  = _t(r_maxx, e_maxx)
    bottom_t = _t(r_miny, e_miny)
    top_t    = _t(r_maxy, e_maxy)

    return left_t, right_t, bottom_t, top_t


def _inset_rectangle(
    room_name:      str,
    base_poly:      Polygon,
    build_envelope: Polygon,
) -> Polygon:
    """
    Apply per-edge wall insets to a rectangular base polygon.

    Mathematical derivation:
    ─────────────────────────
    Given base polygon bounds (r_minx, r_miny, r_maxx, r_maxy) and
    per-edge thicknesses (left_t, right_t, bottom_t, top_t):

        clear_minx = r_minx + left_t
        clear_miny = r_miny + bottom_t
        clear_maxx = r_maxx − right_t
        clear_maxy = r_maxy − top_t

        clear_polygon = box(clear_minx, clear_miny, clear_maxx, clear_maxy)

    Shapely operation chain:
        1. base_poly.bounds       → extracts corner coordinates
        2. _classify_wall_thicknesses() → determines each edge's inset
        3. box(c_minx, c_miny, c_maxx, c_maxy) → constructs clear polygon
        4. polygon.intersection(build_envelope) → clips to legal boundary
           (no-op for rectangles fully inside the envelope; safety guard)

    Alternative approach for non-rectangular rooms (future-proofing):
        For irregular polygons, Shapely's negative buffer approximates
        a uniform inset:
            approx_clear = base_poly.buffer(-EXT_WALL_T, join_style=2)
        However, this applies the SAME thickness to ALL edges, ignoring
        the external vs internal distinction.  The per-edge arithmetic
        above is more accurate for rectangular plans.

    Args:
        room_name:      Used in SpaceDeficitError messages only.
        base_poly:      Rectangular base polygon.
        build_envelope: Build envelope — used for edge classification only.

    Returns:
        Shapely Polygon of the clear carpeted area.

    Raises:
        SpaceDeficitError: If the insets leave zero or negative clear area
                           (room base polygon too small for its wall thicknesses).
    """
    left_t, right_t, bottom_t, top_t = _classify_wall_thicknesses(
        base_poly, build_envelope
    )

    r_minx, r_miny, r_maxx, r_maxy = base_poly.bounds

    clear_minx = r_minx + left_t
    clear_miny = r_miny + bottom_t
    clear_maxx = r_maxx - right_t
    clear_maxy = r_maxy - top_t

    # ── Degenerate-geometry guard ─────────────────────────────────────────
    clear_w = clear_maxx - clear_minx
    clear_d = clear_maxy - clear_miny

    if clear_w <= 0 or clear_d <= 0:
        base_w = r_maxx - r_minx
        base_d = r_maxy - r_miny
        raise SpaceDeficitError(
            f"'{room_name}' base polygon ({base_w:.3f}m × {base_d:.3f}m = "
            f"{base_poly.area:.3f}m²) leaves zero or negative clear area after "
            f"wall deduction (L={left_t:.4f}m, R={right_t:.4f}m, "
            f"B={bottom_t:.4f}m, T={top_t:.4f}m).  "
            f"The allocated base polygon is physically too narrow for its walls.",
            room_type=room_name,
            base_area_sqm=round(base_poly.area, 4),
            carpet_area_sqm=0.0,
            nbc_minimum_sqm=NBC_CARPET_MINIMUMS.get(room_name, _DEFAULT_NBC_MIN),
            wall_overhead_sqm=round(base_poly.area, 4),
            base_dims=f"{base_w:.3f}x{base_d:.3f}m",
            clear_dims=f"{clear_w:.3f}x{clear_d:.3f}m",
        )

    # ── Construct and clip clear polygon ─────────────────────────────────
    clear_polygon = box(clear_minx, clear_miny, clear_maxx, clear_maxy)

    # Safety clip: ensure the clear polygon stays within the build envelope
    # (should be a no-op for valid inputs, but protects against float drift)
    clear_polygon = clear_polygon.intersection(build_envelope)

    return clear_polygon


# ── Public API ────────────────────────────────────────────────────────────────

def apply_wall_thickness(
    allocated_rooms: AllocatedRoomMap,
    build_envelope:  Polygon,
) -> FloorPlanMap:
    """
    Geometry Engine — apply wall thicknesses to produce the final floor plan.

    Converts each base polygon from the allocator into a clear carpeted area
    by subtracting wall mass from the appropriate edges.

    Pipeline:
    ─────────
    For each (room_name, base_polygon) in allocated_rooms:

      1. Classify edges:
         _classify_wall_thicknesses() compares each face of base_polygon
         against the build_envelope boundary.
             face on boundary → EXT_WALL_T (0.230m)
             face interior    → INT_WALL_HALF (0.0575m)

      2. Inset rectangle:
         _inset_rectangle() computes:
             clear_minx = base_minx + left_t
             clear_miny = base_miny + bottom_t
             clear_maxx = base_maxx − right_t
             clear_maxy = base_maxy − top_t
         then constructs clear_polygon = box(clear_minx, ..., clear_maxy).

      3. Area calculation:
             carpet_area_sqm = clear_polygon.area

      4. NBC validation:
         If carpet_area_sqm < NBC_CARPET_MINIMUMS[room_name]:
             → raise SpaceDeficitError

      5. Dimensions:
             (clear_width_m, clear_depth_m) = (clear_maxx - clear_minx,
                                               clear_maxy - clear_miny)

    Wall overhead accounting:
    ─────────────────────────
    For a room with one external and three internal walls (e.g., a bedroom
    sharing three walls with neighbours and one external south wall):

        base_area   = base_w × base_d
        clear_area  = (base_w − EXT_WALL_T − INT_WALL_HALF) ×
                      (base_d − EXT_WALL_T − INT_WALL_HALF)
                    = (base_w − 0.230 − 0.0575) ×
                      (base_d − 0.230 − 0.0575)
                    = (base_w − 0.2875) × (base_d − 0.2875)

    For a corner room (two external walls, two internal):
        clear_area  = (base_w − 0.230 − 0.0575) ×
                      (base_d − 0.230 − 0.0575)
        (same formula — corner rooms lose the same deduction because
        the TOTAL horizontal/vertical inset is always 1 ext + 1 int per axis)

    Wall overhead = base_area − clear_area.

    Worked example — MasterBedroom in SW cell of a 12×22m CMDA G+1 plot:
    ──────────────────────────────────────────────────────────────────────
      Build envelope:  box(1.5, 1.5, 10.5, 20.5)   [9.0m × 19.0m]
      SW cell:         box(1.5, 1.5, 4.5, 7.83)    [3.0m × 6.33m]
      MasterBedroom base (67.86% of SW cell height):
                       box(1.5, 1.5, 4.5, 5.80)    [3.0m × 4.30m = 12.9m²]

      Edge classification:
        Left  (x=1.5  ≈ env.minx=1.5) → EXTERNAL → 0.230m
        Right (x=4.5  ≠ env.maxx=10.5)→ INTERNAL → 0.0575m
        Bottom(y=1.5  ≈ env.miny=1.5) → EXTERNAL → 0.230m
        Top   (y=5.80 ≠ env.maxy=20.5)→ INTERNAL → 0.0575m

      Clear area:
        clear_minx = 1.5  + 0.230  = 1.730m
        clear_miny = 1.5  + 0.230  = 1.730m
        clear_maxx = 4.5  − 0.0575 = 4.443m
        clear_maxy = 5.80 − 0.0575 = 5.742m

        clear_w = 4.443 − 1.730 = 2.712m
        clear_d = 5.742 − 1.730 = 4.012m
        carpet_area = 2.712 × 4.012 = 10.88m²  ✓ ≥ 9.5m² NBC

    Args:
        allocated_rooms: AllocatedRoomMap from allocator.resolve_spatial_conflicts().
                         { room_name: base_Polygon }
        build_envelope:  Build envelope Shapely Polygon from constraint.py.
                         Must be the SAME polygon used to generate room_anchors
                         and allocated_rooms.

    Returns:
        FloorPlanMap:
        {
            room_name: {
                "clear_polygon":   Polygon,   # Shapely polygon of carpet area
                "carpet_area_sqm": float,     # area of clear_polygon in m²
                "dimensions":      (float, float) # (width_m, depth_m) of clear area
            }
        }

    Raises:
        ValueError:       allocated_rooms or build_envelope is empty/invalid.
        SpaceDeficitError: A room's clear area falls below its NBC 2016 minimum.
                           Context keys: room_type, base_area_sqm, carpet_area_sqm,
                           nbc_minimum_sqm, wall_overhead_sqm, base_dims, clear_dims.
    """
    if not allocated_rooms:
        raise ValueError("allocated_rooms is empty — run allocator.resolve_spatial_conflicts() first.")

    if build_envelope is None or build_envelope.is_empty or build_envelope.area <= 0:
        raise ValueError("build_envelope must be a valid, non-empty Shapely Polygon.")

    floor_plan: FloorPlanMap = {}

    for room_name, base_poly in allocated_rooms.items():

        # ── Step 1 & 2: classify edges and inset ─────────────────────────
        clear_polygon = _inset_rectangle(room_name, base_poly, build_envelope)

        # ── Step 3: carpet area ───────────────────────────────────────────
        carpet_area = clear_polygon.area

        # ── Step 4: NBC minimum validation ───────────────────────────────
        nbc_min = NBC_CARPET_MINIMUMS.get(room_name, _DEFAULT_NBC_MIN)

        if carpet_area < nbc_min:
            base_w = base_poly.bounds[2] - base_poly.bounds[0]
            base_d = base_poly.bounds[3] - base_poly.bounds[1]
            c_minx, c_miny, c_maxx, c_maxy = clear_polygon.bounds
            clear_w = c_maxx - c_minx
            clear_d = c_maxy - c_miny
            wall_overhead = base_poly.area - carpet_area

            raise SpaceDeficitError(
                f"'{room_name}' clear carpet area {carpet_area:.2f}m² is below "
                f"the NBC 2016 minimum of {nbc_min:.1f}m².  "
                f"Base polygon {base_w:.2f}m × {base_d:.2f}m leaves only "
                f"{clear_w:.3f}m × {clear_d:.3f}m after wall deduction.  "
                f"Wall overhead = {wall_overhead:.2f}m².  "
                f"To satisfy this constraint, increase the plot dimensions or "
                f"reduce the BHK type.",
                room_type=room_name,
                base_area_sqm=round(base_poly.area, 4),
                carpet_area_sqm=round(carpet_area, 4),
                nbc_minimum_sqm=nbc_min,
                wall_overhead_sqm=round(wall_overhead, 4),
                base_dims=f"{base_w:.3f}x{base_d:.3f}m",
                clear_dims=f"{clear_w:.3f}x{clear_d:.3f}m",
            )

        # ── Step 5: dimensions ────────────────────────────────────────────
        c_minx, c_miny, c_maxx, c_maxy = clear_polygon.bounds
        clear_w = round(c_maxx - c_minx, 4)
        clear_d = round(c_maxy - c_miny, 4)

        floor_plan[room_name] = {
            "clear_polygon":   clear_polygon,
            "carpet_area_sqm": round(carpet_area, 4),
            "dimensions":      (clear_w, clear_d),
        }

    return floor_plan


def describe_floor_plan(floor_plan: FloorPlanMap, indent: int = 2) -> str:
    """
    Return a human-readable text report of a FloorPlanMap.

    Example output::

        Floor Plan (9 rooms, carpet total = 108.32 m²)
          MasterBedroom  2.712m × 4.012m = 10.88m²  (NBC min 9.5m²) ✓
          Kitchen        2.712m × 2.085m =  5.66m²  (NBC min 5.0m²) ✓
          ...

    Args:
        floor_plan: FloorPlanMap from apply_wall_thickness().
        indent:     Left-padding spaces for each room line.
    """
    pad   = " " * indent
    total = sum(v["carpet_area_sqm"] for v in floor_plan.values())
    lines = [f"Floor Plan ({len(floor_plan)} rooms, carpet total = {total:.2f} m²)"]

    for room, data in sorted(floor_plan.items(), key=lambda x: -x[1]["carpet_area_sqm"]):
        w, d   = data["dimensions"]
        area   = data["carpet_area_sqm"]
        nbc    = NBC_CARPET_MINIMUMS.get(room, _DEFAULT_NBC_MIN)
        status = "✓" if area >= nbc else "✗"
        lines.append(
            f"{pad}{room:<16} {w:.3f}m × {d:.3f}m = {area:>6.2f}m²"
            f"  (NBC min {nbc:.1f}m²) {status}"
        )

    return "\n".join(lines)


def get_wall_schedule(
    allocated_rooms: AllocatedRoomMap,
    build_envelope:  Polygon,
) -> list[dict]:
    """
    Generate a wall schedule listing every edge of every room with its
    wall type, thickness, and dimensional properties.

    Returns:
        List of dicts:
        [
          {
            "room":        str,   (room name)
            "face":        str,   ("Left", "Right", "Bottom", "Top")
            "wall_type":   str,   ("External" or "Internal")
            "thickness_m": float, (0.230 or 0.0575)
            "length_m":    float, (length of this wall segment in metres)
          },
          ...
        ]

    Useful for:
      - SVG rendering (different stroke widths for external vs internal walls)
      - Bill-of-quantities calculations
      - Structural engineer wall-load summaries
    """
    schedule: list[dict] = []

    for room_name, base_poly in allocated_rooms.items():
        left_t, right_t, bottom_t, top_t = _classify_wall_thicknesses(
            base_poly, build_envelope
        )
        minx, miny, maxx, maxy = base_poly.bounds
        width  = maxx - minx
        height = maxy - miny

        face_data = [
            ("Left",   left_t,   height),
            ("Right",  right_t,  height),
            ("Bottom", bottom_t, width),
            ("Top",    top_t,    width),
        ]
        for face, thick, length in face_data:
            schedule.append({
                "room":        room_name,
                "face":        face,
                "wall_type":   "External" if abs(thick - EXT_WALL_T) < 1e-6 else "Internal",
                "thickness_m": round(thick, 4),
                "length_m":    round(length, 4),
            })

    return schedule
