"""
TN-Flow Database Models
=======================
SQLAlchemy ORM definitions for the TN-Flow Knowledge Base.

Three core tables:
  1. DistrictClimateMatrix  — 38 TN districts with climate zone, authority, materials
  2. PlotEligibilityRules   — TNCDBR 2019 setbacks, FSI, and floor limits per condition
  3. VastuGridLogic         — Directional room anchoring rules for each orientation

These tables are consumed by the Validation Gate (constraint.py) and the
Vastu Router (vastu_router.py) before any polygon geometry is calculated.
"""

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Enum, Text,
    CheckConstraint, UniqueConstraint
)
from sqlalchemy.orm import declarative_base
import enum

Base = declarative_base()


# ---------------------------------------------------------------------------
# Enums — typed vocabulary shared across tables
# ---------------------------------------------------------------------------

class ClimateZoneEnum(str, enum.Enum):
    TROPICAL_COASTAL = "Tropical Coastal"
    TROPICAL_INLAND  = "Tropical Inland"
    HILLY_COLD       = "Hilly/Cold"


class AuthorityEnum(str, enum.Enum):
    CMDA = "CMDA"   # Chennai Metropolitan Development Authority
    DTCP = "DTCP"   # Directorate of Town and Country Planning


class FloorLevelEnum(str, enum.Enum):
    GROUND = "Ground"
    G_PLUS_1 = "G+1"
    G_PLUS_2 = "G+2"


class VastuZoneEnum(str, enum.Enum):
    """
    Eight cardinal/intercardinal Vastu zones mapped to compass octants.
    Classic Vastu assigns each zone a presiding deity/energy (Devata).
    """
    NORTH      = "North"       # Kubera  — wealth, prosperity
    NORTHEAST  = "NorthEast"   # Ishanya — knowledge, prayer (Pooja)
    EAST       = "East"        # Indra   — social, living
    SOUTHEAST  = "SouthEast"   # Agni    — fire/kitchen
    SOUTH      = "South"       # Yama    — rest, master bedroom
    SOUTHWEST  = "SouthWest"   # Niruti  — stability, master bedroom (alt)
    WEST       = "West"        # Varuna  — children, study
    NORTHWEST  = "NorthWest"   # Vayu    — guests, vehicles


# ---------------------------------------------------------------------------
# Table 1: District_Climate_Matrix
# ---------------------------------------------------------------------------

class DistrictClimateMatrix(Base):
    """
    Stores the 38 official Tamil Nadu districts with their climate
    classification and Baker-principle material recommendations.

    Used by:
      - constraint.py  : to load district-level regulatory authority
      - svg_builder.py : to annotate output with material suggestions
    """
    __tablename__ = "district_climate_matrix"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # --- Identity ---
    district_name = Column(String(60), nullable=False, unique=True,
                           comment="Official district name as per TN Govt.")
    district_code = Column(String(10), nullable=False, unique=True,
                           comment="Short uppercase code, e.g. 'CHN', 'CBE'")

    # --- Climate Classification ---
    climate_zone = Column(
        Enum(ClimateZoneEnum),
        nullable=False,
        comment="Baker/ECBC climate classification for the district"
    )

    # --- Regulatory Authority ---
    authority = Column(
        Enum(AuthorityEnum),
        nullable=False,
        comment="Body that issues building permits: CMDA or DTCP"
    )

    # --- Baker-Principle Material Recommendations ---
    primary_wall_material = Column(
        String(80), nullable=False,
        comment="Primary wall construction material (Baker passive design)"
    )
    secondary_wall_material = Column(
        String(80), nullable=True,
        comment="Alternate or supplementary wall material"
    )
    roof_material = Column(
        String(80), nullable=False,
        comment="Recommended roof material for passive cooling/insulation"
    )
    floor_material = Column(
        String(80), nullable=False,
        comment="Recommended floor finish for thermal comfort"
    )

    # --- Geographic Metadata ---
    region = Column(
        String(40), nullable=True,
        comment="Informal region grouping: Northern, Central, Southern, etc."
    )
    has_coastal_belt = Column(
        Boolean, default=False, nullable=False,
        comment="True if any part of the district touches the coastline"
    )

    __table_args__ = (
        CheckConstraint("LENGTH(district_name) > 2", name="chk_district_name_len"),
        CheckConstraint("LENGTH(district_code) >= 3", name="chk_district_code_len"),
    )

    def __repr__(self):
        return (
            f"<DistrictClimateMatrix(id={self.id}, "
            f"district='{self.district_name}', "
            f"zone='{self.climate_zone}', "
            f"authority='{self.authority}')>"
        )


# ---------------------------------------------------------------------------
# Table 2: Plot_Eligibility_Rules
# ---------------------------------------------------------------------------

class PlotEligibilityRules(Base):
    """
    Encodes TNCDBR 2019 and NBC 2016 dimensional constraints.

    The Validation Gate (constraint.py) queries this table to:
      1. Reject plots that are physically too small for the requested BHK/floor.
      2. Determine the correct setback envelope given road width and authority.
      3. Derive the maximum allowed Floor Space Index (FSI) for the plot.

    Rule lookup priority:
      authority → road_width_min_m → floor_level → plot_area_min_sqm
    """
    __tablename__ = "plot_eligibility_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # --- Applicability Scope ---
    authority = Column(
        Enum(AuthorityEnum),
        nullable=False,
        comment="CMDA or DTCP — rules differ between the two bodies"
    )
    floor_level = Column(
        Enum(FloorLevelEnum),
        nullable=False,
        comment="The construction type this rule applies to"
    )

    # --- Road Width Trigger (metres) ---
    road_width_min_m = Column(
        Float, nullable=False, default=0.0,
        comment="Minimum abutting road width (m) to qualify for this rule row"
    )
    road_width_max_m = Column(
        Float, nullable=True,
        comment="Upper bound of road width range; NULL means no upper limit"
    )

    # --- Minimum Plot Size ---
    plot_area_min_sqm = Column(
        Float, nullable=False,
        comment="Minimum gross plot area in sq.m to permit construction"
    )
    plot_width_min_m = Column(
        Float, nullable=False,
        comment="Minimum plot frontage width in metres"
    )
    plot_depth_min_m = Column(
        Float, nullable=False,
        comment="Minimum plot depth in metres"
    )

    # --- Mandatory Setbacks (metres) ---
    setback_front_m = Column(
        Float, nullable=False,
        comment="Front setback from road boundary (metres)"
    )
    setback_rear_m = Column(
        Float, nullable=False,
        comment="Rear setback from plot boundary (metres)"
    )
    setback_side_left_m = Column(
        Float, nullable=False,
        comment="Left side setback from plot boundary (metres)"
    )
    setback_side_right_m = Column(
        Float, nullable=False,
        comment="Right side setback from plot boundary (metres)"
    )

    # --- Density Controls ---
    fsi_value = Column(
        Float, nullable=False,
        comment="Floor Space Index: max permitted built area / gross plot area"
    )
    ground_coverage_pct = Column(
        Float, nullable=False,
        comment="Max footprint as % of gross plot area (e.g. 75 = 75%)"
    )

    # --- Height Limits ---
    max_height_m = Column(
        Float, nullable=True,
        comment="Maximum building height in metres; NULL = no explicit cap"
    )

    # --- Rule Source ---
    rule_reference = Column(
        String(120), nullable=True,
        comment="Regulation clause reference, e.g. 'TNCDBR 2019 Rule 14(3)'"
    )
    notes = Column(
        Text, nullable=True,
        comment="Human-readable clarification for edge cases"
    )

    __table_args__ = (
        CheckConstraint("fsi_value > 0",            name="chk_fsi_positive"),
        CheckConstraint("ground_coverage_pct <= 100", name="chk_coverage_pct"),
        CheckConstraint("setback_front_m >= 0",     name="chk_front_setback"),
        UniqueConstraint(
            "authority", "floor_level", "road_width_min_m",
            name="uq_rule_lookup_key"
        ),
    )

    def __repr__(self):
        return (
            f"<PlotEligibilityRules(id={self.id}, "
            f"authority='{self.authority}', "
            f"floor='{self.floor_level}', "
            f"road>={self.road_width_min_m}m, "
            f"FSI={self.fsi_value})>"
        )


# ---------------------------------------------------------------------------
# Table 3: Vastu_Grid_Logic
# ---------------------------------------------------------------------------

class VastuGridLogic(Base):
    """
    Maps each room type to its Vastu-compliant compass zone for a given
    plot orientation.

    The Vastu Router (vastu_router.py) queries this table keyed on
    (room_type, plot_facing) and receives back the target vastu_zone.
    The geometry engine then anchors that room's polygon to that zone
    within the build envelope.

    Priority system:
      - priority=1  → must be placed in this zone (hard constraint)
      - priority=2  → strongly preferred (soft constraint, fallback allowed)
      - priority=3  → acceptable alternative only if higher priorities fail
    """
    __tablename__ = "vastu_grid_logic"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # --- Room Identity ---
    room_type = Column(
        String(40), nullable=False,
        comment="Canonical room name: Kitchen, MasterBedroom, Pooja, etc."
    )

    # --- Orientation Context ---
    plot_facing = Column(
        String(10), nullable=False,
        comment="Plot's road-facing direction: North, South, East, West"
    )

    # --- Vastu Assignment ---
    vastu_zone = Column(
        Enum(VastuZoneEnum),
        nullable=False,
        comment="Target Vastu compass zone for this room"
    )
    vastu_zone_name = Column(
        String(20), nullable=False,
        comment="Classical Vastu zone deity/energy name, e.g. Agni, Kubera"
    )

    # --- Constraint Strength ---
    priority = Column(
        Integer, nullable=False, default=1,
        comment="1=hard rule, 2=preferred, 3=acceptable fallback"
    )
    is_mandatory = Column(
        Boolean, nullable=False, default=True,
        comment="If True, plan generation must satisfy this placement"
    )

    # --- Rationale ---
    rationale = Column(
        Text, nullable=True,
        comment="Brief Vastu/climate justification for this placement"
    )

    __table_args__ = (
        CheckConstraint("priority IN (1, 2, 3)", name="chk_priority_range"),
        CheckConstraint(
            "plot_facing IN ('North','South','East','West')",
            name="chk_facing_values"
        ),
        UniqueConstraint(
            "room_type", "plot_facing", "priority",
            name="uq_vastu_room_facing_priority"
        ),
    )

    def __repr__(self):
        return (
            f"<VastuGridLogic(id={self.id}, "
            f"room='{self.room_type}', "
            f"facing='{self.plot_facing}', "
            f"zone='{self.vastu_zone}', "
            f"priority={self.priority})>"
        )
