"""
Prediction service
Handles YOLO model inference and result processing
"""
import os
import json
import logging
import numpy as np
import cv2
from PIL import Image
from ultralytics import YOLO
from shapely.geometry import Polygon
import pygeoops

from app.utils.geometry_utils import (
    polygon_area,
    find_groups,
    collect_points,
    sort_points,
    filter_zigzag,
    smooth_path
)

logger = logging.getLogger(__name__)


class PredictionService:
    """Service for running YOLO predictions and processing results"""
    
    def __init__(self, model_path, pixel_to_meter=0.15, config=None):
        """
        Initialize the prediction service.
        
        Args:
            model_path: Path to the YOLO model file
            pixel_to_meter: Conversion factor from pixels to meters
            config: Configuration object with settings
        """
        self.pixel_to_meter = pixel_to_meter
        self.config = config or {}
        
        logger.info(f"Loading YOLO model: {model_path}")
        self.model = YOLO(model_path)
        logger.info("Model loaded successfully")
    
    def predict_image(self, image_path, confidence=0.2):
        """
        Run prediction on a single image and return processed results.
        
        Args:
            image_path: Path to the input image
            confidence: Confidence threshold for detection
        
        Returns:
            Dictionary containing:
                - success: Boolean indicating if prediction succeeded
                - annotated_image: PIL Image with annotations
                - detections: List of detected objects
                - center_points: List of center points
                - polygon_areas: List of polygon areas with coordinates
                - image_info: Dictionary with image metadata
        """
        logger.info(f"Running prediction on: {image_path}")
        
        try:
            image = Image.open(image_path)
            results = self.model.predict(image, save=False, save_txt=False, conf=confidence)
            
            if not results or len(results) == 0:
                logger.warning("No results from prediction")
                return self._empty_result(image)
            
            # Process results
            result = results[0]
            
            if result.boxes is None and result.masks is None:
                logger.info("No objects detected")
                return self._empty_result(image)
            
            # Extract detection data
            detection_data = self._process_detections(result, image)
            
            # Create annotated image
            annotated_image = self._create_annotated_image(result, image, detection_data)
            
            return {
                'success': True,
                'annotated_image': annotated_image,
                'detections': detection_data['detections'],
                'center_points': detection_data['center_points'],
                'polygon_areas': detection_data['polygon_areas'],
                'image_info': {
                    'width': image.width,
                    'height': image.height,
                    'filename': os.path.basename(image_path)
                }
            }
            
        except Exception as e:
            logger.error(f"Error during prediction: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def _empty_result(self, image):
        """Return empty result structure"""
        return {
            'success': True,
            'annotated_image': image,
            'detections': [],
            'center_points': [],
            'polygon_areas': [],
            'image_info': {
                'width': image.width,
                'height': image.height,
                'filename': 'unknown'
            }
        }
    
    def _process_detections(self, result, image):
        """Process YOLO detection results"""
        boxes = result.boxes
        masks = result.masks if hasattr(result, 'masks') else None
        
        image_np = np.array(image)
        h, w, c = image_np.shape
        threshold = h / 30
        
        class_ids = boxes.cls.tolist() if boxes is not None else []
        polygon_points = masks.xy if masks is not None else []
        
        detections = []
        center_points = []
        polygon_areas = []
        all_path_points = []
        
        for box, cls_id, polygon_value in zip(boxes, class_ids, polygon_points):
            poly_area = polygon_area(polygon_value)
            poly_area_meter = poly_area * (self.pixel_to_meter ** 2)
            
            # Extract bounding box
            xmin, ymin = int(box.data[0][0]), int(box.data[0][1])
            xmax, ymax = int(box.data[0][2]), int(box.data[0][3])
            
            # Calculate center point
            center_x = int((xmin + xmax) // 2)
            center_y = int((ymin + ymax) // 2)
            
            # Get class name
            class_id = int(cls_id)
            class_name = result.names.get(class_id, f'Class {class_id}')
            
            # Store detection info
            detections.append({
                'class_id': class_id,
                'class_name': class_name,
                'confidence': float(box.conf[0]),
                'bbox': [xmin, ymin, xmax, ymax],
                'area_m2': round(poly_area_meter, 2)
            })
            
            # Store center point
            center_points.append({
                'class_name': class_name,
                'x': center_x,
                'y': center_y
            })
            
            # Process path objects
            if 'path' in class_name.lower():
                line_list = self._extract_path_lines(polygon_value)
                all_path_points.extend(line_list)
            else:
                polygon_areas.append({
                    class_name: f"{round(poly_area_meter, 2)} m²",
                    'line_value': False
                })
        
        # Process grouped path lines
        if all_path_points:
            path_groups = find_groups(all_path_points, threshold)
            for group in path_groups:
                group_points = collect_points(group)
                sorted_points = sort_points(group_points)
                filtered_points = filter_zigzag(sorted_points, tolerance=50)
                smooth_points = smooth_path(filtered_points, smoothing_factor=0)
                
                # Convert to line segments
                line_list = []
                smooth_points_list = np.array(smooth_points).tolist()
                for i in range(len(smooth_points_list) - 1):
                    start = tuple(smooth_points_list[i])
                    end = tuple(smooth_points_list[i + 1])
                    line_list.append((start, end))
                
                polygon_areas.append({
                    'path': '0.0 m²',  # Paths don't have meaningful area
                    'line_value': line_list
                })
        
        return {
            'detections': detections,
            'center_points': center_points,
            'polygon_areas': polygon_areas
        }
    
    def _extract_path_lines(self, polygon_value):
        """Extract centerline from path polygon"""
        try:
            poly = Polygon(polygon_value)
            centerline = pygeoops.centerline(poly)
            
            line_strings = []
            if hasattr(centerline, 'geoms'):
                line_strings = list(centerline.geoms)
            else:
                line_strings = [centerline]
            
            line_list = []
            for line in line_strings:
                points = [(int(point[0]), int(point[1])) for point in line.coords]
                for i in range(len(points) - 1):
                    line_list.append((points[i], points[i + 1]))
            
            return line_list
        except Exception as e:
            logger.error(f"Error extracting path lines: {e}")
            return []
    
    def _create_annotated_image(self, result, image, detection_data):
        """Create annotated image with detections drawn"""
        try:
            im_array = result.plot(line_width=4, conf=True)
            annotated = Image.fromarray(im_array[..., ::-1])
            
            # Add center points
            image_np = np.array(annotated)
            for cp in detection_data['center_points']:
                cv2.circle(image_np, (cp['x'], cp['y']), 5, (255, 0, 0), -1)
            
            # Add path lines
            for poly in detection_data['polygon_areas']:
                if poly.get('line_value') and poly['line_value'] is not False:
                    for start, end in poly['line_value']:
                        cv2.line(image_np, start, end, color=(0, 255, 0), thickness=2)
            
            return Image.fromarray(image_np)
        except Exception as e:
            logger.warning(f"Could not create annotated image: {e}")
            return image
    
    def save_detection_metadata(self, output_path, center_points, polygon_areas):
        """Save detection metadata to JSON file"""
        metadata = {
            'xy_point': [[cp['x'], cp['y']] for cp in center_points],
            'polygone_area': polygon_areas
        }
        
        with open(output_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"Saved detection metadata: {output_path}")

