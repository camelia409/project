# FINAL v7 – 1.2 m clearance + simplified furniture + clean 12x15 layout (matches original blueprint)
"""
Professional Architectural Floor Plan Renderer v7 -- Blueprint Style (FINAL)
- Pure white background, black walls with ext 0.8pt / int 0.4pt edges
- Wall-centric drawing with clean T-junction handling
- CAD door symbols: leaf + 0.3pt dashed arc + filled triangle arrowhead
- IS 962 3-line window symbols with exterior sill notch
- Furniture: 0.35pt black outlines, 5% opacity grey fill (cleaner professional look)
- Strict 1.2m clearance — furniture NEVER blocks doors or archways
- Tight-room simplification: if dim < 3.2m or area < 10m² → minimal furniture only
- Room labels with m² area, dimension strings, compass, scale bar, legend
- Bedroom auto-numbering (BEDROOM 1/2/3), label centroid in open floor area
"""

import math
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Rectangle, Arc, FancyBboxPatch, PathPatch, Polygon, Circle, Ellipse
from matplotlib.lines import Line2D
from matplotlib.path import Path
import matplotlib.patheffects as pe
import matplotlib.ticker as ticker
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from shapely.geometry import box as sh_box

from engine import FloorPlan, Room

try:
    from algorithms.door_validator import (
        choose_door_placement as _dv_choose,
        door_side_candidates  as _dv_side_cands,
        DoorPlacement,
    )
    _DOOR_VALIDATOR = True
except ImportError:
    _DOOR_VALIDATOR = False

# Drawing constants (all in metres = drawing units)
EXT_WALL    = 0.23
INT_WALL    = 0.12
WALL_COLOR      = "#000000"       # exterior walls — pure black (blueprint standard)
INT_WALL_COLOR  = "#333333"       # interior walls — dark grey (CAD standard)
FLOOR_COLOR = "#FFFFFF"           # white background (professional blueprint)

WIN_RATIO    = 0.60
WIN_MIN      = 0.70
WIN_MAX      = 1.80
WIN_LINE_COL = "#333333"

DOOR_ARC_STYLE = "--"             # dashed arc (CAD architectural convention)
DOOR_ARC_LW    = 1.2
DOOR_LEAF_LW   = 2.5
DOOR_COLOR     = "#1A1A1A"

# NBC 2016 Part 3 / IS 4021 minimum clear widths
DOOR_WIDTHS = {
    "living":   1.20,   # main living / entrance — wide for furniture movement
    "kitchen":  1.20,   # kitchen primary door
    "entrance": 1.20,   # explicit entrance room
    "dining":   0.90,
    "bedroom":  0.90,   # standard bedroom (IS 4021)
    "bathroom": 0.75,   # IS 4021 min 750 mm
    "toilet":   0.75,
    "utility":  0.75,
    "corridor": 0.90,
    "pooja":    0.75,
    "study":    0.80,
    "store":    0.75,
}

FONT_TITLE = 9
FONT_ROOM  = 8
FONT_AREA  = 7
FONT_DIM   = 6.5

# v7 FINAL: Fixture outlines — 0.35pt black, 5% grey fill (cleanest professional look)
_FIX_COL  = "#000000"          # black outlines (professional blueprint)
_FIX_LW   = 0.35               # 0.35pt — slightly thinner than v6 for cleaner look
_FIX_FILL = "#E8E8E8"          # very light grey fill
_FIX_ALPHA = 0.05              # 5% opacity — barely-there fill, outline dominant
_FIX_FS   = 5
_FIX_Z    = 4

# v7: tight-room threshold (m) and minimum area (m²) for simplified furniture
_TIGHT_DIM  = 3.2              # any room dimension < 3.2m → simplified furniture
_TIGHT_AREA = 10.0             # any room area < 10m² → simplified furniture
_CLEAR_MIN  = 1.20             # strict 1.2m furniture clearance from door walls


# Wall Segment Data Structures

@dataclass
class WallOpening:
    pos_along: float
    width: float
    opening_type: str
    room: object
    door_hinge: str = "R"

@dataclass
class WallSegment:
    x1: float
    y1: float
    x2: float
    y2: float
    thickness: float
    is_exterior: bool
    is_horizontal: bool
    openings: list = None

    def __post_init__(self):
        if self.openings is None:
            self.openings = []

    @property
    def length(self):
        return abs(self.x2 - self.x1) if self.is_horizontal else abs(self.y2 - self.y1)


# Wall Computation

def _classify_walls(room, all_rooms, eps=0.08):
    """Return {side: 'ext'|'int'} for N/S/E/W walls of *room*.

    A side is 'ext' when no other (non-courtyard) room occupies the thin
    eps-metre strip immediately outside that face of the room.
    """
    rx0, ry0, rx1, ry1 = room.x, room.y, room.x2, room.y2
    other_boxes = [
        sh_box(r.x, r.y, r.x2, r.y2)
        for r in all_rooms
        if id(r) != id(room) and r.room_type != "courtyard"
    ]
    strips = {
        "N": sh_box(rx0,       ry1,       rx1,       ry1 + eps),
        "S": sh_box(rx0,       ry0 - eps, rx1,       ry0),
        "E": sh_box(rx1,       ry0,       rx1 + eps, ry1),
        "W": sh_box(rx0 - eps, ry0,       rx0,       ry1),
    }
    return {
        side: ("int" if any(strip.intersects(ob) for ob in other_boxes) else "ext")
        for side, strip in strips.items()
    }


def _compute_wall_segments(rooms, pw, ph, tol=0.05):
    # pw / ph kept for API compatibility; is_ext now uses Shapely neighbour test
    h_edges = []
    v_edges = []
    for r in rooms:
        if r.room_type in ("courtyard",):
            continue
        h_edges.append((round(r.y2, 3), r.x, r.x2, r, "N"))
        h_edges.append((round(r.y,  3), r.x, r.x2, r, "S"))
        v_edges.append((round(r.x,  3), r.y, r.y2, r, "W"))
        v_edges.append((round(r.x2, 3), r.y, r.y2, r, "E"))

    # Pre-compute per-room, per-side exterior classification using Shapely
    _cls = {
        id(r): _classify_walls(r, rooms)
        for r in rooms
        if r.room_type != "courtyard"
    }

    segments = []

    h_groups = {}
    for y_coord, xs, xe, rm, side in h_edges:
        key = round(y_coord / tol) * tol
        h_groups.setdefault(key, []).append((min(xs, xe), max(xs, xe), rm, side))

    for y_key, edges in h_groups.items():
        merged = _merge_intervals(edges)
        for start, end, meta in merged:
            force_int = any(m[0].room_type in ("corridor", "lightwell") for m in meta)
            is_ext = (not force_int) and any(
                _cls.get(id(m[0]), {}).get(m[1], "int") == "ext" for m in meta
            )
            t = EXT_WALL if is_ext else INT_WALL
            segments.append(WallSegment(x1=start, y1=y_key, x2=end, y2=y_key,
                                        thickness=t, is_exterior=is_ext,
                                        is_horizontal=True))

    v_groups = {}
    for x_coord, ys, ye, rm, side in v_edges:
        key = round(x_coord / tol) * tol
        v_groups.setdefault(key, []).append((min(ys, ye), max(ys, ye), rm, side))

    for x_key, edges in v_groups.items():
        merged = _merge_intervals(edges)
        for start, end, meta in merged:
            force_int = any(m[0].room_type in ("corridor", "lightwell") for m in meta)
            is_ext = (not force_int) and any(
                _cls.get(id(m[0]), {}).get(m[1], "int") == "ext" for m in meta
            )
            t = EXT_WALL if is_ext else INT_WALL
            segments.append(WallSegment(x1=x_key, y1=start, x2=x_key, y2=end,
                                        thickness=t, is_exterior=is_ext,
                                        is_horizontal=False))

    # Post-process: remove micro-fragments then re-join adjacent collinear walls
    segments = _prune_short_segments(segments)
    segments = _merge_collinear_segs(segments)
    # Final pass: collapse near-parallel double-walls into one wall
    segments = _dedupe_parallel_walls(segments)
    return segments


def _merge_intervals(edges):
    if not edges:
        return []
    sorted_e = sorted(edges, key=lambda e: e[0])
    merged = []
    cs, ce = sorted_e[0][0], sorted_e[0][1]
    cm = [(sorted_e[0][2], sorted_e[0][3])]
    for e in sorted_e[1:]:
        # 0.12 m gap tolerance — absorbs wall-thickness micro-gaps and float drift
        if e[0] <= ce + 0.12:
            ce = max(ce, e[1])
            cm.append((e[2], e[3]))
        else:
            merged.append((cs, ce, cm))
            cs, ce = e[0], e[1]
            cm = [(e[2], e[3])]
    merged.append((cs, ce, cm))
    return merged


_SEG_MIN_LEN = 0.30   # drop wall fragments shorter than this


def _prune_short_segments(segments):
    """Remove wall segments shorter than _SEG_MIN_LEN (float artifacts / zero-width gaps)."""
    out = []
    for s in segments:
        if s.is_horizontal:
            if s.x2 - s.x1 >= _SEG_MIN_LEN:
                out.append(s)
        else:
            if s.y2 - s.y1 >= _SEG_MIN_LEN:
                out.append(s)
    return out


def _merge_collinear_segs(segments):
    """
    Second-pass merge: after pruning, re-join any now-adjacent collinear segments
    that share the same wall-line coordinate, direction, and exterior flag.

    A gap ≤ 0.05 m between pruned ends is bridged (e.g., a micro-segment was
    the only thing separating two otherwise continuous walls).
    """
    MERGE_GAP = 0.05

    # Group by (coord_key, is_horizontal, is_exterior, thickness)
    groups: dict = {}
    for s in segments:
        coord = round((s.y1 if s.is_horizontal else s.x1), 4)
        key = (coord, s.is_horizontal, s.is_exterior, s.thickness)
        groups.setdefault(key, []).append(s)

    out = []
    for (coord, is_h, is_ext, thick), segs in groups.items():
        # Sort by span start
        segs_sorted = sorted(segs, key=lambda s: s.x1 if is_h else s.y1)
        cur = segs_sorted[0]
        cur_openings = list(cur.openings)
        for nxt in segs_sorted[1:]:
            cur_end  = cur.x2  if is_h else cur.y2
            nxt_start = nxt.x1 if is_h else nxt.y1
            if nxt_start <= cur_end + MERGE_GAP:
                # Merge: extend current span and collect openings
                nxt_end = nxt.x2 if is_h else nxt.y2
                if is_h:
                    cur = WallSegment(x1=cur.x1, y1=coord, x2=max(cur_end, nxt_end),
                                      y2=coord, thickness=thick, is_exterior=is_ext,
                                      is_horizontal=True)
                else:
                    cur = WallSegment(x1=coord, y1=cur.y1, x2=coord,
                                      y2=max(cur_end, nxt_end),
                                      thickness=thick, is_exterior=is_ext,
                                      is_horizontal=False)
                cur_openings.extend(nxt.openings)
            else:
                cur.openings[:] = cur_openings
                out.append(cur)
                cur = nxt
                cur_openings = list(nxt.openings)
        cur.openings[:] = cur_openings
        out.append(cur)

    return out


def _dedupe_parallel_walls(segments, coord_gap=0.12):
    """
    Collapse near-parallel, overlapping wall segments into a single wall.

    Two wall segments are "near-parallel" when they:
      1. Share the same direction (both horizontal or both vertical)
      2. Lie within coord_gap metres of each other on their shared axis
         (coord_gap = INT_WALL = 0.12 m — any gap ≤ wall thickness is one wall)
      3. Have overlapping spans of at least 0.10 m

    In such cases the DOMINANT segment (exterior > interior; then longer) is
    kept.  The weaker segment is discarded.  This prevents the double-wall
    rendering artifact that appears as an elongated dark block.

    Called inside _compute_wall_segments() before openings are assigned.
    """
    discard: set = set()

    for i, si in enumerate(segments):
        if i in discard:
            continue
        for j, sj in enumerate(segments):
            if j <= i or j in discard:
                continue
            if si.is_horizontal != sj.is_horizontal:
                continue

            if si.is_horizontal:
                gap  = abs(si.y1 - sj.y1)
                ovlp = min(si.x2, sj.x2) - max(si.x1, sj.x1)
                si_len, sj_len = si.x2 - si.x1, sj.x2 - sj.x1
            else:
                gap  = abs(si.x1 - sj.x1)
                ovlp = min(si.y2, sj.y2) - max(si.y1, sj.y1)
                si_len, sj_len = si.y2 - si.y1, sj.y2 - sj.y1

            if gap > coord_gap or ovlp < 0.10:
                continue   # not a near-parallel pair

            # Determine which segment dominates
            # Rule 1: exterior beats interior
            if si.is_exterior and not sj.is_exterior:
                discard.add(j)
            elif sj.is_exterior and not si.is_exterior:
                discard.add(i)
                break           # si is gone — skip its remaining pairs
            else:
                # Same exterior flag — keep the longer one
                if sj_len > si_len:
                    discard.add(i)
                    break
                else:
                    discard.add(j)

    return [s for k, s in enumerate(segments) if k not in discard]


def _wall_intersections(segments, tol=0.05):
    """
    Return every (x, y) point where a vertical wall segment physically crosses
    a horizontal wall segment (within ±tol metres on each axis).

    These are the only geometrically valid structural column positions.
    """
    h_segs = [s for s in segments if     s.is_horizontal]
    v_segs = [s for s in segments if not s.is_horizontal]
    pts: set = set()
    for vs in v_segs:
        vx = vs.x1
        for hs in h_segs:
            hy = hs.y1
            in_h = (hs.x1 - tol) <= vx <= (hs.x2 + tol)
            in_v = (vs.y1 - tol) <= hy <= (vs.y2 + tol)
            if in_h and in_v:
                pts.add((round(vx, 3), round(hy, 3)))
    return sorted(pts)


# Opening Assignment

def _assign_openings(wall_segments, rooms, pw, ph):
    for r in rooms:
        if r.room_type in ("courtyard", "lightwell", "verandah"):
            continue

        skip_tags = {"open_sky", "via corridor"}
        real_wins = [w for w in r.windows if not w.startswith("vent") and w not in skip_tags]
        for win_side in real_wins:
            seg = _find_seg_for_room_side(wall_segments, r, win_side, pw, ph)
            if not seg:
                continue
            if not seg.is_exterior:          # windows on exterior walls only
                continue
            if seg.is_horizontal:
                room_start = max(seg.x1, r.x)
                room_end   = min(seg.x2, r.x2)
            else:
                room_start = max(seg.y1, r.y)
                room_end   = min(seg.y2, r.y2)
            room_span = room_end - room_start
            wl = max(WIN_MIN, min(WIN_MAX, room_span * WIN_RATIO))
            seg_origin = seg.x1 if seg.is_horizontal else seg.y1
            pos = (room_start - seg_origin) + (room_span - wl) / 2
            seg.openings.append(WallOpening(
                pos_along=pos, width=wl, opening_type="window", room=r))

        int_side = _interior_door_side(r, rooms)
        primary_side = int_side if int_side is not None else r.door_side

        dw = DOOR_WIDTHS.get(r.room_type, 0.80)
        dw = min(dw, r.width * 0.45, r.height * 0.45)
        dw = max(dw, 0.45)

        if _DOOR_VALIDATOR:
            # Try walls in priority order; place on the best validated wall
            placed = False
            for try_side in _dv_side_cands(r, rooms, primary_side):
                seg = _find_seg_for_room_side(wall_segments, r, try_side, pw, ph)
                if not seg:
                    continue
                if seg.is_horizontal:
                    room_start = max(seg.x1, r.x)
                    room_end   = min(seg.x2, r.x2)
                else:
                    room_start = max(seg.y1, r.y)
                    room_end   = min(seg.y2, r.y2)
                if room_end - room_start < dw + 0.10:
                    continue    # span too narrow for this door width
                placement = _dv_choose(seg, r, room_start, room_end, dw, wall_segments)
                seg.openings.append(WallOpening(
                    pos_along=placement.pos, width=dw, opening_type="door",
                    room=r, door_hinge=placement.hinge))
                placed = True
                break   # door placed — stop trying walls
            if not placed:
                # Absolute fallback: use primary side, centred, default hinge
                seg = _find_seg_for_room_side(wall_segments, r, primary_side, pw, ph)
                if seg:
                    if seg.is_horizontal:
                        room_start = max(seg.x1, r.x)
                        room_end   = min(seg.x2, r.x2)
                    else:
                        room_start = max(seg.y1, r.y)
                        room_end   = min(seg.y2, r.y2)
                    seg_origin = seg.x1 if seg.is_horizontal else seg.y1
                    pos = max(0.02, (room_start - seg_origin) + (room_end - room_start - dw) / 2.0)
                    hinge = "L" if seg.is_horizontal else "B"
                    seg.openings.append(WallOpening(
                        pos_along=pos, width=dw, opening_type="door",
                        room=r, door_hinge=hinge))
        else:
            # Legacy path (door_validator not available)
            seg = _find_seg_for_room_side(wall_segments, r, primary_side, pw, ph)
            if not seg:
                continue
            if seg.is_horizontal:
                room_start = max(seg.x1, r.x)
                room_end   = min(seg.x2, r.x2)
            else:
                room_start = max(seg.y1, r.y)
                room_end   = min(seg.y2, r.y2)
            room_span  = room_end - room_start
            seg_origin = seg.x1 if seg.is_horizontal else seg.y1
            CLEAR  = _CLEAR_MIN
            avail  = (room_span - dw) / 2.0
            if avail < CLEAR:
                CLEAR = max(0.05, avail * 0.70)
            pos_center = (room_start - seg_origin) + (room_span - dw) / 2.0
            pos_min    = (room_start - seg_origin) + CLEAR
            pos_max    = (room_end   - seg_origin) - dw - CLEAR
            if pos_min > pos_max:
                pos   = max(0.02, pos_center)
                hinge = "L" if seg.is_horizontal else "B"
            else:
                pos = max(0.02, max(pos_min, min(pos_max, pos_center)))
                abs_start = seg_origin + pos
                abs_end   = abs_start  + dw
                cl_near   = abs_start  - room_start
                cl_far    = room_end   - abs_end
                hinge = ("L" if cl_near <= cl_far else "R") if seg.is_horizontal \
                        else ("B" if cl_near <= cl_far else "T")
            seg.openings.append(WallOpening(
                pos_along=pos, width=dw, opening_type="door",
                room=r, door_hinge=hinge))

    for seg in wall_segments:
        if len(seg.openings) < 2:
            continue
        seg.openings.sort(key=lambda o: o.pos_along)
        resolved = [seg.openings[0]]
        for o in seg.openings[1:]:
            prev = resolved[-1]
            if o.pos_along < prev.pos_along + prev.width + 0.30:   # 300 mm min spacing
                if prev.opening_type == "door":
                    continue
                elif o.opening_type == "door":
                    resolved[-1] = o
            else:
                resolved.append(o)
        seg.openings = resolved



def _assign_archways(wall_segments, rooms, tol=0.18):
    """Add wide archway openings between public-zone rooms sharing a wall."""
    # Archways replace doors: open passages in public circulation zones.
    # corridor↔living = wide open passage (no door in Indian open-plan)
    # living↔dining   = archway if rooms share a wall (open-plan flow)
    ARCHWAY_PAIRS = {
        frozenset(["living",  "dining"]),
        frozenset(["corridor","living"]),
    }
    for seg in wall_segments:
        if seg.is_exterior:
            continue
        side1, side2 = [], []
        if seg.is_horizontal:
            for r in rooms:
                ov = min(r.x2, seg.x2) - max(r.x, seg.x1)
                if ov < 0.3:
                    continue
                if abs(r.y2 - seg.y1) < tol:
                    side1.append(r)
                elif abs(r.y - seg.y1) < tol:
                    side2.append(r)
        else:
            for r in rooms:
                ov = min(r.y2, seg.y2) - max(r.y, seg.y1)
                if ov < 0.3:
                    continue
                if abs(r.x2 - seg.x1) < tol:
                    side1.append(r)
                elif abs(r.x - seg.x1) < tol:
                    side2.append(r)
        for r1 in side1:
            for r2 in side2:
                if frozenset([r1.room_type, r2.room_type]) not in ARCHWAY_PAIRS:
                    continue
                if seg.is_horizontal:
                    os = max(r1.x, r2.x, seg.x1)
                    oe = min(r1.x2, r2.x2, seg.x2)
                else:
                    os = max(r1.y, r2.y, seg.y1)
                    oe = min(r1.y2, r2.y2, seg.y2)
                span = oe - os
                if span < 0.6:
                    continue
                arch_w = min(2.0, max(1.10, span * 0.65))
                seg_orig = seg.x1 if seg.is_horizontal else seg.y1
                pos = (os - seg_orig) + (span - arch_w) / 2.0
                pos = max(0.05, pos)
                # Archways REPLACE any door already on this span
                # (_assign_openings runs first, so doors appear before we do)
                seg.openings = [
                    op for op in seg.openings
                    if not (op.pos_along < pos + arch_w + 0.10 and
                            pos < op.pos_along + op.width + 0.10)
                ]
                seg.openings.append(WallOpening(
                    pos_along=pos, width=arch_w,
                    opening_type="archway", room=r1))


def _find_seg_for_room_side(segments, room, side, pw, ph, tol=0.15):
    if side == "N":
        target = room.y2
        for s in segments:
            if s.is_horizontal and abs(s.y1 - target) < tol:
                if s.x1 - 0.01 <= room.cx <= s.x2 + 0.01:
                    return s
    elif side == "S":
        target = room.y
        for s in segments:
            if s.is_horizontal and abs(s.y1 - target) < tol:
                if s.x1 - 0.01 <= room.cx <= s.x2 + 0.01:
                    return s
    elif side == "E":
        target = room.x2
        for s in segments:
            if not s.is_horizontal and abs(s.x1 - target) < tol:
                if s.y1 - 0.01 <= room.cy <= s.y2 + 0.01:
                    return s
    elif side == "W":
        target = room.x
        for s in segments:
            if not s.is_horizontal and abs(s.x1 - target) < tol:
                if s.y1 - 0.01 <= room.cy <= s.y2 + 0.01:
                    return s
    return None


# Main render function

def render_floorplan(fp, figsize=(14, 11), show_grid=True,
                     show_compass=True, show_dimensions=True,
                     show_legend=True, dpi=150):

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.patch.set_facecolor("#FFFFFF")
    ax.set_facecolor("#FFFFFF")

    pw, ph = fp.plot_width, fp.plot_height

    if show_grid:
        _grid(ax, pw, ph)

    _plot_boundary(ax, pw, ph)

    # 1. Floor fill
    _draw_floor_fill(ax, fp.rooms, pw, ph)

    # 2. Verandah pattern
    _draw_verandah_pattern(ax, fp.rooms)

    # 3. Courtyard
    if fp.courtyard:
        ct = fp.courtyard
        ax.add_patch(Rectangle((ct["x"], ct["y"]), ct["w"], ct["h"],
                                facecolor="#C5E1A5", edgecolor="#558B2F",
                                linewidth=1.2, linestyle="--", zorder=3, alpha=0.85))
        ax.text(ct["x"] + ct["w"]/2, ct["y"] + ct["h"]/2,
                "Courtyard\n(Open Sky)", ha="center", va="center",
                fontsize=7, color="#1B5E20", fontweight="bold",
                fontstyle="italic", zorder=8)

    # 4. Furniture (below walls)
    for r in fp.rooms:
        _apply_grammar(ax, r)

    # 5. Wall segments
    wall_segments = _compute_wall_segments(fp.rooms, pw, ph)
    _assign_openings(wall_segments, fp.rooms, pw, ph)
    _assign_archways(wall_segments, fp.rooms)

    _draw_wall_segments(ax, wall_segments)

    # 6. Openings (windows + doors)
    _draw_all_openings(ax, wall_segments)

    # 6b. Baker principle overlays
    _draw_baker_overlays(ax, fp, wall_segments)

    # 6c. Feature 5: Door/Window reference tags + opening size callouts
    _draw_opening_tags(ax, wall_segments)

    # 7. Columns — placed at structural grid intersections only
    _draw_columns(ax, fp.rooms, 0, pw, ph,
                  structural_grid=getattr(fp, "structural_grid", None),
                  wall_segments=wall_segments)

    # 8. Room labels (v8: bedroom numbering removed)
    for r in fp.rooms:
        _room_label(ax, r, None)

    # 8b. XAI explainability icons
    _draw_xai_icons(ax, fp.rooms)

    if show_dimensions:
        _draw_dimensions(ax, fp.rooms, pw, ph, 0)

    if show_compass:
        _compass(ax, pw, ph, fp.facing)

    _scale_bar(ax, pw, ph)

    if show_legend:
        _legend_margin(ax, pw, ph)

    _draw_level_marker(ax, fp, wall_segments)
    _draw_title_header(fig, fp)

    if fp.adjacency_violations:
        viol_text = "Adjacency: " + " | ".join(fp.adjacency_violations[:3])
        fig.text(0.5, 0.005, viol_text, ha="center", fontsize=6,
                 color="#B71C1C", style="italic")

    # Section cut A-A — Feature 3: circle bubble tags with direction arrows
    section_y = ph * 0.40
    SC = 0.22  # bubble radius in metres
    SL = "#CC0000"
    ax.plot([0, pw], [section_y, section_y],
            color=SL, lw=0.8, linestyle="-.", zorder=11)
    # Left bubble (view direction: downward = negative Y)
    bx_L = -1.20
    ax.add_patch(plt.Circle((bx_L, section_y), SC,
                             facecolor="white", edgecolor=SL, lw=0.9, zorder=12))
    ax.text(bx_L, section_y, "A", ha="center", va="center",
            fontsize=6, fontweight="bold", color=SL, zorder=13)
    # Arrow below left bubble pointing down (view direction)
    ax.annotate("", xy=(bx_L, section_y - SC - 0.32), xytext=(bx_L, section_y - SC),
                arrowprops=dict(arrowstyle="->", color=SL, lw=0.8), zorder=12)
    # Connecting line from building edge to bubble
    ax.plot([0, bx_L + SC], [section_y, section_y],
            color=SL, lw=0.8, linestyle="-.", zorder=11)
    # Right bubble (view direction: downward)
    bx_R = pw + 1.20
    ax.add_patch(plt.Circle((bx_R, section_y), SC,
                             facecolor="white", edgecolor=SL, lw=0.9, zorder=12))
    ax.text(bx_R, section_y, "A", ha="center", va="center",
            fontsize=6, fontweight="bold", color=SL, zorder=13)
    # Arrow below right bubble pointing down
    ax.annotate("", xy=(bx_R, section_y - SC - 0.32), xytext=(bx_R, section_y - SC),
                arrowprops=dict(arrowstyle="->", color=SL, lw=0.8), zorder=12)
    # Connecting line from building edge to bubble
    ax.plot([pw, bx_R - SC], [section_y, section_y],
            color=SL, lw=0.8, linestyle="-.", zorder=11)
    ax.text(bx_R + SC + 0.08, section_y - 0.30, "Section A-A",
            ha="left", va="top", fontsize=5, color="#666666", zorder=11)

    ax.set_xlim(-2.0, pw + 2.5)
    ax.set_ylim(-1.8, ph + 1.0)
    # rect=[left, bottom, right, top]: reserve top for title, small margins elsewhere
    plt.tight_layout(pad=0.5, rect=[0, 0.02, 1, 0.94])
    return fig


# Grid, Boundary, Floor Fill, Verandah

def _grid(ax, pw, ph):
    # Fix 1: Lighter grid lines for pure white background
    for x in np.arange(0, pw + 0.01, 1.0):
        ax.axvline(x, color="#EEEEEE", lw=0.2, zorder=0)
    for y in np.arange(0, ph + 0.01, 1.0):
        ax.axhline(y, color="#EEEEEE", lw=0.2, zorder=0)


def _plot_boundary(ax, pw, ph, setbacks=None):
    """Feature 6: Plot boundary with setback lines and dimension labels."""
    ax.add_patch(Rectangle((0, 0), pw, ph,
                            fill=False, edgecolor="#1A1A1A", lw=2.5, zorder=10))
    # Setback defaults (TNCDBR 2019 typical for 180m² plot)
    sb = setbacks or {"front_m": 3.0, "rear_m": 2.0, "side_each_m": 1.5}
    s_front = sb.get("front_m", 3.0)
    s_rear  = sb.get("rear_m", 2.0)
    s_side  = sb.get("side_each_m", 1.5)
    # Use minimum setback as the inner dashed rectangle offset
    s_min = min(s_front, s_rear, s_side)
    s = max(0.4, s_min * 0.25)   # visual offset capped at 0.4m for legibility at 1:100
    ax.add_patch(Rectangle((s, s), pw - 2*s, ph - 2*s,
                            fill=False, edgecolor="#999999", lw=0.7, linestyle=":", zorder=10))
    for cx, cy in [(0, 0), (pw, 0), (pw, ph), (0, ph)]:
        ax.plot([cx-0.25, cx+0.25], [cy, cy], "k-", lw=1.0, zorder=11)
        ax.plot([cx, cx], [cy-0.25, cy+0.25], "k-", lw=1.0, zorder=11)
    # Setback dimension labels (italic, small, outside boundary)
    SB_C  = "#555577"
    SB_FS = 4.5
    # Front setback (bottom edge — facing direction entry)
    ax.text(pw / 2, -0.14, f"Front Setback: {s_front:.1f} m",
            ha="center", va="top", fontsize=SB_FS, color=SB_C, style="italic", zorder=10)
    # Rear setback (top edge)
    ax.text(pw / 2, ph + 0.14, f"Rear Setback: {s_rear:.1f} m",
            ha="center", va="bottom", fontsize=SB_FS, color=SB_C, style="italic", zorder=10)
    # Side setbacks (left and right edges)
    ax.text(-0.14, ph / 2, f"Side: {s_side:.1f} m",
            ha="right", va="center", fontsize=SB_FS, color=SB_C,
            style="italic", rotation=90, zorder=10)
    ax.text(pw + 0.14, ph / 2, f"Side: {s_side:.1f} m",
            ha="left", va="center", fontsize=SB_FS, color=SB_C,
            style="italic", rotation=90, zorder=10)


def _draw_floor_fill(ax, rooms, pw, ph):
    valid = [r for r in rooms if r.room_type not in ("lightwell",)]
    if not valid:
        return
    min_x = min(r.x for r in valid)
    max_x = max(r.x2 for r in valid)
    min_y = min(r.y for r in valid)
    max_y = max(r.y2 for r in valid)
    ax.add_patch(Rectangle((min_x, min_y), max_x - min_x, max_y - min_y,
                            facecolor=FLOOR_COLOR, edgecolor="none", zorder=2))


def _draw_verandah_pattern(ax, rooms):
    """Verandah: clean white fill with thin dashed border (professional blueprint)."""
    for r in rooms:
        if r.room_type != "verandah":
            continue
        ax.add_patch(Rectangle((r.x, r.y), r.width, r.height,
                                facecolor="#FFFFFF", edgecolor="#888888",
                                linewidth=0.5, linestyle="--", zorder=2.3))


# Wall Drawing

def _draw_wall_segments(ax, wall_segments):
    for seg in wall_segments:
        t = seg.thickness
        fc = WALL_COLOR if seg.is_exterior else INT_WALL_COLOR
        # Fix 5: Wall edge lineweights — ext 0.8pt, int 0.4pt (clean T-junctions)
        edge_lw = 0.8 if seg.is_exterior else 0.4
        edge_ec = "#000000" if seg.is_exterior else "#333333"
        # Solid fill — professional CAD style (no hatch)
        sol_fc = "#1A1A1A" if seg.is_exterior else "#3D3D3D"
        if seg.is_horizontal:
            ax.add_patch(Rectangle((seg.x1, seg.y1 - t / 2), seg.x2 - seg.x1, t,
                                    facecolor=sol_fc, edgecolor=sol_fc,
                                    linewidth=0, zorder=5))
        else:
            ax.add_patch(Rectangle((seg.x1 - t / 2, seg.y1), t, seg.y2 - seg.y1,
                                    facecolor=sol_fc, edgecolor=sol_fc,
                                    linewidth=0, zorder=5))


def _draw_all_openings(ax, wall_segments):
    for seg in wall_segments:
        for opening in seg.openings:
            if opening.opening_type == "window":
                _draw_window_opening(ax, seg, opening)
            elif opening.opening_type == "door":
                _draw_door_opening(ax, seg, opening)
            elif opening.opening_type == "archway":
                _draw_archway_opening(ax, seg, opening)


def _draw_opening_tags(ax, wall_segments):
    """Feature 5: Door (D1, D2…) and Window (W1, W2…) reference tags with size callouts."""
    # Determine building bounding box to know which side is 'exterior'
    all_xs = [seg.x1 for seg in wall_segments] + [seg.x2 for seg in wall_segments]
    all_ys = [seg.y1 for seg in wall_segments] + [seg.y2 for seg in wall_segments]
    if not all_xs:
        return
    min_bx = min(all_xs) + 0.5   # half-metre threshold for exterior test
    max_bx = max(all_xs) - 0.5
    min_by = min(all_ys) + 0.5
    max_by = max(all_ys) - 0.5

    d_count = 1
    w_count = 1
    TAG_OFF = 0.38   # distance from wall face to tag centre
    SIZE_OFF = 0.20  # extra offset for mm size text beyond tag

    for seg in wall_segments:
        t = seg.thickness
        for op in seg.openings:
            if op.opening_type == "archway":
                continue  # skip archways — too wide, confusing tag
            mid_pos = op.pos_along + op.width / 2.0
            if seg.is_horizontal:
                tx = seg.x1 + mid_pos
                seg_y = seg.y1
                # Exterior direction: bottom edge → go down; top edge → go up
                out_dy = -1 if seg_y < min_by else +1
                ty = seg_y + (t / 2 + TAG_OFF) * out_dy
                ty2 = ty + SIZE_OFF * out_dy   # mm text further out
                tag_rot = 0
            else:
                ty = seg.y1 + mid_pos
                seg_x = seg.x1
                # Exterior direction: left edge → go left; right edge → go right
                out_dx = -1 if seg_x < min_bx else +1
                tx = seg_x + (t / 2 + TAG_OFF) * out_dx
                tx2 = tx + SIZE_OFF * out_dx
                tag_rot = 90

            size_mm = f"{op.width * 1000:.0f}"

            if op.opening_type == "door":
                label = f"D{d_count}"
                d_count += 1
                # Pale-yellow circle tag
                ax.add_patch(plt.Circle((tx, ty), 0.14,
                                        facecolor="#FFF9C4", edgecolor="#795548",
                                        linewidth=0.6, zorder=9.5))
                ax.text(tx, ty, label, ha="center", va="center",
                        fontsize=4.5, fontweight="bold", color="#4E342E", zorder=9.6)
                # Size callout in mm
                if seg.is_horizontal:
                    ax.text(tx, ty2, size_mm,
                            ha="center", va="center", fontsize=4.0,
                            color="#888888", zorder=9.5)
                else:
                    ax.text(tx2, ty, size_mm,
                            ha="center", va="center", fontsize=4.0,
                            color="#888888", rotation=90, zorder=9.5)
            else:  # window
                label = f"W{w_count}"
                w_count += 1
                # Pale-blue rectangle tag
                rw, rh = 0.26, 0.16
                ax.add_patch(Rectangle((tx - rw / 2, ty - rh / 2), rw, rh,
                                        facecolor="#E3F2FD", edgecolor="#1565C0",
                                        linewidth=0.6, zorder=9.5))
                ax.text(tx, ty, label, ha="center", va="center",
                        fontsize=4.5, fontweight="bold", color="#0D47A1", zorder=9.6)
                # Size callout in mm
                if seg.is_horizontal:
                    ax.text(tx, ty2, size_mm,
                            ha="center", va="center", fontsize=4.0,
                            color="#888888", zorder=9.5)
                else:
                    ax.text(tx2, ty, size_mm,
                            ha="center", va="center", fontsize=4.0,
                            color="#888888", rotation=90, zorder=9.5)


def _draw_window_opening(ax, seg, opening):
    """
    Classic 3-line window symbol per IS 962 / BS 1192 (plan view):
      1. Wall gap  — white rectangle
      2. Outer-face line — thin line at exterior wall face
      3. Glass line      — slightly heavier line at wall centre (glazing pane)
      4. Inner-face line — thin line at interior wall face
      5. Jamb lines      — short lines at each end, full wall thickness
      6. Sill notch      — two short perpendicular stubs on the exterior face,
                           representing the window sill projection in plan

    Exterior face is determined from opening.room position relative to the wall.
    """
    t  = seg.thickness
    wl = opening.width
    r  = opening.room

    WIN_C_FACE  = "#111111"   # face + jamb lines
    WIN_C_GLASS = "#444444"   # glass line (slightly lighter)
    FACE_LW     = 0.9         # outer / inner face lines
    GLASS_LW    = 0.6         # centre glass line (thinner — glass is thin)
    JAMB_LW     = 0.9         # jamb end-lines
    NOTCH_D     = 0.055       # sill notch depth (55 mm sill projection in plan)
    NOTCH_LW    = 0.8

    if seg.is_horizontal:
        # ── Horizontal wall window ─────────────────────────────────────────
        wx  = seg.x1 + opening.pos_along   # left edge of opening
        wy  = seg.y1 - t / 2               # bottom of wall band

        # 1. Clear wall gap
        ax.add_patch(Rectangle((wx, wy), wl, t,
                                facecolor="#FFFFFF", edgecolor="none", zorder=6))

        # 2. Outer face line (bottom of wall band)
        ax.plot([wx, wx + wl], [wy,       wy      ],
                color=WIN_C_FACE, lw=FACE_LW, zorder=7)
        # 3. Glass line (centre of wall)
        ax.plot([wx, wx + wl], [wy + t/2, wy + t/2],
                color=WIN_C_GLASS, lw=GLASS_LW, zorder=7)
        # 4. Inner face line (top of wall band)
        ax.plot([wx, wx + wl], [wy + t,   wy + t  ],
                color=WIN_C_FACE, lw=FACE_LW, zorder=7)

        # 5. Jamb lines at each end (perpendicular to wall, full thickness)
        for xj in [wx, wx + wl]:
            ax.plot([xj, xj], [wy, wy + t],
                    color=WIN_C_FACE, lw=JAMB_LW, solid_capstyle="butt", zorder=7)

        # 6. Exterior sill notch — determine exterior face from room position
        if r is not None and r.cy > seg.y1:
            # room is ABOVE → exterior = bottom face (wy)
            ext_y = wy
            for xn in [wx, wx + wl]:
                ax.plot([xn, xn], [ext_y, ext_y - NOTCH_D],
                        color=WIN_C_FACE, lw=NOTCH_LW, zorder=7)
        else:
            # room is BELOW → exterior = top face (wy + t)
            ext_y = wy + t
            for xn in [wx, wx + wl]:
                ax.plot([xn, xn], [ext_y, ext_y + NOTCH_D],
                        color=WIN_C_FACE, lw=NOTCH_LW, zorder=7)

    else:
        # ── Vertical wall window ───────────────────────────────────────────
        wx  = seg.x1 - t / 2               # left of wall band
        wy  = seg.y1 + opening.pos_along   # bottom edge of opening

        # 1. Clear wall gap
        ax.add_patch(Rectangle((wx, wy), t, wl,
                                facecolor="#FFFFFF", edgecolor="none", zorder=6))

        # 2. Outer face line (left of wall band)
        ax.plot([wx,       wx      ], [wy, wy + wl],
                color=WIN_C_FACE, lw=FACE_LW, zorder=7)
        # 3. Glass line (centre of wall)
        ax.plot([wx + t/2, wx + t/2], [wy, wy + wl],
                color=WIN_C_GLASS, lw=GLASS_LW, zorder=7)
        # 4. Inner face line (right of wall band)
        ax.plot([wx + t,   wx + t  ], [wy, wy + wl],
                color=WIN_C_FACE, lw=FACE_LW, zorder=7)

        # 5. Jamb lines at each end (perpendicular to wall, full thickness)
        for yj in [wy, wy + wl]:
            ax.plot([wx, wx + t], [yj, yj],
                    color=WIN_C_FACE, lw=JAMB_LW, solid_capstyle="butt", zorder=7)

        # 6. Exterior sill notch — determine exterior face from room position
        if r is not None and r.cx > seg.x1:
            # room is to the RIGHT → exterior = left face (wx)
            ext_x = wx
            for yn in [wy, wy + wl]:
                ax.plot([ext_x, ext_x - NOTCH_D], [yn, yn],
                        color=WIN_C_FACE, lw=NOTCH_LW, zorder=7)
        else:
            # room is to the LEFT → exterior = right face (wx + t)
            ext_x = wx + t
            for yn in [wy, wy + wl]:
                ax.plot([ext_x, ext_x + NOTCH_D], [yn, yn],
                        color=WIN_C_FACE, lw=NOTCH_LW, zorder=7)


def _draw_door_opening(ax, seg, opening):
    """
    Professional CAD door symbol — 3 elements per BS 1192 / IS 962 convention:
      1. Wall gap  — white rectangle clearing the wall thickness
      2. Leaf line — from hinge point, PERPENDICULAR to wall, into the room
                     (represents door in fully-open 90° position)
      3. Swing arc — 90° dashed quarter-circle, centre = hinge, r = door width,
                     traces closed-position latch-end → open-position leaf-tip
                     + small arrowhead at arc tip indicating swing direction

    Hinge encoding (stored in opening.door_hinge):
      Horizontal wall → "L" (hinge at x-left end) | "R" (hinge at x-right end)
      Vertical   wall → "B" (hinge at y-bottom end) | "T" (hinge at y-top end)
    """
    t     = seg.thickness
    dw    = opening.width
    room  = opening.room
    hinge = getattr(opening, "door_hinge", "L")

    LEAF_LW  = 1.4                     # bold solid leaf
    LEAF_C   = "#000000"
    # Fix 2: Door swing arc — 0.3pt dashed [2,1] pattern + filled arrowhead
    ARC_LW   = 0.3                     # thin 0.3pt dashed arc
    ARC_C    = "#000000"
    ARC_LS   = (0, (2, 1))             # [2,1] dash pattern (short dashes)
    N_PTS    = 64                      # arc resolution (smooth quarter-circle)

    if seg.is_horizontal:
        # ── Horizontal wall: gap runs along X ──────────────────────────────
        dx = seg.x1 + opening.pos_along
        dy = seg.y1

        # 1. Clear wall gap
        ax.add_patch(Rectangle((dx, dy - t / 2), dw, t,
                                facecolor="#FFFFFF", edgecolor="none", zorder=6))

        room_is_below = room.cy < dy

        # Hinge pin coords
        hx = dx if hinge == "L" else dx + dw
        hy = dy

        # 2 + 3. Leaf tip and arc sweep angles
        if room_is_below:
            leaf_tip = (hx, hy - dw)          # perpendicular DOWN into room
            if hinge == "L":
                # closed latch at (dx+dw, dy)=0°  →  open tip at (dx, dy-dw)=-90°
                t_arc = np.linspace(0.0, -np.pi / 2, N_PTS)
            else:  # R
                # closed latch at (dx, dy)=180°  →  open tip at (dx+dw, dy-dw)=270°
                t_arc = np.linspace(np.pi, 3 * np.pi / 2, N_PTS)
        else:
            leaf_tip = (hx, hy + dw)           # perpendicular UP into room
            if hinge == "L":
                # 0° → +90°
                t_arc = np.linspace(0.0, np.pi / 2, N_PTS)
            else:  # R
                # 180° → +90°
                t_arc = np.linspace(np.pi, np.pi / 2, N_PTS)

    else:
        # ── Vertical wall: gap runs along Y ────────────────────────────────
        dy = seg.y1 + opening.pos_along
        dx = seg.x1

        # 1. Clear wall gap
        ax.add_patch(Rectangle((dx - t / 2, dy), t, dw,
                                facecolor="#FFFFFF", edgecolor="none", zorder=6))

        room_is_right = room.cx > dx

        # Hinge pin coords
        hx = dx
        hy = dy if hinge == "B" else dy + dw

        # 2 + 3. Leaf tip and arc sweep angles
        if room_is_right:
            leaf_tip = (hx + dw, hy)           # perpendicular RIGHT into room
            if hinge == "B":
                # closed latch at (dx, dy+dw)=90°  →  open tip at (dx+dw, dy)=0°
                t_arc = np.linspace(np.pi / 2, 0.0, N_PTS)
            else:  # T
                # closed latch at (dx, dy)=-90°  →  open tip at (dx+dw, dy+dw)=0°
                t_arc = np.linspace(-np.pi / 2, 0.0, N_PTS)
        else:
            leaf_tip = (hx - dw, hy)           # perpendicular LEFT into room
            if hinge == "B":
                # 90° → 180°
                t_arc = np.linspace(np.pi / 2, np.pi, N_PTS)
            else:  # T
                # -90° → -180°
                t_arc = np.linspace(-np.pi / 2, -np.pi, N_PTS)

    # ── 2. Door leaf: hinge → open position (perpendicular to wall) ────────
    ax.plot([hx, leaf_tip[0]], [hy, leaf_tip[1]],
            color=LEAF_C, lw=LEAF_LW, solid_capstyle="round", zorder=7)

    # ── 3a. Swing arc (dashed quarter-circle) ──────────────────────────────
    arc_x = hx + dw * np.cos(t_arc)
    arc_y = hy + dw * np.sin(t_arc)
    ax.plot(arc_x, arc_y,
            color=ARC_C, lw=ARC_LW, linestyle=ARC_LS,
            solid_capstyle="butt", zorder=7)

    # ── 3b. Fix 2: Filled triangle arrowhead at arc tip ────────────────────
    # Compute tangent direction at arc end for arrowhead orientation
    dx_tip = arc_x[-1] - arc_x[-3]
    dy_tip = arc_y[-1] - arc_y[-3]
    tip_len = max(1e-9, (dx_tip**2 + dy_tip**2)**0.5)
    ux, uy = dx_tip / tip_len, dy_tip / tip_len   # unit tangent
    # Perpendicular
    px, py = -uy, ux
    AH = 0.08   # arrowhead half-width
    AL = 0.14   # arrowhead length
    tip_x, tip_y = arc_x[-1], arc_y[-1]
    tri = Polygon([
        (tip_x, tip_y),
        (tip_x - AL * ux + AH * px, tip_y - AL * uy + AH * py),
        (tip_x - AL * ux - AH * px, tip_y - AL * uy - AH * py),
    ], closed=True, facecolor=ARC_C, edgecolor="none", zorder=7.5)
    ax.add_patch(tri)

    # ── 4. Hinge-pin dot (small filled circle at pivot) ────────────────────
    ax.plot(hx, hy, "o",
            color=LEAF_C, ms=1.8,
            markerfacecolor=LEAF_C, markeredgewidth=0, zorder=8)




def _draw_archway_opening(ax, seg, opening):
    """
    Open-passage archway symbol — no door, no swing arc.
    3 elements:
      1. Wall gap       — white rectangle (same as other openings)
      2. Jamb cap-lines — bold short lines at each end, spanning wall thickness,
                         visually terminating the wall at the opening edge
      3. Header arch    — shallow half-ellipse at the passage face (room side),
                         spanning full opening width; represents the arch soffit
                         visible in plan. Rise = 22 % of opening width (max 280 mm).

    The arch is drawn on the face that is closer to the room in opening.room;
    a faint sill line marks the opposite (far) face for completeness.
    """
    t     = seg.thickness
    aw    = opening.width
    r     = opening.room

    JAMB_LW  = 2.2              # bold jamb cap — matches wall line weight
    ARCH_LW  = 1.0              # header arch curve
    SILL_LW  = 0.4              # far-face sill line
    ARCH_C   = "#000000"
    N_ARC    = 60
    rise     = min(0.28, aw * 0.22)    # arch rise: 22 % of span, max 280 mm

    if seg.is_horizontal:
        # ── Horizontal wall archway ────────────────────────────────────────
        ax_s = seg.x1 + opening.pos_along   # left edge of opening
        ay   = seg.y1 - t / 2               # bottom of wall band

        # 1. Clear gap
        ax.add_patch(Rectangle((ax_s, ay), aw, t,
                                facecolor="#FFFFFF", edgecolor="none", zorder=6))

        # 2. Jamb cap-lines (bold vertical lines at each opening edge)
        for xj in [ax_s, ax_s + aw]:
            ax.plot([xj, xj], [ay, ay + t],
                    color=ARCH_C, lw=JAMB_LW, solid_capstyle="butt", zorder=7)

        # 3. Header arch + sill line
        # Arch goes on the room-side face; determine from room.cy vs seg.y1
        if r is not None and r.cy > seg.y1:
            # room is ABOVE → arch on TOP face (ay + t), rises further upward
            arch_cy = ay + t
            t_arc   = np.linspace(0, np.pi, N_ARC)
            ax.plot(ax_s + aw / 2 + (aw / 2) * np.cos(t_arc),
                    arch_cy + rise * np.sin(t_arc),
                    color=ARCH_C, lw=ARCH_LW, zorder=7)
            # faint sill line at bottom face
            ax.plot([ax_s, ax_s + aw], [ay, ay],
                    color=ARCH_C, lw=SILL_LW, linestyle="--", zorder=7)
        else:
            # room is BELOW → arch on BOTTOM face (ay), rises further downward
            arch_cy = ay
            t_arc   = np.linspace(0, np.pi, N_ARC)
            ax.plot(ax_s + aw / 2 + (aw / 2) * np.cos(t_arc),
                    arch_cy - rise * np.sin(t_arc),
                    color=ARCH_C, lw=ARCH_LW, zorder=7)
            # faint sill line at top face
            ax.plot([ax_s, ax_s + aw], [ay + t, ay + t],
                    color=ARCH_C, lw=SILL_LW, linestyle="--", zorder=7)

    else:
        # ── Vertical wall archway ──────────────────────────────────────────
        ay_s = seg.y1 + opening.pos_along   # bottom edge of opening
        ax_x = seg.x1 - t / 2              # left of wall band

        # 1. Clear gap
        ax.add_patch(Rectangle((ax_x, ay_s), t, aw,
                                facecolor="#FFFFFF", edgecolor="none", zorder=6))

        # 2. Jamb cap-lines (bold horizontal lines at each opening edge)
        for yj in [ay_s, ay_s + aw]:
            ax.plot([ax_x, ax_x + t], [yj, yj],
                    color=ARCH_C, lw=JAMB_LW, solid_capstyle="butt", zorder=7)

        # 3. Header arch + sill line
        if r is not None and r.cx > seg.x1:
            # room is to the RIGHT → arch on RIGHT face (ax_x + t), rises rightward
            arch_cx = ax_x + t
            t_arc   = np.linspace(-np.pi / 2, np.pi / 2, N_ARC)
            ax.plot(arch_cx + rise * np.cos(t_arc),
                    ay_s + aw / 2 + (aw / 2) * np.sin(t_arc),
                    color=ARCH_C, lw=ARCH_LW, zorder=7)
            # faint sill line at left face
            ax.plot([ax_x, ax_x], [ay_s, ay_s + aw],
                    color=ARCH_C, lw=SILL_LW, linestyle="--", zorder=7)
        else:
            # room is to the LEFT → arch on LEFT face (ax_x), rises leftward
            arch_cx = ax_x
            t_arc   = np.linspace(-np.pi / 2, np.pi / 2, N_ARC)
            ax.plot(arch_cx - rise * np.cos(t_arc),
                    ay_s + aw / 2 + (aw / 2) * np.sin(t_arc),
                    color=ARCH_C, lw=ARCH_LW, zorder=7)
            # faint sill line at right face
            ax.plot([ax_x + t, ax_x + t], [ay_s, ay_s + aw],
                    color=ARCH_C, lw=SILL_LW, linestyle="--", zorder=7)


# Columns + Interior Door Side

def _draw_columns(ax, rooms, margin, plot_w, plot_h, structural_grid=None, wall_segments=None):
    """
    Feature 4: Structural RCC column grid.

    Columns are placed ONLY at true structural grid intersections — the cross-
    points of the primary column-grid lines derived from bay spacing.  This
    follows NBC 2016 Part 6 §5.3 (RCC frame spacing 3–6 m) and IS 456:2000.

    Uses the StructuralGrid passed from the engine (post-rotation) to determine
    exact column positions.  Falls back to deriving a uniform grid from room
    extents if no grid is available.

    Column squares are 300×300 mm (0.30 m) solid black, CAD style.
    Columns only at structural intersections — NOT at every room-corner T-junction.
    """
    col_size = 0.30

    if not rooms:
        return

    # ── Step 1: Establish structural grid lines ───────────────────────────────
    snap_tol = 0.20   # room-edge snapping tolerance

    if structural_grid is not None:
        # Use the engine-supplied rotated structural grid directly
        grid_xs = list(structural_grid.col_lines)
        grid_ys = list(structural_grid.row_lines)
    else:
        # Fallback: derive a uniform bay grid from the final room extents
        all_xs = sorted({round(r.x, 2) for r in rooms}
                        | {round(r.x + r.width, 2) for r in rooms})
        all_ys = sorted({round(r.y, 2) for r in rooms}
                        | {round(r.y + r.height, 2) for r in rooms})
        if len(all_xs) < 2 or len(all_ys) < 2:
            return

        bldg_w = all_xs[-1] - all_xs[0]
        bldg_h = all_ys[-1] - all_ys[0]

        def _uniform_grid(x0, span, target_bay=3.0):
            n = max(1, round(span / target_bay))
            bay = span / n
            return [round(x0 + i * bay, 4) for i in range(n + 1)]

        grid_xs = _uniform_grid(all_xs[0], bldg_w)
        grid_ys = _uniform_grid(all_ys[0], bldg_h)

    # ── Step 2: Snap each grid line to the nearest actual room edge ───────────
    # Columns must sit where walls are, not floating in mid-air.
    all_room_xs = sorted({round(r.x, 4) for r in rooms}
                         | {round(r.x + r.width, 4) for r in rooms})
    all_room_ys = sorted({round(r.y, 4) for r in rooms}
                         | {round(r.y + r.height, 4) for r in rooms})

    def _snap_to_room_edges(grid_lines, room_edges, tol):
        snapped = []
        for g in grid_lines:
            nearest = min(room_edges, key=lambda e: abs(e - g), default=g)
            if abs(nearest - g) <= tol:
                snapped.append(round(nearest, 4))
            else:
                snapped.append(round(g, 4))   # keep as-is (perimeter may have no room edge)
        return list(dict.fromkeys(snapped))   # deduplicate preserving order

    grid_xs = _snap_to_room_edges(grid_xs, all_room_xs, snap_tol)
    grid_ys = _snap_to_room_edges(grid_ys, all_room_ys, snap_tol)

    # ── Step 3: Compute valid column positions from actual wall crossings ────
    # A column is placed ONLY where a vertical and horizontal wall segment
    # physically cross AND that crossing is within 0.10 m of a structural
    # grid intersection.  This prevents floating squares inside large rooms.
    GRID_TOL = 0.10   # max distance from wall crossing to nearest grid point

    if wall_segments:
        crossing_pts = _wall_intersections(wall_segments)
        col_positions = [
            (wx, wy) for wx, wy in crossing_pts
            if any(
                abs(gx - wx) <= GRID_TOL and abs(gy - wy) <= GRID_TOL
                for gx in grid_xs for gy in grid_ys
            )
        ]
    else:
        # Fallback — no segment data: place at every grid intersection
        col_positions = [(gx, gy) for gx in grid_xs for gy in grid_ys]

    # ── Step 4: Draw structural columns at confirmed crossing positions ───────
    drawn = set()
    for (cx, cy) in col_positions:
        key = (round(cx, 2), round(cy, 2))
        if key in drawn:
            continue
        drawn.add(key)
        ax.add_patch(Rectangle(
            (cx - col_size / 2, cy - col_size / 2),
            col_size, col_size,
            facecolor="#1A1A1A", edgecolor="#1A1A1A",
            linewidth=0, zorder=10,
        ))

    # Grid reference labels (A,B,C / 1,2,3) removed per user request (v8)


def _interior_door_side(r, rooms):
    DOOR_TARGETS = {
        "bathroom":  ["bedroom", "corridor", "living"],
        "toilet":    ["bedroom", "corridor", "living"],
        "bedroom":   ["corridor", "living", "dining"],
        "corridor":  ["living", "dining", "bedroom"],
        "utility":   ["kitchen", "corridor", "dining"],
        "pooja":     ["living", "corridor", "dining"],
        "study":     ["corridor", "living", "bedroom"],
        "store":     ["corridor", "utility", "kitchen"],
        "kitchen":   ["dining", "corridor", "living"],
        "dining":    ["kitchen", "living", "corridor"],
        "living":    ["verandah", "corridor", "dining", "kitchen", "bedroom"],
    }
    targets = DOOR_TARGETS.get(r.room_type, ["corridor", "living"])
    adj_rooms = [ar for ar in rooms if ar.name in r.adjacent_to and ar.name != r.name]

    def _prio(ar):
        try:    return targets.index(ar.room_type)
        except: return 99

    adj_rooms.sort(key=_prio)
    adj_rooms = [ar for ar in adj_rooms if _prio(ar) < 99]
    tol = 0.35
    min_overlap = 0.50
    for target in adj_rooms:
        if abs(target.y - r.y2) < tol:
            if min(target.x2, r.x2) - max(target.x, r.x) >= min_overlap:
                return "N"
        if abs(target.y2 - r.y) < tol:
            if min(target.x2, r.x2) - max(target.x, r.x) >= min_overlap:
                return "S"
        if abs(target.x - r.x2) < tol:
            if min(target.y2, r.y2) - max(target.y, r.y) >= min_overlap:
                return "E"
        if abs(target.x2 - r.x) < tol:
            if min(target.y2, r.y2) - max(target.y, r.y) >= min_overlap:
                return "W"
    return None


# ── Shape Grammar Furniture System ───────────────────────────────────────────
# Replaces all hand-coded _fix_* functions.
# Each room type has a list of rules; each rule specifies element, anchor,
# size (as a lambda of room w/h), and a when-guard.
# _apply_grammar() is the only public entry point called from render_floorplan().

GRAMMAR = {
    "bedroom": [
        {"el": "bed",       "anchor": "top_centre",
         "size": lambda w, h: (min(1.75, w * 0.78), 2.0),
         "when": lambda w, h: w >= 2.4},
        {"el": "wardrobe",  "anchor": "bottom_full",
         "size": lambda w, h: (w - 0.10, 0.56),
         "when": lambda w, h: h >= 3.0},
        {"el": "sidetable", "anchor": "bed_left",
         "size": lambda w, h: (0.38, 0.38),
         "when": lambda w, h: w >= 3.2},
        {"el": "sidetable", "anchor": "bed_right",
         "size": lambda w, h: (0.38, 0.38),
         "when": lambda w, h: w >= 3.5},
    ],
    "living": [
        {"el": "sofa",    "anchor": "bottom_centre",
         "size": lambda w, h: (min(2.0, w * 0.75), 0.82),
         "when": lambda w, h: True},
        # v8: TV on side wall (E/W) to avoid blocking door entrance on sofa-facing wall
        {"el": "tv_unit", "anchor": "side_wall_centre",
         "size": lambda w, h: (0.30, min(1.10, h * 0.38)),
         "when": lambda w, h: w >= 3.0},
        {"el": "coffee",  "anchor": "sofa_front",
         "size": lambda w, h: (0.88, 0.44),
         "when": lambda w, h: h >= 3.5},
        {"el": "rug",     "anchor": "sofa_front",
         "size": lambda w, h: (min(1.8, w * 0.70), 1.1),
         "when": lambda w, h: h >= 3.5},
    ],
    "kitchen": [
        {"el": "counter_back", "anchor": "top_full",
         "size": lambda w, h: (w - 0.10, 0.60),
         "when": lambda w, h: True},
        {"el": "counter_side", "anchor": "left_centre",
         "size": lambda w, h: (0.60, h * 0.38),
         "when": lambda w, h: w >= 2.8},
        {"el": "hob",          "anchor": "top_right",
         "size": lambda w, h: (0.58, 0.52),
         "when": lambda w, h: True},
        {"el": "sink",         "anchor": "top_left",
         "size": lambda w, h: (0.52, 0.38),
         "when": lambda w, h: True},
        {"el": "fridge",       "anchor": "bottom_left",
         "size": lambda w, h: (0.62, 0.62),
         "when": lambda w, h: h >= 3.0},
    ],
    "bathroom": [
        {"el": "wc",     "anchor": "bottom_left",
         "size": lambda w, h: (0.38, 0.56),
         "when": lambda w, h: True},
        {"el": "basin",  "anchor": "bottom_right",
         "size": lambda w, h: (0.44, 0.36),
         "when": lambda w, h: True},
        {"el": "shower", "anchor": "top_right",
         "size": lambda w, h: (min(0.90, w * 0.38),
                               min(0.90, h * 0.38)),
         "when": lambda w, h: w >= 1.8 and h >= 2.0},
    ],
    "toilet": [
        {"el": "wc",    "anchor": "bottom_left",
         "size": lambda w, h: (0.38, 0.56),
         "when": lambda w, h: True},
        {"el": "basin", "anchor": "bottom_right",
         "size": lambda w, h: (0.44, 0.36),
         "when": lambda w, h: True},
    ],
    "utility": [
        {"el": "washing", "anchor": "top_left",
         "size": lambda w, h: (0.58, 0.58),
         "when": lambda w, h: w >= 1.8},
        {"el": "counter", "anchor": "top_right",
         "size": lambda w, h: (w * 0.40, 0.52),
         "when": lambda w, h: w >= 2.4},
    ],
    "study": [
        {"el": "desk",   "anchor": "top_centre",
         "size": lambda w, h: (min(1.20, w * 0.78), min(0.60, h * 0.30)),
         "when": lambda w, h: True},
    ],
}
# "office" maps to same rules as "study"
GRAMMAR["office"] = GRAMMAR["study"]


def _resolve_anchor(anchor, room, fw, fd, ctx):
    """Convert anchor name → (x, y) top-left of furniture piece."""
    rx, ry = room.x, room.y
    rw, rh = room.width, room.height
    PAD = 0.08

    anchors = {
        "top_centre":    (rx + rw / 2 - fw / 2,  ry + rh - fd - PAD),
        "top_left":      (rx + PAD,               ry + rh - fd - PAD),
        "top_right":     (rx + rw - fw - PAD,     ry + rh - fd - PAD),
        "top_full":      (rx + PAD,               ry + rh - fd - PAD),
        "bottom_centre": (rx + rw / 2 - fw / 2,  ry + PAD),
        "bottom_left":   (rx + PAD,               ry + PAD),
        "bottom_right":  (rx + rw - fw - PAD,     ry + PAD),
        "centre":        (rx + rw / 2 - fw / 2,  ry + rh / 2 - fd / 2),
        "left_centre":   (rx + PAD,               ry + rh / 2 - fd / 2),
        "right_centre":  (rx + rw - fw - PAD,     ry + rh / 2 - fd / 2),
    }

    if anchor == "sofa_front" and "sofa" in ctx:
        sx, sy, sw, sd = ctx["sofa"]
        return (sx, sy + sd + 0.30)

    if anchor == "bed_left" and "bed" in ctx:
        bx, by, bw, bd = ctx["bed"]
        return (bx - fw - 0.05, by + bd * 0.35)

    if anchor == "bed_right" and "bed" in ctx:
        bx, by, bw, bd = ctx["bed"]
        return (bx + bw + 0.05, by + bd * 0.35)

    # v8: TV on side wall — perpendicular to sofa-door axis, avoiding door wall
    if anchor == "side_wall_centre":
        # fw = TV depth (0.30m), fd = TV length (vertical strip on side wall)
        # Try E wall first, then W wall; check clearance from sofa
        e_x = rx + rw - fw - PAD
        w_x = rx + PAD
        cy = ry + (rh - fd) / 2   # centred vertically

        if "sofa" in ctx:
            sx, sy, sw, sd = ctx["sofa"]
            sofa_right = sx + sw
            sofa_left  = sx
            e_gap = e_x - sofa_right       # gap between sofa and E-wall TV
            w_gap = sofa_left - (w_x + fw)  # gap between W-wall TV and sofa
        else:
            e_gap = rw * 0.3
            w_gap = rw * 0.3

        # Prefer E wall (more open in typical layouts)
        if e_gap >= 0.25:
            return (e_x, cy)
        elif w_gap >= 0.25:
            return (w_x, cy)
        else:
            # Fallback: E wall anyway (tight room, still better than door wall)
            return (e_x, cy)

    return anchors.get(anchor, (rx + PAD, ry + PAD))


def _draw_element(ax, el, x, y, w, d, room):
    """Render a single furniture element onto ax."""
    if el == "bed":
        # Mattress
        ax.add_patch(Rectangle((x, y), w, d,
                                fc="#EDE5D5", ec="#777766", lw=0.8, zorder=4))
        # Headboard
        ax.add_patch(Rectangle((x, y + d - 0.13), w, 0.13,
                                fc="#8B7355", lw=0, zorder=5))
        # Pillows (1 or 2)
        n = 2 if w >= 1.5 else 1
        pw2 = w / n - 0.07
        for i in range(n):
            ax.add_patch(FancyBboxPatch(
                (x + 0.04 + i * (w / n), y + d - 0.19 - 0.34),
                pw2, 0.33,
                boxstyle="round,pad=0.03",
                fc="#F8F4EE", ec="#BBBBAA", lw=0.5, zorder=5))
        # Sheet fold line
        ax.plot([x + 0.05, x + w - 0.05],
                [y + d - 0.55, y + d - 0.55],
                color="#CCCCBB", lw=0.5, ls="--", zorder=5)

    elif el == "wardrobe":
        ax.add_patch(Rectangle((x, y), w, d,
                                fc="#D5CCB8", ec="#888877", lw=0.7, zorder=4))
        mid = x + w / 2
        ax.plot([x + 0.05, mid - 0.03], [y + 0.05, y + d - 0.05],
                color="#999988", lw=0.5, zorder=5)
        ax.plot([mid + 0.03, x + w - 0.05], [y + 0.05, y + d - 0.05],
                color="#999988", lw=0.5, zorder=5)

    elif el == "sidetable":
        ax.add_patch(Rectangle((x, y), w, d,
                                fc="#D4C9B8", ec="#999988", lw=0.5, zorder=4))

    elif el == "sofa":
        ax.add_patch(Rectangle((x, y), w, d,
                                fc="#D5CCBB", ec="#888877", lw=0.8, zorder=4))
        # Armrests
        for ax2 in [x - 0.10, x + w]:
            ax.add_patch(Rectangle((ax2, y), 0.10, d,
                                   fc="#C0B8A8", ec="#888877", lw=0.6, zorder=5))
        # Back cushions (3 segments)
        cw = (w - 0.08) / 3
        for i in range(3):
            ax.add_patch(FancyBboxPatch(
                (x + 0.04 + i * cw, y + d - 0.20),
                cw - 0.04, 0.18,
                boxstyle="round,pad=0.02",
                fc="#C5BDB0", ec="#999988", lw=0.4, zorder=5))

    elif el == "tv_unit":
        ax.add_patch(Rectangle((x, y), w, d,
                                fc="#C8C0B0", ec="#777766", lw=0.6, zorder=4))
        ax.add_patch(Rectangle((x + 0.07, y + 0.05), w - 0.14, d - 0.10,
                                fc="#888899", lw=0, zorder=5))

    elif el == "coffee":
        ax.add_patch(FancyBboxPatch((x, y), w, d,
                                    boxstyle="round,pad=0.05",
                                    fc="#C4B89A", ec="#887766", lw=0.6, zorder=4))

    elif el == "rug":
        ax.add_patch(Rectangle((x, y), w, d,
                                fc="#D4C8B8", ec="#AA9988",
                                lw=0.5, ls="--", zorder=3, alpha=0.4))

    elif el in ("counter_back", "counter_side", "counter"):
        ax.add_patch(Rectangle((x, y), w, d,
                                fc="#C8C0B0", ec="#888877", lw=0.8, zorder=4))
        if el == "counter_back":
            ax.plot([x + 0.04, x + w - 0.04], [y + 0.05, y + 0.05],
                    color="#666655", lw=0.5, zorder=5)

    elif el == "hob":
        ax.add_patch(Rectangle((x, y), w, d,
                                fc="#BBBBBB", ec="#777777", lw=0.5, zorder=5))
        for ox, oy in [(0.14, 0.13), (0.40, 0.13), (0.14, 0.37), (0.40, 0.37)]:
            if ox < w - 0.08 and oy < d - 0.08:
                ax.add_patch(Circle((x + ox, y + oy), 0.08,
                                    fc="#999999", ec="#555555", lw=0.5, zorder=6))

    elif el == "sink":
        ax.add_patch(Rectangle((x, y), w, d,
                                fc="#DDDDE8", ec="#888888", lw=0.6, zorder=5))
        ax.add_patch(Ellipse((x + w / 2, y + d / 2), 0.18, 0.12,
                              fc="#AAAAAA", ec="#888888", lw=0.5, zorder=6))

    elif el == "fridge":
        ax.add_patch(Rectangle((x, y), w, d,
                                fc="#D8D8D0", ec="#888888", lw=0.6, zorder=5))
        ax.plot([x + w * 0.55, x + w * 0.55], [y + 0.15, y + d - 0.15],
                color="#666666", lw=1.5, zorder=6)

    elif el == "wc":
        ax.add_patch(Rectangle((x, y + d - 0.16), w, 0.16,
                                fc="#CCCCDD", ec="#888899", lw=0.6, zorder=5))
        ax.add_patch(Ellipse((x + w / 2, y + d * 0.38), w - 0.05, d * 0.62,
                              fc="#DDDDEE", ec="#888899", lw=0.6, zorder=5))

    elif el == "basin":
        ax.add_patch(FancyBboxPatch((x, y), w, d,
                                    boxstyle="round,pad=0.04",
                                    fc="#DDDDEE", ec="#888899", lw=0.6, zorder=5))
        ax.add_patch(Circle((x + w / 2, y + d * 0.55), 0.03,
                             fc="#AAAAAA", lw=0, zorder=6))

    elif el == "shower":
        ax.add_patch(Rectangle((x, y), w, d,
                                fc="#E8EEF4", ec="#8899AA", lw=0.6, zorder=4))
        n = 4
        for i in range(1, n):
            ax.plot([x + w * i / n, x + w * i / n], [y, y + d],
                    color="#AABBCC", lw=0.3, zorder=5)
            ax.plot([x, x + w], [y + d * i / n, y + d * i / n],
                    color="#AABBCC", lw=0.3, zorder=5)
        ax.add_patch(Circle((x + w * 0.5, y + d * 0.5), 0.06,
                             fc="#9AABBB", ec="#778899", lw=0.5, zorder=6))

    elif el == "washing":
        ax.add_patch(Rectangle((x, y), w, d,
                                fc="#D8D8E8", ec="#888899", lw=0.6, zorder=4))
        ax.add_patch(Circle((x + w / 2, y + d / 2), min(w, d) * 0.35,
                             fc="#BBBBCC", ec="#777788", lw=0.5, zorder=5))

    elif el == "desk":
        ax.add_patch(Rectangle((x, y), w, d,
                                fc="#D5CCB8", ec="#888877", lw=0.7, zorder=4))
        # Chair circle below desk
        chair_r = min(0.18, d * 0.30)
        ax.add_patch(Circle((x + w / 2, y - chair_r - 0.05), chair_r,
                             fc="none", ec="#888877", lw=0.7, zorder=4))


def _apply_grammar(ax, room):
    """Apply shape grammar rules for *room* and draw all matching furniture."""
    rtype = room.room_type.lower()
    rules = GRAMMAR.get(rtype, [])
    ctx: dict = {}

    for rule in rules:
        rw, rh = room.width, room.height
        if not rule["when"](rw, rh):
            continue

        fw, fd = rule["size"](rw, rh)
        fx, fy = _resolve_anchor(rule["anchor"], room, fw, fd, ctx)

        # Bounds check — skip if piece falls outside room footprint
        if (fx < room.x - 0.05 or fy < room.y - 0.05 or
                fx + fw > room.x + rw + 0.05 or
                fy + fd > room.y + rh + 0.05):
            continue

        _draw_element(ax, rule["el"], fx, fy, fw, fd, room)
        ctx[rule["el"]] = (fx, fy, fw, fd)


# ── Baker Principle Overlays ──────────────────────────────────────────────────

def _draw_baker_overlays(ax, fp, wall_segments):
    """Render Baker principle visual indicators on the floor plan."""
    _draw_filler_slab_hatching(ax, fp)
    _draw_rattrap_texture(ax, fp, wall_segments)
    _draw_jali_indicators(ax, fp)


def _draw_filler_slab_hatching(ax, fp):
    """Faint diagonal cross-hatch over building footprint → filler slab roof."""
    valid = [r for r in fp.rooms if r.room_type not in ("lightwell",)]
    if not valid:
        return
    min_x = min(r.x for r in valid)
    max_x = max(r.x2 for r in valid)
    min_y = min(r.y for r in valid)
    max_y = max(r.y2 for r in valid)
    # Fix 1: Reduce filler slab hatch to near-invisible (pure white background)
    ax.add_patch(Rectangle((min_x, min_y), max_x - min_x, max_y - min_y,
                            facecolor="none", edgecolor="#CCCCCC",
                            hatch='xx', linewidth=0, zorder=3.5, alpha=0.03))


def _draw_rattrap_texture(ax, fp, wall_segments):
    """Brick-bond hatching on SW-corner exterior wall to indicate rat-trap bond."""
    # Identify the SW corner of the building based on facing
    _FACING_SW = {
        "North": ("S", "W"), "South": ("N", "E"),
        "East": ("S", "E"), "West": ("N", "W"),
        "North-East": ("S", "W"), "North-West": ("S", "E"),
        "South-East": ("N", "W"), "South-West": ("N", "E"),
    }
    sw_sides = _FACING_SW.get(fp.facing, ("S", "W"))

    # Find exterior wall segments on those sides
    pw, ph = fp.plot_width, fp.plot_height
    tol = 0.5
    for seg in wall_segments:
        if not seg.is_exterior:
            continue
        on_sw = False
        if seg.is_horizontal:
            if "S" in sw_sides and seg.y1 < tol:
                on_sw = True
            elif "N" in sw_sides and seg.y1 > ph - tol:
                on_sw = True
        else:
            if "W" in sw_sides and seg.x1 < tol:
                on_sw = True
            elif "E" in sw_sides and seg.x1 > pw - tol:
                on_sw = True

        if on_sw:
            t = seg.thickness
            if seg.is_horizontal:
                rx, ry = seg.x1, seg.y1 - t / 2
                rw, rh = seg.x2 - seg.x1, t
            else:
                rx, ry = seg.x1 - t / 2, seg.y1
                rw, rh = t, seg.y2 - seg.y1
            ax.add_patch(Rectangle((rx, ry), rw, rh,
                                    facecolor="none", edgecolor="#8B4513",
                                    hatch='///', linewidth=0, zorder=5.5, alpha=0.35))


def _draw_jali_indicators(ax, fp):
    """Mark jali-recommended rooms with a small lattice symbol near their windows."""
    for r in fp.rooms:
        if not getattr(r, "jali_recommended", False):
            continue
        # Draw a small jali lattice icon at the room's top-left corner
        jx = r.x + 0.15
        jy = r.y2 - 0.50
        jw, jh = 0.30, 0.30
        # Fix 1: Jali icon — white background (no cream)
        ax.add_patch(Rectangle((jx, jy), jw, jh,
                                facecolor="#FFFFFF", edgecolor="#A1887F",
                                lw=0.5, zorder=9, alpha=0.8))
        # 3x3 lattice grid
        for i in range(1, 3):
            ax.plot([jx + jw * i / 3, jx + jw * i / 3], [jy, jy + jh],
                    color="#A1887F", lw=0.4, zorder=9)
            ax.plot([jx, jx + jw], [jy + jh * i / 3, jy + jh * i / 3],
                    color="#A1887F", lw=0.4, zorder=9)
        ax.text(jx + jw / 2, jy - 0.06, "Jali", ha="center", va="top",
                fontsize=3.5, color="#795548", zorder=9)


# ── XAI Explainability Icons ─────────────────────────────────────────────────

def _draw_xai_icons(ax, rooms):
    """Draw numbered info circles in each room (>=3m2) for XAI legend mapping."""
    # Unicode circled numbers: ①②③④⑤⑥⑦⑧⑨⑩
    # ①-⑩ supported by DejaVu Sans; fallback to plain digits for 11+
    _CIRCLED = [chr(0x2460 + i) for i in range(10)]
    idx = 0
    for r in rooms:
        if r.area < 3.0 or r.room_type in ("lightwell", "courtyard"):
            continue
        ix = r.x2 - 0.25
        iy = r.y2 - 0.25
        # Clamp inside room
        ix = max(r.x + 0.15, min(ix, r.x2 - 0.15))
        iy = max(r.y + 0.15, min(iy, r.y2 - 0.15))
        ax.add_patch(plt.Circle((ix, iy), 0.18, facecolor="#E3F2FD",
                                 edgecolor="#1565C0", lw=0.6, alpha=0.55, zorder=9))
        label = _CIRCLED[idx] if idx < len(_CIRCLED) else str(idx + 1)
        ax.text(ix, iy, label, ha="center", va="center",
                fontsize=5, color="#0D47A1", fontweight="bold", zorder=9)
        idx += 1


# ── PROMPT 4 UPDATES ─────────────────────────────────────────────────────────

def _room_label(ax, r, bedroom_idx=None):
    """
    PROMPT 4 + PROMPT 6 FINAL: Professional 3-tier room label.

    Tier 1  — Room name, bold uppercase, sans-serif  (scaled, max ≈ 11 pt)
    Tier 2  — "W × H m" dimensions                  (scaled, max ≈  9 pt)
    Tier 3  — "A m²" area                           (scaled, max ≈  8 pt)

    Narrow rooms (min_dim < 1.2 m) : name only, rotated for tall corridors.
    Medium rooms (1.2 ≤ min_dim < 2.0 m) : name + dimensions only.
    Large rooms  (min_dim ≥ 2.0 m) : all three tiers.

    PROMPT 6: Bedrooms auto-numbered (BEDROOM 1/2/3); label centroid
    shifted 25% toward door side (into open floor space, away from bed).
    """
    # ── Guard ──────────────────────────────────────────────────────────────
    if r.width * r.height < 1.2:
        return
    if r.room_type in ("lightwell",):
        return

    # ── Centroid of room bounding box ──────────────────────────────────────
    cx = r.x + r.width  / 2.0
    cy = r.y  + r.height / 2.0
    min_dim = min(r.width, r.height)
    max_dim = max(r.width, r.height)

    # PROMPT 6 FINAL – STRICT 1.0m CLEARANCE + LABEL SAFETY + UNIVERSAL FIX
    # Bedroom label shift: 25% toward door side (open floor area, not over bed)
    if r.room_type == "bedroom":
        door = getattr(r, "door_side", "S")
        shift_y = r.height * 0.25   # increased from 18% → 25% for more clearance
        shift_x = r.width  * 0.25
        if door in ("S", ""):
            cy -= shift_y   # label toward south (door side, away from N-wall bed)
        elif door == "N":
            cy += shift_y   # toward north
        elif door == "E":
            cx += shift_x   # toward east
        else:               # W
            cx -= shift_x   # toward west
        # Clamp shifted centroid well inside room boundaries
        margin_x = r.width  * 0.12
        margin_y = r.height * 0.12
        cx = max(r.x  + margin_x, min(r.x2 - margin_x, cx))
        cy = max(r.y  + margin_y, min(r.y2 - margin_y, cy))

    # PROMPT 6 FINAL – STRICT 1.0m CLEARANCE + LABEL SAFETY + UNIVERSAL FIX
    # Name: clean uppercase + bedroom auto-numbering + optional line-wrap
    raw_name = r.name.replace("_", " ").strip().upper()
    # v8: bedroom auto-numbering removed — all bedrooms labeled "BEDROOM"
    if len(raw_name) > 11 and " " in raw_name:
        # Split at last space so the number stays on its own line
        pivot    = raw_name.rfind(" ")
        raw_name = raw_name[:pivot] + "\n" + raw_name[pivot + 1:]
    n_name_lines = raw_name.count("\n") + 1

    # ── Font sizes — scale with smallest room dimension, hard limits ───────
    #   min_dim  1.0 m  →  fs_name  6.0,  fs_dim  5.0,  fs_area  4.5
    #   min_dim  2.5 m  →  fs_name  9.5,  fs_dim  7.5,  fs_area  7.0
    #   min_dim  4.0 m  →  fs_name 11.0,  fs_dim  9.0,  fs_area  8.0  (capped)
    fs_name = max(6.0,  min(11.0, 4.0 + min_dim * 2.0))
    fs_dim  = max(5.0,  min( 9.0, fs_name - 2.0))
    fs_area = max(4.5,  min( 8.0, fs_name - 2.5))

    # ── Line spacing in data-space (metres) ────────────────────────────────
    #   Approximate at 1:100 on a 14" figure: 1 pt ≈ 0.013–0.022 m.
    #   Use room-size-proportional step so labels breathe in big rooms.
    line_h = max(0.13, min(0.30, min_dim * 0.10))

    TXT_KW = dict(ha="center", va="center", fontfamily="sans-serif", zorder=8)

    # ── NARROW / CORRIDOR: single name only ───────────────────────────────
    if min_dim < 1.2:
        rotate = (r.height > r.width * 1.6)   # tall corridor → vertical label
        ax.text(cx, cy, raw_name,
                fontsize=max(4.5, fs_name * 0.75), fontweight="bold",
                color="#1A1A1A", rotation=90 if rotate else 0,
                multialignment="center", linespacing=1.15, **TXT_KW)
        return

    # ── String helpers ─────────────────────────────────────────────────────
    dim_str  = "{:.1f} \u00d7 {:.1f} m".format(r.width, r.height)
    area_str = "{:.1f} m\u00b2".format(r.area)

    # Inset from room edges so text never kisses the wall line
    y_inset = max(0.10, r.height * 0.07)
    y_lo    = r.y  + y_inset
    y_hi    = r.y2 - y_inset

    # ── MEDIUM room: name + dimensions ────────────────────────────────────
    if min_dim < 2.0:
        # Two-tier stack: centre of the pair at cy
        name_y = cy + line_h * 0.55
        dim_y  = cy - line_h * 0.55
        name_y = min(y_hi, max(y_lo, name_y))
        dim_y  = min(y_hi, max(y_lo, dim_y))

        ax.text(cx, name_y, raw_name,
                fontsize=fs_name, fontweight="bold", color="#1A1A1A",
                multialignment="center", linespacing=1.15, **TXT_KW)
        ax.text(cx, dim_y, dim_str,
                fontsize=fs_dim, color="#444444", **TXT_KW)
        return

    # ── LARGE room: name + dimensions + area ──────────────────────────────
    # Total vertical block height (approximate):
    #   n_name_lines × line_h  +  1 × line_h  +  1 × line_h  =  (n+2) × line_h
    # Centre the block at cy.
    block_h = (n_name_lines + 1.8) * line_h
    name_y  = cy + block_h / 2.0 - (n_name_lines - 1) * line_h * 0.5
    dim_y   = name_y - n_name_lines * line_h - line_h * 0.25
    area_y  = dim_y  - line_h * 0.85

    # Clamp all three tiers inside the room
    name_y = min(y_hi, max(y_lo, name_y))
    dim_y  = min(y_hi, max(y_lo, dim_y))
    area_y = min(y_hi, max(y_lo, area_y))

    ax.text(cx, name_y, raw_name,
            fontsize=fs_name, fontweight="bold", color="#1A1A1A",
            multialignment="center", linespacing=1.15, **TXT_KW)
    ax.text(cx, dim_y, dim_str,
            fontsize=fs_dim, color="#444444", **TXT_KW)
    ax.text(cx, area_y, area_str,
            fontsize=fs_area, color="#777777", **TXT_KW)



# ── PROMPT 4 UPDATES ─────────────────────────────────────────────────────────

def _draw_dimensions(ax, rooms, pw, ph, margin):
    """
    PROMPT 4: Professional dimension system — two stacked rows per axis.

    Row 1 (inner)  — chain dimensions for every room-edge grid line:
                     thin dim line + 45° slash tick terminators + dotted
                     extension lines from the building face + "X.X" label.
    Row 2 (outer)  — single overall dimension for the entire building:
                     slightly heavier line + filled solid-triangle arrowheads
                     + bold "X.X m" label.

    Horizontal system drawn below the building; vertical system to the left.
    Works for any plot size because offsets are calculated from actual room
    bounding box (not the full plot), so annotations always hug the rooms.
    """
    # ── Colour / weight constants ─────────────────────────────────────────
    DC     = "#555555"     # chain dim colour
    DC_OV  = "#1A1A1A"     # overall dim colour (bolder)
    LW_DIM = 0.55          # chain line weight
    LW_OV  = 0.80          # overall line weight
    LW_EXT = 0.35          # extension line weight
    LW_TK  = 0.75          # tick line weight
    FS_CH  = 5.5           # chain label font size
    FS_OV  = 7.5           # overall label font size
    TK     = 0.090         # 45° tick half-length (metres)
    AH_L   = 0.130         # arrowhead length   (metres, for overall)
    AH_W   = 0.055         # arrowhead half-width (metres, for overall)

    # ── Offsets from building bounding-box face to dim lines ─────────────
    CH_OFF = 0.55          # chain row offset from building edge
    OV_OFF = 1.05          # overall row offset from building edge
    EXT_OVR = 0.12         # how far extension line overshoots the dim line

    # ── Room grid coordinates ─────────────────────────────────────────────
    all_x = sorted(set(round(v, 3) for r in rooms
                       for v in (r.x, r.x + r.width)))
    all_y = sorted(set(round(v, 3) for r in rooms
                       for v in (r.y, r.y + r.height)))
    if len(all_x) < 2 or len(all_y) < 2:
        return

    # PROMPT 6 FINAL – STRICT 1.0m CLEARANCE + LABEL SAFETY + UNIVERSAL FIX
    # Use actual room bounding box for chains; pass pw/ph for overall labels
    bx0, bx1 = all_x[0], all_x[-1]   # building left / right
    by0, by1 = all_y[0], all_y[-1]    # building bottom / top
    # Overall span: expand to full plot boundary to avoid "10.0m instead of 12.0m" bug
    ov_bx0 = min(bx0, 0.0)
    ov_bx1 = max(bx1, pw)
    ov_by0 = min(by0, 0.0)
    ov_by1 = max(by1, ph)

    # Row positions (below building for horizontal; left of building for vertical)
    dim_yC = by0 - CH_OFF    # horizontal chain Y
    dim_yO = by0 - OV_OFF    # horizontal overall Y
    dim_xC = bx0 - CH_OFF    # vertical chain X
    dim_xO = bx0 - OV_OFF    # vertical overall X

    TXT_KW = dict(fontfamily="sans-serif", zorder=11)

    # ── Helper: filled solid-triangle arrowhead ──────────────────────────
    def _arrow(tip_xy, from_xy):
        """Filled triangle at tip_xy, base toward from_xy."""
        tx, ty = tip_xy
        fx, fy = from_xy
        dx, dy = tx - fx, ty - fy
        length  = max(1e-9, (dx**2 + dy**2) ** 0.5)
        ux, uy  = dx / length, dy / length   # unit vector → tip
        px, py  = -uy, ux                    # perpendicular
        tri = Polygon([
            (tx,                           ty),
            (tx - AH_L * ux + AH_W * px,  ty - AH_L * uy + AH_W * py),
            (tx - AH_L * ux - AH_W * px,  ty - AH_L * uy - AH_W * py),
        ], closed=True, facecolor=DC_OV, edgecolor="none", zorder=11.5)
        ax.add_patch(tri)

    # ── Helper: 45° slash tick ───────────────────────────────────────────
    def _tick_h(x, y):
        ax.plot([x - TK, x + TK], [y - TK, y + TK],
                color=DC, lw=LW_TK, solid_capstyle="butt", zorder=11)

    def _tick_v(x, y):
        ax.plot([x - TK, x + TK], [y - TK, y + TK],
                color=DC, lw=LW_TK, solid_capstyle="butt", zorder=11)

    # ────────────────────────────────────────────────────────────────────
    # HORIZONTAL CHAIN  (runs below the building)
    # ────────────────────────────────────────────────────────────────────
    for i in range(len(all_x) - 1):
        x1, x2 = all_x[i], all_x[i + 1]
        span    = x2 - x1
        if span < 0.25:
            continue
        mid = (x1 + x2) / 2.0

        # Dimension line segment
        ax.plot([x1, x2], [dim_yC, dim_yC],
                color=DC, lw=LW_DIM, zorder=11)
        # 45° slash tick terminators
        _tick_h(x1, dim_yC)
        _tick_h(x2, dim_yC)
        # Dotted extension lines from building face down to dim line
        for tx in [x1, x2]:
            ax.plot([tx, tx], [by0, dim_yC + EXT_OVR],
                    color=DC, lw=LW_EXT, linestyle=(0, (3, 2)), zorder=10)
        # Chain label: "X.X" centred above dim line
        ax.text(mid, dim_yC - 0.15, "{:.1f}".format(span),
                ha="center", va="top", fontsize=FS_CH, color=DC, **TXT_KW)

    # HORIZONTAL OVERALL (uses full plot width ov_bx0→ov_bx1)
    ax.plot([ov_bx0, ov_bx1], [dim_yO, dim_yO],
            color=DC_OV, lw=LW_OV, zorder=11)
    # Filled arrowheads at each end
    _arrow((ov_bx0, dim_yO), (ov_bx1, dim_yO))
    _arrow((ov_bx1, dim_yO), (ov_bx0, dim_yO))
    # Extension lines for overall row
    for tx in [ov_bx0, ov_bx1]:
        ax.plot([tx, tx], [by0, dim_yO + EXT_OVR],
                color=DC_OV, lw=LW_EXT, linestyle=(0, (3, 2)), zorder=10)
    # Bold overall label — shows full plot width (not just room extent)
    ax.text((ov_bx0 + ov_bx1) / 2.0, dim_yO - 0.17,
            "{:.1f} m".format(ov_bx1 - ov_bx0),
            ha="center", va="top", fontsize=FS_OV, fontweight="bold",
            color=DC_OV, **TXT_KW)

    # ────────────────────────────────────────────────────────────────────
    # VERTICAL CHAIN  (runs to the left of the building)
    # ────────────────────────────────────────────────────────────────────
    for i in range(len(all_y) - 1):
        y1, y2 = all_y[i], all_y[i + 1]
        span    = y2 - y1
        if span < 0.25:
            continue
        mid = (y1 + y2) / 2.0

        # Dimension line segment
        ax.plot([dim_xC, dim_xC], [y1, y2],
                color=DC, lw=LW_DIM, zorder=11)
        # 45° slash tick terminators
        _tick_v(dim_xC, y1)
        _tick_v(dim_xC, y2)
        # Dotted extension lines from building face left to dim line
        for ty in [y1, y2]:
            ax.plot([bx0, dim_xC + EXT_OVR], [ty, ty],
                    color=DC, lw=LW_EXT, linestyle=(0, (3, 2)), zorder=10)
        # Chain label: "X.X" centred right of dim line (rotated 90°)
        ax.text(dim_xC - 0.16, mid, "{:.1f}".format(span),
                ha="right", va="center", fontsize=FS_CH, color=DC,
                rotation=90, **TXT_KW)

    # VERTICAL OVERALL (uses full plot height ov_by0→ov_by1)
    ax.plot([dim_xO, dim_xO], [ov_by0, ov_by1],
            color=DC_OV, lw=LW_OV, zorder=11)
    _arrow((dim_xO, ov_by0), (dim_xO, ov_by1))
    _arrow((dim_xO, ov_by1), (dim_xO, ov_by0))
    for ty in [ov_by0, ov_by1]:
        ax.plot([bx0, dim_xO + EXT_OVR], [ty, ty],
                color=DC_OV, lw=LW_EXT, linestyle=(0, (3, 2)), zorder=10)
    ax.text(dim_xO - 0.17, (ov_by0 + ov_by1) / 2.0,
            "{:.1f} m".format(ov_by1 - ov_by0),
            ha="right", va="center", fontsize=FS_OV, fontweight="bold",
            color=DC_OV, rotation=90, **TXT_KW)


def _draw_level_marker(ax, fp, wall_segments):
    """Draw a level marker (circle + cross-hairs + +/- 0.00) at the entrance door."""
    # Find the verandah/entrance exterior door
    entry_room = None
    for r in fp.rooms:
        if r.room_type in ("verandah", "entrance"):
            entry_room = r
            break
    if not entry_room:
        return

    # Find the exterior door opening on this room's exterior wall
    door_x, door_y = None, None
    for seg in wall_segments:
        if not seg.is_exterior:
            continue
        for op in seg.openings:
            if op.opening_type != "door":
                continue
            if seg.is_horizontal:
                ox = seg.x1 + op.pos_along + op.width / 2
                oy = seg.y1
                # Check if this door belongs to the entry room
                if entry_room.x - 0.5 <= ox <= entry_room.x2 + 0.5:
                    if abs(oy - entry_room.y) < 0.5 or abs(oy - entry_room.y2) < 0.5:
                        door_x, door_y = ox, oy
            else:
                ox = seg.x1
                oy = seg.y1 + op.pos_along + op.width / 2
                if entry_room.y - 0.5 <= oy <= entry_room.y2 + 0.5:
                    if abs(ox - entry_room.x) < 0.5 or abs(ox - entry_room.x2) < 0.5:
                        door_x, door_y = ox, oy

    if door_x is None:
        # Fallback: centre of entry room's front wall
        door_x = entry_room.cx
        door_y = entry_room.y2  # top of verandah

    # Draw level marker: circle + cross + text
    r = 0.25
    ax.add_patch(plt.Circle((door_x, door_y), r, fill=False,
                             edgecolor="#333333", lw=1.0, zorder=12))
    ax.plot([door_x - r * 0.6, door_x + r * 0.6], [door_y, door_y],
            color="#333333", lw=0.6, zorder=12)
    ax.plot([door_x, door_x], [door_y - r * 0.6, door_y + r * 0.6],
            color="#333333", lw=0.6, zorder=12)
    ax.text(door_x, door_y - r - 0.12, "+/- 0.00",
            ha="center", va="top", fontsize=5.5, fontweight="bold",
            color="#333333", zorder=12)
    ax.text(door_x, door_y - r - 0.32, "FFL",
            ha="center", va="top", fontsize=4.5, color="#666666",
            style="italic", zorder=12)


def _compass(ax, pw, ph, facing):
    FACING_TO_ANGLE = {"North":90,"South":270,"East":0,"West":180,
        "North-East":45,"North-West":135,"South-East":315,"South-West":225}
    cx=pw+0.9; cy=ph-1.0; r=0.55
    ax.add_patch(plt.Circle((cx,cy),r,fill=False,edgecolor="#333333",lw=1.0,zorder=15))
    for label,deg in [("N",90),("S",270),("E",0),("W",180)]:
        rad=math.radians(deg)
        ax.text(cx+(r+0.18)*math.cos(rad),cy+(r+0.18)*math.sin(rad),label,
                ha="center",va="center",fontsize=7.5,fontweight="bold",
                color="#C62828" if label=="N" else "#333333",zorder=16)
    ax.annotate("",xy=(cx,cy+r*0.85),xytext=(cx,cy),
                arrowprops=dict(arrowstyle="-|>",color="#C62828",lw=2.0))
    fa=math.radians(FACING_TO_ANGLE.get(facing,90))
    ax.annotate("",xy=(cx+r*0.6*math.cos(fa),cy+r*0.6*math.sin(fa)),xytext=(cx,cy),
                arrowprops=dict(arrowstyle="-|>",color="#1565C0",lw=1.5,linestyle="dashed"))
    ax.text(cx,cy-r-0.30,"Facing: {}".format(facing),
            ha="center",va="top",fontsize=6,color="#333333",style="italic",zorder=16)


def _scale_bar(ax, pw, ph):
    bx,by=0.2,-0.90; seg=1.0; n_segs=4
    for i in range(n_segs):
        fc="#1A1A1A" if i%2==0 else "#FFFFFF"
        ax.add_patch(Rectangle((bx+i*seg,by),seg,0.18,
                               facecolor=fc,edgecolor="#333333",lw=0.7,zorder=15))
    for i in range(n_segs+1):
        ax.text(bx+i*seg,by-0.12,"{}m".format(i),ha="center",va="top",fontsize=6,color="#333333")
    ax.text(bx+n_segs*seg/2,by-0.30,"Scale Bar (1:100)",
            ha="center",va="top",fontsize=6,color="#555555",style="italic")


def _legend(ax):
    handles = [
        mpatches.Patch(facecolor=WALL_COLOR, edgecolor="none",
                       label="Ext. Wall ({}mm)".format(int(EXT_WALL*1000))),
        mpatches.Patch(facecolor="#555555", edgecolor="none",
                       label="Int. Wall ({}mm)".format(int(INT_WALL*1000))),
        mpatches.Patch(facecolor=FLOOR_COLOR, edgecolor="#333333", lw=0.5,
                       label="Floor"),
        Line2D([0], [0], color=WIN_LINE_COL, lw=1.0, label="Window"),
        Line2D([0], [0], color=DOOR_COLOR, lw=DOOR_LEAF_LW, label="Door"),
        Line2D([0], [0], color=DOOR_COLOR, lw=DOOR_ARC_LW,
               linestyle=DOOR_ARC_STYLE, label="Door swing"),
    ]
    # Place legend OUTSIDE the plan, at bottom-right below the scale bar
    ax.legend(handles=handles, loc="upper left",
              bbox_to_anchor=(1.02, 0.55),
              fontsize=6.0, title="Legend", title_fontsize=6.5,
              framealpha=0.92, frameon=True, edgecolor="#AAAAAA",
              borderpad=0.6, labelspacing=0.4)



def _legend_margin(ax, pw, ph):
    """Compact legend drawn in data coords in the right margin — no overlap."""
    lx  = pw + 0.28
    lw  = 1.85
    ih  = 0.50
    by  = ph * 0.08

    items = [
        ("wall_ext",  WALL_COLOR,    "Ext. Wall 230mm"),
        ("wall_int",  INT_WALL_COLOR,"Int. Wall 120mm"),
        ("window",    WIN_LINE_COL,  "Window"),
        ("door",      DOOR_COLOR,    "Door"),
        ("swing",     DOOR_COLOR,    "Door swing"),
        ("archway",   WALL_COLOR,    "Open archway"),
        ("rattrap",   "#8B4513",     "Rat-trap bond"),
        ("jali",      "#A1887F",     "Jali screen"),
        ("filler",    "#999999",     "Filler slab roof"),
    ]
    box_h = len(items) * ih + 0.70
    # Fix 1: Legend background pure white (no cream/beige tones)
    ax.add_patch(Rectangle((lx - 0.08, by - 0.10), lw + 0.16, box_h,
                             facecolor="#FFFFFF", edgecolor="#BBBBBB",
                             lw=0.6, zorder=14, alpha=0.95))
    ax.text(lx + lw / 2, by + box_h - 0.22, "LEGEND",
            ha="center", va="center", fontsize=6.5, fontweight="bold",
            color="#333333", zorder=15)
    ax.plot([lx + 0.06, lx + lw - 0.06],
            [by + box_h - 0.44, by + box_h - 0.44],
            color="#CCCCCC", lw=0.5, zorder=15)

    for i, (style, color, label) in enumerate(items):
        iy  = by + box_h - 0.60 - i * ih
        sx, sx2 = lx + 0.08, lx + 0.58
        sy  = iy + ih * 0.20
        sh  = ih * 0.55

        if style == "wall_ext":
            ax.add_patch(Rectangle((sx, sy), sx2 - sx, sh,
                                    facecolor=color, edgecolor="none", zorder=15))
            ax.add_patch(Rectangle((sx, sy), sx2 - sx, sh,
                                    facecolor="none", edgecolor="#888888",
                                    linewidth=0, hatch="////", alpha=0.70, zorder=15.1))
        elif style == "wall_int":
            ax.add_patch(Rectangle((sx, sy + sh * 0.2), sx2 - sx, sh * 0.6,
                                    facecolor=color, edgecolor="none",
                                    zorder=15, alpha=0.7))
            ax.add_patch(Rectangle((sx, sy + sh * 0.2), sx2 - sx, sh * 0.6,
                                    facecolor="none", edgecolor="#AAAAAA",
                                    linewidth=0, hatch="////", alpha=0.50, zorder=15.1))
        elif style == "window":
            ax.add_patch(Rectangle((sx, sy + sh * 0.1), sx2 - sx, sh * 0.8,
                                    facecolor=FLOOR_COLOR, edgecolor="#444444",
                                    lw=0.5, zorder=15))
            for frac in [1/3, 2/3]:
                lxw = sx + (sx2 - sx) * frac
                ax.plot([lxw, lxw], [sy + sh * 0.1, sy + sh * 0.9],
                        color=color, lw=0.8, zorder=15)
        elif style == "door":
            ax.plot([sx, sx2], [sy + sh / 2, sy + sh / 2],
                    color=color, lw=2.2, zorder=15)
        elif style == "swing":
            t_a = np.linspace(0, np.pi / 2, 25)
            r_a = (sx2 - sx) * 0.92
            ax.plot(sx + r_a * np.cos(t_a),
                    (sy + sh / 2) + r_a * np.sin(t_a),
                    color=color, lw=1.0, zorder=15)
        elif style == "archway":
            pw2 = 0.06
            ax.add_patch(Rectangle((sx + pw2, sy + sh * 0.1),
                                    sx2 - sx - 2 * pw2, sh * 0.8,
                                    facecolor=FLOOR_COLOR, edgecolor="none", zorder=15))
            for pxa in [sx, sx2 - pw2]:
                ax.add_patch(Rectangle((pxa, sy), pw2, sh,
                                        facecolor=WALL_COLOR, zorder=15))
        elif style == "rattrap":
            ax.add_patch(Rectangle((sx, sy), sx2 - sx, sh,
                                    facecolor="none", edgecolor=color,
                                    hatch='///', linewidth=0, zorder=15, alpha=0.5))
        elif style == "jali":
            ax.add_patch(Rectangle((sx, sy), sx2 - sx, sh,
                                    facecolor="#FFF8E1", edgecolor=color,
                                    lw=0.4, zorder=15))
            for frac in [1/3, 2/3]:
                lxj = sx + (sx2 - sx) * frac
                ax.plot([lxj, lxj], [sy, sy + sh], color=color, lw=0.3, zorder=15)
                lyj = sy + sh * frac
                ax.plot([sx, sx2], [lyj, lyj], color=color, lw=0.3, zorder=15)
        elif style == "filler":
            ax.add_patch(Rectangle((sx, sy), sx2 - sx, sh,
                                    facecolor="none", edgecolor=color,
                                    hatch='xx', linewidth=0, zorder=15, alpha=0.15))

        ax.text(sx2 + 0.12, sy + sh / 2, label,
                ha="left", va="center", fontsize=5.5, color="#333333", zorder=15)


def _draw_title_header(fig, fp):
    """Professional top-bar title: single line + score badge (pure blueprint style)."""
    import datetime

    zone_short  = fp.climate_zone.split("(")[0].strip()
    overall     = fp.scores.get("Overall", 0)
    agent_tag   = "  \u2022  Agent-Integrated" if getattr(fp, "agent_integrated", False) else ""
    score_color = "#2E7D32" if overall >= 70 else "#F57F17" if overall >= 50 else "#C62828"
    today       = datetime.date.today().strftime("%d-%m-%Y")

    # ── Outer border frame (figure-level, using Line2D so no zorder issue) ─
    from matplotlib.lines import Line2D as _L2D
    import matplotlib.patches as _mp
    tf = fig.transFigure
    # Outer trim rectangle via patches.append (transform keeps it in fig coords)
    outer = _mp.Rectangle((0.01, 0.01), 0.98, 0.98,
                           transform=tf, fill=False,
                           edgecolor="#333333", linewidth=0.8)
    outer.set_zorder(0)
    fig.patches.append(outer)

    # ── Title bar axes (top ~6% of figure) ──────────────────────────────────
    ax_t = fig.add_axes([0.01, 0.945, 0.98, 0.048])
    ax_t.set_xlim(0, 1); ax_t.set_ylim(0, 1)
    ax_t.set_facecolor("#1A237E")          # deep navy background
    ax_t.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
    for spine in ax_t.spines.values():
        spine.set_visible(False)

    # Main title text (centred)
    main_title = (
        f"FLOOR PLAN  \u2014  {fp.bhk_type}"
        f"  \u2022  Plot: {fp.plot_width:.1f}\u00d7{fp.plot_height:.1f} m"
        f"  \u2022  {zone_short}"
        f"  \u2022  Facing: {fp.facing}"
        + agent_tag
    )
    ax_t.text(0.50, 0.55, main_title,
              ha="center", va="center", fontsize=9.5, fontweight="bold",
              color="#FFFFFF", zorder=5)

    # Date + drawing number (right side, small)
    ax_t.text(0.985, 0.20, f"DRG A-101  \u2022  {today}  \u2022  SCALE 1:100",
              ha="right", va="center", fontsize=6, color="#BBDEFB", zorder=5)

    # ── Score badge axes (small box, top-right corner of drawing area) ──────
    ax_s = fig.add_axes([0.845, 0.870, 0.145, 0.072])
    ax_s.set_xlim(0, 1); ax_s.set_ylim(0, 1)
    ax_s.set_facecolor("#F5F5F5")
    ax_s.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
    for spine in ax_s.spines.values():
        spine.set_visible(True)
        spine.set_edgecolor(score_color)
        spine.set_linewidth(1.2)

    ax_s.text(0.50, 0.82, "DESIGN SCORE",
              ha="center", va="center", fontsize=5.5, color="#555555", fontweight="bold")
    ax_s.text(0.50, 0.46, f"{overall:.0f}",
              ha="center", va="center", fontsize=18, color=score_color, fontweight="bold")
    ax_s.text(0.50, 0.12, "/ 100",
              ha="center", va="center", fontsize=6, color="#888888")

    # Thin score bar at bottom of badge
    ax_s.add_patch(Rectangle((0.05, 0.02), 0.90, 0.06,
                              facecolor="#E0E0E0", edgecolor="none"))
    ax_s.add_patch(Rectangle((0.05, 0.02), 0.90 * (overall / 100), 0.06,
                              facecolor=score_color, edgecolor="none", alpha=0.8))
