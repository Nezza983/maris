"""
Source Estimation
Estimate probable spill source using backward trajectory analysis.
"""

import logging
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple
import math

logger = logging.getLogger(__name__)

class SourceEstimator:
    """Estimate probable spill source from forward simulation data."""
    
    def __init__(self, detected_lat: float, detected_lon: float, 
                 detected_time: datetime):
        """
        Initialize source estimator.
        
        Args:
            detected_lat (float): Where spill was detected (lat)
            detected_lon (float): Where spill was detected (lon)
            detected_time (datetime): When spill was detected
        """
        self.detected_lat = detected_lat
        self.detected_lon = detected_lon
        self.detected_time = detected_time
        
        logger.info(f"✓ SourceEstimator initialized at ({detected_lat}, {detected_lon})")
    
    def estimate_from_backward_drift(self, 
                                     wind_u: float, wind_v: float,
                                     current_u: float, current_v: float,
                                     backtrack_hours: int = 24) -> Dict[str, Any]:
        """
        Estimate source using simple backward drift analysis.
        
        This is NOT a full reverse simulation, but a scientifically-reasonable
        approximation for MVP that traces back the mean drift path.
        
        Args:
            wind_u, wind_v (float): Wind components (m/s)
            current_u, current_v (float): Current components (m/s)
            backtrack_hours (int): How far back to trace
        
        Returns:
            dict: Estimated source location and confidence
        """
        
        # For MVP: assume constant drift
        # In production: run reverse simulation with OpenDrift
        
        # Total drift velocity = wind drift + ocean current
        # Wind typically drives oil more than current (wind drag ~2-3%)
        # We'll use empirical factors
        
        wind_drag_factor = 0.03      # Wind contributes ~3% of wind speed
        current_factor = 1.0         # Ocean current contributes fully
        
        # Calculate effective drift
        total_u = (wind_u * wind_drag_factor) + (current_u * current_factor)
        total_v = (wind_v * wind_drag_factor) + (current_v * current_factor)
        
        # Backtrack: drift is reversed
        backtrack_u = -total_u
        backtrack_v = -total_v
        
        # Distance traveled (m/s * seconds)
        backtrack_seconds = backtrack_hours * 3600
        delta_lon_m = backtrack_u * backtrack_seconds
        delta_lat_m = backtrack_v * backtrack_seconds
        
        # Convert meters to degrees (approximate)
        # 1 degree ≈ 111,000 meters
        delta_lon_deg = delta_lon_m / 111000
        delta_lat_deg = delta_lat_m / 111000
        
        # Estimated source
        source_lat = self.detected_lat + delta_lat_deg
        source_lon = self.detected_lon + delta_lon_deg
        
        # Confidence based on drift magnitude
        # Larger drift = lower confidence (more uncertainty)
        drift_distance_km = math.sqrt((delta_lon_deg * 111)**2 + (delta_lat_deg * 111)**2)
        
        if drift_distance_km < 5:
            confidence = 0.95  # Very close: high confidence
        elif drift_distance_km < 20:
            confidence = 0.75  # Moderate: medium confidence
        elif drift_distance_km < 50:
            confidence = 0.55  # Far: low confidence
        else:
            confidence = 0.35  # Very far: very low confidence
        
        logger.info(f"✓ Backward drift: {drift_distance_km:.1f} km over {backtrack_hours}h")
        logger.info(f"  Estimated source: ({source_lat:.4f}, {source_lon:.4f}), "
                   f"confidence: {confidence:.2f}")
        
        result = {
            'latitude': source_lat,
            'longitude': source_lon,
            'confidence': confidence,
            'method': 'backward_drift_trace_mvp',
            'drift_distance_km': drift_distance_km,
            'backtrack_hours': backtrack_hours,
            'notes': 'MVP approximation: constant drift backtracking. '
                    'Full reverse simulation recommended in production.'
        }
        
        return result
    
    def estimate_spill_age(self, detected_area_km2: float, 
                          estimated_area_km2: float) -> Dict[str, Any]:
        """
        Estimate spill age based on area growth.
        
        OPTIONAL feature: uses simple area growth model.
        
        Args:
            detected_area_km2 (float): Area at detection
            estimated_area_km2 (float): Current simulated extent
        
        Returns:
            dict: Age estimate and parameters
        """
        
        # Empirical oil spreading model (very simplified)
        # Slick area ≈ sqrt(time) for thick slicks
        # This is VERY approximate and should be validated with real data
        
        if detected_area_km2 <= 0 or estimated_area_km2 <= 0:
            logger.warning("Invalid areas for age estimation")
            return {
                'estimated_age_hours': None,
                'method': 'area_growth_mvp',
                'confidence': 0.2,
                'notes': 'Insufficient data. Do not rely on this estimate.'
            }
        
        # Simple model: area grows with sqrt(time)
        # A(t) = A0 * sqrt(t/t0)
        # Solving for t: t = t0 * (A(t) / A0)^2
        
        t0 = 1  # Reference time = 1 hour
        
        if estimated_area_km2 >= detected_area_km2:
            age_ratio = (estimated_area_km2 / detected_area_km2) ** 2
            estimated_age_hours = t0 * age_ratio
        else:
            # Area decreased? (shouldn't happen, but handle gracefully)
            estimated_age_hours = 0
        
        # Confidence is LOW for this MVP estimate
        confidence = 0.25  # Very unreliable
        
        logger.info(f"✓ Estimated spill age: {estimated_age_hours:.1f} hours "
                   f"(LOW confidence: {confidence:.2f})")
        
        result = {
            'estimated_age_hours': max(0, estimated_age_hours),
            'detected_area_km2': detected_area_km2,
            'current_area_km2': estimated_area_km2,
            'method': 'area_growth_mvp',
            'confidence': confidence,
            'notes': 'MVP area-growth model (VERY unreliable). Requires validation.'
        }
        
        return result
    
    def assess_risk_level(self, coastal_impact_prob: float, 
                         area_km2: float, 
                         drift_speed_ms: float) -> Dict[str, Any]:
        """
        Assess risk level based on multiple factors.
        
        Args:
            coastal_impact_prob (float): Probability of coastal impact (0-1)
            area_km2 (float): Spill extent (km²)
            drift_speed_ms (float): Mean drift velocity (m/s)
        
        Returns:
            dict: Risk assessment
        """
        
        # Scoring system
        coastal_score = coastal_impact_prob * 100  # 0-100
        area_score = min(area_km2 / 100 * 100, 100)  # 100 km² = max score
        speed_score = min(drift_speed_ms / 2 * 100, 100)  # 2 m/s = max
        
        # Weighted average (coastal impact heavily weighted)
        total_score = (coastal_score * 0.5) + (area_score * 0.3) + (speed_score * 0.2)
        
        # Risk classification
        if total_score >= 75:
            risk_level = "CRITICAL"
        elif total_score >= 50:
            risk_level = "HIGH"
        elif total_score >= 25:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"
        
        logger.info(f"✓ Risk assessment: {risk_level} (score: {total_score:.1f}/100)")
        
        result = {
            'risk_level': risk_level,
            'risk_score': total_score,
            'coastal_impact_probability': coastal_impact_prob,
            'components': {
                'coastal_score': coastal_score,
                'area_score': area_score,
                'speed_score': speed_score
            }
        }
        
        return result