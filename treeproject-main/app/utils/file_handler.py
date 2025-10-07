"""
File handling utilities
"""
import os
import zipfile
import shutil
from pathlib import Path
from werkzeug.utils import secure_filename


def allowed_file(filename, allowed_extensions):
    """Check if file has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions


def save_uploaded_file(file, upload_folder):
    """Save an uploaded file and return its path."""
    filename = secure_filename(file.filename)
    filepath = os.path.join(upload_folder, filename)
    file.save(filepath)
    return filepath


def unzip_file(zip_path, extract_to):
    """Extract a zip file to a directory."""
    with zipfile.ZipFile(zip_path, 'r') as zipf:
        zipf.extractall(extract_to)
    
    # Handle nested directories and __MACOSX folders
    exclude_folders = {'__MACOSX', '.DS_Store'}
    
    for item in os.listdir(extract_to):
        item_path = os.path.join(extract_to, item)
        
        # Skip unwanted folders
        if item in exclude_folders:
            if os.path.isdir(item_path):
                shutil.rmtree(item_path)
            else:
                os.remove(item_path)
            continue
        
        # If there's a single folder, move its contents up
        if os.path.isdir(item_path) and len([x for x in os.listdir(extract_to) if x not in exclude_folders]) == 1:
            for sub_item in os.listdir(item_path):
                shutil.move(os.path.join(item_path, sub_item), extract_to)
            shutil.rmtree(item_path)
            break
    
    return extract_to


def zip_folder(folder_path, zip_file_path):
    """Create a ZIP file from a folder."""
    with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                zipf.write(file_path, os.path.relpath(file_path, folder_path))


def cleanup_temp_files(*paths):
    """Remove temporary files and directories."""
    for path in paths:
        if os.path.exists(path):
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)


def remove_tif_files(folder_path):
    """Remove all TIFF files from a folder."""
    for file in os.listdir(folder_path):
        if file.lower().endswith(('.tif', '.tiff')):
            os.remove(os.path.join(folder_path, file))


def ensure_directory(path):
    """Ensure a directory exists, create if it doesn't."""
    os.makedirs(path, exist_ok=True)
    return path

