"""
Module 04 Configuration
All hardcoded values, mock data, and settings go here.
"""

import json
from datetime import datetime, timedelta

# ============================================================================
# SPILL PARAMETERS (INPUT)
# ============================================================================

# Example spill detection from Module 2
DETECTED_SPILL = {
    "spill_id": "SPILL_001",
    "timestamp": "2026-08-26T09:30:00Z",  # When detected
    "latitude": 12.3456,
    "longitude": 74.5678,
    "confidence": 0.89,
    "area_km2": 8.5,
}

# Simulation time window
SIMULATION_START_HOURS = 0  # Start from detection
SIMULATION_DURATION_HOURS = 72  # Predict 3 days ahead
SIMULATION_TIME_STEP_MINUTES = 60  # 1-hour steps

# ============================================================================
# MOCK ENVIRONMENTAL DATA
# ============================================================================
# In production, these come from Module 3 (Copernicus Marine Service)
# For MVP, we use constant/synthetic values

MOCK_ENVIRONMENTAL_DATA = {
    "wind_speed_ms": 6.4,           # meters/second
    "wind_direction_deg": 245,      # degrees (SW)
    "current_speed_ms": 0.8,        # meters/second
    "current_direction_deg": 220,   # degrees (SW)
    "sea_surface_temp_c": 28.5,     # Celsius (optional)
}

# ============================================================================
# OPENDRIFT CONFIGURATION
# ============================================================================

OPENDRIFT_CONFIG = {
    "num_particles": 1000,          # Number of oil particles to track
    "use_wind": True,
    "use_current": True,
    "use_buoyancy": True,           # Oil rises/sinks
    "use_turbulence": True,
    "oil_type": "GENERIC HEAVY CRUDE",  # OpenOil default type
    "simulation_timestep": 300,     # seconds
}

# ============================================================================
# SOURCE ESTIMATION (BACKTRACKING)
# ============================================================================

SOURCE_ESTIMATION_CONFIG = {
    "backtrack_duration_hours": 24,    # How far back to trace
    "backtrack_particles": 500,        # Fewer particles for speed
    "source_confidence_threshold": 0.5, # Min confidence to report
}

# ============================================================================
# OUTPUT SCHEMA
# ============================================================================

OUTPUT_SCHEMA_PATH = "schemas/output_schema.json"

# ============================================================================
# FILE PATHS
# ============================================================================

DATA_INPUT_DIR = "data/input"
DATA_OUTPUT_DIR = "data/output"

# Paths for generated outputs
GENERATED_MAP_PATH = "data/output/spill_map.html"
GENERATED_JSON_PATH = "data/output/module04_output.json"
GENERATED_TRAJECTORY_GEOJSON = "data/output/trajectory.geojson"

# ============================================================================
# LOGGING
# ============================================================================

LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR

print("✓ Config loaded successfully")