"""
TN-Flow Seed Script — District_Climate_Matrix
=============================================
Populates the `district_climate_matrix` table with all 38 official
Tamil Nadu districts (as constituted after the 2019–2020 reorganisation).

Baker-Principle Material Logic applied:
  Tropical Coastal → Fly Ash Brick (humidity/salt resistant) + AAC Blocks
  Tropical Inland  → Rat-trap Bond Brick (cavity insulation) + Terracotta
  Hilly/Cold       → Laterite Stone / Granite + Lime Mortar (thermal mass)

Authority Mapping:
  CMDA → Chennai, Kanchipuram, Tiruvallur, Chengalpattu (CMA boundary)
  DTCP → All remaining 34 districts

Run:
    python -m backend.database.seed_tn_districts
  or from the project root:
    python backend/database/seed_tn_districts.py
"""

import sys
import os

# Allow running directly from project root without installing as a package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.database.db import SessionLocal, engine
from backend.database.models import (
    Base,
    DistrictClimateMatrix,
    ClimateZoneEnum,
    AuthorityEnum,
)


# ---------------------------------------------------------------------------
# Master District Dataset — all 38 Tamil Nadu districts
# ---------------------------------------------------------------------------
# Each dict maps 1:1 to a DistrictClimateMatrix row.
# Material selections follow Lauren Baker's passive design recommendations
# for the Indian sub-continent, adapted for TN's three climate bands.
# ---------------------------------------------------------------------------

DISTRICTS: list[dict] = [

    # =========================================================
    # CMDA-governed districts (Chennai Metropolitan Area)
    # =========================================================
    {
        "district_name": "Chennai",
        "district_code": "CHN",
        "climate_zone": ClimateZoneEnum.TROPICAL_COASTAL,
        "authority": AuthorityEnum.CMDA,
        "primary_wall_material": "Fly Ash Brick (230mm solid)",
        "secondary_wall_material": "AAC Blocks (200mm)",
        "roof_material": "RCC Flat Roof with China Mosaic / White Reflective Coating",
        "floor_material": "Kota Stone / Ceramic Vitrified Tile",
        "region": "Northern Coastal",
        "has_coastal_belt": True,
    },
    {
        "district_name": "Kanchipuram",
        "district_code": "KPM",
        "climate_zone": ClimateZoneEnum.TROPICAL_COASTAL,
        "authority": AuthorityEnum.CMDA,
        "primary_wall_material": "Fly Ash Brick (230mm solid)",
        "secondary_wall_material": "AAC Blocks (200mm)",
        "roof_material": "RCC Flat Roof with White Reflective Coating",
        "floor_material": "Kota Stone / Ceramic Vitrified Tile",
        "region": "Northern Coastal",
        "has_coastal_belt": True,
    },
    {
        "district_name": "Tiruvallur",
        "district_code": "TVR",
        "climate_zone": ClimateZoneEnum.TROPICAL_COASTAL,
        "authority": AuthorityEnum.CMDA,
        "primary_wall_material": "Fly Ash Brick (230mm solid)",
        "secondary_wall_material": "AAC Blocks (200mm)",
        "roof_material": "RCC Flat Roof with China Mosaic Finish",
        "floor_material": "Kota Stone / Ceramic Tile",
        "region": "Northern Coastal",
        "has_coastal_belt": True,
    },
    {
        "district_name": "Chengalpattu",
        "district_code": "CGP",
        "climate_zone": ClimateZoneEnum.TROPICAL_COASTAL,
        "authority": AuthorityEnum.CMDA,
        "primary_wall_material": "Fly Ash Brick (230mm solid)",
        "secondary_wall_material": "AAC Blocks (200mm)",
        "roof_material": "RCC Flat Roof with White Reflective Coating",
        "floor_material": "Kota Stone / Ceramic Vitrified Tile",
        "region": "Northern Coastal",
        "has_coastal_belt": True,
    },

    # =========================================================
    # Northern Inland — DTCP
    # =========================================================
    {
        "district_name": "Vellore",
        "district_code": "VLR",
        "climate_zone": ClimateZoneEnum.TROPICAL_INLAND,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Rat-trap Bond Brick (230mm cavity wall)",
        "secondary_wall_material": "Stabilised Mud Block (SMB)",
        "roof_material": "Mangalore / Country Tile on Timber Rafters (pitched)",
        "floor_material": "Terracotta / Shahabad Stone",
        "region": "Northern Inland",
        "has_coastal_belt": False,
    },
    {
        "district_name": "Ranipet",
        "district_code": "RNP",
        "climate_zone": ClimateZoneEnum.TROPICAL_INLAND,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Rat-trap Bond Brick (230mm cavity wall)",
        "secondary_wall_material": "Stabilised Mud Block (SMB)",
        "roof_material": "Mangalore / Country Tile on Timber Rafters (pitched)",
        "floor_material": "Terracotta / Shahabad Stone",
        "region": "Northern Inland",
        "has_coastal_belt": False,
    },
    {
        "district_name": "Tirupattur",
        "district_code": "TPT",
        "climate_zone": ClimateZoneEnum.TROPICAL_INLAND,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Rat-trap Bond Brick (230mm cavity wall)",
        "secondary_wall_material": "Stabilised Mud Block (SMB)",
        "roof_material": "Mangalore / Country Tile on Timber Rafters (pitched)",
        "floor_material": "Terracotta / Shahabad Stone",
        "region": "Northern Inland",
        "has_coastal_belt": False,
    },
    {
        "district_name": "Tiruvannamalai",
        "district_code": "TVL",
        "climate_zone": ClimateZoneEnum.TROPICAL_INLAND,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Rat-trap Bond Brick (230mm cavity wall)",
        "secondary_wall_material": "Granite Rubble Masonry",
        "roof_material": "Mangalore / Country Tile on Timber Rafters (pitched)",
        "floor_material": "Terracotta / Granite Slab",
        "region": "Northern Inland",
        "has_coastal_belt": False,
    },
    {
        "district_name": "Villupuram",
        "district_code": "VPM",
        "climate_zone": ClimateZoneEnum.TROPICAL_COASTAL,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Fly Ash Brick (230mm solid)",
        "secondary_wall_material": "AAC Blocks (200mm)",
        "roof_material": "RCC Flat Roof with White Reflective Coating",
        "floor_material": "Kota Stone / Ceramic Tile",
        "region": "Northern Coastal",
        "has_coastal_belt": True,
    },
    {
        "district_name": "Kallakurichi",
        "district_code": "KLK",
        "climate_zone": ClimateZoneEnum.TROPICAL_INLAND,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Rat-trap Bond Brick (230mm cavity wall)",
        "secondary_wall_material": "Stabilised Mud Block (SMB)",
        "roof_material": "Mangalore / Country Tile on Timber Rafters (pitched)",
        "floor_material": "Terracotta / Shahabad Stone",
        "region": "Northern Inland",
        "has_coastal_belt": False,
    },
    {
        "district_name": "Cuddalore",
        "district_code": "CDL",
        "climate_zone": ClimateZoneEnum.TROPICAL_COASTAL,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Fly Ash Brick (230mm solid)",
        "secondary_wall_material": "AAC Blocks (200mm)",
        "roof_material": "RCC Flat Roof with China Mosaic Finish",
        "floor_material": "Kota Stone / Ceramic Vitrified Tile",
        "region": "Northern Coastal",
        "has_coastal_belt": True,
    },

    # =========================================================
    # Northwestern Inland — DTCP
    # =========================================================
    {
        "district_name": "Krishnagiri",
        "district_code": "KRG",
        "climate_zone": ClimateZoneEnum.TROPICAL_INLAND,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Rat-trap Bond Brick (230mm cavity wall)",
        "secondary_wall_material": "Granite Rubble Masonry",
        "roof_material": "Mangalore / Country Tile on Timber Rafters (pitched)",
        "floor_material": "Terracotta / Granite Slab",
        "region": "Northwestern Inland",
        "has_coastal_belt": False,
    },
    {
        "district_name": "Dharmapuri",
        "district_code": "DPR",
        "climate_zone": ClimateZoneEnum.TROPICAL_INLAND,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Rat-trap Bond Brick (230mm cavity wall)",
        "secondary_wall_material": "Granite Rubble Masonry",
        "roof_material": "Mangalore / Country Tile on Timber Rafters (pitched)",
        "floor_material": "Terracotta / Granite Slab",
        "region": "Northwestern Inland",
        "has_coastal_belt": False,
    },
    {
        "district_name": "Salem",
        "district_code": "SLM",
        "climate_zone": ClimateZoneEnum.TROPICAL_INLAND,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Rat-trap Bond Brick (230mm cavity wall)",
        "secondary_wall_material": "Granite Rubble Masonry",
        "roof_material": "Mangalore / Country Tile on Timber Rafters (pitched)",
        "floor_material": "Terracotta / Shahabad Stone",
        "region": "Northwestern Inland",
        "has_coastal_belt": False,
    },
    {
        "district_name": "Namakkal",
        "district_code": "NMK",
        "climate_zone": ClimateZoneEnum.TROPICAL_INLAND,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Rat-trap Bond Brick (230mm cavity wall)",
        "secondary_wall_material": "Stabilised Mud Block (SMB)",
        "roof_material": "Mangalore / Country Tile on Timber Rafters (pitched)",
        "floor_material": "Terracotta / Shahabad Stone",
        "region": "Central Inland",
        "has_coastal_belt": False,
    },
    {
        "district_name": "Erode",
        "district_code": "ERD",
        "climate_zone": ClimateZoneEnum.TROPICAL_INLAND,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Rat-trap Bond Brick (230mm cavity wall)",
        "secondary_wall_material": "Stabilised Mud Block (SMB)",
        "roof_material": "Mangalore / Country Tile on Timber Rafters (pitched)",
        "floor_material": "Terracotta / Shahabad Stone",
        "region": "Northwestern Inland",
        "has_coastal_belt": False,
    },

    # =========================================================
    # Western — DTCP (Coimbatore belt + Nilgiris)
    # =========================================================
    {
        "district_name": "Tiruppur",
        "district_code": "TPR",
        "climate_zone": ClimateZoneEnum.TROPICAL_INLAND,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Rat-trap Bond Brick (230mm cavity wall)",
        "secondary_wall_material": "Stabilised Mud Block (SMB)",
        "roof_material": "Mangalore / Country Tile on Timber Rafters (pitched)",
        "floor_material": "Terracotta / Shahabad Stone",
        "region": "Western Inland",
        "has_coastal_belt": False,
    },
    {
        "district_name": "Coimbatore",
        "district_code": "CBE",
        "climate_zone": ClimateZoneEnum.TROPICAL_INLAND,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Rat-trap Bond Brick (230mm cavity wall)",
        "secondary_wall_material": "AAC Blocks (200mm)",
        "roof_material": "Mangalore / Country Tile on Timber Rafters (pitched)",
        "floor_material": "Terracotta / Shahabad Stone",
        "region": "Western Inland",
        "has_coastal_belt": False,
    },
    {
        "district_name": "The Nilgiris",
        "district_code": "NLG",
        "climate_zone": ClimateZoneEnum.HILLY_COLD,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Laterite Stone Masonry (300mm)",
        "secondary_wall_material": "Granite Rubble Masonry with Lime Mortar",
        "roof_material": "Galvanised Iron (GI) Sheet / Slate Tile (pitched, steep)",
        "floor_material": "Granite Slab / Local Stone Paving",
        "region": "Western Hills",
        "has_coastal_belt": False,
    },

    # =========================================================
    # Central — DTCP
    # =========================================================
    {
        "district_name": "Karur",
        "district_code": "KRR",
        "climate_zone": ClimateZoneEnum.TROPICAL_INLAND,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Rat-trap Bond Brick (230mm cavity wall)",
        "secondary_wall_material": "Stabilised Mud Block (SMB)",
        "roof_material": "Mangalore / Country Tile on Timber Rafters (pitched)",
        "floor_material": "Terracotta / Shahabad Stone",
        "region": "Central Inland",
        "has_coastal_belt": False,
    },
    {
        "district_name": "Tiruchirappalli",
        "district_code": "TRY",
        "climate_zone": ClimateZoneEnum.TROPICAL_INLAND,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Rat-trap Bond Brick (230mm cavity wall)",
        "secondary_wall_material": "Stabilised Mud Block (SMB)",
        "roof_material": "Mangalore / Country Tile on Timber Rafters (pitched)",
        "floor_material": "Terracotta / Shahabad Stone",
        "region": "Central Inland",
        "has_coastal_belt": False,
    },
    {
        "district_name": "Perambalur",
        "district_code": "PBR",
        "climate_zone": ClimateZoneEnum.TROPICAL_INLAND,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Rat-trap Bond Brick (230mm cavity wall)",
        "secondary_wall_material": "Stabilised Mud Block (SMB)",
        "roof_material": "Mangalore / Country Tile on Timber Rafters (pitched)",
        "floor_material": "Terracotta / Shahabad Stone",
        "region": "Central Inland",
        "has_coastal_belt": False,
    },
    {
        "district_name": "Ariyalur",
        "district_code": "AYR",
        "climate_zone": ClimateZoneEnum.TROPICAL_INLAND,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Rat-trap Bond Brick (230mm cavity wall)",
        "secondary_wall_material": "Stabilised Mud Block (SMB)",
        "roof_material": "Mangalore / Country Tile on Timber Rafters (pitched)",
        "floor_material": "Terracotta / Shahabad Stone",
        "region": "Central Inland",
        "has_coastal_belt": False,
    },

    # =========================================================
    # Cauvery Delta / Coastal — DTCP
    # =========================================================
    {
        "district_name": "Thanjavur",
        "district_code": "TNJ",
        "climate_zone": ClimateZoneEnum.TROPICAL_COASTAL,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Fly Ash Brick (230mm solid)",
        "secondary_wall_material": "AAC Blocks (200mm)",
        "roof_material": "RCC Flat Roof with White Reflective Coating",
        "floor_material": "Kota Stone / Ceramic Tile",
        "region": "Cauvery Delta",
        "has_coastal_belt": False,
    },
    {
        "district_name": "Tiruvarur",
        "district_code": "TRR",
        "climate_zone": ClimateZoneEnum.TROPICAL_COASTAL,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Fly Ash Brick (230mm solid)",
        "secondary_wall_material": "AAC Blocks (200mm)",
        "roof_material": "RCC Flat Roof with China Mosaic Finish",
        "floor_material": "Kota Stone / Ceramic Tile",
        "region": "Cauvery Delta",
        "has_coastal_belt": True,
    },
    {
        "district_name": "Nagapattinam",
        "district_code": "NGP",
        "climate_zone": ClimateZoneEnum.TROPICAL_COASTAL,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Fly Ash Brick (230mm solid)",
        "secondary_wall_material": "AAC Blocks (200mm)",
        "roof_material": "RCC Flat Roof with China Mosaic Finish",
        "floor_material": "Kota Stone / Ceramic Vitrified Tile",
        "region": "Cauvery Delta",
        "has_coastal_belt": True,
    },
    {
        "district_name": "Mayiladuthurai",
        "district_code": "MYD",
        "climate_zone": ClimateZoneEnum.TROPICAL_COASTAL,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Fly Ash Brick (230mm solid)",
        "secondary_wall_material": "AAC Blocks (200mm)",
        "roof_material": "RCC Flat Roof with China Mosaic Finish",
        "floor_material": "Kota Stone / Ceramic Tile",
        "region": "Cauvery Delta",
        "has_coastal_belt": True,
    },

    # =========================================================
    # Central-South — DTCP
    # =========================================================
    {
        "district_name": "Pudukottai",
        "district_code": "PDK",
        "climate_zone": ClimateZoneEnum.TROPICAL_INLAND,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Rat-trap Bond Brick (230mm cavity wall)",
        "secondary_wall_material": "Stabilised Mud Block (SMB)",
        "roof_material": "Mangalore / Country Tile on Timber Rafters (pitched)",
        "floor_material": "Terracotta / Shahabad Stone",
        "region": "Central South Inland",
        "has_coastal_belt": False,
    },
    {
        "district_name": "Dindigul",
        "district_code": "DDL",
        "climate_zone": ClimateZoneEnum.TROPICAL_INLAND,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Rat-trap Bond Brick (230mm cavity wall)",
        "secondary_wall_material": "Stabilised Mud Block (SMB)",
        "roof_material": "Mangalore / Country Tile on Timber Rafters (pitched)",
        "floor_material": "Terracotta / Shahabad Stone",
        "region": "Central South Inland",
        "has_coastal_belt": False,
    },
    {
        "district_name": "Theni",
        "district_code": "THN",
        "climate_zone": ClimateZoneEnum.HILLY_COLD,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Laterite Stone Masonry (300mm)",
        "secondary_wall_material": "Granite Rubble Masonry with Lime Mortar",
        "roof_material": "GI Sheet / Terracotta Tile (pitched) for upper elevation",
        "floor_material": "Granite Slab / Local Stone Paving",
        "region": "Western Hills",
        "has_coastal_belt": False,
    },

    # =========================================================
    # South-Central — DTCP
    # =========================================================
    {
        "district_name": "Madurai",
        "district_code": "MDU",
        "climate_zone": ClimateZoneEnum.TROPICAL_INLAND,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Rat-trap Bond Brick (230mm cavity wall)",
        "secondary_wall_material": "Stabilised Mud Block (SMB)",
        "roof_material": "Mangalore / Country Tile on Timber Rafters (pitched)",
        "floor_material": "Terracotta / Shahabad Stone",
        "region": "South-Central Inland",
        "has_coastal_belt": False,
    },
    {
        "district_name": "Sivaganga",
        "district_code": "SVG",
        "climate_zone": ClimateZoneEnum.TROPICAL_INLAND,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Rat-trap Bond Brick (230mm cavity wall)",
        "secondary_wall_material": "Stabilised Mud Block (SMB)",
        "roof_material": "Mangalore / Country Tile on Timber Rafters (pitched)",
        "floor_material": "Terracotta / Shahabad Stone",
        "region": "South-Central Inland",
        "has_coastal_belt": False,
    },
    {
        "district_name": "Virudhunagar",
        "district_code": "VDN",
        "climate_zone": ClimateZoneEnum.TROPICAL_INLAND,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Rat-trap Bond Brick (230mm cavity wall)",
        "secondary_wall_material": "Stabilised Mud Block (SMB)",
        "roof_material": "Mangalore / Country Tile on Timber Rafters (pitched)",
        "floor_material": "Terracotta / Shahabad Stone",
        "region": "Southern Inland",
        "has_coastal_belt": False,
    },
    {
        "district_name": "Ramanathapuram",
        "district_code": "RMD",
        "climate_zone": ClimateZoneEnum.TROPICAL_COASTAL,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Fly Ash Brick (230mm solid)",
        "secondary_wall_material": "AAC Blocks (200mm)",
        "roof_material": "RCC Flat Roof with White Reflective Coating",
        "floor_material": "Kota Stone / Ceramic Vitrified Tile",
        "region": "Southern Coastal",
        "has_coastal_belt": True,
    },

    # =========================================================
    # Southern — DTCP
    # =========================================================
    {
        "district_name": "Thoothukudi",
        "district_code": "TUT",
        "climate_zone": ClimateZoneEnum.TROPICAL_COASTAL,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Fly Ash Brick (230mm solid)",
        "secondary_wall_material": "AAC Blocks (200mm)",
        "roof_material": "RCC Flat Roof with China Mosaic / White Reflective Coating",
        "floor_material": "Kota Stone / Ceramic Vitrified Tile",
        "region": "Southern Coastal",
        "has_coastal_belt": True,
    },
    {
        "district_name": "Tirunelveli",
        "district_code": "TNV",
        "climate_zone": ClimateZoneEnum.TROPICAL_COASTAL,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Fly Ash Brick (230mm solid)",
        "secondary_wall_material": "Rat-trap Bond Brick (230mm) for inland areas",
        "roof_material": "RCC Flat Roof with White Reflective Coating",
        "floor_material": "Kota Stone / Ceramic Tile",
        "region": "Southern Coastal",
        "has_coastal_belt": True,
    },
    {
        "district_name": "Tenkasi",
        "district_code": "TKS",
        "climate_zone": ClimateZoneEnum.HILLY_COLD,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Laterite Stone Masonry (300mm)",
        "secondary_wall_material": "Granite Rubble Masonry with Lime Mortar",
        "roof_material": "GI Sheet / Country Tile (pitched) — heavy rainfall zone",
        "floor_material": "Granite Slab / Local Stone Paving",
        "region": "Western Hills",
        "has_coastal_belt": False,
    },
    {
        "district_name": "Kanniyakumari",
        "district_code": "KNK",
        "climate_zone": ClimateZoneEnum.TROPICAL_COASTAL,
        "authority": AuthorityEnum.DTCP,
        "primary_wall_material": "Fly Ash Brick (230mm solid)",
        "secondary_wall_material": "Laterite Stone Masonry (coastal-hill transition)",
        "roof_material": "GI Sheet / Country Tile (pitched — high rainfall & wind)",
        "floor_material": "Granite Slab / Ceramic Vitrified Tile",
        "region": "Far South Coastal",
        "has_coastal_belt": True,
    },
]


# ---------------------------------------------------------------------------
# Validation helper
# ---------------------------------------------------------------------------

def _validate_dataset(districts: list[dict]) -> None:
    """Fail fast if the dataset is mis-assembled."""
    assert len(districts) == 38, (
        f"Expected 38 districts, got {len(districts)}. "
        "Check for duplicates or missing entries."
    )
    codes  = [d["district_code"] for d in districts]
    names  = [d["district_name"] for d in districts]
    assert len(set(codes)) == 38,  "Duplicate district_code detected."
    assert len(set(names)) == 38,  "Duplicate district_name detected."

    cmda_count = sum(1 for d in districts if d["authority"] == AuthorityEnum.CMDA)
    assert cmda_count == 4, (
        f"Expected exactly 4 CMDA districts, found {cmda_count}."
    )

    hilly_count = sum(
        1 for d in districts
        if d["climate_zone"] == ClimateZoneEnum.HILLY_COLD
    )
    assert hilly_count == 3, (
        f"Expected 3 Hilly/Cold districts (Nilgiris, Theni, Tenkasi), "
        f"found {hilly_count}."
    )
    print(f"[Validation] OK — {len(districts)} districts, "
          f"{cmda_count} CMDA, {hilly_count} Hilly/Cold.")


# ---------------------------------------------------------------------------
# Seed runner
# ---------------------------------------------------------------------------

def seed_districts(drop_existing: bool = False) -> None:
    """
    Create tables and insert district rows.

    Args:
        drop_existing: If True, drops and recreates the table before seeding.
                       Use only in development; never in production.
    """
    _validate_dataset(DISTRICTS)

    if drop_existing:
        DistrictClimateMatrix.__table__.drop(engine, checkfirst=True)
        print("[DB] Dropped existing district_climate_matrix table.")

    Base.metadata.create_all(bind=engine)
    print("[DB] Tables created (if not existing).")

    db = SessionLocal()
    try:
        existing_count = db.query(DistrictClimateMatrix).count()
        if existing_count > 0 and not drop_existing:
            print(
                f"[Seed] Skipped — table already contains {existing_count} rows. "
                "Pass drop_existing=True to reseed."
            )
            return

        rows = [DistrictClimateMatrix(**d) for d in DISTRICTS]
        db.bulk_save_objects(rows)
        db.commit()
        print(f"[Seed] Successfully inserted {len(rows)} district records.")

    except Exception as exc:
        db.rollback()
        print(f"[Seed] ERROR — rolled back. Reason: {exc}")
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Seed the TN-Flow district_climate_matrix table."
    )
    parser.add_argument(
        "--drop",
        action="store_true",
        help="Drop and recreate the table before seeding (dev only).",
    )
    args = parser.parse_args()
    seed_districts(drop_existing=args.drop)
