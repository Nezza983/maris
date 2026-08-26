"""
Oil Model Wrapper
Initializes and configures OpenDrift's OpenOil model for spill simulation.
"""

import logging
from datetime import datetime, timedelta

import config
from opendrift.models.openoil import OpenOil

logger = logging.getLogger(__name__)


class OilSpillModel:
    """Wrapper around OpenDrift's OpenOil model."""

    def __init__(self):
        """Initialize the oil model."""
        self.model = None
        self.particles_released = False
        self.simulation_complete = False
        self.trajectories = None

    def initialize(self):
        """
        Initialize OpenOil model with configuration from config.py.

        Raises:
            Exception: If model initialization fails.
        """
        try:
            self.model = OpenOil(loglevel=0)
            logger.info("✓ OpenOil model initialized")

            # ================================================================
            # SYNTHETIC ENVIRONMENTAL CONDITIONS — MVP
            # ================================================================
            #
            # These constant values are currently derived from the mock
            # environmental data in config.py.
            #
            # Later, Module 3 / Copernicus data will replace these with
            # real OpenDrift readers.
            #
            # OpenDrift 1.14.10 supports environment:constant:* for
            # constant wind and ocean-current fields.
            # ================================================================

            self.model.set_config(
                "environment:constant:x_wind",
                -5.80
            )

            self.model.set_config(
                "environment:constant:y_wind",
                -2.70
            )

            self.model.set_config(
                "environment:constant:x_sea_water_velocity",
                -0.51
            )

            self.model.set_config(
                "environment:constant:y_sea_water_velocity",
                -0.61
            )

            # ================================================================
            # OIL / DIFFUSION CONFIGURATION
            # ================================================================

            self.model.set_config(
                "environment:constant:horizontal_diffusivity",
                0.1
            )

            self.model.set_config(
                "environment:constant:ocean_vertical_diffusivity",
                0.001
            )

            # Enable important OpenOil processes.
            self.model.set_config(
                "processes:emulsification",
                True
            )

            self.model.set_config(
                "processes:dispersion",
                True
            )

            logger.info("✓ Model configuration applied")

        except Exception as e:
            logger.error(
                f"Failed to initialize OpenOil: {e}"
            )
            raise

    def release_particles(
        self,
        latitude: float,
        longitude: float,
        timestamp: datetime,
        num_particles: int = None,
        oil_type: str = None
    ):
        """
        Release oil particles at a given location.

        Args:
            latitude (float):
                Spill latitude.

            longitude (float):
                Spill longitude.

            timestamp (datetime):
                When spill occurred.

            num_particles (int):
                Number of particles to release.

            oil_type (str):
                OpenOil oil type. If None, the value from config.py
                is used.

        Raises:
            RuntimeError:
                If the model has not been initialized.

            Exception:
                If particle release fails.
        """

        if self.model is None:
            raise RuntimeError(
                "Model not initialized. Call initialize() first."
            )

        if num_particles is None:
            num_particles = config.OPENDRIFT_CONFIG[
                "num_particles"
            ]

        if oil_type is None:
            oil_type = config.OPENDRIFT_CONFIG[
                "oil_type"
            ]

        try:
            logger.info(
                f"Releasing {num_particles} particles "
                f"using oil type: {oil_type}"
            )

            # ================================================================
            # RELEASE OIL PARTICLES
            # ================================================================
            #
            # OpenDrift/OpenOil 1.14.10 accepts oil_type directly
            # through seed_elements().
            # ================================================================

            self.model.seed_elements(
                lon=longitude,
                lat=latitude,
                time=timestamp,
                number=num_particles,
                oil_type=oil_type
            )

            self.particles_released = True

            logger.info(
                f"✓ Released {num_particles} particles "
                f"at ({latitude}, {longitude})"
            )

        except Exception as e:
            logger.error(
                f"Failed to release particles: {e}"
            )
            raise

    def set_environmental_data(
        self,
        wind_u: float,
        wind_v: float,
        current_u: float,
        current_v: float
    ):
        """
        Set environmental wind and current data.

        For the current MVP, constant OpenDrift environment values
        are used.

        In production, this method can be replaced/extended to use
        Module 3 Copernicus/xarray readers.

        Args:
            wind_u (float):
                Wind east-west component in m/s.

            wind_v (float):
                Wind north-south component in m/s.

            current_u (float):
                Current east-west component in m/s.

            current_v (float):
                Current north-south component in m/s.
        """

        if self.model is None:
            raise RuntimeError(
                "Model not initialized."
            )

        try:

            # Wind components.
            self.model.set_config(
                "environment:constant:x_wind",
                wind_u
            )

            self.model.set_config(
                "environment:constant:y_wind",
                wind_v
            )

            # Ocean current components.
            self.model.set_config(
                "environment:constant:x_sea_water_velocity",
                current_u
            )

            self.model.set_config(
                "environment:constant:y_sea_water_velocity",
                current_v
            )

            logger.info(
                "✓ Environmental data set: "
                f"wind=({wind_u:.2f}, {wind_v:.2f}) m/s, "
                f"current=({current_u:.2f}, {current_v:.2f}) m/s"
            )

        except Exception as e:
            logger.error(
                f"Failed to set environmental data: {e}"
            )
            raise

    def run_simulation(
        self,
        duration_hours: int,
        timestep_minutes: int = 60
    ):
        """
        Run the oil spill simulation.

        Args:
            duration_hours (int):
                How long to simulate in hours.

            timestep_minutes (int):
                Simulation timestep in minutes.

        Raises:
            RuntimeError:
                If particles have not been released.

            Exception:
                If simulation fails.
        """

        if not self.particles_released:
            raise RuntimeError(
                "No particles released. "
                "Call release_particles() first."
            )

        try:

            timestep_seconds = timestep_minutes * 60

            num_steps = int(
                (duration_hours * 3600)
                / timestep_seconds
            )

            logger.info(
                f"Starting simulation: "
                f"{duration_hours}h with "
                f"{num_steps} steps"
            )

            # ================================================================
            # RUN OPENDRIFT
            # ================================================================

            self.model.run(
                time_step=timedelta(
                    seconds=timestep_seconds
                ),
                steps=num_steps,
                outfile=None
            )

            self.simulation_complete = True

            logger.info(
                "✓ Simulation complete. "
                f"Final particle count: "
                f"{self.model.num_elements_total()}"
            )

        except Exception as e:
            logger.error(
                f"Simulation failed: {e}"
            )
            raise

    def get_trajectories(self):
        """
        Extract particle trajectories from completed simulation.

        Returns:
            dict:
                Trajectories containing timestamps,
                longitude, latitude, particle count,
                and timestep count.
        """

        if not self.simulation_complete:
            raise RuntimeError(
                "Simulation not complete. "
                "Call run_simulation() first."
            )

        try:

            result = self.model.result

            lon = result["lon"].values.T
            lat = result["lat"].values.T
            time = result["time"].values

            logger.info(
                f"✓ Extracted {len(time)} timesteps, "
                f"{lon.shape[1]} particles"
            )

            self.trajectories = {
                "time": time,
                "lon": lon,
                "lat": lat,
                "num_particles": lon.shape[1],
                "num_timesteps": len(time)
            }

            return self.trajectories

        except Exception as e:
            logger.error(
                f"Failed to extract trajectories: {e}"
            )
            raise

    def get_current_position(self):
        """
        Get the current/final position of oil particles.

        Returns:
            dict:
                Current longitude/latitude arrays,
                mean longitude/latitude,
                and particle count.
        """

        if not self.simulation_complete:
            raise RuntimeError(
                "Simulation not complete."
            )

        try:

            lon = self.model.elements.lon
            lat = self.model.elements.lat

            return {
                "lon": lon,
                "lat": lat,
                "lon_mean": float(lon.mean()),
                "lat_mean": float(lat.mean()),
                "num_particles": len(lon)
            }

        except Exception as e:
            logger.error(
                f"Failed to get current position: {e}"
            )
            raise