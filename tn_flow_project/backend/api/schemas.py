"""
TN-Flow API Pydantic Schemas — schemas.py
==========================================
Request and response models for the TN-Flow FastAPI layer.

All models use Pydantic v2 semantics (model_config, Field validators).

Endpoint summary:
  POST /api/validate-plot   → ValidatePlotRequest  / ValidatePlotResponse
  POST /api/generate-layout → GenerateRequest      / GenerateResponse
"""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


# ── Shared Enums (string literals kept loose so the API is self-documenting) ──

VALID_AUTHORITIES  = {"CMDA", "DTCP"}
VALID_FLOOR_LEVELS = {"Ground", "G+1", "G+2"}
VALID_FACINGS      = {"North", "South", "East", "West"}
VALID_BHK_TYPES    = {"1BHK", "2BHK", "3BHK", "3BHK_VILLA"}


# ── /api/validate-plot ────────────────────────────────────────────────────────

class ValidatePlotRequest(BaseModel):
    """
    Input payload for the TNCDBR 2019 plot validation check.

    Fields:
        plot_width   : East-West dimension of the plot in metres.
        plot_depth   : North-South dimension of the plot in metres.
        authority    : Regulatory body — "CMDA" (Chennai metro) or "DTCP" (rest of TN).
        floor_level  : Permitted construction type — "Ground", "G+1", or "G+2".
        road_width   : Width of the abutting road in metres (triggers setback rules).
        plot_facing  : Direction the main road faces — "North", "South", "East", "West".
    """
    plot_width:  float = Field(..., gt=0, description="Plot East-West width (metres)")
    plot_depth:  float = Field(..., gt=0, description="Plot North-South depth (metres)")
    authority:   str   = Field(..., description="CMDA or DTCP")
    floor_level: str   = Field(..., description="Ground / G+1 / G+2")
    road_width:  float = Field(..., gt=0, description="Abutting road width (metres)")
    plot_facing: str   = Field(..., description="North / South / East / West")

    @field_validator("authority")
    @classmethod
    def check_authority(cls, v: str) -> str:
        if v not in VALID_AUTHORITIES:
            raise ValueError(f"authority must be one of {sorted(VALID_AUTHORITIES)}")
        return v

    @field_validator("floor_level")
    @classmethod
    def check_floor_level(cls, v: str) -> str:
        if v not in VALID_FLOOR_LEVELS:
            raise ValueError(f"floor_level must be one of {sorted(VALID_FLOOR_LEVELS)}")
        return v

    @field_validator("plot_facing")
    @classmethod
    def check_facing(cls, v: str) -> str:
        if v not in VALID_FACINGS:
            raise ValueError(f"plot_facing must be one of {sorted(VALID_FACINGS)}")
        return v

    model_config = {"json_schema_extra": {
        "example": {
            "plot_width": 12.0, "plot_depth": 22.0,
            "authority": "CMDA", "floor_level": "G+1",
            "road_width": 12.0, "plot_facing": "North",
        }
    }}


class SetbackDetail(BaseModel):
    """Setback distances (metres) for each side of the build envelope."""
    front_m:      float
    rear_m:       float
    side_left_m:  float
    side_right_m: float


class ValidatePlotResponse(BaseModel):
    """
    Response payload from /api/validate-plot.

    Contains the derived BuildZone geometry details and FSI/coverage controls
    without executing the full layout pipeline.
    """
    is_buildable:       bool
    plot_area_sqm:      float = Field(description="Gross plot area (m²)")
    envelope_area_sqm:  float = Field(description="Legal build envelope area (m²)")
    envelope_width_m:   float = Field(description="Build envelope East-West width (m)")
    envelope_depth_m:   float = Field(description="Build envelope North-South depth (m)")
    fsi:                float = Field(description="Floor Space Index (permitted)")
    ground_coverage_pct:float = Field(description="Max ground coverage as % of plot area")
    max_buildable_sqm:  float = Field(description="Maximum total built-up area (m²)")
    max_footprint_sqm:  float = Field(description="Maximum ground-floor footprint (m²)")
    max_height_m:       Optional[float] = Field(None, description="Maximum building height (m)")
    setbacks:           SetbackDetail
    rule_ref:           str   = Field(description="TNCDBR 2019 regulation clause reference")
    reason:             Optional[str] = Field(None, description="Reason if not buildable")


# ── /api/generate-layout ─────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    """
    Input payload for the full TN-Flow layout generation pipeline.

    The engine runs:
        Validation Gate → Vastu Router → Spatial Allocator → Geometry Engine → SVG Renderer

    Fields:
        plot_width   : East-West plot dimension (metres).
        plot_depth   : North-South plot dimension (metres).
        plot_facing  : Main road compass direction.
        district     : Tamil Nadu district name (used to derive regulatory authority).
                       Case-insensitive.  Example: "Chennai", "Coimbatore".
        bhk_type     : Flat configuration — "1BHK", "2BHK", "3BHK", "3BHK_VILLA".
        floor_level  : Floor type — defaults to "G+1".
        road_width   : Abutting road width in metres — defaults to 9.0m.
    """
    plot_width:  float = Field(..., gt=0, description="Plot East-West width (metres)")
    plot_depth:  float = Field(..., gt=0, description="Plot North-South depth (metres)")
    plot_facing: str   = Field(..., description="North / South / East / West")
    district:    str   = Field(..., min_length=2, description="Tamil Nadu district name")
    bhk_type:    str   = Field(..., description="1BHK / 2BHK / 3BHK / 3BHK_VILLA")
    floor_level: str   = Field("G+1",  description="Ground / G+1 / G+2")
    road_width:  float = Field(9.0, gt=0, description="Abutting road width (metres)")

    @field_validator("plot_facing")
    @classmethod
    def check_facing(cls, v: str) -> str:
        if v not in VALID_FACINGS:
            raise ValueError(f"plot_facing must be one of {sorted(VALID_FACINGS)}")
        return v

    @field_validator("bhk_type")
    @classmethod
    def check_bhk(cls, v: str) -> str:
        if v not in VALID_BHK_TYPES:
            raise ValueError(f"bhk_type must be one of {sorted(VALID_BHK_TYPES)}")
        return v

    @field_validator("floor_level")
    @classmethod
    def check_floor_level(cls, v: str) -> str:
        if v not in VALID_FLOOR_LEVELS:
            raise ValueError(f"floor_level must be one of {sorted(VALID_FLOOR_LEVELS)}")
        return v

    model_config = {"json_schema_extra": {
        "example": {
            "plot_width": 12.0, "plot_depth": 22.0,
            "plot_facing": "North", "district": "Chennai",
            "bhk_type": "2BHK", "floor_level": "G+1", "road_width": 12.0,
        }
    }}


class RoomData(BaseModel):
    """Per-room output data in the GenerateResponse."""
    room_name:       str   = Field(description="Room type identifier")
    zone:            str   = Field(description="Vastu zone abbreviation (NE, SW, etc.)")
    carpet_area_sqm: float = Field(description="Clear carpet area after wall deduction (m²)")
    width_m:         float = Field(description="Clear internal width (m)")
    depth_m:         float = Field(description="Clear internal depth (m)")
    nbc_minimum_sqm: float = Field(description="NBC 2016 minimum carpet area for this room type")


class GenerateResponse(BaseModel):
    """
    Response payload from /api/generate-layout.

    Contains:
      - Plot and envelope metadata (from the Validation Gate)
      - Per-room spatial data including Vastu zone, carpet area, and dimensions
      - List of optional rooms dropped by the fallback mechanism (may be empty)
      - The complete SVG floor plan as a raw string

    The ``svg`` field contains a complete, self-contained ``<svg>`` element
    that can be embedded directly in an HTML page or saved as a .svg file.
    """
    # ── Plot metadata ──────────────────────────────────────────────────────
    district:           str
    authority:          str   = Field(description="CMDA or DTCP (derived from district)")
    plot_facing:        str
    plot_area_sqm:      float
    envelope_area_sqm:  float
    fsi:                float
    max_buildable_sqm:  float

    # ── Layout results ─────────────────────────────────────────────────────
    bhk_type:           str
    rooms_dropped:      List[str] = Field(
        default_factory=list,
        description="Optional rooms removed by space-deficit fallback (may be empty)",
    )
    rooms:              List[RoomData]
    total_carpet_sqm:   float = Field(description="Sum of all room carpet areas (m²)")

    # ── Visual output ──────────────────────────────────────────────────────
    svg:                str = Field(description="Complete SVG floor plan markup")
