"""
Environmental Data Processing
Handles wind, ocean currents, and temperature data.

In production, this loads from Copernicus Marine Service (Module 3).
For MVP, it returns mock data from config.
"""

import config
from typing import Dict, Any
import logging
import math

logger = logging.getLogger(__name__)

class EnvironmentalDataHandler:
    """Load and provide environmental data for OpenDrift simulations."""
    
    def __init__(self):
        """Initialize with mock data (production: load from Module 3)."""
        self.wind_speed_ms = None
        self.wind_direction_deg = None
        self.current_speed_ms = None
        self.current_direction_deg = None
        self.temperature_c = None
        
    def load_mock_data(self) -> Dict[str, Any]:
        """
        Load mock environmental data from config.
        
        Returns:
            dict: Environmental parameters
        """
        data = config.MOCK_ENVIRONMENTAL_DATA.copy()
        logger.info(f"✓ Loaded mock environmental data: {data}")
        
        self.wind_speed_ms = data['wind_speed_ms']
        self.wind_direction_deg = data['wind_direction_deg']
        self.current_speed_ms = data['current_speed_ms']
        self.current_direction_deg = data['current_direction_deg']
        self.temperature_c = data.get('sea_surface_temp_c', 25.0)
        
        return data
    
    def get_wind_vector(self) -> tuple:
        """
        Convert wind speed + direction to u, v components.
        
        Direction convention: 0° = North, 90° = East, 180° = South, 270° = West
        
        Returns:
            (u, v): Wind components in m/s
        """
        direction_rad = math.radians(self.wind_direction_deg)
        u = self.wind_speed_ms * math.sin(direction_rad)
        v = self.wind_speed_ms * math.cos(direction_rad)
        
        logger.debug(f"Wind vector: u={u:.2f}, v={v:.2f} m/s")
        return u, v
    
    def get_current_vector(self) -> tuple:
        """
        Convert current speed + direction to u, v components.
        
        Returns:
            (u, v): Current components in m/s
        """
        direction_rad = math.radians(self.current_direction_deg)
        u = self.current_speed_ms * math.sin(direction_rad)
        v = self.current_speed_ms * math.cos(direction_rad)
        
        logger.debug(f"Current vector: u={u:.2f}, v={v:.2f} m/s")
        return u, v
    
    def to_dict(self) -> Dict[str, Any]:
        """Export as dictionary for JSON serialization."""
        return {
            "wind_speed_ms": self.wind_speed_ms,
            "wind_direction_deg": self.wind_direction_deg,
            "current_speed_ms": self.current_speed_ms,
            "current_direction_deg": self.current_direction_deg,
            "sea_surface_temp_c": self.temperature_c,
        }


def load_environmental_data() -> EnvironmentalDataHandler:
    """Convenience function: load environment data."""
    env = EnvironmentalDataHandler()
    env.load_mock_data()
    return env