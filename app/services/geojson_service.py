"""
GeoJSON generation service
Converts detection results to GeoJSON format
"""
import json
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class GeoJsonService:
    """Service for generating GeoJSON output"""
    
    @staticmethod
    def create_feature_collection(features: List[Dict], crs_name: str = "urn:ogc:def:crs:EPSG::4326"):
        """
        Create a GeoJSON FeatureCollection.
        
        Args:
            features: List of GeoJSON features
            crs_name: CRS identifier (default: WGS84)
        
        Returns:
            Dictionary representing a GeoJSON FeatureCollection
        """
        return {
            "type": "FeatureCollection",
            "name": "tree-detection-results",
            "crs": {
                "type": "name",
                "properties": {
                    "name": crs_name
                }
            },
            "features": features
        }
    
    @staticmethod
    def create_point_feature(coordinates: List[float], properties: Dict, feature_id: int = None):
        """
        Create a GeoJSON Point feature.
        
        Args:
            coordinates: [longitude, latitude]
            properties: Feature properties
            feature_id: Optional feature ID
        
        Returns:
            GeoJSON Point feature dictionary
        """
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": coordinates
            },
            "properties": properties
        }
        
        if feature_id is not None:
            feature["properties"]["id"] = feature_id
        
        return feature
    
    @staticmethod
    def create_linestring_feature(coordinates: List[List[float]], properties: Dict, feature_id: int = None):
        """
        Create a GeoJSON LineString feature.
        
        Args:
            coordinates: List of [longitude, latitude] pairs
            properties: Feature properties
            feature_id: Optional feature ID
        
        Returns:
            GeoJSON LineString feature dictionary
        """
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates
            },
            "properties": properties
        }
        
        if feature_id is not None:
            feature["properties"]["id"] = feature_id
        
        return feature
    
    @staticmethod
    def generate_geojson(
        center_coordinates: List[List[float]],
        polygon_areas: List[Dict],
        image_filename: str,
        model_type: str = "summer"
    ):
        """
        Generate GeoJSON from detection results.
        
        Args:
            center_coordinates: List of [lon, lat] coordinates
            polygon_areas: List of polygon area dictionaries
            image_filename: Name of the source image
            model_type: Type of model used ("summer" or "winter")
        
        Returns:
            List of GeoJSON features
        """
        features = []
        feature_id = 0
        
        # For winter model, primarily focus on paths
        if model_type == "winter":
            for poly in polygon_areas:
                detection_name = list(poly.keys())[0]
                area_value = poly[detection_name]
                
                if 'path' in detection_name.lower():
                    line_coords = poly.get('line_value', [])
                    if line_coords and line_coords is not False:
                        feature_id += 1
                        features.append(
                            GeoJsonService.create_linestring_feature(
                                coordinates=line_coords,
                                properties={
                                    "name": detection_name,
                                    "description": image_filename,
                                    "polygon_area": area_value
                                },
                                feature_id=feature_id
                            )
                        )
        
        # For summer model or mixed detection
        else:
            # Add point features for tree detections
            for idx, coords in enumerate(center_coordinates):
                try:
                    poly = polygon_areas[idx]
                    detection_name = list(poly.keys())[0]
                    area_value = poly[detection_name]
                except (IndexError, KeyError):
                    detection_name = 'unhealthy-tree'
                    area_value = '0.0 m²'
                
                # Skip paths in center coordinates
                if 'path' not in detection_name.lower():
                    feature_id += 1
                    features.append(
                        GeoJsonService.create_point_feature(
                            coordinates=coords,
                            properties={
                                "name": detection_name,
                                "description": image_filename,
                                "polygon_area": area_value
                            },
                            feature_id=feature_id
                        )
                    )
            
            # Add line features for paths
            for poly in polygon_areas:
                detection_name = list(poly.keys())[0]
                area_value = poly[detection_name]
                
                if 'path' in detection_name.lower():
                    line_coords = poly.get('line_value', [])
                    if line_coords and line_coords is not False:
                        feature_id += 1
                        features.append(
                            GeoJsonService.create_linestring_feature(
                                coordinates=line_coords,
                                properties={
                                    "name": detection_name,
                                    "description": image_filename,
                                    "polygon_area": area_value
                                },
                                feature_id=feature_id
                            )
                        )
        
        return features
    
    @staticmethod
    def save_geojson(features: List[Dict], output_path: str, crs_name: str = "urn:ogc:def:crs:EPSG::4326"):
        """
        Save features as a GeoJSON file.
        
        Args:
            features: List of GeoJSON features
            output_path: Path where to save the GeoJSON file
            crs_name: CRS identifier
        """
        feature_collection = GeoJsonService.create_feature_collection(features, crs_name)
        
        with open(output_path, 'w') as f:
            json.dump(feature_collection, f, indent=2)
        
        logger.info(f"Saved GeoJSON with {len(features)} features to: {output_path}")
    
    @staticmethod
    def merge_geojson_files(geojson_paths: List[str], output_path: str):
        """
        Merge multiple GeoJSON files into one.
        
        Args:
            geojson_paths: List of paths to GeoJSON files
            output_path: Path where to save the merged GeoJSON
        """
        all_features = []
        
        for path in geojson_paths:
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    if 'features' in data:
                        all_features.extend(data['features'])
            except Exception as e:
                logger.error(f"Error reading {path}: {e}")
        
        # Re-number feature IDs
        for idx, feature in enumerate(all_features, start=1):
            if 'properties' in feature:
                feature['properties']['id'] = idx
        
        GeoJsonService.save_geojson(all_features, output_path)
        logger.info(f"Merged {len(geojson_paths)} files into {output_path}")

