from __future__ import annotations

import argparse
import os
from pathlib import Path

from area_plot import plot_comparison_areas
from combined_plot import plot_combined_vegetation_rainfall
from download_s2_ndvi import download_ndvi
from extract_compare_ndvi import compare_ndvi
from fractional_cover import compute_fractional_cover, summarise_fractional_cover
from io_utils import ensure_dir
from rainfall import download_silo_rainfall


def main() -> None:
    parser = argparse.ArgumentParser(
        description="End-to-end workflow: download Sentinel-2 NDVI, then compare mask vs target polygon."
    )
    parser.add_argument("--aoi-raster", required=True, help="Raster defining the overall AOI extent, e.g. DEM")
    parser.add_argument("--boolean-raster", required=True, help="Raster with TRUE pixels coded as 1 (or another provided include value)")
    parser.add_argument("--target-polygon", required=True, help="Shapefile/GPKG/GeoJSON for the comparison polygon")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--outdir", required=True, help="Output directory")
    parser.add_argument("--include-values", nargs="+", default=[1], help="Raster values to treat as TRUE in the boolean raster")
    parser.add_argument("--save-pixel-values", action="store_true")
    parser.add_argument("--all-touched", action="store_true")
    parser.add_argument("--out-crs", default="EPSG:6933")
    parser.add_argument("--resolution", type=int, default=10)
    parser.add_argument("--max-cloud-cover", type=float, default=40.0)
    parser.add_argument("--max-nan-fraction", type=float, default=0.20)
    parser.add_argument("--chunk-x", type=int, default=1024)
    parser.add_argument("--chunk-y", type=int, default=1024)
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--threads-per-worker", type=int, default=2)
    parser.add_argument("--skip-fractional-cover", action="store_true", help="Only compute NDVI outputs")
    parser.add_argument("--fc-model-n", type=int, default=4, choices=(1, 2, 3, 4), help="Fractional cover TFLite model variant")
    parser.add_argument("--fc-correction", action="store_true", help="Apply the optional fractionalcover3 band correction")
    parser.add_argument("--silo-email", help="Registered SILO email for rainfall download; can also use SILO_EMAIL")
    parser.add_argument("--plot-group", default="target_polygon", help="Group to use for the combined NDVI/fractional-cover plot")
    args = parser.parse_args()

    outdir = ensure_dir(args.outdir)
    ndvi_zarr = Path(outdir) / "ndvi_timeseries.zarr"
    parsed_values = tuple(float(v) if "." in str(v) else int(v) for v in args.include_values)

    total_steps = 3 if args.skip_fractional_cover else 5
    print(f"Step 1/{total_steps}: downloading Sentinel-2 and computing NDVI...")
    download_ndvi(
        aoi_raster=args.aoi_raster,
        start=args.start,
        end=args.end,
        out_zarr=str(ndvi_zarr),
        out_crs=args.out_crs,
        resolution=args.resolution,
        max_cloud_cover=args.max_cloud_cover,
        max_nan_fraction=args.max_nan_fraction,
        chunk_x=args.chunk_x,
        chunk_y=args.chunk_y,
        num_workers=args.num_workers,
        threads_per_worker=args.threads_per_worker,
        keep_source_bands=not args.skip_fractional_cover,
    )

    print(f"Step 2/{total_steps}: extracting and comparing NDVI values...")
    compare_ndvi(
        ndvi_zarr=str(ndvi_zarr),
        boolean_raster=args.boolean_raster,
        target_polygon=args.target_polygon,
        outdir=str(outdir),
        include_values=parsed_values,
        save_pixel_values=args.save_pixel_values,
        all_touched=args.all_touched,
    )

    print(f"Step 3/{total_steps}: plotting compared areas...")
    plot_comparison_areas(
        ndvi_zarr=str(ndvi_zarr),
        boolean_raster=args.boolean_raster,
        target_polygon=args.target_polygon,
        out_png=Path(outdir) / "comparison_areas.png",
        include_values=parsed_values,
        all_touched=args.all_touched,
    )

    if not args.skip_fractional_cover:
        print(f"Step 4/{total_steps}: computing and comparing fractional cover...")
        fractional_cover_zarr = Path(outdir) / "fractional_cover_timeseries.zarr"
        compute_fractional_cover(
            sentinel2_zarr=str(ndvi_zarr),
            out_zarr=str(fractional_cover_zarr),
            model_n=args.fc_model_n,
            correction=args.fc_correction,
        )
        summarise_fractional_cover(
            fractional_cover_zarr=str(fractional_cover_zarr),
            boolean_raster=args.boolean_raster,
            target_polygon=args.target_polygon,
            outdir=str(outdir),
            include_values=parsed_values,
            all_touched=args.all_touched,
        )

        print(f"Step 5/{total_steps}: plotting vegetation fractions, NDVI, and rainfall...")
        rainfall_csv = Path(outdir) / "silo_daily_rainfall.csv"
        silo_email = args.silo_email or os.environ.get("SILO_EMAIL")
        if rainfall_csv.exists():
            print(f"  Using cached rainfall: {rainfall_csv}")
        elif silo_email:
            download_silo_rainfall(
                target_polygon=args.target_polygon,
                start=args.start,
                end=args.end,
                out_csv=rainfall_csv,
                email=silo_email,
            )
        else:
            rainfall_csv = None
            print("  No cached rainfall found; pass --silo-email or set SILO_EMAIL to include SILO rainfall.")

        plot_combined_vegetation_rainfall(
            ndvi_summary_csv=Path(outdir) / "ndvi_summary_timeseries.csv",
            fractional_cover_summary_csv=Path(outdir) / "fractional_cover_summary_timeseries.csv",
            rainfall_csv=rainfall_csv,
            out_png=Path(outdir) / "vegetation_ndvi_rainfall.png",
            group=args.plot_group,
        )

    print(f"Workflow complete. Outputs written to: {outdir}")


if __name__ == "__main__":
    main()
