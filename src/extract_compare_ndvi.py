from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rioxarray  # noqa: F401
import xarray as xr

from io_utils import ensure_dir, polygon_to_bool_mask, raster_to_bool_mask


def summarise_group(values_2d: np.ndarray, times: np.ndarray, label: str) -> pd.DataFrame:
    records = []
    for i, t in enumerate(times):
        row = values_2d[i, :]
        row = row[np.isfinite(row)]
        if row.size == 0:
            records.append(
                {
                    "date": pd.to_datetime(str(t)),
                    "group": label,
                    "n_pixels": 0,
                    "mean_ndvi": np.nan,
                    "median_ndvi": np.nan,
                    "std_ndvi": np.nan,
                    "p25_ndvi": np.nan,
                    "p75_ndvi": np.nan,
                    "min_ndvi": np.nan,
                    "max_ndvi": np.nan,
                }
            )
            continue
        records.append(
            {
                "date": pd.to_datetime(str(t)),
                "group": label,
                "n_pixels": int(row.size),
                "mean_ndvi": float(np.nanmean(row)),
                "median_ndvi": float(np.nanmedian(row)),
                "std_ndvi": float(np.nanstd(row)),
                "p25_ndvi": float(np.nanpercentile(row, 25)),
                "p75_ndvi": float(np.nanpercentile(row, 75)),
                "min_ndvi": float(np.nanmin(row)),
                "max_ndvi": float(np.nanmax(row)),
            }
        )
    return pd.DataFrame.from_records(records)


def plot_timeseries(summary_df: pd.DataFrame, out_png: str | Path) -> None:
    plt.figure(figsize=(12, 6))
    for group_name, grp in summary_df.groupby("group"):
        grp = grp.sort_values("date")
        plt.plot(grp["date"], grp["mean_ndvi"], label=group_name)
        plt.fill_between(grp["date"], grp["p25_ndvi"], grp["p75_ndvi"], alpha=0.2)
    plt.xlabel("Date")
    plt.ylabel("NDVI")
    plt.title("Sentinel-2 NDVI time series comparison")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_png, dpi=200)
    plt.close()


def compare_ndvi(
    ndvi_zarr: str,
    boolean_raster: str,
    target_polygon: str,
    outdir: str,
    include_values: tuple[int | float, ...] = (1,),
    save_pixel_values: bool = False,
    all_touched: bool = False,
) -> None:
    outdir = ensure_dir(outdir)
    ds = xr.open_zarr(ndvi_zarr, chunks=None)
    ndvi = ds["NDVI"].rio.write_crs(ds.rio.crs or "EPSG:6933", inplace=False)

    height = ndvi.sizes["y"]
    width = ndvi.sizes["x"]
    transform = ndvi.rio.transform()
    crs = ndvi.rio.crs

    mask_bool = raster_to_bool_mask(
        raster_path=boolean_raster,
        reference_transform=transform,
        width=width,
        height=height,
        reference_crs=crs,
        include_values=include_values,
    )
    poly_bool = polygon_to_bool_mask(
        vector_path=target_polygon,
        reference_transform=transform,
        width=width,
        height=height,
        reference_crs=crs,
        all_touched=all_touched,
    )

    ndvi_np = ndvi.values  # (time, y, x)
    times = ndvi.time.values

    mask_pixels = ndvi_np[:, mask_bool]
    poly_pixels = ndvi_np[:, poly_bool]
    overlap_pixels = ndvi_np[:, (mask_bool & poly_bool)]

    summary = pd.concat(
        [
            summarise_group(mask_pixels, times, "boolean_mask_eq_1"),
            summarise_group(poly_pixels, times, "target_polygon"),
            summarise_group(overlap_pixels, times, "mask_and_polygon_overlap"),
        ],
        ignore_index=True,
    )
    summary.to_csv(outdir / "ndvi_summary_timeseries.csv", index=False)

    # Difference table: mask minus polygon means.
    wide = summary.pivot(index="date", columns="group", values="mean_ndvi").reset_index()
    if {"boolean_mask_eq_1", "target_polygon"}.issubset(wide.columns):
        wide["mean_ndvi_diff_mask_minus_polygon"] = wide["boolean_mask_eq_1"] - wide["target_polygon"]
    wide.to_csv(outdir / "ndvi_mean_difference_timeseries.csv", index=False)

    plot_timeseries(summary_df=summary[summary["group"] != "mask_and_polygon_overlap"], out_png=outdir / "ndvi_comparison.png")

    mask_count = int(mask_bool.sum())
    poly_count = int(poly_bool.sum())
    overlap_count = int((mask_bool & poly_bool).sum())
    pd.DataFrame(
        {
            "group": ["boolean_mask_eq_1", "target_polygon", "mask_and_polygon_overlap"],
            "n_pixels": [mask_count, poly_count, overlap_count],
        }
    ).to_csv(outdir / "pixel_counts.csv", index=False)

    if save_pixel_values:
        records = []
        for label, bool_mask in [
            ("boolean_mask_eq_1", mask_bool),
            ("target_polygon", poly_bool),
            ("mask_and_polygon_overlap", mask_bool & poly_bool),
        ]:
            ys, xs = np.where(bool_mask)
            data = ndvi_np[:, ys, xs]
            for idx, (yy, xx) in enumerate(zip(ys, xs)):
                pixel_series = data[:, idx]
                for t, value in zip(times, pixel_series):
                    records.append(
                        {
                            "date": pd.to_datetime(str(t)),
                            "group": label,
                            "row": int(yy),
                            "col": int(xx),
                            "x": float(ndvi.x.values[xx]),
                            "y": float(ndvi.y.values[yy]),
                            "ndvi": float(value) if np.isfinite(value) else np.nan,
                        }
                    )
        pd.DataFrame.from_records(records).to_csv(outdir / "ndvi_pixel_values_long.csv", index=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract and compare NDVI values for a boolean raster and a target polygon.")
    parser.add_argument("--ndvi-zarr", required=True)
    parser.add_argument("--boolean-raster", required=True)
    parser.add_argument("--target-polygon", required=True)
    parser.add_argument("--outdir", required=True)
    parser.add_argument("--include-values", nargs="+", default=[1], help="Raster values to treat as TRUE in the boolean raster")
    parser.add_argument("--save-pixel-values", action="store_true")
    parser.add_argument("--all-touched", action="store_true")
    args = parser.parse_args()

    parsed_values = tuple(float(v) if "." in str(v) else int(v) for v in args.include_values)
    compare_ndvi(
        ndvi_zarr=args.ndvi_zarr,
        boolean_raster=args.boolean_raster,
        target_polygon=args.target_polygon,
        outdir=args.outdir,
        include_values=parsed_values,
        save_pixel_values=args.save_pixel_values,
        all_touched=args.all_touched,
    )
    print(f"Saved comparison outputs to: {args.outdir}")
