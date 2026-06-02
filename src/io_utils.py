from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import geopandas as gpd
import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.features import rasterize
from shapely.geometry import box


def ensure_dir(path: str | Path) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_vector(path: str | Path, default_crs: str = "EPSG:4326") -> gpd.GeoDataFrame:
    """Read a vector file, attempting to repair a missing .shx for shapefiles.

    Notes
    -----
    The uploaded shapefile in this task only included the .shp file. GDAL/Fiona can
    often reconstruct the .shx index if SHAPE_RESTORE_SHX=YES is set.
    """
    path = str(path)
    os.environ.setdefault("SHAPE_RESTORE_SHX", "YES")
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs(default_crs)
    return gdf


def get_bbox_from_raster(raster_path: str | Path, out_crs: str = "EPSG:4326") -> list[float]:
    with rasterio.open(raster_path) as src:
        bounds = src.bounds
        src_crs = src.crs

    if src_crs is None:
        raise ValueError(f"Raster has no CRS: {raster_path}")

    if str(src_crs) == out_crs:
        return [bounds.left, bounds.bottom, bounds.right, bounds.top]

    transformer = Transformer.from_crs(src_crs, out_crs, always_xy=True)
    xs = [bounds.left, bounds.right, bounds.right, bounds.left]
    ys = [bounds.bottom, bounds.bottom, bounds.top, bounds.top]
    tx, ty = transformer.transform(xs, ys)
    return [min(tx), min(ty), max(tx), max(ty)]


def get_bbox_from_vector(
    vector_path: str | Path,
    out_crs: str = "EPSG:4326",
    buffer_m: float = 0.0,
    buffer_crs: str = "EPSG:6933",
) -> list[float]:
    gdf = read_vector(vector_path).to_crs(buffer_crs)
    if buffer_m:
        gdf = gdf.copy()
        gdf["geometry"] = gdf.geometry.buffer(buffer_m)
    gdf = gdf.to_crs(out_crs)
    minx, miny, maxx, maxy = gdf.total_bounds
    return [float(minx), float(miny), float(maxx), float(maxy)]


def raster_footprint_gdf(raster_path: str | Path) -> gpd.GeoDataFrame:
    with rasterio.open(raster_path) as src:
        geom = box(*src.bounds)
        crs = src.crs
    return gpd.GeoDataFrame({"name": [Path(raster_path).stem]}, geometry=[geom], crs=crs)


def raster_to_bool_mask(
    raster_path: str | Path,
    reference_transform,
    width: int,
    height: int,
    reference_crs,
    include_values: tuple[int | float, ...] = (1,),
) -> np.ndarray:
    """Reproject/resample a raster to the reference grid and return a boolean mask.

    Nearest-neighbour is used to preserve discrete boolean/category values.
    """
    from rasterio.enums import Resampling
    from rasterio.warp import reproject

    with rasterio.open(raster_path) as src:
        source = src.read(1)
        destination = np.full((height, width), np.nan, dtype="float32")
        reproject(
            source=source,
            destination=destination,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=reference_transform,
            dst_crs=reference_crs,
            resampling=Resampling.nearest,
            src_nodata=src.nodata,
            dst_nodata=np.nan,
        )

    return np.isin(destination, include_values)


def buffered_polygon_to_bool_mask(
    vector_path: str | Path,
    reference_transform,
    width: int,
    height: int,
    reference_crs,
    buffer_m: float,
    all_touched: bool = False,
    default_crs: str = "EPSG:4326",
) -> np.ndarray:
    gdf = read_vector(vector_path, default_crs=default_crs).to_crs(reference_crs)
    gdf = gdf.copy()
    gdf["geometry"] = gdf.geometry.buffer(buffer_m)
    shapes = ((geom, 1) for geom in gdf.geometry if geom is not None and not geom.is_empty)
    mask = rasterize(
        shapes=shapes,
        out_shape=(height, width),
        transform=reference_transform,
        fill=0,
        default_value=1,
        dtype="uint8",
        all_touched=all_touched,
    )
    return mask == 1


def polygon_to_bool_mask(
    vector_path: str | Path,
    reference_transform,
    width: int,
    height: int,
    reference_crs,
    all_touched: bool = False,
    default_crs: str = "EPSG:4326",
) -> np.ndarray:
    gdf = read_vector(vector_path, default_crs=default_crs).to_crs(reference_crs)
    shapes = ((geom, 1) for geom in gdf.geometry if geom is not None and not geom.is_empty)
    mask = rasterize(
        shapes=shapes,
        out_shape=(height, width),
        transform=reference_transform,
        fill=0,
        default_value=1,
        dtype="uint8",
        all_touched=all_touched,
    )
    return mask == 1
