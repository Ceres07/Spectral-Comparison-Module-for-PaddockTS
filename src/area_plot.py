from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import rioxarray  # noqa: F401
import xarray as xr
from rasterio.plot import plotting_extent

from io_utils import buffered_polygon_to_bool_mask, ensure_dir, polygon_to_bool_mask, raster_to_bool_mask, read_vector


def plot_comparison_areas(
    ndvi_zarr: str | Path,
    target_polygon: str | Path,
    out_png: str | Path,
    boolean_raster: str | Path | None = None,
    buffer_m: float | None = None,
    include_values: tuple[int | float, ...] = (1,),
    all_touched: bool = False,
) -> None:
    ds = xr.open_zarr(ndvi_zarr, chunks=None)
    ref = ds["NDVI"].rio.write_crs(ds.rio.crs or "EPSG:6933", inplace=False)

    height = ref.sizes["y"]
    width = ref.sizes["x"]
    transform = ref.rio.transform()
    crs = ref.rio.crs

    if boolean_raster:
        mask_bool = raster_to_bool_mask(
            raster_path=boolean_raster,
            reference_transform=transform,
            width=width,
            height=height,
            reference_crs=crs,
            include_values=include_values,
        )
        mask_label = "Boolean raster only"
    elif buffer_m is not None:
        mask_bool = buffered_polygon_to_bool_mask(
            vector_path=target_polygon,
            reference_transform=transform,
            width=width,
            height=height,
            reference_crs=crs,
            buffer_m=buffer_m,
            all_touched=all_touched,
        )
        mask_label = "Buffer area only"
    else:
        raise ValueError("Either boolean_raster or buffer_m must be provided.")

    poly_bool = polygon_to_bool_mask(
        vector_path=target_polygon,
        reference_transform=transform,
        width=width,
        height=height,
        reference_crs=crs,
        all_touched=all_touched,
    )

    classes = np.zeros((height, width), dtype=np.uint8)
    classes[mask_bool] = 1
    classes[poly_bool] = 2
    classes[mask_bool & poly_bool] = 3
    classes_masked = np.ma.masked_where(classes == 0, classes)

    gdf = read_vector(target_polygon).to_crs(crs)
    extent = plotting_extent(classes, transform)

    cmap = mcolors.ListedColormap(["#e0a23a", "#4c78a8", "#3a9f68"])
    norm = mcolors.BoundaryNorm([0.5, 1.5, 2.5, 3.5], cmap.N)

    fig, ax = plt.subplots(figsize=(9, 9))
    ax.imshow(classes_masked, extent=extent, origin="upper", cmap=cmap, norm=norm, interpolation="nearest", alpha=0.72)
    gdf.boundary.plot(ax=ax, color="#1f1f1f", linewidth=1.5)

    handles = [
        mpatches.Patch(color="#e0a23a", label=mask_label),
        mpatches.Patch(color="#4c78a8", label="Target polygon only"),
        mpatches.Patch(color="#3a9f68", label="Overlap"),
    ]
    ax.legend(handles=handles, loc="upper right")
    ax.set_title("Compared areas on the analysis grid")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.set_aspect("equal")
    fig.tight_layout()

    out_png = Path(out_png)
    ensure_dir(out_png.parent)
    fig.savefig(out_png, dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plot the compared mask, polygon, and overlap areas.")
    parser.add_argument("--ndvi-zarr", required=True)
    parser.add_argument("--target-polygon", required=True)
    parser.add_argument("--out-png", required=True)
    parser.add_argument("--boolean-raster")
    parser.add_argument("--buffer-m", type=float)
    parser.add_argument("--include-values", nargs="+", default=[1])
    parser.add_argument("--all-touched", action="store_true")
    args = parser.parse_args()

    parsed_values = tuple(float(v) if "." in str(v) else int(v) for v in args.include_values)
    plot_comparison_areas(
        ndvi_zarr=args.ndvi_zarr,
        target_polygon=args.target_polygon,
        out_png=args.out_png,
        boolean_raster=args.boolean_raster,
        buffer_m=args.buffer_m,
        include_values=parsed_values,
        all_touched=args.all_touched,
    )
    print(f"Saved comparison area plot to: {args.out_png}")
