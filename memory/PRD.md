# TN-Flow Engine — Product Requirements Document

## Problem Statement
Build the Validation Gate (constraint.py) and Vastu Router (vastu_router.py) modules
to bridge the database (TNCDBR 2019 rules + Vastu logic) and the geometry engine.
Before calculating wall-centric polygons the engine must:
1. Mathematically validate if a requested plot configuration is legally permitted.
2. Assign spatial anchor points to primary rooms based on the plot's orientation.

## Architecture

### Project Root
```
/app/tn_flow_project/
├── backend/
│   ├── database/
│   │   ├── models.py          — SQLAlchemy ORM (3 tables)
│   │   ├── db.py              — SessionLocal / engine (SQLite dev, PostgreSQL prod)
│   │   ├── seed_tn_districts.py  — 38 TN districts with climate + materials
│   │   └── seed_rules_vastu.py   — 26 TNCDBR rules + 120 Vastu rules
│   ├── engine/
│   │   ├── exceptions.py      — Custom exception hierarchy (8 classes)
│   │   ├── constraint.py      — Validation Gate (BuildZone, setback math)
│   │   └── vastu_router.py    — Vastu Purusha Mandala 3×3 grid router ← NEW
│   ├── api/                   — FastAPI routes (future)
│   ├── render/                — SVG/DXF output (future)
│   └── requirements.txt
└── tn_flow.db                 — SQLite DB (seeded with 26+120 rows)
```

### Tech Stack
- Python 3.x, SQLAlchemy 2.0 (sync), SQLite (dev) / PostgreSQL (prod)
- Shapely 2.0 for polygon geometry
- FastAPI (future API layer)

## Database (Fully Seeded)
| Table | Rows | Purpose |
|---|---|---|
| district_climate_matrix | 38 | TN districts, climate zones, materials, authority |
| plot_eligibility_rules | 26 | TNCDBR 2019 setbacks, FSI, coverage, heights |
| vastu_grid_logic | 120 | Room→Zone assignments for 11 rooms × 4 facings × 3 priorities |

## Implemented Modules

### 1. backend/engine/exceptions.py (Pre-existing, complete)
Custom exception hierarchy:
- `TNFlowBaseError` — root, carries `context` dict + `to_dict()` serialiser
- `TNCDBRValidationError` → `RoadWidthInsufficientError`, `PlotTooSmallError`,
  `FloorLevelNotPermittedError`, `SetbackExceedsPlotError`, `InsufficientBuildEnvelopeError`
- `VastuRoutingError` → `UnresolvableRoomPlacementError`, `VastuZoneUnavailableError`

### 2. backend/engine/constraint.py (Pre-existing, complete)
- **`BuildZone`** dataclass: `plot_polygon`, `envelope_polygon`, `plot_area_sqm`,
  `envelope_area_sqm`, `fsi`, `ground_coverage_pct`, `max_buildable_sqm`,
  `max_footprint_sqm`, `max_height_m`, setbacks, rule provenance, derived properties
- **`calculate_build_envelope(plot_width, plot_depth, authority, floor_level, road_width, session, plot_facing)`**
  — queries PlotEligibilityRules, validates dimensions, applies orientation-aware setbacks
  via Shapely `box()`, returns BuildZone
- **`is_buildable()`** — non-raising convenience wrapper
- **`_SETBACK_FORMULA`** — orientation-aware setback dict for all 4 compass directions

### 3. backend/engine/vastu_router.py (Created 2025-Feb)
- **`get_mandala_grid(envelope_polygon)`** — Divides build envelope into 3×3 Vastu Purusha
  Mandala using equal-thirds division (W/3 × H/3 cells), clips cells to actual envelope
- **`get_room_anchors(plot_facing, build_zone_polygon, session, priority=1)`**
  — Queries VastuGridLogic for (plot_facing, priority), overlays mandala grid,
  validates NBC 2016 minimum areas, returns RoomAnchorMap
  `{ room_type: {"zone": "SE", "bounding_box": Polygon} }`
- **`get_all_priority_anchors()`** — Returns P1/P2/P3 anchors in one call
- **`describe_anchors()`** — Human-readable text report for debugging/CLI
- **`_ZONE_GRID_POSITION`** — Maps each VastuZoneEnum to (col, row) in 3×3 grid
- **`_NBC_MIN_ROOM_AREA_SQM`** — Per-room NBC 2016 minimum area thresholds

## Coordinate System
- Origin (0, 0) = South-West corner of plot
- +X = East, +Y = North
- Road-facing edge = plot_facing direction
- All polygons in absolute plot coordinates (metres)

## Vastu Purusha Mandala Grid
```
┌──────────┬──────────┬──────────┐  Y↑
│ NW (0,2) │ N  (1,2) │ NE (2,2) │  Row 2 (North third)
├──────────┼──────────┼──────────┤
│ W  (0,1) │ Brahma   │ E  (2,1) │  Row 1 (Centre)
├──────────┼──────────┼──────────┤
│ SW (0,0) │ S  (1,0) │ SE (2,0) │  Row 0 (South third)
└──────────┴──────────┴──────────┘  └──→ X
  Col 0      Col 1      Col 2
```

## P1 Room→Zone Assignments (all orientations identical, Entrance is exception)
| Room | P1 Zone | Rationale |
|---|---|---|
| Kitchen | SE (Agni) | Fire zone, morning sun sterilisation |
| MasterBedroom | SW (Niruthi) | Stability, head-to-South sleep |
| Bedroom2 | W (Varuna) | Nurturing, afternoon shade |
| Bedroom3 | S (Yama) | Secondary rest zone |
| Pooja | NE (Ishanya) | Sacred zone, morning sun |
| Toilet | NW (Vayu) | Ventilation, waste-pipe routing |
| Hall | E (Indra) | Sunrise, social energy |
| Dining | W (Varuna) | Nourishment, setting sun |
| Staircase | SW (Niruthi) | Structural stability |
| StoreRoom | W (Varuna) | Shade, stable temperature |
| Entrance (North) | NE (Ishanya) | Most auspicious pada |
| Entrance (East) | NE (Ishanya) | Mukhya pada |
| Entrance (South) | SE (Agni) | Grihapati pada |
| Entrance (West) | NW (Vayu) | Sugriva pada |

## Testing Status
- All 7 test scenarios passed (2025-Feb)
- Full pipeline: constraint.py → BuildZone → vastu_router.py → RoomAnchorMap verified
- Error cases: FloorLevelNotPermitted, PlotTooSmall, SetbackExceeds, VastuZoneUnavailable all verified

## Prioritised Backlog

### P0 (Next Session)
- [ ] allocator.py — Resolve zone conflicts when multiple rooms share a cell
- [ ] geometry.py — Wall-centric polygon subdivision within each zone cell
- [ ] FastAPI routes: POST /api/validate-plot, POST /api/generate-layout

### P1
- [ ] svg_builder.py — Render BuildZone + room anchors to SVG
- [ ] dxf_exporter.py — DXF output for CAD workflows
- [ ] DistrictClimateMatrix integration — auto-derive authority from district name

### P2
- [ ] PostgreSQL migration + connection pooling
- [ ] BHK-specific room list selection (1BHK skips Bedroom2/3/Staircase)
- [ ] Non-rectangular plot support (L-shaped, irregular boundaries)
- [ ] Vastu deviation report (flag P2/P3 assignments in output)

## Next Tasks
1. Implement `allocator.py` to subdivide shared Vastu zones
2. Add FastAPI routes for the validate + generate pipeline
3. Add SVG render output
