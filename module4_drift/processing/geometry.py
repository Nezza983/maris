"""
Geometry Processing
Create GeoJSON geometries from simulation results.
"""

import logging
from typing import Dict, List, Any, Tuple
import numpy as np

logger = logging.getLogger(__name__)

class GeometryProcessor:
    """Create and validate GeoJSON geometries."""
    
    @staticmethod
    def create_point(longitude: float, latitude: float, 
                    properties: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Create a GeoJSON Point.
        
        Args:
            longitude (float): Point longitude
            latitude (float): Point latitude
            properties (dict): Feature properties
        
        Returns:
            dict: GeoJSON Point Feature
        """
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [longitude, latitude]  # [lon, lat] in GeoJSON
            },
            "properties": properties or {}
        }
        
        return feature
    
    @staticmethod
    def create_linestring(coordinates: List[Tuple[float, float]],
                         properties: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Create a GeoJSON LineString.
        
        Args:
            coordinates (list): List of [lon, lat] tuples
            properties (dict): Feature properties
        
        Returns:
            dict: GeoJSON LineString Feature
        """
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates  # [[lon, lat], [lon, lat], ...]
            },
            "properties": properties or {}
        }
        
        return feature
    
    @staticmethod
    def create_polygon(coordinates: List[List[Tuple[float, float]]],
                      properties: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Create a GeoJSON Polygon.
        
        Args:
            coordinates (list): List of rings (each ring is list of [lon, lat])
                                First ring is exterior, rest are holes
            properties (dict): Feature properties
        
        Returns:
            dict: GeoJSON Polygon Feature
        """
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": coordinates
            },
            "properties": properties or {}
        }
        
        return feature
    
    @staticmethod
    def create_feature_collection(features: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Create a GeoJSON FeatureCollection.
        
        Args:
            features (list): List of GeoJSON Feature objects
        
        Returns:
            dict: GeoJSON FeatureCollection
        """
        collection = {
            "type": "FeatureCollection",
            "features": features
        }
        
        logger.info(f"✓ Created FeatureCollection with {len(features)} features")
        return collection
    
    @staticmethod
    def validate_coordinates(lon: float, lat: float) -> bool:
        """
        Validate geographic coordinates.
        
        Args:
            lon (float): Longitude (-180 to 180)
            lat (float): Latitude (-90 to 90)
        
        Returns:
            bool: True if valid
        """
        if not (-180 <= lon <= 180):
            logger.warning(f"Invalid longitude: {lon}")
            return False
        
        if not (-90 <= lat <= 90):
            logger.warning(f"Invalid latitude: {lat}")
            return False
        
        return True
    
    @staticmethod
    def convex_hull_from_points(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """
        Calculate convex hull from points using Graham's scan.
        
        Args:
            points (list): List of [lon, lat] tuples
        
        Returns:
            list: Hull points in order
        """
        try:
            from scipy.spatial import ConvexHull
            
            if len(points) < 3:
                logger.warning("Need at least 3 points for convex hull")
                return points
            
            hull = ConvexHull(points)
            hull_points = [tuple(points[i]) for i in hull.vertices]
            # Close the polygon
            if hull_points and hull_points[0] != hull_points[-1]:
                hull_points.append(hull_points[0])
            
            logger.info(f"✓ Computed convex hull with {len(hull_points)} vertices")
            return hull_points
            
        except ImportError:
            # Fallback: simple algorithm if scipy not available
            logger.warning("scipy not available, using simplified hull calculation")
            return GeometryProcessor._simple_convex_hull(points)
    
    @staticmethod
    def _simple_convex_hull(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """
        Simplified convex hull for fallback (Graham's scan approximation).
        
        Args:
            points (list): List of [lon, lat] tuples
        
        Returns:
            list: Hull points
        """
        if len(points) < 3:
            return points
        
        # Sort by x, then y
        sorted_points = sorted(set(points))
        
        if len(sorted_points) <= 2:
            return sorted_points
        
        # Build lower hull
        lower = []
        for p in sorted_points:
            while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
                lower.pop()
            lower.append(p)
        
        # Build upper hull
        upper = []
        for p in reversed(sorted_points):
            while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
                upper.pop()
            upper.append(p)
        
        # Concatenate and remove duplicates
        hull = lower[:-1] + upper[:-1]
        
        # Close the polygon
        if hull and hull[0] != hull[-1]:
            hull.append(hull[0])
        
        return hull


def cross(o: Tuple[float, float], a: Tuple[float, float], 
          b: Tuple[float, float]) -> float:
    """Cross product of vectors OA and OB."""
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])