"""
Tamil Nadu Climate Data Module
================================
Source References:
  - India Meteorological Department (IMD) Climatological Tables 1981–2010
  - ISHRAE (Indian Society of Heating, Refrigerating and Air-Conditioning Engineers)
    Chapter 4: Climatic data for building design, 2016
  - NBC 2016 Part 8 Section 1: Climatic Data & Design
  - ECBC (Energy Conservation Building Code) 2017 — Climate Zone Map
  - Kotharkar et al., "Thermal comfort in outdoor spaces of Nagpur", 2014
  - CEPT Research: "Passive Cooling Strategies for Hot-Dry and Hot-Humid Climates"

ECBC Climate Zones relevant to Tamil Nadu:
  Zone 1 — Hot & Dry   (Madurai, Salem, Trichy, Vellore)
  Zone 2 — Warm & Humid (Chennai, Pondicherry, Nagapattinam, Kanyakumari)
  Zone 4 — Composite    (Coimbatore foothills — some months hot-dry, some warm-humid)
  Zone 5 — Temperate    (Ooty, Kodaikanal, Yercaud — highlands above 1000m ASL)
"""

# ── Monthly climate data for major Tamil Nadu stations ─────────────────────────
# Format: [Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sep, Oct, Nov, Dec]
# Data from IMD Climatological Normals 1981–2010

STATION_CLIMATE = {
    "Chennai": {
        "lat_lon": (13.08, 80.27),
        "altitude_m": 16,
        "ecbc_zone": "Warm & Humid",
        "avg_temp_max_c": [29.4, 31.3, 33.7, 35.6, 38.0, 37.0, 35.5, 35.4, 34.4, 32.1, 29.5, 28.2],
        "avg_temp_min_c": [19.4, 20.5, 22.7, 26.0, 28.0, 27.3, 26.0, 25.8, 25.3, 24.3, 22.0, 19.9],
        "avg_rh_morning_pct": [79, 77, 74, 73, 68, 72, 77, 78, 80, 83, 82, 81],
        "avg_rh_evening_pct": [60, 57, 56, 58, 58, 66, 70, 72, 74, 77, 72, 67],
        "avg_rainfall_mm": [35, 8, 13, 24, 52, 53, 88, 124, 119, 267, 309, 139],
        "sunshine_hrs_day": [9.3, 9.6, 9.9, 9.4, 8.7, 7.5, 7.0, 7.1, 7.2, 7.3, 7.8, 8.7],
        "prevailing_wind_dir": "SE",
        "avg_wind_speed_kmh": [11, 12, 14, 16, 19, 25, 24, 21, 18, 14, 11, 10],
        "design_summer_db_c": 38.0,       # dry-bulb design temp (ASHRAE 99.6%)
        "design_summer_wb_c": 28.5,       # wet-bulb design temp
        "degree_days_cooling": 3920,       # base 18.3°C
        "degree_days_heating": 0,
        "solar_radiation_kwh_m2_day": [4.8, 5.6, 6.2, 6.0, 5.8, 4.5, 4.3, 4.5, 4.7, 4.2, 4.0, 4.3],
    },
    "Madurai": {
        "lat_lon": (9.93, 78.12),
        "altitude_m": 101,
        "ecbc_zone": "Hot & Dry",
        "avg_temp_max_c": [31.4, 33.8, 36.5, 38.2, 38.5, 36.0, 34.5, 34.3, 34.0, 32.8, 30.5, 29.8],
        "avg_temp_min_c": [20.3, 21.5, 23.8, 26.4, 27.9, 26.8, 25.8, 25.5, 25.0, 24.2, 21.8, 20.2],
        "avg_rh_morning_pct": [72, 68, 60, 54, 55, 65, 71, 73, 74, 74, 73, 74],
        "avg_rh_evening_pct": [41, 37, 30, 27, 30, 44, 51, 52, 51, 48, 44, 44],
        "avg_rainfall_mm": [18, 8, 12, 35, 60, 31, 55, 79, 104, 162, 115, 38],
        "sunshine_hrs_day": [9.6, 9.9, 10.2, 10.1, 9.4, 7.0, 6.8, 7.0, 7.4, 7.9, 8.8, 9.2],
        "prevailing_wind_dir": "SW",
        "avg_wind_speed_kmh": [7, 8, 11, 14, 16, 18, 17, 15, 12, 9, 7, 7],
        "design_summer_db_c": 40.5,
        "design_summer_wb_c": 27.0,
        "degree_days_cooling": 4200,
        "degree_days_heating": 0,
        "solar_radiation_kwh_m2_day": [5.2, 6.0, 6.8, 6.6, 6.3, 5.0, 4.8, 5.0, 5.3, 5.0, 4.8, 4.9],
    },
    "Coimbatore": {
        "lat_lon": (11.02, 76.96),
        "altitude_m": 417,
        "ecbc_zone": "Composite",
        "avg_temp_max_c": [30.0, 32.8, 35.5, 36.0, 34.5, 30.5, 29.8, 30.0, 30.2, 29.8, 28.5, 28.2],
        "avg_temp_min_c": [17.6, 19.3, 21.8, 24.0, 24.4, 22.8, 21.8, 22.0, 22.2, 22.0, 19.8, 18.0],
        "avg_rh_morning_pct": [76, 70, 63, 60, 63, 75, 79, 79, 79, 82, 82, 81],
        "avg_rh_evening_pct": [45, 40, 35, 35, 42, 57, 62, 62, 61, 59, 55, 50],
        "avg_rainfall_mm": [10, 8, 16, 73, 96, 40, 53, 65, 88, 168, 76, 22],
        "sunshine_hrs_day": [9.1, 9.5, 10.1, 9.7, 8.5, 5.5, 5.2, 5.5, 6.0, 6.5, 7.5, 8.5],
        "prevailing_wind_dir": "SW",
        "avg_wind_speed_kmh": [14, 15, 17, 18, 16, 18, 17, 16, 14, 12, 12, 12],
        "design_summer_db_c": 37.5,
        "design_summer_wb_c": 25.8,
        "degree_days_cooling": 3100,
        "degree_days_heating": 80,
        "solar_radiation_kwh_m2_day": [5.0, 5.8, 6.5, 6.2, 5.7, 4.0, 3.9, 4.2, 4.5, 4.3, 4.5, 4.8],
    },
    "Ooty": {
        "lat_lon": (11.41, 76.70),
        "altitude_m": 2240,
        "ecbc_zone": "Temperate",
        "avg_temp_max_c": [19.9, 21.8, 23.0, 22.8, 21.0, 17.8, 17.5, 17.8, 18.5, 18.8, 18.5, 18.2],
        "avg_temp_min_c": [5.5, 7.2, 9.8, 12.0, 12.2, 12.0, 12.0, 12.2, 12.0, 11.5, 8.8, 6.0],
        "avg_rh_morning_pct": [83, 79, 74, 73, 75, 90, 93, 93, 91, 90, 88, 86],
        "avg_rh_evening_pct": [57, 53, 51, 55, 63, 80, 84, 83, 80, 76, 70, 61],
        "avg_rainfall_mm": [22, 25, 32, 82, 135, 178, 195, 163, 119, 183, 65, 30],
        "sunshine_hrs_day": [7.5, 8.0, 7.5, 6.5, 5.5, 3.0, 2.5, 3.0, 4.0, 4.5, 5.5, 6.5],
        "prevailing_wind_dir": "NE",
        "avg_wind_speed_kmh": [10, 11, 13, 14, 12, 8, 7, 7, 8, 9, 9, 9],
        "design_summer_db_c": 24.0,
        "design_summer_wb_c": 16.0,
        "degree_days_cooling": 350,
        "degree_days_heating": 950,
        "solar_radiation_kwh_m2_day": [3.8, 4.5, 4.8, 4.5, 4.0, 2.2, 2.0, 2.3, 3.0, 3.2, 3.5, 3.8],
    },
}

# ── Thermal comfort thresholds (ASHRAE 55 / adaptive model for Indian climates)
COMFORT_THRESHOLDS = {
    "hot_humid": {
        "comfort_temp_range_c": (24, 31),     # Szokolay adaptive model
        "max_acceptable_rh_pct": 80,
        "min_air_speed_m_s": 0.5,            # to compensate for heat
        "effective_temp_upper_c": 29.5,
    },
    "hot_dry": {
        "comfort_temp_range_c": (22, 32),
        "max_acceptable_rh_pct": 60,
        "min_air_speed_m_s": 0.3,
        "effective_temp_upper_c": 31.0,
    },
    "composite": {
        "comfort_temp_range_c": (22, 30),
        "max_acceptable_rh_pct": 75,
        "min_air_speed_m_s": 0.4,
        "effective_temp_upper_c": 29.0,
    },
    "temperate_cool": {
        "comfort_temp_range_c": (18, 26),
        "max_acceptable_rh_pct": 70,
        "min_air_speed_m_s": 0.1,
        "effective_temp_upper_c": 26.0,
    },
}

# ── Passive design strategy selection based on climate
# Source: Olgyay & Olgyay "Design with Climate" + CEPT passive cooling guide
PASSIVE_STRATEGIES = {
    "hot_humid": {
        "primary": ["cross_ventilation", "shading", "high_mass_walls"],
        "secondary": ["evaporative_cooling", "courtyard", "elevated_floor"],
        "avoid": ["sealed_envelope", "east_west_glazing"],
        "wall_u_value_target": 1.2,    # W/m²K
        "roof_u_value_target": 0.8,
        "window_to_wall_ratio": 0.30,  # 30% WWR for cross-vent
        "overhang_projection_m": 0.9,
    },
    "hot_dry": {
        "primary": ["thermal_mass", "courtyard", "night_ventilation"],
        "secondary": ["evaporative_cooling", "small_windows", "thick_walls"],
        "avoid": ["large_glazing", "low_mass"],
        "wall_u_value_target": 0.8,
        "roof_u_value_target": 0.5,
        "window_to_wall_ratio": 0.15,  # smaller openings
        "overhang_projection_m": 1.2,
    },
    "composite": {
        "primary": ["shading", "cross_ventilation", "thermal_mass"],
        "secondary": ["courtyard", "night_purge", "high_ceilings"],
        "avoid": ["west_glazing"],
        "wall_u_value_target": 1.0,
        "roof_u_value_target": 0.6,
        "window_to_wall_ratio": 0.25,
        "overhang_projection_m": 1.0,
    },
    "temperate_cool": {
        "primary": ["south_glazing", "thermal_mass", "compact_form"],
        "secondary": ["wind_protection", "double_glazing", "earth_berming"],
        "avoid": ["excessive_ventilation", "large_north_windows"],
        "wall_u_value_target": 0.6,
        "roof_u_value_target": 0.4,
        "window_to_wall_ratio": 0.20,
        "overhang_projection_m": 0.5,
    },
}

# ── Sun angles for Tamil Nadu latitudes (for shading design)
# Source: Solar Geometry, CEPT + NBC 2016 Appendix C
SUN_ANGLES = {
    "Chennai_lat13": {
        "summer_solstice_alt_noon": 77.5,    # degrees above horizon at noon (Jun 21)
        "winter_solstice_alt_noon": 53.5,    # degrees (Dec 21)
        "equinox_alt_noon": 66.9,
        "recommended_overhang_ratio": 0.25,  # overhang depth / window height
    },
    "Madurai_lat10": {
        "summer_solstice_alt_noon": 80.5,
        "winter_solstice_alt_noon": 56.5,
        "equinox_alt_noon": 69.9,
        "recommended_overhang_ratio": 0.22,
    },
    "Coimbatore_lat11": {
        "summer_solstice_alt_noon": 79.5,
        "winter_solstice_alt_noon": 55.5,
        "equinox_alt_noon": 68.9,
        "recommended_overhang_ratio": 0.23,
    },
    "Ooty_lat11.4": {
        "summer_solstice_alt_noon": 79.1,
        "winter_solstice_alt_noon": 55.1,
        "equinox_alt_noon": 68.5,
        "recommended_overhang_ratio": 0.30,  # deeper for heavy rain/fog
    },
}

# ── Wind rose data (primary + secondary wind directions by season)
# Source: IMD Wind Atlas of India 2010
WIND_ROSE = {
    "Chennai": {
        "Jan–Feb":   {"dominant": "NE",  "secondary": "N",   "speed_kmh": 11},
        "Mar–May":   {"dominant": "SE",  "secondary": "E",   "speed_kmh": 16},
        "Jun–Sep":   {"dominant": "SE",  "secondary": "SW",  "speed_kmh": 23},
        "Oct–Dec":   {"dominant": "NE",  "secondary": "N",   "speed_kmh": 13},
        "annual_dominant": "SE",
    },
    "Madurai": {
        "Jan–Feb":   {"dominant": "SW",  "secondary": "W",   "speed_kmh": 7},
        "Mar–May":   {"dominant": "SW",  "secondary": "SE",  "speed_kmh": 14},
        "Jun–Sep":   {"dominant": "SW",  "secondary": "W",   "speed_kmh": 17},
        "Oct–Dec":   {"dominant": "NE",  "secondary": "N",   "speed_kmh": 8},
        "annual_dominant": "SW",
    },
    "Coimbatore": {
        "Jan–Feb":   {"dominant": "SW",  "secondary": "NE",  "speed_kmh": 14},
        "Mar–May":   {"dominant": "SW",  "secondary": "W",   "speed_kmh": 17},
        "Jun–Sep":   {"dominant": "SW",  "secondary": "W",   "speed_kmh": 18},
        "Oct–Dec":   {"dominant": "NE",  "secondary": "E",   "speed_kmh": 12},
        "annual_dominant": "SW",
    },
}
