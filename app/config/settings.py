"""
Application Configuration
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Config:
    """Base configuration"""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # Directories
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    OUTPUT_FOLDER = os.path.join(BASE_DIR, 'outputs')
    TEMP_FOLDER = os.path.join(BASE_DIR, 'temp')
    MODEL_FOLDER = os.path.join(BASE_DIR, 'models')
    
    # Model paths
    SUMMER_MODEL_DIR = os.path.join(MODEL_FOLDER, 'summer')
    WINTER_MODEL_DIR = os.path.join(MODEL_FOLDER, 'winter')
    
    # Default models
    DEFAULT_SUMMER_MODEL = 'best.pt'
    DEFAULT_WINTER_MODEL = 'best.pt'
    
    # YOLO settings
    YOLO_CONFIDENCE = 0.2
    YOLO_LINE_WIDTH = 4
    
    # Coordinate conversion settings
    PIXEL_TO_METER = 0.15  # Conversion factor from pixels to meters
    
    # Path processing settings
    PATH_MERGE_TOLERANCE = 10
    PATH_FILTER_TOLERANCE = 50
    PATH_SMOOTHING_FACTOR = 0
    
    # TIFF tile settings
    TILE_SIZE_X = 150  # meters
    TILE_SIZE_Y = 150  # meters
    TILE_RESIZE = (1000, 1000)  # pixels
    
    # File upload settings
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB
    ALLOWED_EXTENSIONS = {'zip', 'tif', 'tiff'}
    
    # GeoJSON settings
    DEFAULT_CRS_NAME = "urn:ogc:def:crs:EPSG::4326"
    UTM_ZONE_DEFAULT = 25832  # Germany UTM Zone 32N


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False


class TestingConfig(Config):
    """Testing configuration"""
    DEBUG = True
    TESTING = True


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}

