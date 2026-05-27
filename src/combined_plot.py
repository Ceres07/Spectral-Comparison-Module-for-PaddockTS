from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


FC_COLORS = {
    "mean_bg": "#b05d3a",
    "mean_pv": "#2f8f45",
    "mean_npv": "#7d78b8",
}


def _select_group(df: pd.DataFrame, group: str) -> pd.DataFrame:
    selected = df[df["group"] == group].copy()
    if selected.empty:
        raise ValueError(f"No rows found for group {group!r}")
    selected["date"] = pd.to_datetime(selected["date"])
    return selected.sort_values("date")


def _read_rainfall(rainfall_csv: str | Path) -> pd.DataFrame:
    rainfall = pd.read_csv(rainfall_csv)
    if "date" not in rainfall.columns and "YYYY-MM-DD" in rainfall.columns:
        rainfall = rainfall.rename(columns={"YYYY-MM-DD": "date"})
    if "date" not in rainfall.columns:
        raise ValueError(f"Rainfall CSV must contain a date or YYYY-MM-DD column: {rainfall_csv}")
    if "daily_rain" not in rainfall.columns:
        raise ValueError(f"Rainfall CSV must contain a daily_rain column: {rainfall_csv}")
    rainfall["date"] = pd.to_datetime(rainfall["date"])
    rainfall["daily_rain"] = pd.to_numeric(rainfall["daily_rain"], errors="coerce").fillna(0)
    return rainfall.sort_values("date")


def plot_combined_vegetation_rainfall(
    ndvi_summary_csv: str | Path,
    fractional_cover_summary_csv: str | Path,
    out_png: str | Path,
    rainfall_csv: str | Path | None = None,
    group: str = "target_polygon",
) -> None:
    ndvi = _select_group(pd.read_csv(ndvi_summary_csv), group)
    fc = _select_group(pd.read_csv(fractional_cover_summary_csv), group)

    merged = pd.merge(
        ndvi[["date", "mean_ndvi"]],
        fc[["date", "mean_bg", "mean_pv", "mean_npv"]],
        on="date",
        how="inner",
    )
    if merged.empty:
        raise ValueError("NDVI and fractional-cover summaries have no dates in common.")

    fc_values = merged[["mean_bg", "mean_pv", "mean_npv"]].clip(lower=0)
    fc_total = fc_values.sum(axis=1).replace(0, np.nan)
    fc_props = fc_values.div(fc_total, axis=0)

    rainfall = None
    has_rainfall = rainfall_csv is not None and Path(rainfall_csv).exists()
    if has_rainfall:
        rainfall = _read_rainfall(rainfall_csv)

    if has_rainfall:
        fig, (ndvi_ax, veg_ax, rain_ax) = plt.subplots(
            3,
            1,
            figsize=(13, 9),
            sharex=True,
            gridspec_kw={"height_ratios": [1.4, 2.2, 1]},
        )
    else:
        fig, (ndvi_ax, veg_ax) = plt.subplots(
            2,
            1,
            figsize=(13, 7),
            sharex=True,
            gridspec_kw={"height_ratios": [1.3, 2]},
        )
        rain_ax = None

    ndvi_ax.plot(merged["date"], merged["mean_ndvi"], color="#111111", linewidth=2.1, label="NDVI")
    ndvi_ax.set_ylim(-0.1, 1)
    ndvi_ax.set_ylabel("NDVI")
    ndvi_ax.legend(loc="upper left")
    ndvi_ax.grid(axis="y", alpha=0.25)
    ndvi_ax.set_title(f"Vegetation fractions, NDVI, and rainfall: {group}")

    veg_ax.stackplot(
        merged["date"],
        fc_props["mean_bg"],
        fc_props["mean_pv"],
        fc_props["mean_npv"],
        labels=["Bare ground", "Green vegetation", "Non-green vegetation"],
        colors=[FC_COLORS["mean_bg"], FC_COLORS["mean_pv"], FC_COLORS["mean_npv"]],
        alpha=0.72,
    )
    veg_ax.set_ylim(0, 1)
    veg_ax.set_ylabel("Fractional cover proportion")
    veg_ax.legend(loc="upper left", ncols=3)
    veg_ax.grid(axis="y", alpha=0.25)

    if has_rainfall and rain_ax is not None and rainfall is not None:
        rain_ax.bar(rainfall["date"], rainfall["daily_rain"], width=1.0, color="#4f85c5", alpha=0.65)
        rain_ax.set_ylabel("Rainfall (mm)")
        rain_ax.set_xlabel("Date")
        rain_ax.grid(axis="y", alpha=0.25)
    else:
        veg_ax.set_xlabel("Date")

    fig.tight_layout()
    fig.savefig(out_png, dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plot fractional-cover proportions alongside NDVI and optional rainfall.")
    parser.add_argument("--ndvi-summary-csv", required=True)
    parser.add_argument("--fractional-cover-summary-csv", required=True)
    parser.add_argument("--out-png", required=True)
    parser.add_argument("--rainfall-csv")
    parser.add_argument("--group", default="target_polygon")
    args = parser.parse_args()

    plot_combined_vegetation_rainfall(
        ndvi_summary_csv=args.ndvi_summary_csv,
        fractional_cover_summary_csv=args.fractional_cover_summary_csv,
        rainfall_csv=args.rainfall_csv,
        out_png=args.out_png,
        group=args.group,
    )
    print(f"Saved combined plot to: {args.out_png}")
