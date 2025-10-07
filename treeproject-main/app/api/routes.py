"""
API Routes
Main endpoints for the tree detection service
"""
import os
import json
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, send_file, current_app, Response
from werkzeug.utils import secure_filename

from app.services.prediction_service import PredictionService
from app.services.coordinate_service import CoordinateService
from app.services.geojson_service import GeoJsonService
from app.services.tiff_service import TiffService
from app.utils.file_handler import (
    allowed_file,
    save_uploaded_file,
    unzip_file,
    zip_folder,
    cleanup_temp_files,
    remove_tif_files,
    ensure_directory
)
from app.api.schemas import validate_model_type

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__)


@api_bp.route('/predict', methods=['POST'])
def predict():
    """
    Main prediction endpoint.
    
    Accepts:
        - file: ZIP file containing JPEG images with JGW files, or a single TIFF file
        - model: 'summer' or 'winter'
        - model_name: Optional specific model filename
        - confidence: Optional confidence threshold (default: 0.2)
        - return_geojson: If 'true', returns GeoJSON inline; if 'false', returns URLs (default: true)
    
    Returns:
        JSON response with GeoJSON data or download URLs
    """
    try:
        # Validate request
        if 'file' not in request.files:
            return jsonify({'status': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'status': False, 'error': 'Empty filename'}), 400
        
        # Get parameters
        model_type = request.form.get('model', 'summer').lower()
        model_name = request.form.get('model_name')
        confidence = float(request.form.get('confidence', 0.2))
        return_geojson = request.form.get('return_geojson', 'true').lower() == 'true'
        
        # Validate model type
        if not validate_model_type(model_type):
            return jsonify({'status': False, 'error': 'Invalid model type. Use "summer" or "winter"'}), 400
        
        # Validate file extension
        if not allowed_file(file.filename, current_app.config['ALLOWED_EXTENSIONS']):
            return jsonify({'status': False, 'error': 'Invalid file type. Use ZIP or TIFF files'}), 400
        
        # Create unique job directory
        job_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        job_dir = ensure_directory(os.path.join(current_app.config['TEMP_FOLDER'], job_id))
        output_dir = ensure_directory(os.path.join(current_app.config['OUTPUT_FOLDER'], job_id))
        
        # Save uploaded file
        file_path = save_uploaded_file(file, job_dir)
        logger.info(f"Processing job {job_id}: {file.filename}")
        
        # Process based on file type
        if file.filename.lower().endswith(('.tif', '.tiff')):
            result = _process_tiff_file(file_path, job_dir, output_dir, model_type, model_name, confidence, return_geojson)
        else:  # ZIP file
            result = _process_zip_file(file_path, job_dir, output_dir, model_type, model_name, confidence, return_geojson)
        
        # Add job ID to response
        result['job_id'] = job_id
        
        return jsonify(result), 200 if result['status'] else 500
        
    except Exception as e:
        logger.error(f"Error in prediction endpoint: {e}", exc_info=True)
        return jsonify({'status': False, 'error': str(e)}), 500


def _process_tiff_file(file_path, job_dir, output_dir, model_type, model_name, confidence, return_geojson=True):
    """Process a TIFF file"""
    if not TiffService.is_available():
        return {
            'status': False,
            'error': 'TIFF processing not available. Please install GDAL or upload a ZIP file with JPEG+JGW files.'
        }
    
    logger.info("Starting TIFF processing")
    
    # Split TIFF into tiles
    tile_paths = TiffService.split_tiff_into_tiles(
        file_path,
        job_dir,
        tile_size_x=current_app.config['TILE_SIZE_X'],
        tile_size_y=current_app.config['TILE_SIZE_Y']
    )
    
    logger.info(f"Split TIFF into {len(tile_paths)} tiles")
    
    # Create JGW files for each tile
    for tile_path in tile_paths:
        tiff_path = tile_path.replace('.jpeg', '.tif')
        if os.path.exists(tiff_path):
            CoordinateService.create_jgw_from_tiff(tiff_path)
    
    # Run predictions
    return _run_predictions(job_dir, output_dir, model_type, model_name, confidence, return_geojson)


def _process_zip_file(file_path, job_dir, output_dir, model_type, model_name, confidence, return_geojson=True):
    """Process a ZIP file"""
    logger.info("Starting ZIP file processing")
    
    # Extract ZIP
    extract_dir = ensure_directory(os.path.join(job_dir, 'extracted'))
    unzip_file(file_path, extract_dir)
    
    # Verify JGW files exist for all images
    image_files = [f for f in os.listdir(extract_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    
    logger.info(f"Found {len(image_files)} images in ZIP")
    
    for img_file in image_files:
        jgw_file = os.path.splitext(img_file)[0] + '.jgw'
        if not os.path.exists(os.path.join(extract_dir, jgw_file)):
            return {
                'status': False,
                'error': f'Missing JGW file for {img_file}. Each image must have a corresponding .jgw world file.'
            }
    
    # Run predictions
    return _run_predictions(extract_dir, output_dir, model_type, model_name, confidence, return_geojson)


def _run_predictions(input_dir, output_dir, model_type, model_name, confidence, return_geojson=True):
    """Run predictions on all images in a directory"""
    # Load model
    model_path = _get_model_path(model_type, model_name)
    if not os.path.exists(model_path):
        return {'status': False, 'error': f'Model not found: {model_path}'}
    
    logger.info(f"Loading model from: {model_path}")
    
    try:
        prediction_service = PredictionService(
            model_path,
            pixel_to_meter=current_app.config['PIXEL_TO_METER']
        )
    except Exception as e:
        logger.error(f"Failed to load model: {e}", exc_info=True)
        return {'status': False, 'error': f'Failed to load model: {str(e)}'}
    
    # Process each image
    all_features = []
    image_files = [f for f in os.listdir(input_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    
    logger.info(f"Processing {len(image_files)} images")
    
    if len(image_files) == 0:
        return {'status': False, 'error': 'No valid image files found in input'}
    
    total_detections = 0
    processed_images = 0
    
    for idx, img_file in enumerate(image_files, 1):
        logger.info(f"Processing image {idx}/{len(image_files)}: {img_file}")
        
        img_path = os.path.join(input_dir, img_file)
        jgw_path = os.path.join(input_dir, os.path.splitext(img_file)[0] + '.jgw')
        
        # Run prediction
        try:
            pred_result = prediction_service.predict_image(img_path, confidence)
        except Exception as e:
            logger.error(f"Prediction error for {img_file}: {e}", exc_info=True)
            continue
        
        if not pred_result['success']:
            logger.warning(f"Prediction failed for {img_file}: {pred_result.get('error')}")
            continue
        
        processed_images += 1
        total_detections += len(pred_result['detections'])
        
        logger.info(f"Found {len(pred_result['detections'])} detections in {img_file}")
        
        # Save annotated image
        try:
            annotated_path = os.path.join(output_dir, f"annotated_{img_file}")
            pred_result['annotated_image'].save(annotated_path)
        except Exception as e:
            logger.warning(f"Could not save annotated image: {e}")
        
        # Transform coordinates
        center_coords_pixel = [[cp['x'], cp['y']] for cp in pred_result['center_points']]
        
        if os.path.exists(jgw_path):
            try:
                geographic_coords, transformed_polygons = CoordinateService.transform_coordinates(
                    jgw_path,
                    center_coords_pixel,
                    pred_result['polygon_areas']
                )
            except Exception as e:
                logger.error(f"Coordinate transformation error for {img_file}: {e}", exc_info=True)
                geographic_coords = center_coords_pixel
                transformed_polygons = pred_result['polygon_areas']
        else:
            logger.warning(f"No JGW file for {img_file}, using pixel coordinates")
            geographic_coords = center_coords_pixel
            transformed_polygons = pred_result['polygon_areas']
        
        # Generate GeoJSON features
        try:
            features = GeoJsonService.generate_geojson(
                geographic_coords,
                transformed_polygons,
                img_file,
                model_type
            )
            all_features.extend(features)
        except Exception as e:
            logger.error(f"GeoJSON generation error for {img_file}: {e}", exc_info=True)
    
    logger.info(f"Prediction complete. Processed {processed_images} images, found {total_detections} detections")
    
    if processed_images == 0:
        return {'status': False, 'error': 'No images were successfully processed'}
    
    # Save combined GeoJSON
    geojson_path = os.path.join(output_dir, 'output.geojson')
    try:
        GeoJsonService.save_geojson(all_features, geojson_path)
        logger.info(f"Saved GeoJSON to: {geojson_path}")
    except Exception as e:
        logger.error(f"Failed to save GeoJSON: {e}", exc_info=True)
        return {'status': False, 'error': f'Failed to save GeoJSON: {str(e)}'}
    
    # Create output ZIP (skip if it fails)
    try:
        remove_tif_files(input_dir)
        zip_path = os.path.join(output_dir, 'processed_images.zip')
        zip_folder(output_dir, zip_path)
        logger.info(f"Created output ZIP: {zip_path}")
    except Exception as e:
        logger.warning(f"Failed to create output ZIP: {e}")
    
    # Prepare response
    job_id = os.path.basename(output_dir)
    
    # Always return URLs for file downloads
    response = {
        'status': True,
        'message': 'Prediction completed successfully',
        'stats': {
            'processed_images': processed_images,
            'total_detections': total_detections,
            'features': len(all_features)
        },
        'geojson_url': f'/api/v1/download/{job_id}/output.geojson',
        'zip_url': f'/api/v1/download/{job_id}/processed_images.zip'
    }
    
    # Optionally include GeoJSON inline for small responses
    if return_geojson:
        try:
            # Only include inline if file is reasonably small (< 5MB)
            file_size = os.path.getsize(geojson_path)
            if file_size < 5 * 1024 * 1024:  # 5MB limit
                with open(geojson_path, 'r') as f:
                    geojson_data = json.load(f)
                response['geojson'] = geojson_data
                logger.info(f"Returning GeoJSON inline in response (size: {file_size} bytes)")
            else:
                logger.info(f"GeoJSON too large ({file_size} bytes), returning URL only")
        except Exception as e:
            logger.error(f"Failed to load GeoJSON for response: {e}")
    
    return response


def _get_model_path(model_type, model_name=None):
    """Get the full path to the model file"""
    if model_type == 'summer':
        model_dir = current_app.config['SUMMER_MODEL_DIR']
        default_model = current_app.config['DEFAULT_SUMMER_MODEL']
    else:
        model_dir = current_app.config['WINTER_MODEL_DIR']
        default_model = current_app.config['DEFAULT_WINTER_MODEL']
    
    model_file = model_name if model_name else default_model
    return os.path.join(model_dir, model_file)


@api_bp.route('/download/<job_id>/<filename>', methods=['GET'])
def download_file(job_id, filename):
    """Download a result file"""
    try:
        file_path = os.path.join(current_app.config['OUTPUT_FOLDER'], job_id, filename)
        
        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found'}), 404
        
        # Set appropriate mimetype for GeoJSON files
        mimetype = None
        if filename.endswith('.geojson') or filename.endswith('.json'):
            mimetype = 'application/geo+json'
        elif filename.endswith('.zip'):
            mimetype = 'application/zip'
        
        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename,
            mimetype=mimetype
        )
    
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/geojson/<job_id>', methods=['GET'])
def get_geojson(job_id):
    """Get GeoJSON result as JSON response (not as file download)"""
    try:
        geojson_path = os.path.join(current_app.config['OUTPUT_FOLDER'], job_id, 'output.geojson')
        
        if not os.path.exists(geojson_path):
            return jsonify({'error': 'GeoJSON file not found'}), 404
        
        # Read and return GeoJSON
        with open(geojson_path, 'r') as f:
            geojson_data = json.load(f)
        
        # Return with proper content type
        return Response(
            json.dumps(geojson_data, indent=2),
            mimetype='application/geo+json',
            headers={'Content-Disposition': f'inline; filename="output.geojson"'}
        )
    
    except Exception as e:
        logger.error(f"Error getting GeoJSON: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/models', methods=['GET'])
def list_models():
    """List available models"""
    try:
        summer_models = os.listdir(current_app.config['SUMMER_MODEL_DIR'])
        winter_models = os.listdir(current_app.config['WINTER_MODEL_DIR'])
        
        return jsonify({
            'summer': [m for m in summer_models if m.endswith('.pt')],
            'winter': [m for m in winter_models if m.endswith('.pt')]
        }), 200
    
    except Exception as e:
        logger.error(f"Error listing models: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/status/<job_id>', methods=['GET'])
def job_status(job_id):
    """Check the status of a job"""
    try:
        output_dir = os.path.join(current_app.config['OUTPUT_FOLDER'], job_id)
        
        if not os.path.exists(output_dir):
            return jsonify({'status': 'not_found'}), 404
        
        geojson_path = os.path.join(output_dir, 'output.geojson')
        
        if os.path.exists(geojson_path):
            return jsonify({
                'status': 'completed',
                'geojson_url': f'/api/v1/download/{job_id}/output.geojson',
                'zip_url': f'/api/v1/download/{job_id}/processed_images.zip'
            }), 200
        else:
            return jsonify({'status': 'processing'}), 200
    
    except Exception as e:
        logger.error(f"Error checking job status: {e}")
        return jsonify({'error': str(e)}), 500

