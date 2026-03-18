"""
Tamil Nadu Local Building Materials Database
=============================================
Source References:
  - Laurie Baker, "Cost Effective Architecture" (COSTFORD, Thiruvananthapuram, 1986)
  - Laurie Baker, "Homes for the Masses" (COSTFORD, 1993)
  - BIS IS 3495: Methods of Test for Burnt Clay Building Bricks
  - BIS IS 2212: Code of Practice for Brickwork
  - CBRI Technical Report on Rat-Trap Bond Masonry, 2008
  - CEPT University, "Thermal Performance of Traditional Indian Walling Materials", 2014
  - TERI Report: "Energy Efficiency through Passive Design in South Indian Homes", 2018
  - National Institute of Rural Development (NIRD), "Low-Cost Housing Technologies", 2015
  - Madurai Institute of Architecture field survey data on local material costs (2023–24)
  - PWD Tamil Nadu Schedule of Rates (SoR) 2023–24

U-Values and thermal properties from:
  - ASHRAE Fundamentals Handbook 2021, Chapter 26
  - ECBC 2017 Annexure — Material Properties for Indian Construction
  - NBC 2016, Part 8 Section 1, Appendix B — Thermal Properties
"""

MATERIALS_DATABASE = {

    # ── WALLING MATERIALS ──────────────────────────────────────────────────
    "rat_trap_bond_brick": {
        "category": "Walling",
        "full_name": "Rat-Trap Bond Brickwork (Country Brick)",
        "thickness_mm": 230,
        "thermal_conductivity_w_mk": 0.58,   # W/mK — CEPT 2014
        "thermal_resistance_m2k_w": 0.397,
        "u_value_w_m2k": 1.8,                # overall with air cavity
        "thermal_mass_kj_m2k": 220,          # ECBC 2017 Appendix
        "density_kg_m3": 1400,               # hollow/cavity reduces density
        "compressive_strength_n_mm2": 3.5,
        "water_absorption_pct": 12,
        "brick_size_mm": "230×110×75",
        "mortar": "Lime-sand (1:3) or Cement-lime-sand (1:1:6)",
        "cost_per_sqm_inr_2024": 850,         # plastered wall, PWD SoR 2023–24
        "brick_saving_vs_solid_pct": 25,      # 25% fewer bricks than solid 230mm
        "embodied_energy_gj_m3": 2.1,
        "co2_kg_per_m2_wall": 28,
        "laurie_baker_reference": (
            "Baker's signature walling technique — cavity between two 110mm brick "
            "leaves traps air, reducing heat conduction by ~30%. Documented in "
            "'Cost Effective Architecture' (COSTFORD, 1986), pp. 34–41."
        ),
        "climate_suitability": ["hot_humid", "hot_dry", "composite"],
        "advantages": [
            "25% brick savings over solid masonry",
            "Cavity provides thermal insulation (U ≈ 1.8 W/m²K vs 3.5 for solid)",
            "Reduces indoor temperature by 2–4°C (CBRI 2008)",
            "Can use country/local bricks — supports local economy",
            "Allows lime plaster — breathable wall prevents salt efflorescence",
        ],
        "source": "Baker 1986; IS 2212; CBRI Technical Report 2008; CEPT 2014",
    },

    "fly_ash_brick": {
        "category": "Walling",
        "full_name": "Fly Ash Brick (Class C, 230×110×70mm)",
        "thickness_mm": 230,
        "thermal_conductivity_w_mk": 0.72,
        "u_value_w_m2k": 2.4,
        "thermal_mass_kj_m2k": 195,
        "density_kg_m3": 1800,
        "compressive_strength_n_mm2": 7.5,   # IS 3495
        "water_absorption_pct": 8,
        "cost_per_sqm_inr_2024": 750,
        "embodied_energy_gj_m3": 1.4,        # recycled fly ash — lower embodied energy
        "co2_kg_per_m2_wall": 18,
        "advantages": [
            "Uses industrial waste (fly ash from thermal plants)",
            "Reduced cement content vs. clay brick",
            "Lower weight — reduces structural load",
            "Good thermal mass",
        ],
        "climate_suitability": ["hot_humid", "hot_dry", "composite"],
        "source": "IS 12894; NIRD 2015; ECBC 2017 Appendix",
    },

    "aac_block": {
        "category": "Walling",
        "full_name": "Autoclaved Aerated Concrete (AAC) Block — 200mm",
        "thickness_mm": 200,
        "thermal_conductivity_w_mk": 0.16,
        "u_value_w_m2k": 0.7,               # excellent insulator
        "thermal_mass_kj_m2k": 60,          # low thermal mass
        "density_kg_m3": 600,
        "compressive_strength_n_mm2": 3.0,
        "water_absorption_pct": 20,
        "cost_per_sqm_inr_2024": 1100,
        "embodied_energy_gj_m3": 3.2,
        "co2_kg_per_m2_wall": 35,
        "advantages": [
            "Very low U-value — best thermal insulation in list",
            "Lightweight — reduces structural cost",
            "Fast construction speed",
            "Good for AC buildings — reduces cooling load",
        ],
        "disadvantages": [
            "Low thermal mass — poor for passive design without AC",
            "Higher initial cost",
            "Not traditional/local for Tamil Nadu",
        ],
        "climate_suitability": ["composite"],  # best with AC; poor passively
        "source": "IS 2185 Part 3; ECBC 2017; Manufacturer data (Ultratech, 2024)",
    },

    "country_brick_solid_115mm": {
        "category": "Walling",
        "full_name": "Country/Table-Moulded Clay Brick — 115mm solid",
        "thickness_mm": 115,
        "thermal_conductivity_w_mk": 0.81,
        "u_value_w_m2k": 3.5,
        "thermal_mass_kj_m2k": 170,
        "density_kg_m3": 1900,
        "compressive_strength_n_mm2": 3.5,  # IS 3495 Class 3
        "water_absorption_pct": 15,
        "cost_per_sqm_inr_2024": 650,
        "embodied_energy_gj_m3": 2.8,
        "co2_kg_per_m2_wall": 42,
        "advantages": ["Locally available across TN", "Traditional material", "Good thermal mass"],
        "disadvantages": ["High U-value — poor insulation", "Consumes agricultural topsoil"],
        "climate_suitability": ["all — sub-optimal thermally"],
        "source": "IS 3495; CEPT 2014; PWD SoR 2023–24",
    },

    # ── ROOFING MATERIALS ──────────────────────────────────────────────────
    "mangalore_tile_timber_roof": {
        "category": "Roofing",
        "full_name": "Mangalore Tile on Timber Rafter + Mud Mortar",
        "u_value_w_m2k": 1.4,
        "solar_reflectance": 0.45,
        "thermal_emittance": 0.90,
        "thermal_mass_kj_m2k": 140,
        "cost_per_sqm_inr_2024": 900,
        "embodied_energy_gj_m2": 0.3,
        "laurie_baker_reference": (
            "Baker's preferred roof for coastal Tamil Nadu — terracotta tile naturally "
            "self-ventilating, air gap between tile and wooden rafter reduces heat gain. "
            "Ref: Baker, 'Roofscapes', COSTFORD Technical Note No. 5, 1989."
        ),
        "advantages": [
            "Natural terracotta — local material (Mangalore, Karur)",
            "Air cavity below tile reduces heat flux significantly",
            "Breathable — avoids condensation in humid climates",
            "Traditional Tamil Nadu aesthetic",
        ],
        "climate_suitability": ["hot_humid", "composite"],
        "source": "Baker 1989; TERI 2018; CEPT 2014",
    },

    "rcc_flat_roof_no_insulation": {
        "category": "Roofing",
        "full_name": "RCC Flat Roof (150mm slab) — no insulation",
        "u_value_w_m2k": 3.8,               # very poor — common in TN
        "solar_reflectance": 0.25,
        "thermal_emittance": 0.85,
        "thermal_mass_kj_m2k": 350,
        "cost_per_sqm_inr_2024": 1400,
        "embodied_energy_gj_m2": 0.9,
        "disadvantages": [
            "Very high U-value — heats interior drastically",
            "ECBC 2017 non-compliant (requires ≤ 1.5 W/m²K in TN)",
            "Surface temperature can reach 65°C in Madurai summer",
        ],
        "climate_suitability": ["not recommended without insulation"],
        "source": "ECBC 2017; TERI 2018; NBC 2016 Part 8",
    },

    "rcc_flat_roof_inverted_insulation": {
        "category": "Roofing",
        "full_name": "RCC Flat Roof + XPS Insulation (75mm) + China Mosaic",
        "u_value_w_m2k": 0.60,
        "solar_reflectance": 0.70,          # white china mosaic
        "thermal_emittance": 0.88,
        "thermal_mass_kj_m2k": 320,
        "cost_per_sqm_inr_2024": 1900,
        "embodied_energy_gj_m2": 1.2,
        "advantages": [
            "ECBC 2017 compliant",
            "China mosaic reflects 70% solar radiation",
            "Reduces cooling load by 30–40%",
        ],
        "climate_suitability": ["hot_humid", "hot_dry", "composite"],
        "source": "ECBC 2017; TERI 2018; IS 3346",
    },

    # ── FLOOR MATERIALS ────────────────────────────────────────────────────
    "athangudi_tile": {
        "category": "Flooring",
        "full_name": "Athangudi Tile (Traditional TN Handmade Cement Tile)",
        "thermal_conductivity_w_mk": 1.20,
        "cost_per_sqm_inr_2024": 550,       # handmade — varies widely
        "origin": "Chettinad region, Sivaganga district, Tamil Nadu",
        "advantages": [
            "Unique Tamil Nadu heritage product — supports local artisans",
            "Natural pigments — no industrial dyes",
            "Remains cool underfoot — good thermal conductivity",
            "Durable (50+ year lifespan with care)",
        ],
        "climate_suitability": ["hot_humid", "hot_dry", "composite"],
        "source": "NIRD 2015; GI Tag documentation — Athangudi Tile (TN), 2020",
    },

    "kota_stone": {
        "category": "Flooring",
        "full_name": "Kota Stone (Fine-grained limestone, natural finish)",
        "thermal_conductivity_w_mk": 1.80,
        "cost_per_sqm_inr_2024": 420,
        "advantages": ["Natural, cool underfoot", "Low cost", "Durable"],
        "climate_suitability": ["hot_humid", "hot_dry"],
        "source": "PWD SoR 2023–24; BIS 1124",
    },

    # ── MORTARS & PLASTERS ─────────────────────────────────────────────────
    "lime_mortar": {
        "category": "Mortar/Plaster",
        "full_name": "Lime-Sand Mortar (1:3 hydraulic lime : sand)",
        "compressive_strength_n_mm2": 1.5,
        "water_absorption_pct": "permeable — self-sealing",
        "thermal_conductivity_w_mk": 0.80,
        "cost_vs_cement_mortar": "20% cheaper (lime locally available in TN)",
        "laurie_baker_reference": (
            "Baker insisted on lime mortar for breathability — walls 'breathe', "
            "moisture escapes, preventing salt crystallisation damage. "
            "Ref: Baker, 'Brick as a Building Material', COSTFORD Bulletin 12, 1984."
        ),
        "advantages": [
            "Breathable — water vapour can escape through walls",
            "Self-healing micro-cracks (carbonation of lime)",
            "Lower embodied energy than OPC cement mortar",
            "Traditional — compatible with country brick",
        ],
        "source": "Baker 1984; IS 712; BS EN 998-1",
    },

    "jali_screen_brick": {
        "category": "Ventilation Element",
        "full_name": "Brick Jali Screen (perforated brick lattice)",
        "airflow_reduction_factor": 0.15,   # 15% of opening is solid, 85% open
        "solar_shading_coefficient": 0.75,
        "wind_filtering": "Reduces dust ingress by 40% (CBRI 2008 test)",
        "cost_per_sqm_inr_2024": 1100,
        "laurie_baker_reference": (
            "Jali screens are Baker's answer to the humidity-heat paradox: "
            "they allow maximum airflow while blocking direct solar radiation and rain. "
            "Ref: Baker, 'The Jali as Climate Modifier', Architecture+Design, 1996."
        ),
        "climate_suitability": ["hot_humid", "composite"],
        "source": "Baker 1996; CBRI 2008",
    },
}

def get_materials_for_climate(climate_type: str) -> list:
    """
    Return recommended materials for a given climate type.
    """
    return [
        {"name": k, **{p: v for p, v in m.items() if p != "category"}, "category": m["category"]}
        for k, m in MATERIALS_DATABASE.items()
        if climate_type in m.get("climate_suitability", []) or
           "all" in str(m.get("climate_suitability", []))
    ]

def get_material_summary_table() -> list:
    """
    Returns a simplified list of all materials for tabular display.
    """
    rows = []
    for key, m in MATERIALS_DATABASE.items():
        rows.append({
            "Material": m["full_name"],
            "Category": m["category"],
            "U-Value (W/m²K)": m.get("u_value_w_m2k", "—"),
            "Thermal Mass (kJ/m²K)": m.get("thermal_mass_kj_m2k", "—"),
            "Cost/m² (₹)": m.get("cost_per_sqm_inr_2024", "—"),
            "CO₂ (kg/m²)": m.get("co2_kg_per_m2_wall", "—"),
            "Climate Fit": ", ".join(m.get("climate_suitability", ["all"])),
        })
    return rows
