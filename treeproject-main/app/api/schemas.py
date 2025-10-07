"""
API request and response schemas
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class PredictionRequest:
    """Request schema for prediction endpoint"""
    model_type: str  # 'summer' or 'winter'
    model_name: Optional[str] = None  # Specific model file name
    confidence: float = 0.2  # Confidence threshold


@dataclass
class PredictionResponse:
    """Response schema for prediction endpoint"""
    status: bool
    message: str
    geojson_url: Optional[str] = None
    zip_url: Optional[str] = None
    error: Optional[str] = None
    stats: Optional[dict] = None


def validate_model_type(model_type: str) -> bool:
    """Validate model type"""
    return model_type.lower() in ['summer', 'winter']


def validate_file_extension(filename: str, allowed_extensions: set) -> bool:
    """Validate file extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

