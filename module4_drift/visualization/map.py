"""
Map Visualization
Create interactive Folium maps for spill visualization.
"""

import logging
from typing import Dict, List, Any
import folium
from folium import plugins
import json

logger = logging.getLogger(__name__)

class SpillMapVisualizer:
    """Create interactive maps of oil spill predictions."""
    
    def __init__(self, center_lat: float, center_lon: float, zoom_start: int = 8):
        """
        Initialize map.
        
        Args:
            center_lat (float): Map center latitude
            center_lon (float): Map center longitude
            zoom_start (int): Initial zoom level
        """
        self.map = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=zoom_start,
            tiles="OpenStreetMap"
        )
        
        logger.info(f"✓ Map initialized at ({center_lat}, {center_lon})")
    
    def add_spill_detection(self, latitude: float, longitude: float,
                           timestamp: str = None, confidence: float = None):
        """
        Add detected spill location marker.
        
        Args:
            latitude (float): Spill latitude
            longitude (float): Spill longitude
            timestamp (str): Detection timestamp
            confidence (float): Detection confidence
        """
        popup_text = "DETECTED SPILL"
        if timestamp:
            popup_text += f"<br/>Time: {timestamp}"
        if confidence:
            popup_text += f"<br/>Confidence: {confidence:.1%}"
        
        folium.Marker(
            location=[latitude, longitude],
            popup=popup_text,
            icon=folium.Icon(color='red', icon='info-sign'),
            tooltip='Detected spill location'
        ).add_to(self.map)
        
        logger.info(f"✓ Added detection marker at ({latitude}, {longitude})")
    
    def add_source_estimation(self, latitude: float, longitude: float,
                             confidence: float = None):
        """
        Add estimated source location.
        
        Args:
            latitude (float): Source latitude
            longitude (float): Source longitude
            confidence (float): Confidence score
        """
        popup_text = "ESTIMATED SOURCE"
        if confidence:
            popup_text += f"<br/>Confidence: {confidence:.1%}"
        
        folium.Marker(
            location=[latitude, longitude],
            popup=popup_text,
            icon=folium.Icon(color='orange', icon='location'),
            tooltip='Estimated source'
        ).add_to(self.map)
        
        logger.info(f"✓ Added source marker at ({latitude}, {longitude})")
    
    def add_trajectory(self, coordinates: List[List[float]], 
                      color: str = 'blue', weight: int = 2):
        """
        Add predicted trajectory as a line.
        
        Args:
            coordinates (list): List of [lat, lon] pairs
            color (str): Line color
            weight (int): Line width
        """
        # Convert [lon, lat] to [lat, lon] for Folium
        folium_coords = [[lat, lon] for lon, lat in coordinates]
        
        folium.PolyLine(
            locations=folium_coords,
            color=color,
            weight=weight,
            opacity=0.8,
            popup='Predicted trajectory'
        ).add_to(self.map)
        
        logger.info(f"✓ Added trajectory with {len(coordinates)} points")
    
    def add_spill_extent_polygon(self, geojson_polygon: Dict[str, Any],
                                color: str = 'purple', fill_opacity: float = 0.3):
        """
        Add spill extent polygon.
        
        Args:
            geojson_polygon (dict): GeoJSON Polygon geometry
            color (str): Border color
            fill_opacity (float): Fill transparency (0-1)
        """
        folium.GeoJson(
            geojson_polygon,
            style_function=lambda x: {
                'color': color,
                'fillOpacity': fill_opacity,
                'weight': 2
            },
            popup='Spill extent'
        ).add_to(self.map)
        
        logger.info("✓ Added spill extent polygon")
    
    def add_predicted_positions(self, positions: List[Dict[str, float]]):
        """
        Add predicted spill positions as markers.
        
        Args:
            positions (list): List of {latitude, longitude, time}
        """
        for i, pos in enumerate(positions):
            folium.CircleMarker(
                location=[pos['latitude'], pos['longitude']],
                radius=4,
                popup=f"T+{i*60}h",
                color='lightblue',
                fill_color='blue',
                fill_opacity=0.5,
                weight=1
            ).add_to(self.map)
        
        logger.info(f"✓ Added {len(positions)} predicted position markers")
    
    def add_risk_heatmap(self, risk_level: str = "HIGH"):
        """
        Add a title with risk assessment.
        
        Args:
            risk_level (str): Risk level (LOW, MEDIUM, HIGH, CRITICAL)
        """
        risk_colors = {
            "LOW": "green",
            "MEDIUM": "yellow",
            "HIGH": "orange",
            "CRITICAL": "red"
        }
        
        color = risk_colors.get(risk_level, "gray")
        
        # Add title/legend as HTML
        title_html = f'''
        <div style="position: fixed; 
                    top: 10px; right: 10px; width: 250px; 
                    background-color: white; border:2px solid grey; z-index:9999; 
                    font-size:14px; padding: 10px; border-radius: 5px;
                    box-shadow: 2px 2px 6px rgba(0,0,0,0.3);">
            <b>Oil Spill Risk Assessment</b><br/>
            Risk Level: <span style="color: {color}; font-weight: bold;">{risk_level}</span><br/>
            <small>Module 04 - OpenDrift Simulation</small>
        </div>
        '''
        
        self.map.get_root().html.add_child(folium.Element(title_html))
        logger.info(f"✓ Added risk indicator: {risk_level}")
    
    def save(self, filepath: str):
        """
        Save map to HTML file.
        
        Args:
            filepath (str): Output file path
        """
        try:
            self.map.save(filepath)
            logger.info(f"✓ Map saved to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save map: {e}")
            raise
    
    def get_html(self) -> str:
        """
        Get map as HTML string.
        
        Returns:
            str: HTML representation
        """
        return self.map._repr_html_()


def create_spill_map(detected_lat: float, detected_lon: float,
                    estimated_source_lat: float = None,
                    estimated_source_lon: float = None,
                    trajectory_coords: List[List[float]] = None,
                    extent_polygon: Dict = None,
                    predicted_positions: List[Dict] = None,
                    risk_level: str = "HIGH") -> SpillMapVisualizer:
    """
    Convenience function to create a complete spill map.
    
    Args:
        detected_lat (float): Detection latitude
        detected_lon (float): Detection longitude
        estimated_source_lat (float): Source latitude
        estimated_source_lon (float): Source longitude
        trajectory_coords (list): Trajectory coordinates [[lon, lat], ...]
        extent_polygon (dict): GeoJSON polygon
        predicted_positions (list): Future positions
        risk_level (str): Risk level
    
    Returns:
        SpillMapVisualizer: Map object
    """
    viz = SpillMapVisualizer(detected_lat, detected_lon, zoom_start=10)
    
    # Add detection
    viz.add_spill_detection(detected_lat, detected_lon)
    
    # Add source if provided
    if estimated_source_lat and estimated_source_lon:
        viz.add_source_estimation(estimated_source_lat, estimated_source_lon)
    
    # Add trajectory if provided
    if trajectory_coords:
        viz.add_trajectory(trajectory_coords)
    
    # Add extent if provided
    if extent_polygon:
        viz.add_spill_extent_polygon(extent_polygon)
    
    # Add predicted positions if provided
    if predicted_positions:
        viz.add_predicted_positions(predicted_positions)
    
    # Add risk
    viz.add_risk_heatmap(risk_level)
    
    logger.info("✓ Complete spill map created")
    return viz