"""
Module 04 Main Entry Point
Orchestrates the complete oil spill simulation pipeline.

WORKFLOW:
1. Load configuration
2. Load environmental conditions
3. Initialize OpenDrift
4. Configure environmental conditions
5. Release oil particles
6. Run forward simulation
7. Extract trajectories
8. Process trajectories
9. Estimate source (backtrack)
10. Calculate risk
11. Generate standardized JSON output
12. Generate visualization map
13. Print summary
"""

import logging
import json
import os
from datetime import datetime,timedelta, timezone 

import config

# Import our modules
from processing.environmental_data import load_environmental_data
from simulation.oil_model import OilSpillModel
from simulation.trajectory import TrajectoryProcessor
from simulation.source_estimation import SourceEstimator
from processing.geometry import GeometryProcessor
from visualization.map import create_spill_map


# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


def run_module_04_pipeline():
    """
    Execute the complete Module 04 pipeline.

    Returns:
        dict: Final output JSON
    """

    logger.info("=" * 80)
    logger.info("MODULE 04: Oil Spill Movement & Source Estimation")
    logger.info("=" * 80)

    try:

        # ====================================================================
        # STEP 1: LOAD CONFIGURATION AND INPUT DATA
        # ====================================================================

        logger.info("\n[STEP 1] Loading input data and configuration...")

        with open("integration_spill_input.json", "r") as f:
            spill_data = json.load(f)

        spill_lat = spill_data["latitude"]
        spill_lon = spill_data["longitude"]

        spill_time = datetime.fromisoformat(
            spill_data["timestamp"].replace("Z", "+00:00")
        ).replace(tzinfo=None)

        spill_confidence = spill_data.get("confidence",0.0)
        initial_area = spill_data.get("area_km2", 8.5)

        logger.info(
            f"Detected spill: "
            f"({spill_lat}, {spill_lon}) at {spill_time}"
        )

        logger.info(
            f"Confidence: {spill_confidence:.1%}, "
            f"Area: {initial_area} km²"
        )


        # ====================================================================
        # STEP 2: LOAD ENVIRONMENTAL DATA
        # ====================================================================

        logger.info("\n[STEP 2] Loading environmental data...")

        env_handler = load_environmental_data()
        env_data = env_handler.to_dict()

        # Convert environmental data to U/V vectors.
        wind_u, wind_v = env_handler.get_wind_vector()
        current_u, current_v = env_handler.get_current_vector()

        logger.info(
            f"Wind: "
            f"{env_data['wind_speed_ms']} m/s "
            f"@ {env_data['wind_direction_deg']}°"
        )

        logger.info(
            f"Current: "
            f"{env_data['current_speed_ms']} m/s "
            f"@ {env_data['current_direction_deg']}°"
        )

        logger.info(
            f"Wind vector: "
            f"({wind_u:.2f}, {wind_v:.2f}) m/s"
        )

        logger.info(
            f"Current vector: "
            f"({current_u:.2f}, {current_v:.2f}) m/s"
        )


        # ====================================================================
        # STEP 3: INITIALIZE OPENDRIFT / OPENOIL
        # ====================================================================

        logger.info(
            "\n[STEP 3] Initializing OpenDrift model..."
        )

        model = OilSpillModel()
        model.initialize()


        # ====================================================================
        # STEP 4: SET ENVIRONMENTAL CONDITIONS
        # ====================================================================
        #
        # IMPORTANT:
        # OpenDrift requires environmental configuration BEFORE
        # particles are seeded.
        #
        # Previously this happened after release_particles(), which caused:
        #
        # Cannot set config after elements have been seeded
        #
        # We therefore configure wind/current BEFORE particle release.
        # ====================================================================

        logger.info(
            "\n[STEP 4] Setting environmental conditions..."
        )

        model.set_environmental_data(
            wind_u=wind_u,
            wind_v=wind_v,
            current_u=current_u,
            current_v=current_v
        )


        # ====================================================================
        # STEP 5: RELEASE PARTICLES AT SPILL LOCATION
        # ====================================================================

        logger.info(
            "\n[STEP 5] Releasing oil particles..."
        )

        model.release_particles(
            latitude=spill_lat,
            longitude=spill_lon,
            timestamp=spill_time,
            num_particles=config.OPENDRIFT_CONFIG["num_particles"],
            oil_type=config.OPENDRIFT_CONFIG["oil_type"]
        )


        # ====================================================================
        # STEP 6: RUN FORWARD SIMULATION
        # ====================================================================

        logger.info(
            "\n[STEP 6] Running forward drift simulation..."
        )

        logger.info(
            f"Duration: "
            f"{config.SIMULATION_DURATION_HOURS} hours"
        )

        logger.info(
            f"Timestep: "
            f"{config.SIMULATION_TIME_STEP_MINUTES} minutes"
        )

        model.run_simulation(
            duration_hours=config.SIMULATION_DURATION_HOURS,
            timestep_minutes=config.SIMULATION_TIME_STEP_MINUTES
        )


        # ====================================================================
        # STEP 7: EXTRACT TRAJECTORIES
        # ====================================================================

        logger.info(
            "\n[STEP 7] Extracting particle trajectories..."
        )

        trajectories = model.get_trajectories()


        # ====================================================================
        # STEP 8: PROCESS TRAJECTORIES
        # ====================================================================

        logger.info(
            "\n[STEP 8] Processing trajectories..."
        )

        trajectory_proc = TrajectoryProcessor(
            trajectories
        )

        # Get predicted positions.
        predicted_positions = (
            trajectory_proc.get_predicted_positions(
                sample_every_n_steps=1
            )
        )

        # Get trajectory as GeoJSON LineString.
        trajectory_geojson = (
            trajectory_proc.get_trajectory_linestring(
                sample_every_n_steps=1
            )
        )

        # Estimate spill extent polygon.
        extent_area_km2, extent_polygon = (
            trajectory_proc.estimate_spill_extent_polygon()
        )

        # Get particle statistics.
        particle_stats = (
            trajectory_proc.get_particle_statistics()
        )

        logger.info(
            f"Final spill extent: "
            f"{extent_area_km2:.2f} km²"
        )

        logger.info(
            f"Particles active: "
            f"{particle_stats['particles_active']}"
        )


        # ====================================================================
        # STEP 9: ESTIMATE PROBABLE SOURCE
        # ====================================================================

        logger.info(
            "\n[STEP 9] Estimating probable spill source..."
        )

        source_estimator = SourceEstimator(
            spill_lat,
            spill_lon,
            spill_time
        )

        source_result = (
            source_estimator.estimate_from_backward_drift(
                wind_u=wind_u,
                wind_v=wind_v,
                current_u=current_u,
                current_v=current_v,
                backtrack_hours=(
                    config.SOURCE_ESTIMATION_CONFIG[
                        "backtrack_duration_hours"
                    ]
                )
            )
        )

        logger.info(
            f"Source: "
            f"({source_result['latitude']:.4f}, "
            f"{source_result['longitude']:.4f})"
        )

        logger.info(
            f"Confidence: "
            f"{source_result['confidence']:.2f}"
        )


        # ====================================================================
        # STEP 10: ASSESS RISK
        # ====================================================================

        logger.info(
            "\n[STEP 10] Assessing spill risk..."
        )

        # Estimate effective drift speed.
        drift_speed_ms = (
            env_data["wind_speed_ms"] * 0.03
            + env_data["current_speed_ms"]
        ) / 2

        # Estimate coastal impact.
        coastal_prob = (
            trajectory_proc
            .estimate_coastal_impact_probability()
        )

        # Calculate risk.
        risk_result = (
            source_estimator.assess_risk_level(
                coastal_impact_prob=coastal_prob,
                area_km2=extent_area_km2,
                drift_speed_ms=drift_speed_ms
            )
        )

        logger.info(
            f"Risk Level: "
            f"{risk_result['risk_level']}"
        )

        logger.info(
            f"Coastal Impact Probability: "
            f"{coastal_prob:.1%}"
        )


        # ====================================================================
        # STEP 11: BUILD STANDARDIZED OUTPUT JSON
        # ====================================================================

        logger.info(
            "\n[STEP 11] Building standardized JSON output..."
        )

        # Get final position from simulation.
        current_pos = model.get_current_position()

        output = {
            "spill_id": spill_data.get("spill_id", spill_data.get("image_id", "unknown")),

            "timestamp": (
                datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            ),

            "source_estimation": {
                "latitude": source_result["latitude"],
                "longitude": source_result["longitude"],
                "confidence": source_result["confidence"],
                "method": source_result["method"]
            },

            "spill_movement": {

                "current_position": {
                    "latitude": float(
                        current_pos["lat_mean"]
                    ),
                    "longitude": float(
                        current_pos["lon_mean"]
                    ),
                    "timestamp": (
                        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                    )
                },

                "predicted_positions": (
                    predicted_positions
                ),

                "trajectory_geometry": (
                    trajectory_geojson
                )
            },

            "spill_extent": {
                "area_km2": extent_area_km2,

                "geometry": (
                    extent_polygon
                    if extent_polygon
                    else {
                        "type": "Polygon",
                        "coordinates": []
                    }
                )
            },

            "environmental_conditions": env_data,

            "risk": {
                "risk_level": risk_result["risk_level"],
                "coastal_impact_probability": coastal_prob,
                "risk_score": risk_result["risk_score"]
            },

            "metadata": {
                "simulation_duration_hours": (
                    config.SIMULATION_DURATION_HOURS
                ),

                "num_particles": (
                    config.OPENDRIFT_CONFIG[
                        "num_particles"
                    ]
                ),

                "particle_count_at_end": (
                    particle_stats[
                        "particles_active"
                    ]
                ),

                "mean_drift_km": (
                    particle_stats[
                        "mean_drift_km"
                    ]
                ),

                "max_drift_km": (
                    particle_stats[
                        "max_drift_km"
                    ]
                )
            }
        }


        # ====================================================================
        # STEP 12: SAVE JSON OUTPUT
        # ====================================================================

        logger.info(
            "\n[STEP 12] Saving JSON output..."
        )

        # Make sure output directory exists.
        os.makedirs(
            os.path.dirname(
                config.GENERATED_JSON_PATH
            ),
            exist_ok=True
        )

        with open(
            config.GENERATED_JSON_PATH,
            "w"
        ) as f:

            json.dump(
                output,
                f,
                indent=2
            )

        logger.info(
            f"✓ JSON saved to "
            f"{config.GENERATED_JSON_PATH}"
        )


        # ====================================================================
        # STEP 13: CREATE FOLIUM VISUALIZATION
        # ====================================================================

        logger.info(
            "\n[STEP 13] Creating Folium map visualization..."
        )

        # Convert GeoJSON coordinates:
        # GeoJSON = [longitude, latitude]
        # Folium = [latitude, longitude]

        traj_latlon = [
            [lat, lon]
            for lon, lat
            in trajectory_geojson["coordinates"]
        ]

        map_viz = create_spill_map(

            detected_lat=spill_lat,

            detected_lon=spill_lon,

            estimated_source_lat=(
                source_result["latitude"]
            ),

            estimated_source_lon=(
                source_result["longitude"]
            ),

            trajectory_coords=traj_latlon,

            extent_polygon=extent_polygon,

            predicted_positions=(
                predicted_positions
            ),

            risk_level=(
                risk_result["risk_level"]
            )
        )

        map_viz.save(
            config.GENERATED_MAP_PATH
        )

        logger.info(
            f"✓ Map saved to "
            f"{config.GENERATED_MAP_PATH}"
        )


        # ====================================================================
        # STEP 14: PRINT FINAL SUMMARY
        # ====================================================================

        logger.info(
            "\n" + "=" * 80
        )

        logger.info(
            "PIPELINE COMPLETE - SUMMARY"
        )

        logger.info(
            "=" * 80
        )


        logger.info(
            "\nDETECTED SPILL:"
        )

        logger.info(
            f"  Location: "
            f"({spill_lat:.4f}, "
            f"{spill_lon:.4f})"
        )

        logger.info(
            f"  Initial area: "
            f"{initial_area} km²"
        )


        logger.info(
            "\nESTIMATED SOURCE:"
        )

        logger.info(
            f"  Location: "
            f"({source_result['latitude']:.4f}, "
            f"{source_result['longitude']:.4f})"
        )

        logger.info(
            f"  Confidence: "
            f"{source_result['confidence']:.1%}"
        )


        logger.info(
            "\nPREDICTED MOVEMENT:"
        )

        logger.info(
            f"  Final extent: "
            f"{extent_area_km2:.2f} km"
            f"²"
        )

        logger.info(
            f"  Mean drift: "
            f"{particle_stats['mean_drift_km']:.2f} km"
        )

        logger.info(
            f"  Max drift: "
            f"{particle_stats['max_drift_km']:.2f} km"
        )


        logger.info(
            "\nRISK ASSESSMENT:"
        )

        logger.info(
            f"  Risk level: "
            f"{risk_result['risk_level']}"
        )

        logger.info(
            f"  Coastal impact: "
            f"{coastal_prob:.1%}"
        )


        logger.info(
            "\nOUTPUTS:"
        )

        logger.info(
            f"  JSON: "
            f"{config.GENERATED_JSON_PATH}"
        )

        logger.info(
            f"  Map: "
            f"{config.GENERATED_MAP_PATH}"
        )


        logger.info(
            "\n" + "=" * 80
        )

        return output


    except Exception as e:

        logger.error(
            f"\nPIPELINE FAILED: {e}",
            exc_info=True
        )

        raise


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    result = run_module_04_pipeline()   