"""Editable one-line workflow query.

Run with:

    python src/run_query.py

For the buffer mode, set comparison_mode to "buffer" and provide only a
target_polygon plus buffer_m. The buffered polygon defines both the Sentinel-2
download extent and the comparison area.
"""

CONFIG = {
    # Required in both modes.
    "target_polygon": "/path/to/target_paddock.shp",
    "start": "2019-01-01",
    "end": "2026-03-01",
    "outdir": "/path/to/output_folder",

    # Choose "raster" for an existing boolean raster, or "buffer" to build the
    # comparison area from target_polygon buffered by buffer_m metres.
    "comparison_mode": "buffer",
    "buffer_m": 500,

    # Raster mode only.
    "aoi_raster": None,
    "boolean_raster": None,
    "include_values": [1],

    # Download / processing settings.
    "out_crs": "EPSG:6933",
    "resolution": 10,
    "max_cloud_cover": 40.0,
    "max_nan_fraction": 0.20,
    "chunk_x": 512,
    "chunk_y": 512,
    "num_workers": 2,
    "threads_per_worker": 1,

    # Optional outputs.
    "save_pixel_values": False,
    "all_touched": False,
    "skip_fractional_cover": False,
    "fc_model_n": 4,
    "fc_correction": False,
    "silo_email": None,
    "plot_group": "target_polygon",
    "comparison_group": None,
    "plot_method": "absolute",
}
