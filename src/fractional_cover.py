from __future__ import annotations

import argparse
import os
import warnings
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
warnings.filterwarnings("ignore", module="tensorflow")
warnings.filterwarnings("ignore", module="keras")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rioxarray  # noqa: F401
import xarray as xr

from io_utils import ensure_dir, polygon_to_bool_mask, raster_to_bool_mask


FC_BANDS = ("nbart_blue", "nbart_green", "nbart_red", "nbart_nir_1", "nbart_swir_2", "nbart_swir_3")
FC_OUTPUTS = ("bg", "pv", "npv")
MODEL_FILES = (
    "fcModel_32x32x32.tflite",
    "fcModel_64x64x64.tflite",
    "fcModel_256x64x256.tflite",
    "fcModel_256x128x256.tflite",
)


def get_model(model_n: int = 4):
    try:
        from tensorflow import lite as tflite
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Fractional cover estimation requires tensorflow. Install it with `pip install tensorflow`."
        ) from exc

    if not 1 <= model_n <= len(MODEL_FILES):
        raise ValueError(f"model_n must be between 1 and {len(MODEL_FILES)}")

    model_path = Path(__file__).resolve().parent / "fractional_cover_models" / MODEL_FILES[model_n - 1]
    if not model_path.exists():
        raise FileNotFoundError(f"Missing fractional cover model: {model_path}")
    return tflite.Interpreter(model_path=str(model_path))


def unmix_fractional_cover(surface_reflectance: np.ndarray, fc_model, in_null: float = 0, out_null: float = 0) -> np.ndarray:
    """Unmix six-band Sentinel-2 reflectance to bare/green/non-green fractions."""
    inshape = surface_reflectance[1:].shape
    ref_data = np.reshape(surface_reflectance[1:], (inshape[0], -1)).T

    input_details = fc_model.get_input_details()
    output_details = fc_model.get_output_details()
    fc_model.resize_tensor_input(input_details[0]["index"], ref_data.shape)
    fc_model.allocate_tensors()
    fc_model.set_tensor(input_details[0]["index"], ref_data.astype(np.float32))
    fc_model.invoke()

    fc_layers = fc_model.get_tensor(output_details[0]["index"]).T
    output_fc = np.reshape(fc_layers, (3, inshape[1], inshape[2]))
    output_fc[output_fc == in_null] = out_null
    return output_fc


def compute_fractional_cover(
    sentinel2_zarr: str | Path,
    out_zarr: str | Path,
    model_n: int = 4,
    correction: bool = False,
) -> Path:
    ds = xr.open_zarr(sentinel2_zarr, chunks={})
    missing = [band for band in FC_BANDS if band not in ds]
    if missing:
        raise ValueError(
            "The Sentinel-2 Zarr does not contain the bands needed for fractional cover: "
            f"{', '.join(missing)}. Re-run download with source bands enabled."
        )

    if ds.sizes.get("time", 0) == 0:
        raise ValueError("The Sentinel-2 Zarr has no timesteps to process.")

    if correction:
        scale = np.array([0.9551, 1.0582, 0.9871, 1.0187, 0.9528, 0.9688], dtype=np.float32) + np.array(
            [-0.0022, 0.0031, 0.0064, 0.012, 0.0079, -0.0042], dtype=np.float32
        )
    else:
        scale = np.full(len(FC_BANDS), 0.0001, dtype=np.float32)

    out_zarr = Path(out_zarr)
    ensure_dir(out_zarr.parent)
    model = get_model(model_n=model_n)

    for time_idx in range(ds.sizes["time"]):
        frame = np.stack([ds[band].isel(time=time_idx).values for band in FC_BANDS], axis=0).astype(np.float32)
        frame[frame == 0] = np.nan
        frame *= scale[:, np.newaxis, np.newaxis]

        valid = np.isfinite(frame).all(axis=0)
        frame = np.nan_to_num(frame, nan=0.0)
        mixed = unmix_fractional_cover(frame, fc_model=model)
        mixed[:, ~valid] = np.nan

        coords = {"time": ds.time.isel(time=[time_idx]), "y": ds.y, "x": ds.x}
        frame_ds = xr.Dataset(
            {
                "bg": xr.DataArray(mixed[np.newaxis, 0], dims=("time", "y", "x"), coords=coords),
                "pv": xr.DataArray(mixed[np.newaxis, 1], dims=("time", "y", "x"), coords=coords),
                "npv": xr.DataArray(mixed[np.newaxis, 2], dims=("time", "y", "x"), coords=coords),
            }
        )
        for name, long_name in {
            "bg": "Bare ground fractional cover",
            "pv": "Green vegetation fractional cover",
            "npv": "Non-green vegetation fractional cover",
        }.items():
            frame_ds[name].attrs.update({"long_name": long_name})

        if ds.rio.crs is not None:
            frame_ds = frame_ds.rio.write_crs(ds.rio.crs, inplace=False)

        if time_idx == 0:
            frame_ds.to_zarr(out_zarr, mode="w", zarr_format=2)
        else:
            frame_ds.to_zarr(out_zarr, mode="a", append_dim="time", zarr_format=2)
    return out_zarr


def summarise_fractional_cover_group(fc_ds: xr.Dataset, bool_mask: np.ndarray, label: str) -> pd.DataFrame:
    records = []
    times = fc_ds.time.values
    for time_idx, time_value in enumerate(times):
        record = {"date": pd.to_datetime(str(time_value)), "group": label}
        valid_count = 0
        for band in FC_OUTPUTS:
            values = fc_ds[band].isel(time=time_idx).values[bool_mask]
            values = values[np.isfinite(values)]
            valid_count = max(valid_count, int(values.size))
            record[f"mean_{band}"] = float(np.nanmean(values)) if values.size else np.nan
            record[f"median_{band}"] = float(np.nanmedian(values)) if values.size else np.nan
            record[f"p25_{band}"] = float(np.nanpercentile(values, 25)) if values.size else np.nan
            record[f"p75_{band}"] = float(np.nanpercentile(values, 75)) if values.size else np.nan
        record["n_pixels"] = valid_count
        records.append(record)
    return pd.DataFrame.from_records(records)


def plot_fractional_cover(summary_df: pd.DataFrame, out_png: str | Path) -> None:
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
    for ax, band, label in zip(axes, FC_OUTPUTS, ("Bare ground", "Green vegetation", "Non-green vegetation")):
        for group_name, grp in summary_df.groupby("group"):
            if group_name == "mask_and_polygon_overlap":
                continue
            grp = grp.sort_values("date")
            ax.plot(grp["date"], grp[f"mean_{band}"], label=group_name)
            ax.fill_between(grp["date"], grp[f"p25_{band}"], grp[f"p75_{band}"], alpha=0.2)
        ax.set_ylabel(label)
        ax.set_ylim(0, 1)
    axes[0].legend()
    axes[-1].set_xlabel("Date")
    fig.suptitle("Sentinel-2 fractional cover time series comparison")
    fig.tight_layout()
    fig.savefig(out_png, dpi=200)
    plt.close(fig)


def summarise_fractional_cover(
    fractional_cover_zarr: str | Path,
    boolean_raster: str | Path,
    target_polygon: str | Path,
    outdir: str | Path,
    include_values: tuple[int | float, ...] = (1,),
    all_touched: bool = False,
) -> None:
    outdir = ensure_dir(outdir)
    fc_ds = xr.open_zarr(fractional_cover_zarr, chunks=None)
    ref = fc_ds["pv"].rio.write_crs(fc_ds.rio.crs or "EPSG:6933", inplace=False)

    height = ref.sizes["y"]
    width = ref.sizes["x"]
    transform = ref.rio.transform()
    crs = ref.rio.crs

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

    summary = pd.concat(
        [
            summarise_fractional_cover_group(fc_ds, mask_bool, "boolean_mask_eq_1"),
            summarise_fractional_cover_group(fc_ds, poly_bool, "target_polygon"),
            summarise_fractional_cover_group(fc_ds, mask_bool & poly_bool, "mask_and_polygon_overlap"),
        ],
        ignore_index=True,
    )
    summary.to_csv(outdir / "fractional_cover_summary_timeseries.csv", index=False)

    wide = summary.pivot(index="date", columns="group", values=["mean_bg", "mean_pv", "mean_npv"])
    wide.columns = [f"{metric}_{group}" for metric, group in wide.columns]
    if "mean_pv_boolean_mask_eq_1" in wide and "mean_pv_target_polygon" in wide:
        wide["mean_pv_diff_mask_minus_polygon"] = wide["mean_pv_boolean_mask_eq_1"] - wide["mean_pv_target_polygon"]
    wide.reset_index().to_csv(outdir / "fractional_cover_mean_difference_timeseries.csv", index=False)

    plot_fractional_cover(summary, outdir / "fractional_cover_comparison.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute and summarise Sentinel-2 fractional cover.")
    parser.add_argument("--sentinel2-zarr", required=True, help="Zarr containing the six source Sentinel-2 bands")
    parser.add_argument("--out-zarr", required=True, help="Output fractional-cover Zarr path")
    parser.add_argument("--boolean-raster")
    parser.add_argument("--target-polygon")
    parser.add_argument("--outdir")
    parser.add_argument("--include-values", nargs="+", default=[1], help="Raster values to treat as TRUE")
    parser.add_argument("--all-touched", action="store_true")
    parser.add_argument("--model-n", type=int, default=4, choices=(1, 2, 3, 4))
    parser.add_argument("--correction", action="store_true")
    args = parser.parse_args()

    out = compute_fractional_cover(
        sentinel2_zarr=args.sentinel2_zarr,
        out_zarr=args.out_zarr,
        model_n=args.model_n,
        correction=args.correction,
    )
    if args.boolean_raster or args.target_polygon or args.outdir:
        if not (args.boolean_raster and args.target_polygon and args.outdir):
            raise ValueError("--boolean-raster, --target-polygon, and --outdir are required when summarising")
        parsed_values = tuple(float(v) if "." in str(v) else int(v) for v in args.include_values)
        summarise_fractional_cover(
            fractional_cover_zarr=out,
            boolean_raster=args.boolean_raster,
            target_polygon=args.target_polygon,
            outdir=args.outdir,
            include_values=parsed_values,
            all_touched=args.all_touched,
        )
    print(f"Saved fractional cover to: {out}")
