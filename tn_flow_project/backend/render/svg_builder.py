"""
TN-Flow Floor Plan SVG Exporter — svg_builder.py
=================================================
Converts the mathematical Shapely polygons produced by the geometry engine
into a professional, CAD-style black-and-white 2D vector floor plan.

Visual Standards
────────────────
Output strictly follows standard architectural B&W line-drawing conventions:
  - No colours.  All elements are black-on-white.
  - External (load-bearing) walls: solid thick lines (stroke-width 4).
  - Internal (partition) walls:    thin lines    (stroke-width 1.5).
  - Build zone setback boundary:   dashed line   (stroke-width 1, dash 6,4).
  - Plot outer boundary:           medium solid  (stroke-width 2).
  - Room clear areas:              white fill, no independent stroke.
  - Room labels:                   three-line text (Name / Dimensions / Area).
  - North arrow:                   filled triangle + "N" label (top-right).
  - Scale bar:                     alternating filled/unfilled segments (bottom).
  - Title block:                   right-aligned metadata text.

Coordinate Transform
────────────────────
The geometry engine uses a right-handed Cartesian system:
    Origin (0, 0) = South-West corner of the plot
    +X = East
    +Y = North

SVG uses a left-handed screen system:
    Origin (0, 0) = top-left corner of canvas
    +X = East  (same as model)
    +Y = downward (OPPOSITE to model North)

Transform applied by _m2s():
    svg_x = offset_x + model_x  × scale
    svg_y = offset_y + draw_h − model_y × scale   ← Y axis flip

Where:
    scale    = min(avail_W / plot_width, avail_H / plot_depth)   [px/m]
    offset_x = MARGIN + (avail_W − draw_W) / 2   ← horizontal centering
    offset_y = MARGIN + (avail_H − draw_H) / 2   ← vertical centering
    draw_W   = plot_width  × scale
    draw_H   = plot_depth  × scale

Primary public API:
    exporter = FloorPlanSVGExporter(floor_plan, build_zone, allocated_rooms,
                                    plot_width, plot_depth,
                                    bhk_type="2BHK", plot_facing="North")
    svg_string = exporter.export()
"""

from __future__ import annotations

import math
from typing import Dict, Optional

import svgwrite
from shapely.geometry import Polygon

from backend.engine.geometry import (
    get_wall_schedule,
    EXT_WALL_T,
    INT_WALL_HALF,
    NBC_CARPET_MINIMUMS,
)


# ── Canvas & Style Constants ──────────────────────────────────────────────────

CANVAS_W: int = 700
"""Total SVG canvas width in pixels."""

CANVAS_H: int = 940
"""Total SVG canvas height in pixels (taller to accommodate title block)."""

MARGIN: int = 50
"""Minimum white margin on each side of the drawing (pixels)."""

TITLE_BLOCK_H: int = 60
"""Height reserved at the bottom of the canvas for the title block."""

# Derived: available drawing area
_AVAIL_W: int = CANVAS_W - 2 * MARGIN
_AVAIL_H: int = CANVAS_H - 2 * MARGIN - TITLE_BLOCK_H

# ── SVG Style Values ──────────────────────────────────────────────────────────

STROKE_EXT_W:    str = "4"     # External wall stroke width (px)
STROKE_INT_W:    str = "1.5"   # Internal wall stroke width (px)
STROKE_PLOT_W:   str = "2"     # Plot outer boundary
STROKE_SETBACK_W:str = "0.8"   # Build zone dashed boundary
STROKE_COLOR:    str = "#000000"
FILL_ROOM:       str = "#ffffff"
FILL_PLOT_BG:    str = "#f0f0f0"  # Light gray — setback zone filler
FILL_NORTH:      str = "#000000"
DASH_SETBACK:    str = "6,4"      # Dash pattern for setback line

FONT_FAMILY:     str = "Arial, Helvetica, sans-serif"
FONT_ROOM_NAME:  int = 9          # Room name font size (px)
FONT_DIMS:       int = 8          # Dimensions text
FONT_AREA:       int = 8          # Area text
FONT_TITLE:      int = 11         # Title block
FONT_SUBTITLE:   int = 9

# Leading between label lines (px)
LINE_H: int = 11


# ── Helper: human-readable room label ─────────────────────────────────────────

def _format_label(room_name: str, width_m: float, depth_m: float,
                  carpet_area: float) -> tuple[str, str, str]:
    """
    Return three label lines for a room:
      Line 1 — room name (e.g. "MasterBedroom")
      Line 2 — dimensions (e.g. "2.71 x 3.22 m")
      Line 3 — area       (e.g. "8.73 sqm")
    """
    # Shorten long room names to fit small cells
    display_name = {
        "MasterBedroom": "Master Bed",
        "Bedroom2":      "Bedroom 2",
        "Bedroom3":      "Bedroom 3",
        "StoreRoom":     "Store",
        "Entrance":      "Foyer",
        "Staircase":     "Stairs",
    }.get(room_name, room_name)

    dims = f"{width_m:.2f} x {depth_m:.2f} m"
    area = f"{carpet_area:.2f} sqm"
    return display_name, dims, area


# ── Main Exporter Class ───────────────────────────────────────────────────────

class FloorPlanSVGExporter:
    """
    CAD-style B&W floor plan SVG exporter.

    Attributes:
        floor_plan    : FloorPlanMap — { room_name: {clear_polygon, carpet_area_sqm, dimensions} }
        build_zone    : BuildZone   — dataclass with envelope_polygon, plot_polygon, setbacks, etc.
        allocated     : AllocatedRoomMap — { room_name: base_Polygon }
        plot_width    : float — East-West plot dimension (metres)
        plot_depth    : float — North-South plot dimension (metres)
        bhk_type      : str   — e.g. "2BHK" — shown in title block
        plot_facing   : str   — e.g. "North" — used to orient North arrow label
        dropped_rooms : list[str] — rooms omitted by fallback; noted in title block

    Usage::

        exporter = FloorPlanSVGExporter(
            floor_plan, build_zone, allocated_rooms,
            plot_width=12.0, plot_depth=22.0,
            bhk_type="2BHK", plot_facing="North",
        )
        svg_str = exporter.export()
    """

    def __init__(
        self,
        floor_plan:    dict,
        build_zone,                       # BuildZone dataclass (avoids circular import)
        allocated:     dict,
        plot_width:    float,
        plot_depth:    float,
        bhk_type:      str   = "",
        plot_facing:   str   = "North",
        dropped_rooms: list[str] | None = None,
    ):
        self.floor_plan    = floor_plan
        self.build_zone    = build_zone
        self.allocated     = allocated
        self.plot_width    = plot_width
        self.plot_depth    = plot_depth
        self.bhk_type      = bhk_type
        self.plot_facing   = plot_facing
        self.dropped_rooms = dropped_rooms or []

        # ── Compute scale and offsets ─────────────────────────────────────
        scale_x = _AVAIL_W / plot_width
        scale_y = _AVAIL_H / plot_depth
        self.scale: float = min(scale_x, scale_y)

        self.draw_w: float = plot_width  * self.scale
        self.draw_h: float = plot_depth  * self.scale

        # Center the drawing within the available area
        self.offset_x: float = MARGIN + (_AVAIL_W - self.draw_w) / 2
        self.offset_y: float = MARGIN + (_AVAIL_H - self.draw_h) / 2

        # Pre-compute wall schedule (needed for stroke widths)
        env = build_zone.envelope_polygon
        self._wall_schedule: list[dict] = get_wall_schedule(allocated, env)

    # ── Coordinate Transform ──────────────────────────────────────────────────

    def _m2s(self, mx: float, my: float) -> tuple[float, float]:
        """
        Model → SVG coordinate transform.

        Mathematical derivation:
            svg_x = offset_x + mx * scale
            svg_y = offset_y + draw_h − my * scale   (Y-axis flip: North = top)

        Args:
            mx, my: Model coordinates in metres (origin = SW plot corner).

        Returns:
            (svg_x, svg_y): SVG pixel coordinates.
        """
        svg_x = self.offset_x + mx * self.scale
        svg_y = self.offset_y + self.draw_h - my * self.scale
        return round(svg_x, 2), round(svg_y, 2)

    def _rect_pts(self, minx: float, miny: float, maxx: float, maxy: float) -> dict:
        """Convert model bounding box to svgwrite rect insert/size args."""
        sx, sy = self._m2s(minx, maxy)  # SVG top-left = model top-left (y flipped)
        sw = (maxx - minx) * self.scale
        sh = (maxy - miny) * self.scale
        return {"insert": (sx, sy), "size": (round(sw, 2), round(sh, 2))}

    # ── Drawing Layers ────────────────────────────────────────────────────────

    def _draw_backgrounds(self, dwg: svgwrite.Drawing) -> None:
        """
        Layer 0 — Plot background + white room fills.

        Draw a light-gray plot boundary rectangle (representing the setback /
        non-buildable zone), then white rectangles for each allocated room base
        polygon to "punch out" the grey background and reveal white room areas.
        """
        # Full plot — light gray background (setback zone colour)
        px1, py1 = self._m2s(0, 0)
        px2, py2 = self._m2s(self.plot_width, self.plot_depth)
        dwg.add(dwg.rect(
            insert=(min(px1, px2), min(py1, py2)),
            size=(abs(px2 - px1), abs(py2 - py1)),
            fill=FILL_PLOT_BG,
            stroke=STROKE_COLOR,
            stroke_width=STROKE_PLOT_W,
        ))

        # Build zone — white fill (removes the gray from the buildable area)
        env = self.build_zone.envelope_polygon
        bpts = self._rect_pts(*env.bounds)
        dwg.add(dwg.rect(fill=FILL_ROOM, stroke="none", **bpts))

        # Each room base polygon — white fill
        for poly in self.allocated.values():
            rpts = self._rect_pts(*poly.bounds)
            dwg.add(dwg.rect(fill=FILL_ROOM, stroke="none", **rpts))

    def _draw_setback_boundary(self, dwg: svgwrite.Drawing) -> None:
        """
        Layer 1 — Dashed build-zone boundary (setback limit line).

        The build zone envelope is drawn as a dashed rectangle to indicate the
        legal build-to-line mandated by TNCDBR 2019 setbacks.
        """
        env = self.build_zone.envelope_polygon
        bpts = self._rect_pts(*env.bounds)
        dwg.add(dwg.rect(
            fill="none",
            stroke=STROKE_COLOR,
            stroke_width=STROKE_SETBACK_W,
            stroke_dasharray=DASH_SETBACK,
            **bpts,
        ))

        # Setback label — small text above the front edge
        env_minx, _, env_maxx, env_maxy = env.bounds
        sx = self.offset_x + ((env_minx + env_maxx) / 2) * self.scale
        sy_t, _ = self._m2s(0, env_maxy)     # top of envelope in SVG
        sy_b, _ = self._m2s(0, self.build_zone.setback_front_m / 2)
        # Label the front setback value
        sb = self.build_zone.setback_front_m
        dwg.add(dwg.text(
            f"Front setback {sb:.1f}m",
            insert=(sx, sy_t - 4),
            text_anchor="middle",
            font_family=FONT_FAMILY,
            font_size=f"{FONT_SUBTITLE - 1}px",
            fill=STROKE_COLOR,
        ))

    def _draw_walls(self, dwg: svgwrite.Drawing) -> None:
        """
        Layer 2 — Wall lines with CAD-standard stroke widths.

        For every room, draws four edge-line segments.  Each edge is checked
        against the wall schedule:
            External wall (abuts build envelope) → stroke-width = 4
            Internal wall (shared partition)     → stroke-width = 1.5

        Wall schedule maps: room × face → (wall_type, thickness_m, length_m).

        Shapely-derived room base polygon bounds are used for line endpoint
        calculation; the Y-axis flip (_m2s) ensures North appears at the top.

        CAD convention:
            External walls are drawn as thick solid lines (representing 230mm
            load-bearing brick — IS 2212).
            Internal partition walls are drawn as thin solid lines (representing
            115mm half-brick — IS 1905).
        """
        # Build a lookup: (room, face) → wall_type
        sched_lookup: dict[tuple[str, str], str] = {}
        for entry in self._wall_schedule:
            sched_lookup[(entry["room"], entry["face"])] = entry["wall_type"]

        for room_name, base_poly in self.allocated.items():
            minx, miny, maxx, maxy = base_poly.bounds

            # Four edges: (face_label, model_pt1, model_pt2)
            edges = [
                ("Left",   (minx, miny), (minx, maxy)),
                ("Right",  (maxx, miny), (maxx, maxy)),
                ("Bottom", (minx, miny), (maxx, miny)),
                ("Top",    (minx, maxy), (maxx, maxy)),
            ]

            for face_label, p1, p2 in edges:
                wtype = sched_lookup.get((room_name, face_label), "Internal")
                sw    = STROKE_EXT_W if wtype == "External" else STROKE_INT_W

                sx1, sy1 = self._m2s(*p1)
                sx2, sy2 = self._m2s(*p2)

                dwg.add(dwg.line(
                    start=(sx1, sy1),
                    end=(sx2, sy2),
                    stroke=STROKE_COLOR,
                    stroke_width=sw,
                    stroke_linecap="square",
                ))

    def _draw_room_labels(self, dwg: svgwrite.Drawing) -> None:
        """
        Layer 3 — Room name, dimensions, and carpet area text labels.

        Each room's clear_polygon centroid is used as the text anchor.
        Three `<tspan>` elements provide:
            Line 1 — Room name (bold, slightly larger)
            Line 2 — Clear dimensions (e.g. "2.71 x 3.22 m")
            Line 3 — Carpet area    (e.g. "8.73 sqm")

        Text is omitted when the clear polygon is too small to accommodate
        a legible label (width < 35px or height < 30px after scaling).

        The centroid computation uses Shapely's polygon.centroid property
        which returns the geometric centre of mass of the polygon.
        """
        for room_name, data in self.floor_plan.items():
            clear_poly: Polygon = data["clear_polygon"]
            w_m, d_m            = data["dimensions"]
            carpet              = data["carpet_area_sqm"]

            # Compute centroid in model coords
            cx_m = clear_poly.centroid.x
            cy_m = clear_poly.centroid.y

            # Check minimum displayable size
            cell_px_w = w_m * self.scale
            cell_px_h = d_m * self.scale
            if cell_px_w < 30 or cell_px_h < 22:
                # Too small for 3-line label; show only abbreviated name
                sx, sy = self._m2s(cx_m, cy_m)
                short = room_name[:3] + "."
                dwg.add(dwg.text(
                    short,
                    insert=(sx, sy),
                    text_anchor="middle",
                    dominant_baseline="middle",
                    font_family=FONT_FAMILY,
                    font_size="7px",
                    fill=STROKE_COLOR,
                ))
                continue

            line1, line2, line3 = _format_label(room_name, w_m, d_m, carpet)

            sx, sy = self._m2s(cx_m, cy_m)

            # Y offsets for the three lines, vertically centred around sy
            y0 = sy - LINE_H         # name line (top)
            y1 = sy                  # dimensions line
            y2 = sy + LINE_H         # area line

            # Scale font down for small rooms
            fs_name = max(6, min(FONT_ROOM_NAME, int(cell_px_h / 3.8)))
            fs_dim  = max(6, min(FONT_DIMS,       int(cell_px_h / 4.5)))

            t = dwg.text("", insert=(sx, y0))
            t.add(dwg.tspan(
                line1,
                x=[sx], y=[y0],
                text_anchor="middle",
                font_family=FONT_FAMILY,
                font_size=f"{fs_name}px",
                font_weight="bold",
            ))
            t.add(dwg.tspan(
                line2,
                x=[sx], dy=[str(LINE_H)],
                text_anchor="middle",
                font_family=FONT_FAMILY,
                font_size=f"{fs_dim}px",
            ))
            t.add(dwg.tspan(
                line3,
                x=[sx], dy=[str(LINE_H - 1)],
                text_anchor="middle",
                font_family=FONT_FAMILY,
                font_size=f"{fs_dim}px",
            ))
            dwg.add(t)

    def _draw_north_arrow(self, dwg: svgwrite.Drawing) -> None:
        """
        Layer 4 — North indicator arrow (top-right of canvas).

        Draws a filled equilateral triangle pointing upward (toward the North
        of the floor plan) and an "N" label centred above the base of the
        triangle.

        Position: top-right margin, 30px from canvas edges.
        Geometry:
            apex  = (ax, ay)
            left  = (ax - 10, ay + 24)
            right = (ax + 10, ay + 24)
        """
        ax = CANVAS_W - 40
        ay = MARGIN + 18

        apex  = (ax,       ay)
        left  = (ax - 10,  ay + 24)
        right = (ax + 10,  ay + 24)

        # Filled black triangle
        dwg.add(dwg.polygon(
            points=[apex, left, right],
            fill=FILL_NORTH,
            stroke="none",
        ))

        # "N" label above apex
        dwg.add(dwg.text(
            "N",
            insert=(ax, ay - 5),
            text_anchor="middle",
            font_family=FONT_FAMILY,
            font_size="14px",
            font_weight="bold",
            fill=STROKE_COLOR,
        ))

        # Compass circle outline
        dwg.add(dwg.circle(
            center=(ax, ay + 12),
            r=16,
            fill="none",
            stroke=STROKE_COLOR,
            stroke_width="0.8",
        ))

    def _draw_scale_bar(self, dwg: svgwrite.Drawing) -> None:
        """
        Layer 5 — Metric scale bar (bottom-left of drawing area).

        Draws a two-segment alternating bar (filled + unfilled) representing
        a fixed model distance, and labels both ends plus the midpoint.

        Bar length is chosen as the nearest round metre value whose SVG
        representation is between 40 and 120 pixels:
            segment_model_m = 1m if scale >= 40 px/m
                            = 2m if 20 <= scale < 40 px/m
                            = 5m if scale < 20 px/m

        Bar is positioned at the bottom of the drawing, 10px below the
        lower edge of the plot rectangle.
        """
        if self.scale >= 40:
            seg_m = 1.0
        elif self.scale >= 20:
            seg_m = 2.0
        else:
            seg_m = 5.0

        seg_px = seg_m * self.scale  # pixels per segment

        # Anchor at bottom-left of drawing area
        bx = self.offset_x
        by = self.offset_y + self.draw_h + 18   # 18px below the plot
        bar_h = 6   # bar height in pixels

        # Segment 1 — filled black
        dwg.add(dwg.rect(
            insert=(bx, by),
            size=(seg_px, bar_h),
            fill=STROKE_COLOR,
            stroke=STROKE_COLOR,
            stroke_width="0.5",
        ))
        # Segment 2 — white with border
        dwg.add(dwg.rect(
            insert=(bx + seg_px, by),
            size=(seg_px, bar_h),
            fill=FILL_ROOM,
            stroke=STROKE_COLOR,
            stroke_width="0.5",
        ))

        # Tick marks
        for tick_x, label in [
            (bx,             "0"),
            (bx + seg_px,    f"{seg_m:.0f}m"),
            (bx + 2 * seg_px, f"{2 * seg_m:.0f}m"),
        ]:
            dwg.add(dwg.line(
                start=(tick_x, by - 3), end=(tick_x, by + bar_h + 3),
                stroke=STROKE_COLOR, stroke_width="0.5",
            ))
            dwg.add(dwg.text(
                label,
                insert=(tick_x, by + bar_h + 12),
                text_anchor="middle",
                font_family=FONT_FAMILY,
                font_size="8px",
                fill=STROKE_COLOR,
            ))

        # "Scale 1:XXX" legend
        approx_scale = round(100 / self.scale * 100 / 10) * 10
        dwg.add(dwg.text(
            f"Scale approx. 1:{max(50, approx_scale):.0f}",
            insert=(bx + seg_px, by + bar_h + 24),
            text_anchor="middle",
            font_family=FONT_FAMILY,
            font_size="8px",
            fill=STROKE_COLOR,
        ))

    def _draw_title_block(self, dwg: svgwrite.Drawing) -> None:
        """
        Layer 6 — Title block (bottom of canvas).

        A horizontal band showing project metadata and regulatory annotation:
            Line 1 — TN-FLOW LAYOUT ENGINE (bold header)
            Line 2 — Plot dimensions | BHK type | Facing | Authority
            Line 3 — TNCDBR 2019 Compliant | Carpet total | Dropped rooms

        The title band sits below the drawing area in the TITLE_BLOCK_H zone
        reserved at the canvas bottom.
        """
        ty_base = CANVAS_H - TITLE_BLOCK_H + 14

        # Separator line
        dwg.add(dwg.line(
            start=(MARGIN, ty_base - 10),
            end=(CANVAS_W - MARGIN, ty_base - 10),
            stroke=STROKE_COLOR,
            stroke_width="0.8",
        ))

        bz  = self.build_zone
        env = bz.envelope_polygon
        total_carpet = sum(
            d["carpet_area_sqm"] for d in self.floor_plan.values()
        )
        authority = getattr(bz, "authority", "")

        lines = [
            ("TN-FLOW LAYOUT ENGINE", True),
            (
                f"Plot {self.plot_width:.0f}m \u00d7 {self.plot_depth:.0f}m  "
                f"\u2502  {self.bhk_type}  "
                f"\u2502  {self.plot_facing}-facing  "
                f"\u2502  FSI {bz.fsi:.1f}  "
                f"\u2502  {int(bz.plot_area_sqm)}m\u00b2 site",
                False,
            ),
            (
                f"TNCDBR 2019 Compliant  "
                f"\u2502  Build zone {bz.envelope_area_sqm:.0f}m\u00b2  "
                f"\u2502  Carpet total {total_carpet:.1f}m\u00b2  "
                + (f"\u2502  Omitted: {', '.join(self.dropped_rooms)}" if self.dropped_rooms else ""),
                False,
            ),
        ]

        for i, (text, bold) in enumerate(lines):
            dwg.add(dwg.text(
                text,
                insert=(CANVAS_W // 2, ty_base + i * 16),
                text_anchor="middle",
                font_family=FONT_FAMILY,
                font_size=f"{FONT_TITLE if bold else FONT_SUBTITLE}px",
                font_weight="bold" if bold else "normal",
                fill=STROKE_COLOR,
            ))

    def _draw_dimension_callouts(self, dwg: svgwrite.Drawing) -> None:
        """
        Layer 7 — Overall plot & build-zone dimension lines (outside the plan).

        Draws horizontal and vertical witness lines with arrowheads at the
        top and left edges of the drawing, annotated with the plot dimensions
        in metres.

        Convention: dimension lines are placed 15px outside the plot boundary.
        Arrowheads are 5×3px triangles at each endpoint.
        """
        # ── Total plot width (horizontal, above plan) ─────────────────────
        sx_l, sy_t = self._m2s(0, self.plot_depth)
        sx_r, _    = self._m2s(self.plot_width, self.plot_depth)
        dim_y      = sy_t - 16

        dwg.add(dwg.line(
            start=(sx_l, dim_y), end=(sx_r, dim_y),
            stroke=STROKE_COLOR, stroke_width="0.8",
        ))
        for tx, ay_off in [(sx_l, -4), (sx_r, 4)]:
            dwg.add(dwg.line(
                start=(tx, dim_y - 3), end=(tx, dim_y + 3),
                stroke=STROKE_COLOR, stroke_width="0.8",
            ))
        dwg.add(dwg.text(
            f"{self.plot_width:.0f} m",
            insert=((sx_l + sx_r) / 2, dim_y - 4),
            text_anchor="middle",
            font_family=FONT_FAMILY,
            font_size="9px",
            fill=STROKE_COLOR,
        ))

        # ── Total plot depth (vertical, left of plan) ─────────────────────
        sx_l2, sy_b = self._m2s(0, 0)
        _, sy_t2    = self._m2s(0, self.plot_depth)
        dim_x       = sx_l2 - 16

        dwg.add(dwg.line(
            start=(dim_x, sy_t2), end=(dim_x, sy_b),
            stroke=STROKE_COLOR, stroke_width="0.8",
        ))
        for ty in [sy_b, sy_t2]:
            dwg.add(dwg.line(
                start=(dim_x - 3, ty), end=(dim_x + 3, ty),
                stroke=STROKE_COLOR, stroke_width="0.8",
            ))
        mid_y = (sy_b + sy_t2) / 2
        dwg.add(dwg.text(
            f"{self.plot_depth:.0f} m",
            insert=(dim_x - 5, mid_y),
            text_anchor="middle",
            font_family=FONT_FAMILY,
            font_size="9px",
            fill=STROKE_COLOR,
            transform=f"rotate(-90, {dim_x - 5}, {mid_y})",
        ))

    # ── Public Entry Point ────────────────────────────────────────────────────

    def export(self) -> str:
        """
        Render the complete floor plan and return raw SVG markup as a string.

        Layer render order (painter's algorithm — last drawn is on top):
            0. Backgrounds (plot gray, build-zone white, room whites)
            1. Setback boundary (dashed line)
            2. Wall lines (external thick, internal thin)
            3. Room labels (name / dimensions / area)
            4. Dimension call-outs (plot W & D)
            5. North arrow
            6. Scale bar
            7. Title block

        Returns:
            str: Complete SVG markup starting with ``<svg ...>`` and ending
                 with ``</svg>``.  Ready to be embedded in HTML or saved as
                 a ``.svg`` file.
        """
        dwg = svgwrite.Drawing(
            size=(f"{CANVAS_W}px", f"{CANVAS_H}px"),
            profile="full",
        )
        dwg.viewbox(0, 0, CANVAS_W, CANVAS_H)

        # Canvas background
        dwg.add(dwg.rect(
            insert=(0, 0),
            size=(CANVAS_W, CANVAS_H),
            fill="#ffffff",
        ))

        self._draw_backgrounds(dwg)
        self._draw_setback_boundary(dwg)
        self._draw_walls(dwg)
        self._draw_room_labels(dwg)
        self._draw_dimension_callouts(dwg)
        self._draw_north_arrow(dwg)
        self._draw_scale_bar(dwg)
        self._draw_title_block(dwg)

        return dwg.tostring()
