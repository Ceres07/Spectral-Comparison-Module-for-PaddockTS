from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import odc.stac
import pystac_client
import xarray as xr
from dask.distributed import Client as DaskClient

from io_utils import ensure_dir, get_bbox_from_raster, get_bbox_from_vector

odc.stac.configure_rio(cloud_defaults=True, aws={"aws_unsigned": True})


DEA_STAC_URL = "https://explorer.dea.ga.gov.au/stac"
DEA_COLLECTIONS = ("ga_s2am_ard_3", "ga_s2bm_ard_3")
NDVI_BANDS = ("nbart_red", "nbart_nir_1")
FRACTIONAL_COVER_BANDS = ("nbart_blue", "nbart_green", "nbart_red", "nbart_nir_1", "nbart_swir_2", "nbart_swir_3")
BANDS = ("oa_fmask", *FRACTIONAL_COVER_BANDS)


def compute_ndvi(ds: xr.Dataset) -> xr.DataArray:
    red = ds["nbart_red"].astype("float32")
    nir = ds["nbart_nir_1"].astype("float32")

    # Match the repo's logic: convert DEA reflectance scaling to 0-1 floats.
    red = xr.where(red == 0, np.nan, red / 10000.0)
    nir = xr.where(nir == 0, np.nan, nir / 10000.0)

    ndvi = (nir - red) / (nir + red)
    ndvi = ndvi.where(np.isfinite(ndvi))
    ndvi.name = "NDVI"
    ndvi.attrs.update({"long_name": "Normalized Difference Vegetation Index"})
    return ndvi


def download_ndvi(
    aoi_raster: str | None,
    start: str,
    end: str,
    out_zarr: str,
    aoi_vector: str | None = None,
    aoi_buffer_m: float = 0.0,
    out_crs: str = "EPSG:6933",
    resolution: int = 10,
    max_cloud_cover: float = 40.0,
    max_nan_fraction: float = 0.20,
    chunk_x: int = 1024,
    chunk_y: int = 1024,
    chunk_time: int = 1,
    num_workers: int = 4,
    threads_per_worker: int = 2,
    keep_source_bands: bool = False,
) -> Path:
    if aoi_raster:
        bbox = get_bbox_from_raster(aoi_raster, out_crs="EPSG:4326")
    elif aoi_vector:
        bbox = get_bbox_from_vector(aoi_vector, out_crs="EPSG:4326", buffer_m=aoi_buffer_m, buffer_crs=out_crs)
    else:
        raise ValueError("Either aoi_raster or aoi_vector must be provided.")

    out_zarr = Path(out_zarr)
    ensure_dir(out_zarr.parent)

    catalog = pystac_client.Client.open(DEA_STAC_URL)
    search = catalog.search(
        bbox=bbox,
        collections=list(DEA_COLLECTIONS),
        datetime=f"{start}/{end}",
        filter={"op": "<", "args": [{"property": "eo:cloud_cover"}, max_cloud_cover]},
    )
    items = list(search.items())
    if not items:
        raise RuntimeError("No Sentinel-2 scenes found for the requested AOI/date range.")

    with DaskClient(n_workers=num_workers, threads_per_worker=threads_per_worker) as client:
        ds = odc.stac.load(
            items,
            bands=list(BANDS),
            crs=out_crs,
            resolution=resolution,
            groupby="solar_day",
            bbox=bbox,
            chunks={"time": chunk_time, "x": chunk_x, "y": chunk_y},
        )

        # DEA fmask classes used in the repo: cloud=2, shadow=3.
        clear_mask = (ds["oa_fmask"] != 2) & (ds["oa_fmask"] != 3)
        ds = ds.drop_vars("oa_fmask").where(clear_mask)

        # Only compute this small time-indexed vector; keep the image cube lazy.
        nan_frac = ds[list(NDVI_BANDS)].to_array().isnull().mean(dim=["variable", "x", "y"]).compute()
        ds = ds.sel(time=nan_frac < max_nan_fraction)
        ds["NDVI"] = compute_ndvi(ds)

        keep_vars = ["NDVI"]
        if keep_source_bands:
            keep_vars.extend([band for band in FRACTIONAL_COVER_BANDS if band in ds])
        keep = ds[keep_vars]
        keep.to_zarr(out_zarr, mode="w", zarr_format=2)
    return out_zarr


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download Sentinel-2 NDVI time series from DEA STAC.")
    parser.add_argument("--aoi-raster", help="Raster defining the overall AOI extent, e.g. DEM.")
    parser.add_argument("--aoi-vector", help="Vector defining the AOI extent when no raster is provided.")
    parser.add_argument("--aoi-buffer-m", type=float, default=0.0, help="Buffer in metres around --aoi-vector for the download extent.")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--out-zarr", required=True, help="Output Zarr path for the NDVI time series")
    parser.add_argument("--out-crs", default="EPSG:6933")
    parser.add_argument("--resolution", type=int, default=10)
    parser.add_argument("--max-cloud-cover", type=float, default=40.0)
    parser.add_argument("--max-nan-fraction", type=float, default=0.20)
    parser.add_argument("--chunk-x", type=int, default=1024)
    parser.add_argument("--chunk-y", type=int, default=1024)
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--threads-per-worker", type=int, default=2)
    parser.add_argument("--keep-source-bands", action="store_true", help="Keep reflectance bands needed for fractional cover")
    args = parser.parse_args()

    out = download_ndvi(
        aoi_raster=args.aoi_raster,
        aoi_vector=args.aoi_vector,
        aoi_buffer_m=args.aoi_buffer_m,
        start=args.start,
        end=args.end,
        out_zarr=args.out_zarr,
        out_crs=args.out_crs,
        resolution=args.resolution,
        max_cloud_cover=args.max_cloud_cover,
        max_nan_fraction=args.max_nan_fraction,
        chunk_x=args.chunk_x,
        chunk_y=args.chunk_y,
        num_workers=args.num_workers,
        threads_per_worker=args.threads_per_worker,
        keep_source_bands=args.keep_source_bands,
    )
    print(f"Saved NDVI time series to: {out}")
