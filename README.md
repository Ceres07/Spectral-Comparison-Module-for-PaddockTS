# Spectral Comparison Module for PaddockTS

This workflow compares Sentinel-2 spectral time series for a target paddock polygon against either a boolean raster or a buffered area around the polygon.

It does four things:

1. downloads a Sentinel-2 NDVI time series for the full extent of an AOI raster or buffered target polygon,
2. compares NDVI through time for:
   - all pixels where a boolean raster equals `1`
   - or all pixels inside a buffer around the target polygon
   - all pixels inside a target polygon
   - the overlap between those two groups
3. estimates fractional cover (`bg`, `pv`, `npv`) from Sentinel-2 reflectance and compares those same groups.

It uses the same basic approach as the `paddock-ts-local` repo you linked: DEA STAC for Sentinel-2 download, cloud/shadow masking via `oa_fmask`, NDVI from `nbart_nir_1` and `nbart_red`, and the bundled fractional-cover TFLite models adapted from `fractionalcover3`.

## Folder contents

- `src/io_utils.py` – helpers for reading vectors/raster bounds and building masks
- `src/download_s2_ndvi.py` – downloads Sentinel-2 from DEA STAC and computes NDVI
- `src/extract_compare_ndvi.py` – extracts NDVI values for the boolean raster and polygon, then summarises them
- `src/fractional_cover.py` – computes and summarises bare/green/non-green fractional cover
- `src/fractional_cover_models/` – bundled TFLite models used by the fractional-cover estimate
- `src/run_query.py` – runs the workflow from editable `workflow_query.py`
- `src/run_workflow.py` – runs the full workflow end-to-end
- `workflow_query.py` – editable one-line workflow configuration
- `requirements.txt` – Python dependencies

## Important note about your uploaded shapefile

Your uploaded shapefile only included the `.shp` component. A complete shapefile normally also includes `.shx`, `.dbf`, and usually `.prj`. The code tries to recover a missing `.shx` automatically and assumes `EPSG:4326` if the CRS is missing, but it is still better to provide the full shapefile set if you can. The uploaded geometry coordinates look like longitude/latitude, so `EPSG:4326` is a reasonable fallback here.

## Inputs expected

### 1) AOI extent
In raster mode, use your DEM for the overall AOI extent.

Example:

- `/mnt/data/PetersPond_dem_5m_2.tif`

In buffer mode, the AOI extent is created from the target polygon plus `--buffer-m`, so no AOI raster is required.

### 2) Boolean raster
In raster mode, this should be a raster where the pixels you want to extract are coded as `1`.

Examples:

- `1 = include, 0 = exclude`
- `1 = treatment area, 0 = not treatment`

If your true values are not `1`, you can pass a different value with `--include-values`.

In buffer mode, no boolean raster is needed. The buffered target polygon becomes the comparison mask and is labelled `buffer_area` in the output tables.

### 3) Target polygon
This is the specific polygon you want to compare against the boolean-mask pixels.

Example:

- `/mnt/data/PetersPondPaddock.shp`

## Setup

Create a clean environment and install dependencies:

```bash
cd /path/to/ndvi_s2_workflow
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
pip install --upgrade pip
pip install -r requirements.txt
```

## Run the full workflow

### Editable query file

Edit `workflow_query.py`, then run the whole workflow with one line:

```bash
python src/run_query.py
```

You can also keep multiple query files and select one:

```bash
python src/run_query.py --query queries/peters_pond.py
```

### Raster comparison mode

```bash
python src/run_workflow.py \
  --aoi-raster /mnt/data/PetersPond_dem_5m_2.tif \
  --boolean-raster /path/to/your_boolean_mask.tif \
  --target-polygon /mnt/data/PetersPondPaddock.shp \
  --start 2019-01-01 \
  --end 2026-03-01 \
  --outdir /path/to/output_folder \
  --silo-email you@example.com
```

Rainfall uses SILO DataDrill at the target polygon centroid. You can pass the registered email with `--silo-email` or set `SILO_EMAIL` in your shell. If no email is provided, the workflow still writes the combined vegetation/NDVI plot without rainfall.

### Buffer comparison mode

To compare a target polygon against everything inside a surrounding buffer, omit `--aoi-raster` and `--boolean-raster`:

```bash
python src/run_workflow.py \
  --target-polygon /mnt/data/PetersPondPaddock.shp \
  --comparison-mode buffer \
  --buffer-m 500 \
  --start 2019-01-01 \
  --end 2026-03-01 \
  --outdir /path/to/output_folder
```

This downloads Sentinel-2 for the buffered target polygon extent. The comparison group in CSV outputs is `buffer_area`.

If your boolean raster uses a different TRUE value, for example `255`:

```bash
python src/run_workflow.py \
  --aoi-raster /mnt/data/PetersPond_dem_5m_2.tif \
  --boolean-raster /path/to/your_boolean_mask.tif \
  --target-polygon /mnt/data/PetersPondPaddock.shp \
  --start 2019-01-01 \
  --end 2026-03-01 \
  --outdir /path/to/output_folder \
  --include-values 255
```

If you also want every pixel value written out in long format:

```bash
python src/run_workflow.py \
  --aoi-raster /mnt/data/PetersPond_dem_5m_2.tif \
  --boolean-raster /path/to/your_boolean_mask.tif \
  --target-polygon /mnt/data/PetersPondPaddock.shp \
  --start 2019-01-01 \
  --end 2026-03-01 \
  --outdir /path/to/output_folder \
  --save-pixel-values
```

## Outputs

The workflow writes these files:

- `ndvi_timeseries.zarr` – full downloaded NDVI cube
- `ndvi_summary_timeseries.csv` – date-by-date summary stats for each group
- `ndvi_mean_difference_timeseries.csv` – mean NDVI difference through time (`mask - polygon`)
- `comparison_areas.png` – map of boolean-raster or buffer pixels, target-polygon pixels, and their overlap on the analysis grid
- `fractional_cover_timeseries.zarr` – fractional cover cube with `bg`, `pv`, and `npv`
- `fractional_cover_summary_timeseries.csv` – date-by-date cover stats for each group
- `fractional_cover_mean_difference_timeseries.csv` – mean cover differences through time
- `fractional_cover_comparison.png` – comparison plot for bare, green, and non-green cover
- `silo_daily_rainfall.csv` – daily SILO rainfall for the target polygon centroid, if a SILO email is provided
- `vegetation_ndvi_rainfall.png` – stacked fractional-cover proportions with NDVI and optional rainfall
- `pixel_counts.csv` – number of pixels in each group
- `ndvi_comparison.png` – comparison plot of mean NDVI through time with IQR ribbon
- `ndvi_pixel_values_long.csv` – optional per-pixel long table if `--save-pixel-values` is used

To keep the old NDVI-only behavior:

```bash
python src/run_workflow.py \
  --aoi-raster /mnt/data/PetersPond_dem_5m_2.tif \
  --boolean-raster /path/to/your_boolean_mask.tif \
  --target-polygon /mnt/data/PetersPondPaddock.shp \
  --start 2019-01-01 \
  --end 2026-03-01 \
  --outdir /path/to/output_folder \
  --skip-fractional-cover
```

## Separate-step execution

If you prefer to run download and extraction separately:

### Step 1 – download NDVI

```bash
python src/download_s2_ndvi.py \
  --aoi-raster /mnt/data/PetersPond_dem_5m_2.tif \
  --start 2019-01-01 \
  --end 2026-03-01 \
  --out-zarr /path/to/output_folder/ndvi_timeseries.zarr \
  --keep-source-bands
```

### Step 2 – extract and compare

```bash
python src/extract_compare_ndvi.py \
  --ndvi-zarr /path/to/output_folder/ndvi_timeseries.zarr \
  --boolean-raster /path/to/your_boolean_mask.tif \
  --target-polygon /mnt/data/PetersPondPaddock.shp \
  --outdir /path/to/output_folder
```

### Step 3 – compute fractional cover

```bash
python src/fractional_cover.py \
  --sentinel2-zarr /path/to/output_folder/ndvi_timeseries.zarr \
  --out-zarr /path/to/output_folder/fractional_cover_timeseries.zarr \
  --boolean-raster /path/to/your_boolean_mask.tif \
  --target-polygon /mnt/data/PetersPondPaddock.shp \
  --outdir /path/to/output_folder
```

### Step 4 – rainfall and combined plot

```bash
python src/rainfall.py \
  --target-polygon /mnt/data/PetersPondPaddock.shp \
  --start 2019-01-01 \
  --end 2026-03-01 \
  --out-csv /path/to/output_folder/silo_daily_rainfall.csv \
  --silo-email you@example.com

python src/combined_plot.py \
  --ndvi-summary-csv /path/to/output_folder/ndvi_summary_timeseries.csv \
  --fractional-cover-summary-csv /path/to/output_folder/fractional_cover_summary_timeseries.csv \
  --rainfall-csv /path/to/output_folder/silo_daily_rainfall.csv \
  --out-png /path/to/output_folder/vegetation_ndvi_rainfall.png
```

To show target-polygon deviation from a comparison group in units of the comparison group's per-date standard deviation:

```bash
python src/combined_plot.py \
  --ndvi-summary-csv /path/to/output_folder/ndvi_summary_timeseries.csv \
  --fractional-cover-summary-csv /path/to/output_folder/fractional_cover_summary_timeseries.csv \
  --rainfall-csv /path/to/output_folder/silo_daily_rainfall.csv \
  --out-png /path/to/output_folder/vegetation_ndvi_rainfall.png \
  --plot-method relative_quantile \
  --group target_polygon \
  --comparison-group boolean_mask_eq_1
```

In this mode, each point is calculated as `(target value - comparison mean) / comparison standard deviation` for that date. The fractional-cover summary must include `std_bg`, `std_pv`, and `std_npv`; rerun the fractional-cover summary step if your CSV was generated before those columns were added.

For buffer mode, use `--comparison-group buffer_area`.

## Assumptions built into the code

- the DEM defines the overall download extent in raster mode
- the buffered target polygon defines the download extent in buffer mode
- the polygon is the comparison area
- in buffer mode, the comparison mask includes all pixels inside the buffer, including the target polygon itself
- the boolean raster can be in a different CRS/resolution; it is reprojected to the NDVI grid with nearest-neighbour resampling
- the polygon is rasterised to the NDVI grid
- summaries are based on all valid NDVI pixels per date after cloud/shadow masking and scene-level NaN filtering

## Practical advice

- Keep the AOI reasonably small. Multi-year Sentinel-2 downloads can get large.
- Start with a shorter test period first, e.g. one year.
- If Dask reports worker memory errors, retry with smaller chunks and fewer workers, for example add `--chunk-x 512 --chunk-y 512 --num-workers 2 --threads-per-worker 1`.
- If downloads are slow or memory-heavy, reduce the date range before scaling up.
- If the polygon result looks shifted, check the CRS of the source vector and upload the missing `.prj` file.
