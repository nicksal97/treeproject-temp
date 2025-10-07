"""
Coordinate transformation service
Handles conversion from pixel coordinates to geographic coordinates
"""
import os
import json
import logging
from pyproj import Transformer
import rasterio
import warnings

logger = logging.getLogger(__name__)


class CoordinateService:
    """Service for coordinate transformations"""
    
    @staticmethod
    def create_jgw_from_tiff(tiff_path):
        """
        Create JGW world file from TIFF georeferencing data.
        Returns the path to the created JGW file.
        """
        logger.info(f"Creating JGW file for: {tiff_path}")
        
        file_name_base = os.path.splitext(tiff_path)[0]
        jgw_path = f"{file_name_base}.jgw"
        
        # Suppress CRS warnings from rasterio
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*old-style crs.*")
            warnings.filterwarnings("ignore", category=UserWarning)
            src = rasterio.open(tiff_path)
        
        with src:
            transform = src.transform
            crs = src.crs
            
            logger.info(f"TIFF Transform: {transform}")
            logger.info(f"TIFF CRS: {crs}")
            
            # Check if CRS is WGS84 or needs reprojection
            is_wgs84 = False
            if crs:
                try:
                    crs_epsg = crs.to_epsg()
                    is_wgs84 = (crs_epsg == 4326)
                    logger.info(f"TIFF CRS EPSG code: {crs_epsg}")
                except:
                    crs_string = str(crs).lower()
                    is_wgs84 = 'epsg:4326' in crs_string or 'wgs84' in crs_string
            
            # Reproject to WGS84 if necessary
            if crs and not is_wgs84:
                logger.info(f"Reprojecting from {crs} to WGS84 (EPSG:4326)")
                
                transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
                
                # Transform origin point
                origin_x, origin_y = transform.c, transform.f
                lon_origin, lat_origin = transformer.transform(origin_x, origin_y)
                
                # Transform adjacent points to calculate pixel sizes
                right_x, right_y = transform.c + transform.a, transform.f
                bottom_x, bottom_y = transform.c, transform.f + transform.e
                
                lon_right, lat_right = transformer.transform(right_x, right_y)
                lon_bottom, lat_bottom = transformer.transform(bottom_x, bottom_y)
                
                # Calculate pixel sizes in degrees
                pixel_width_deg = lon_right - lon_origin
                pixel_height_deg = lat_bottom - lat_origin
                
                logger.info(f"Reprojected: Origin ({origin_x}, {origin_y}) -> ({lon_origin}, {lat_origin})")
                logger.info(f"Pixel size: {pixel_width_deg}° (lon) x {pixel_height_deg}° (lat)")
                
                transform_a = pixel_width_deg
                transform_d = 0.0
                transform_b = 0.0
                transform_e = pixel_height_deg
                transform_c = lon_origin
                transform_f = lat_origin
            else:
                logger.info("CRS is already WGS84")
                transform_a = transform.a
                transform_d = transform.d
                transform_b = transform.b
                transform_e = transform.e
                transform_c = transform.c
                transform_f = transform.f
        
        # Write JGW file
        with open(jgw_path, 'w') as jgw_file:
            jgw_file.write(f"{transform_a}\n")
            jgw_file.write(f"{transform_d}\n")
            jgw_file.write(f"{transform_b}\n")
            jgw_file.write(f"{transform_e}\n")
            jgw_file.write(f"{transform_c}\n")
            jgw_file.write(f"{transform_f}\n")
        
        logger.info(f"Created JGW file: {jgw_path}")
        return jgw_path
    
    @staticmethod
    def transform_coordinates(jgw_file_path, pixel_coordinates, polygon_areas):
        """
        Transform pixel coordinates to geographic coordinates using JGW file.
        
        Args:
            jgw_file_path: Path to the JGW world file
            pixel_coordinates: List of [x, y] pixel coordinates
            polygon_areas: List of polygon area data with line values
        
        Returns:
            Tuple of (geographic_coordinates, transformed_polygon_areas)
        """
        logger.info(f"Transforming coordinates using JGW: {jgw_file_path}")
        
        with open(jgw_file_path, 'r') as jgw_file:
            jgw_lines = jgw_file.readlines()
        
        # Parse JGW parameters
        A = float(jgw_lines[0].strip())  # x pixel size
        D = float(jgw_lines[1].strip())  # rotation y
        B = float(jgw_lines[2].strip())  # rotation x
        E = float(jgw_lines[3].strip())  # y pixel size (negative)
        C = float(jgw_lines[4].strip())  # x origin
        F = float(jgw_lines[5].strip())  # y origin
        
        logger.info(f"JGW Parameters: A={A}, D={D}, B={B}, E={E}, C={C}, F={F}")
        
        # Detect if coordinates are in projected system (UTM)
        is_projected = (abs(C) > 1000 or abs(F) > 1000 or abs(A) > 1)
        
        transformer = None
        if is_projected:
            logger.info("Detected projected coordinates (UTM)")
            # Germany is typically UTM Zone 32N (EPSG:25832)
            if 500000 <= C <= 900000 and 5000000 <= F <= 6500000:
                try:
                    transformer = Transformer.from_crs("EPSG:25832", "EPSG:4326", always_xy=True)
                    logger.info("Created transformer: EPSG:25832 → WGS84")
                except Exception as e:
                    logger.warning(f"Could not create transformer: {e}")
        
        # Transform polygon line values
        for poly in polygon_areas:
            line_values = poly.get('line_value')
            if line_values and line_values is not False:
                transformed_coords = []
                for value in line_values:
                    a, b = value
                    # Apply affine transformation
                    actual_x1 = (A * float(a[0])) + (B * float(a[1])) + C
                    actual_y1 = (D * float(a[0])) + (E * float(a[1])) + F
                    actual_x2 = (A * float(b[0])) + (B * float(b[1])) + C
                    actual_y2 = (D * float(b[0])) + (E * float(b[1])) + F
                    
                    # Reproject if necessary
                    if transformer:
                        actual_x1, actual_y1 = transformer.transform(actual_x1, actual_y1)
                        actual_x2, actual_y2 = transformer.transform(actual_x2, actual_y2)
                    
                    transformed_coords.extend([[actual_x1, actual_y1], [actual_x2, actual_y2]])
                
                poly['line_value'] = transformed_coords
        
        # Transform center point coordinates
        geographic_coords = []
        for pixel_x, pixel_y in pixel_coordinates:
            # Apply affine transformation
            actual_x = (A * pixel_x) + (B * pixel_y) + C
            actual_y = (D * pixel_x) + (E * pixel_y) + F
            
            # Reproject if necessary
            if transformer:
                actual_x, actual_y = transformer.transform(actual_x, actual_y)
                logger.debug(f"Pixel ({pixel_x}, {pixel_y}) -> WGS84 ({actual_x:.6f}, {actual_y:.6f})")
            
            # Store as [longitude, latitude] for GeoJSON
            geographic_coords.append([actual_x, actual_y])
        
        logger.info(f"Transformed {len(geographic_coords)} coordinates")
        return geographic_coords, polygon_areas

