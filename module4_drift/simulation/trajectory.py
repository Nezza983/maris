"""
Trajectory Processing
Calculate and analyze particle trajectories from OpenDrift simulation.
"""

import logging
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any
import math

logger = logging.getLogger(__name__)


class TrajectoryProcessor:
    """Process particle trajectories from simulation."""

    def __init__(self, trajectories: Dict[str, Any]):
        """
        Initialize with simulation trajectories.

        Args:
            trajectories (dict): Output from OilSpillModel.get_trajectories()
        """
        self.time = trajectories['time']
        self.lon = trajectories['lon']          # [timesteps, particles]
        self.lat = trajectories['lat']
        self.num_particles = trajectories['num_particles']
        self.num_timesteps = trajectories['num_timesteps']

        logger.info(
            f"✓ TrajectoryProcessor initialized: "
            f"{self.num_timesteps} timesteps, "
            f"{self.num_particles} particles"
        )

    def get_predicted_positions(
        self,
        sample_every_n_steps: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Extract predicted positions at regular intervals.

        Args:
            sample_every_n_steps (int): Sample every N timesteps (1 = all)

        Returns:
            list: List of position dicts with time, lat, lon
        """
        positions = []

        for i in range(
            0,
            self.num_timesteps,
            sample_every_n_steps
        ):
            # Calculate mean position of particles
            # at this timestep
            lon_mean = float(
                np.nanmean(self.lon[i, :])
            )
            lat_mean = float(
                np.nanmean(self.lat[i, :])
            )

            # ---------------------------------------------------------
            # Normalize timestamp to ISO-8601 UTC format
            # ---------------------------------------------------------
            time_value = self.time[i]

            if hasattr(time_value, "isoformat"):
                time_string = time_value.isoformat()
            else:
                time_string = str(time_value)

            # Ensure UTC marker is present exactly once.
            #
            # Example:
            # 2026-08-26T09:30:00.000000
            #       ↓
            # 2026-08-26T09:30:00.000000Z
            #
            # Also handle:
            # 2026-08-26T09:30:00+00:00
            #       ↓
            # 2026-08-26T09:30:00Z
            if time_string.endswith("+00:00"):
                time_string = time_string[:-6] + "Z"
            elif not time_string.endswith("Z"):
                time_string += "Z"

            positions.append({
                "time": time_string,
                "latitude": lat_mean,
                "longitude": lon_mean
            })

        logger.info(
            f"✓ Extracted {len(positions)} predicted positions"
        )

        return positions

    def get_trajectory_linestring(
        self,
        sample_every_n_steps: int = 1
    ) -> Dict[str, Any]:
        """
        Create a GeoJSON LineString of the spill trajectory.

        Args:
            sample_every_n_steps (int): Sample every N timesteps

        Returns:
            dict: GeoJSON LineString geometry
        """
        coordinates = []

        for i in range(
            0,
            self.num_timesteps,
            sample_every_n_steps
        ):
            lon_mean = float(
                np.nanmean(self.lon[i, :])
            )
            lat_mean = float(
                np.nanmean(self.lat[i, :])
            )

            # GeoJSON uses [longitude, latitude]
            coordinates.append([
                lon_mean,
                lat_mean
            ])

        geojson = {
            "type": "LineString",
            "coordinates": coordinates
        }

        logger.info(
            f"✓ Created trajectory LineString "
            f"with {len(coordinates)} points"
        )

        return geojson

    def estimate_spill_extent_polygon(
        self
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Create a convex hull polygon around final particle positions.

        Returns:
            (area_km2, geojson_polygon): Estimated area and polygon geometry
        """
        try:
            from shapely.geometry import MultiPoint, box
            from shapely.ops import unary_union
        except ImportError:
            logger.error(
                "Shapely not available. Cannot compute extent polygon."
            )
            return 0, None

        # Get final particle positions
        final_lon = self.lon[-1, :]
        final_lat = self.lat[-1, :]

        # Remove NaN values
        valid = ~(
            np.isnan(final_lon) |
            np.isnan(final_lat)
        )

        final_lon = final_lon[valid]
        final_lat = final_lat[valid]

        if len(final_lon) < 3:
            logger.warning(
                "Fewer than 3 valid particles. "
                "Cannot create extent polygon."
            )
            return 0, None

        # Create MultiPoint and compute convex hull
        points = MultiPoint(
            list(zip(final_lon, final_lat))
        )

        extent = points.convex_hull

        # Calculate area in km²
        # Simple approximation: 1 degree ≈ 111 km
        area_km2 = extent.area * (111 ** 2)

        # Convert to GeoJSON Polygon
        if extent.geom_type == 'Polygon':
            coords = list(extent.exterior.coords)

            geojson = {
                "type": "Polygon",
                "coordinates": [
                    [list(c) for c in coords]
                ]
            }

        else:
            # Fallback: create bounding box
            bounds = extent.bounds

            # bounds = (
            #     minx,
            #     miny,
            #     maxx,
            #     maxy
            # )

            geojson = {
                "type": "Polygon",
                "coordinates": [[
                    [bounds[0], bounds[1]],
                    [bounds[2], bounds[1]],
                    [bounds[2], bounds[3]],
                    [bounds[0], bounds[3]],
                    [bounds[0], bounds[1]]
                ]]
            }

        logger.info(
            f"✓ Extent polygon: {area_km2:.2f} km²"
        )

        return area_km2, geojson

    def estimate_coastal_impact_probability(
        self,
        coastline_polygon=None
    ) -> float:
        """
        Estimate probability of particles reaching coast.

        Args:
            coastline_polygon: Shapely Polygon of coastline
                               (None = skip)

        Returns:
            float: Probability 0-1
        """
        if coastline_polygon is None:
            # For MVP: simple heuristic based on particle drift
            # If particles move toward negative latitude
            # (southward), assume coastal risk

            # Check particle movement direction
            start_lat = np.nanmean(
                self.lat[0, :]
            )

            end_lat = np.nanmean(
                self.lat[-1, :]
            )

            # Simple heuristic:
            # if moving south/west, higher coastal impact
            lat_drift = start_lat - end_lat

            if lat_drift > 0.5:
                probability = 0.85

            elif lat_drift > 0.2:
                probability = 0.65

            else:
                probability = 0.35

            logger.info(
                f"✓ Estimated coastal impact probability: "
                f"{probability:.2f}"
            )

            return probability

        # Production: check if particles intersect with coastline
        logger.warning(
            "Coastline polygon not implemented in MVP"
        )

        return 0.5

    def get_particle_statistics(
        self
    ) -> Dict[str, Any]:
        """
        Calculate statistics about particle dispersal.

        Returns:
            dict: Statistics
        """
        # Final particle positions
        final_lon = self.lon[-1, :]
        final_lat = self.lat[-1, :]

        # Distance from starting point
        start_lon = np.nanmean(
            self.lon[0, :]
        )

        start_lat = np.nanmean(
            self.lat[0, :]
        )

        distances = []

        for i in range(len(final_lon)):
            if not (
                np.isnan(final_lon[i]) or
                np.isnan(final_lat[i])
            ):
                dist = calculate_distance(
                    start_lat,
                    start_lon,
                    final_lat[i],
                    final_lon[i]
                )

                distances.append(dist)

        if distances:
            distances = np.array(distances)

            stats = {
                'particles_active': int(
                    np.sum(~np.isnan(final_lon))
                ),
                'particles_lost': int(
                    np.sum(np.isnan(final_lon))
                ),
                'mean_drift_km': float(
                    np.mean(distances)
                ),
                'max_drift_km': float(
                    np.max(distances)
                ),
                'std_drift_km': float(
                    np.std(distances)
                )
            }

        else:
            stats = {
                'particles_active': 0,
                'particles_lost': len(final_lon),
                'mean_drift_km': 0,
                'max_drift_km': 0,
                'std_drift_km': 0
            }

        logger.info(
            f"✓ Particle statistics: "
            f"{stats['particles_active']} active, "
            f"mean drift "
            f"{stats['mean_drift_km']:.2f} km"
        )

        return stats


def calculate_distance(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float
) -> float:
    """
    Calculate distance between two points using Haversine formula.

    Returns:
        float: Distance in kilometers
    """
    R = 6371  # Earth radius in km

    dlat = math.radians(
        lat2 - lat1
    )

    dlon = math.radians(
        lon2 - lon1
    )

    a = (
        math.sin(dlat / 2) ** 2
        +
        math.cos(math.radians(lat1))
        *
        math.cos(math.radians(lat2))
        *
        math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )

    return R * c