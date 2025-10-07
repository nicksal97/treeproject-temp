"""
TIFF processing service
Handles splitting of large TIFF files into tiles
"""
import os
import logging
from PIL import Image

logger = logging.getLogger(__name__)

# Check GDAL availability
try:
    from osgeo import gdal, osr
    GDAL_AVAILABLE = True
except ImportError:
    logger.warning("GDAL not available. TIFF splitting feature will be disabled.")
    GDAL_AVAILABLE = False
    gdal = None
    osr = None


class TiffService:
    """Service for TIFF file processing"""
    
    @staticmethod
    def is_available():
        """Check if TIFF processing is available"""
        return GDAL_AVAILABLE
    
    @staticmethod
    def split_tiff_into_tiles(tiff_path, output_folder, tile_size_x=150, tile_size_y=150):
        """
        Split a large TIFF file into smaller tiles.
        
        Args:
            tiff_path: Path to the input TIFF file
            output_folder: Directory to save the tiles
            tile_size_x: Tile width in meters (default: 150)
            tile_size_y: Tile height in meters (default: 150)
        
        Returns:
            List of created tile paths
        """
        if not GDAL_AVAILABLE:
            raise RuntimeError("GDAL not available. Cannot process TIFF files.")
        
        logger.info(f"Splitting TIFF file: {tiff_path}")
        
        raster = gdal.Open(tiff_path)
        geo_transform = raster.GetGeoTransform()
        wkt = raster.GetProjection()
        
        logger.info(f"GeoTransform: {geo_transform}")
        logger.info(f"CRS WKT: {wkt}")
        
        # Initialize CRS
        crs = osr.SpatialReference()
        crs.ImportFromWkt(wkt)
        
        # Check if units are in meters, reproject if not
        if crs.GetLinearUnitsName() not in ['meter', 'metre', 'meters', 'metres']:
            logger.info("Reprojecting raster to UTM...")
            
            # Determine UTM zone
            utm_zone = int((geo_transform[0] + 180) / 6) + 1
            is_northern = geo_transform[3] > 0
            
            # Create UTM projection
            utm_crs = osr.SpatialReference()
            utm_crs.SetUTM(utm_zone, is_northern)
            utm_crs.SetWellKnownGeogCS('WGS84')
            
            # Warp to UTM
            reprojected_path = os.path.join(output_folder, 'reprojected.tif')
            gdal.Warp(reprojected_path, raster, dstSRS=utm_crs.ExportToWkt())
            
            # Update raster reference
            raster = gdal.Open(reprojected_path)
            geo_transform = raster.GetGeoTransform()
            wkt = raster.GetProjection()
            crs.ImportFromWkt(wkt)
        
        units = crs.GetLinearUnitsName()
        logger.info(f"Linear units: {units}")
        
        # Extract coordinates and resolution
        xmin, ymax = geo_transform[0], geo_transform[3]
        raster_resolution_x = geo_transform[1]
        raster_resolution_y = abs(geo_transform[5])
        
        # Calculate total dimensions
        raster_x_length = raster_resolution_x * raster.RasterXSize
        raster_y_length = raster_resolution_y * raster.RasterYSize
        
        logger.info(f"Raster size: {raster_x_length} x {raster_y_length} {units}")
        
        # Calculate number of tiles
        tiles_x = int(raster_x_length / tile_size_x)
        tiles_y = int(raster_y_length / tile_size_y)
        
        logger.info(f"Creating {tiles_x} x {tiles_y} tiles")
        
        # Generate tile coordinates
        xsteps = [xmin + tile_size_x * i for i in range(tiles_x + 1)]
        ysteps = [ymax - tile_size_y * i for i in range(tiles_y + 1)]
        
        # Create tiles
        tile_paths = []
        gdal.UseExceptions()
        
        for i in range(tiles_x):
            for j in range(tiles_y):
                tile_xmin, tile_xmax = xsteps[i], xsteps[i + 1]
                tile_ymax, tile_ymin = ysteps[j], ysteps[j + 1]
                
                tiff_tile_name = os.path.join(output_folder, f'Segmented_{i}_{j}.tif')
                jpg_tile_name = os.path.join(output_folder, f'Segmented_{i}_{j}.jpeg')
                
                try:
                    # Create TIFF tile
                    gdal.Warp(
                        tiff_tile_name,
                        raster,
                        outputBounds=(tile_xmin, tile_ymin, tile_xmax, tile_ymax),
                        dstNodata=-9999
                    )
                    
                    # Convert to JPEG
                    with Image.open(tiff_tile_name) as tile_img:
                        if tile_img.mode == 'RGBA':
                            tile_img = tile_img.convert('RGB')
                        
                        tile_img.thumbnail((1000, 1000))
                        tile_img.save(jpg_tile_name, 'JPEG', quality=90, dpi=(300, 300))
                    
                    tile_paths.append(jpg_tile_name)
                    logger.info(f"Created tile: {jpg_tile_name}")
                    
                except Exception as e:
                    logger.error(f"Error creating tile ({i}, {j}): {e}")
        
        # Cleanup reprojected file if it exists
        reprojected_path = os.path.join(output_folder, 'reprojected.tif')
        if os.path.exists(reprojected_path):
            try:
                raster = None  # Close GDAL dataset
                os.remove(reprojected_path)
                logger.info("Removed temporary reprojected file")
            except Exception as e:
                logger.warning(f"Could not remove temporary file: {e}")
        
        logger.info(f"Created {len(tile_paths)} tiles")
        return tile_paths

