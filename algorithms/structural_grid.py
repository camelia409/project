"""
structural_grid.py — Structural bay grid that controls floor-plan geometry
==========================================================================
Purpose
-------
In proper architectural practice, all walls align to a structural grid
(column-beam grid). Room boundaries are always at grid lines; rooms occupy
one or more full bays, or one or more half-bays.

This module:
  1. Derives a uniform bay grid from usable building dimensions, targeting
     3.0 m – 4.0 m bay spacing (standard RCC frame spacing in Indian housing).
  2. Snaps room col-widths and row-heights so that every wall falls on a
     grid line (or a defined half-bay subdivision).
  3. Returns the final col-line and row-line positions used by the renderer
     to place column squares ONLY at true structural intersections.

Sources
-------
  - NBC 2016 Part 6 Section 4 §5.3 — RCC frame column spacing 3.0–6.0 m
  - IS 456 : 2000 — Effective span for beams / slabs; 4.0 m preferred
  - HUDCO Type Design series — 3.0 m × 3.0 m module for low-cost housing
  - Neufert Architects' Data 4e — 3.0 / 3.6 / 4.0 m grid modules

API
---
  from algorithms.structural_grid import StructuralGrid, build_grid, snap_dims_to_grid

  grid = build_grid(usable_w=9.0, usable_h=8.5,
                    origin_x=1.5, origin_y=2.5,
                    n_col_bays=3, n_row_bays=3)

  snapped_col, snapped_row = snap_dims_to_grid(col_widths, row_heights, grid)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple

__all__ = [
    "StructuralGrid",
    "build_grid",
    "snap_dims_to_grid",
    "choose_bay_counts",
]

# ── Target bay-spacing band (metres) — RCC frame standard ───────────────────
_BAY_MIN = 3.00   # NBC 2016 Part 6 §5.3 lower limit
_BAY_MAX = 4.50   # upper limit (4.0 preferred; 4.5 allowed for living spans)
_BAY_PREFERRED = 3.00   # HUDCO low-cost module


@dataclass
class StructuralGrid:
    """
    Describes a regular rectangular structural bay grid.

    Attributes
    ----------
    col_lines : sorted x-positions of ALL column lines, including both boundary edges
    row_lines : sorted y-positions of ALL column lines, including both boundary edges
    bay_w     : column bay width (may differ slightly from usable_w/n_col_bays
                due to rounding to half-bay)
    bay_h     : row bay height
    half_w    : half of bay_w (half-bay module for walls)
    half_h    : half of bay_h
    n_col_bays: number of column bays (= len(col_lines) - 1)
    n_row_bays: number of row bays    (= len(row_lines) - 1)
    """

    col_lines:  List[float]
    row_lines:  List[float]
    bay_w:      float
    bay_h:      float
    half_w:     float
    half_h:     float
    n_col_bays: int
    n_row_bays: int

    # ── convenience ─────────────────────────────────────────────────────────

    @property
    def origin_x(self) -> float:
        return self.col_lines[0]

    @property
    def origin_y(self) -> float:
        return self.row_lines[0]

    @property
    def total_w(self) -> float:
        return self.col_lines[-1] - self.col_lines[0]

    @property
    def total_h(self) -> float:
        return self.row_lines[-1] - self.row_lines[0]

    def nearest_col_line(self, x: float) -> float:
        """Snap x to the nearest column-grid line."""
        return min(self.col_lines, key=lambda gx: abs(gx - x))

    def nearest_row_line(self, y: float) -> float:
        """Snap y to the nearest row-grid line."""
        return min(self.row_lines, key=lambda gy: abs(gy - y))

    def snap_x(self, x: float) -> float:
        return round(self.nearest_col_line(x), 4)

    def snap_y(self, y: float) -> float:
        return round(self.nearest_row_line(y), 4)


# ── Grid builder ─────────────────────────────────────────────────────────────

def build_grid(
    usable_w: float,
    usable_h: float,
    origin_x: float,
    origin_y: float,
    n_col_bays: int,
    n_row_bays: int,
) -> StructuralGrid:
    """
    Build a StructuralGrid from usable building dimensions.

    Parameters
    ----------
    usable_w    : total usable width (after setbacks)
    usable_h    : total usable height (after setbacks + verandah)
    origin_x    : x-coordinate of the first (left) column line
    origin_y    : y-coordinate of the first (bottom) column line
    n_col_bays  : number of column bays (= number of col grid intervals)
    n_row_bays  : number of row bays

    Returns
    -------
    StructuralGrid with grid lines placed uniformly at bay_w / bay_h intervals.
    Column lines include the TWO boundary edges plus all interior lines.
    """
    bay_w = round(usable_w / n_col_bays, 4)
    bay_h = round(usable_h / n_row_bays, 4)

    col_lines = [round(origin_x + i * bay_w, 4) for i in range(n_col_bays + 1)]
    row_lines = [round(origin_y + j * bay_h, 4) for j in range(n_row_bays + 1)]

    # Ensure last lines hit exact boundary (float-accumulation guard)
    col_lines[-1] = round(origin_x + usable_w, 4)
    row_lines[-1] = round(origin_y + usable_h, 4)

    return StructuralGrid(
        col_lines=col_lines,
        row_lines=row_lines,
        bay_w=bay_w,
        bay_h=bay_h,
        half_w=round(bay_w / 2, 4),
        half_h=round(bay_h / 2, 4),
        n_col_bays=n_col_bays,
        n_row_bays=n_row_bays,
    )


# ── Bay-count selector ────────────────────────────────────────────────────────

def choose_bay_counts(
    usable_w: float,
    usable_h: float,
    n_template_cols: int,
    n_template_rows: int,
) -> Tuple[int, int]:
    """
    Choose n_col_bays and n_row_bays so that bay spacing lands in [3.0, 4.5] m.

    The template already tells us how many column / row divisions the BHK layout
    needs (e.g. 3BHK → 3 col, 4 row).  We keep those counts if they give bays in
    range.  Otherwise we find the nearest integer that does.

    Returns
    -------
    (n_col_bays, n_row_bays)
    """
    def _best_n(span: float, n_hint: int) -> int:
        # Start from hint and search ±2 for a count that gives bay in target band
        for delta in (0, 1, -1, 2, -2, 3):
            n = n_hint + delta
            if n < 1:
                continue
            bay = span / n
            if _BAY_MIN <= bay <= _BAY_MAX:
                return n
        # Fallback: use the hint even if outside band
        return max(1, n_hint)

    return _best_n(usable_w, n_template_cols), _best_n(usable_h, n_template_rows)


# ── Snap room widths/heights to grid ─────────────────────────────────────────

def snap_dims_to_grid(
    col_widths: List[float],
    row_heights: List[float],
    grid: StructuralGrid,
) -> Tuple[List[float], List[float]]:
    """
    Round each col-width and row-height to the nearest HALF-BAY increment,
    then renormalise so the sums equal the grid's total_w / total_h.

    This ensures every wall falls on a column-grid line or its half-bay
    subdivision — the fundamental requirement for structural-grid architecture.

    Strategy
    --------
    1. Each raw width is rounded to nearest multiple of half_w (= bay_w/2).
       Example: bay_w=3.0, half_w=1.5 — widths snap to 1.5, 3.0, 4.5, 6.0 …
    2. The snapped widths are then scaled proportionally so they sum exactly to
       total_w (ensures no gap between building edge and last room).
    3. Absolute column-line positions are then recomputed from the snapped widths
       and the grid's col_lines are updated accordingly.

    Parameters
    ----------
    col_widths  : raw column widths from engine (based on template ratios)
    row_heights : raw row heights from engine
    grid        : StructuralGrid (in-place col_lines / row_lines are rebuilt)

    Returns
    -------
    (snapped_col_widths, snapped_row_heights)  — same length as inputs
    """
    def _snap(dims: List[float], module: float) -> List[float]:
        snapped = [max(module, round(d / module) * module) for d in dims]
        # Renormalise to original total
        total_orig = sum(dims)
        total_snap = sum(snapped)
        if abs(total_snap) < 1e-6:
            return dims
        scale = total_orig / total_snap
        out = [round(s * scale, 4) for s in snapped]
        # Fix last to exact remainder
        out[-1] = round(total_orig - sum(out[:-1]), 4)
        return out

    snapped_col = _snap(col_widths, grid.half_w)
    snapped_row = _snap(row_heights, grid.half_h)

    # Rebuild col_lines and row_lines from snapped dims
    ox, oy = grid.origin_x, grid.origin_y
    grid.col_lines = [round(ox + sum(snapped_col[:i]), 4)
                      for i in range(len(snapped_col) + 1)]
    grid.row_lines = [round(oy + sum(snapped_row[:j]), 4)
                      for j in range(len(snapped_row) + 1)]
    grid.bay_w = snapped_col[0]           # representative bay (first)
    grid.bay_h = snapped_row[0]
    grid.half_w = round(grid.bay_w / 2, 4)
    grid.half_h = round(grid.bay_h / 2, 4)

    return snapped_col, snapped_row


# ── Intersection set (for renderer) ─────────────────────────────────────────

def column_positions(grid: StructuralGrid) -> List[Tuple[float, float]]:
    """
    Return all (x, y) positions where structural columns should be placed.
    These are the intersections of every col_line with every row_line.
    """
    return [
        (x, y)
        for x in grid.col_lines
        for y in grid.row_lines
    ]


# ── Post-rotation grid transform ─────────────────────────────────────────────

def rotate_grid(
    grid: StructuralGrid,
    facing: str,
    plot_width: float,
    plot_height: float,
) -> "StructuralGrid":
    """
    Transform a StructuralGrid built in canonical (South-entry) coordinates
    to match the rotated room coordinates for a given facing direction.

    The same rotation that _rotate_rooms() applies to room centroids is
    applied here to every grid line intersection, then the resulting
    col_lines / row_lines are extracted.

    Parameters
    ----------
    grid        : StructuralGrid in canonical (pre-rotation) coordinates
    facing      : "North" | "South" | "East" | "West"
    plot_width  : original (pre-rotation) plot width
    plot_height : original (pre-rotation) plot height

    Returns
    -------
    A new StructuralGrid whose col_lines and row_lines are in the rotated
    coordinate space, ready for use by the renderer.
    """
    FACING_ROTATION = {
        "South": 0, "North": 180, "East": 90, "West": 270,
    }
    angle = FACING_ROTATION.get(facing, 0)
    pw, ph = plot_width, plot_height

    # Collect all intersection points and rotate them
    pts = [(x, y) for x in grid.col_lines for y in grid.row_lines]

    if angle == 0:
        new_pts = pts
        new_pw, new_ph = pw, ph
    elif angle == 180:
        new_pts = [(round(pw - x, 4), round(ph - y, 4)) for x, y in pts]
        new_pw, new_ph = pw, ph
    elif angle == 90:   # CCW: (cx,cy) → (cy, pw-cx)
        new_pts = [(round(y, 4), round(pw - x, 4)) for x, y in pts]
        new_pw, new_ph = ph, pw
    elif angle == 270:  # CW: (cx,cy) → (ph-cy, cx)
        new_pts = [(round(ph - y, 4), round(x, 4)) for x, y in pts]
        new_pw, new_ph = ph, pw
    else:
        new_pts = pts
        new_pw, new_ph = pw, ph

    # Extract unique, sorted col and row lines from rotated points
    def _uniq(vals):
        sv = sorted(set(round(v, 4) for v in vals))
        # Merge near-duplicates (within 0.05m float tolerance)
        out = [sv[0]]
        for v in sv[1:]:
            if v - out[-1] > 0.05:
                out.append(v)
        return out

    new_col_lines = _uniq(x for x, y in new_pts)
    new_row_lines = _uniq(y for x, y in new_pts)

    # Compute new bay sizes
    new_bay_w = (new_col_lines[-1] - new_col_lines[0]) / max(len(new_col_lines) - 1, 1)
    new_bay_h = (new_row_lines[-1] - new_row_lines[0]) / max(len(new_row_lines) - 1, 1)

    return StructuralGrid(
        col_lines=new_col_lines,
        row_lines=new_row_lines,
        bay_w=round(new_bay_w, 4),
        bay_h=round(new_bay_h, 4),
        half_w=round(new_bay_w / 2, 4),
        half_h=round(new_bay_h / 2, 4),
        n_col_bays=len(new_col_lines) - 1,
        n_row_bays=len(new_row_lines) - 1,
    )
