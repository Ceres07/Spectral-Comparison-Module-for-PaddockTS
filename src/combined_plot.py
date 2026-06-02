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
FC_LABELS = {
    "bg": "Bare ground",
    "pv": "Green vegetation",
    "npv": "Non-green vegetation",
}
DEFAULT_COMPARISON_GROUP = "boolean_mask_eq_1"


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


def _relative_deviation(
    target_values: pd.Series,
    comparison_mean: pd.Series,
    comparison_std: pd.Series,
) -> pd.Series:
    comparison_std = comparison_std.replace(0, np.nan)
    return (target_values - comparison_mean) / comparison_std


def _merge_target_comparison(df: pd.DataFrame, target_group: str, comparison_group: str) -> pd.DataFrame:
    target = _select_group(df, target_group)
    comparison = _select_group(df, comparison_group)
    merged = pd.merge(target, comparison, on="date", how="inner", suffixes=("_target", "_comparison"))
    if merged.empty:
        raise ValueError(f"{target_group!r} and {comparison_group!r} have no dates in common.")
    return merged


def _require_columns(df: pd.DataFrame, columns: list[str], source_name: str) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(f"{source_name} is missing required columns for relative_quantile: {', '.join(missing)}")


def _plot_relative_quantile(
    ax,
    dates: pd.Series,
    df: pd.DataFrame,
    metric: str,
    label: str,
    color: str,
) -> None:
    mean_target = f"mean_{metric}_target"
    mean_comparison = f"mean_{metric}_comparison"
    std_comparison = f"std_{metric}_comparison"
    p25_target = f"p25_{metric}_target"
    p75_target = f"p75_{metric}_target"
    _require_columns(df, [mean_target, mean_comparison, std_comparison], label)

    mean_rel = _relative_deviation(df[mean_target], df[mean_comparison], df[std_comparison])
    ax.plot(dates, mean_rel, color=color, linewidth=2.0, label=label)

    if p25_target in df.columns and p75_target in df.columns:
        p25_rel = _relative_deviation(df[p25_target], df[mean_comparison], df[std_comparison])
        p75_rel = _relative_deviation(df[p75_target], df[mean_comparison], df[std_comparison])
        ax.fill_between(dates, p25_rel, p75_rel, color=color, alpha=0.18)


def plot_combined_vegetation_rainfall(
    ndvi_summary_csv: str | Path,
    fractional_cover_summary_csv: str | Path,
    out_png: str | Path,
    rainfall_csv: str | Path | None = None,
    group: str = "target_polygon",
    comparison_group: str = DEFAULT_COMPARISON_GROUP,
    plot_method: str = "absolute",
) -> None:
    if plot_method not in {"absolute", "relative_quantile"}:
        raise ValueError("plot_method must be 'absolute' or 'relative_quantile'")

    ndvi_all = pd.read_csv(ndvi_summary_csv)
    fc_all = pd.read_csv(fractional_cover_summary_csv)
    ndvi = _select_group(ndvi_all, group)
    fc = _select_group(fc_all, group)

    ndvi_cols = [col for col in ["date", "mean_ndvi", "p25_ndvi", "p75_ndvi"] if col in ndvi.columns]
    fc_cols = [
        col
        for col in [
            "date",
            "mean_bg",
            "p25_bg",
            "p75_bg",
            "mean_pv",
            "p25_pv",
            "p75_pv",
            "mean_npv",
            "p25_npv",
            "p75_npv",
        ]
        if col in fc.columns
    ]
    merged = pd.merge(ndvi[ndvi_cols], fc[fc_cols], on="date", how="inner")
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

    if plot_method == "relative_quantile":
        ndvi_relative = _merge_target_comparison(ndvi_all, group, comparison_group)
        fc_relative = _merge_target_comparison(fc_all, group, comparison_group)

        _plot_relative_quantile(
            ndvi_ax,
            ndvi_relative["date"],
            ndvi_relative,
            metric="ndvi",
            label="NDVI",
            color="#111111",
        )
        ndvi_ax.axhline(0, color="#777777", linewidth=0.9)
        ndvi_ax.set_ylabel("Relative deviation")
        ndvi_ax.legend(loc="upper left")
        ndvi_ax.grid(axis="y", alpha=0.25)
        ndvi_ax.set_title(f"Target minus comparison, in comparison standard deviations: {group} vs {comparison_group}")

        for key in ("bg", "pv", "npv"):
            _plot_relative_quantile(
                veg_ax,
                fc_relative["date"],
                fc_relative,
                metric=key,
                label=FC_LABELS[key],
                color=FC_COLORS[f"mean_{key}"],
            )
        veg_ax.axhline(0, color="#777777", linewidth=0.9)
        veg_ax.set_ylabel("Relative deviation")
        veg_ax.legend(loc="upper left", ncols=3)
        veg_ax.grid(axis="y", alpha=0.25)
    else:
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
            labels=[FC_LABELS["bg"], FC_LABELS["pv"], FC_LABELS["npv"]],
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
    parser.add_argument("--comparison-group", default=DEFAULT_COMPARISON_GROUP)
    parser.add_argument("--plot-method", choices=("absolute", "relative_quantile"), default="absolute")
    args = parser.parse_args()

    plot_combined_vegetation_rainfall(
        ndvi_summary_csv=args.ndvi_summary_csv,
        fractional_cover_summary_csv=args.fractional_cover_summary_csv,
        rainfall_csv=args.rainfall_csv,
        out_png=args.out_png,
        group=args.group,
        comparison_group=args.comparison_group,
        plot_method=args.plot_method,
    )
    print(f"Saved combined plot to: {args.out_png}")
