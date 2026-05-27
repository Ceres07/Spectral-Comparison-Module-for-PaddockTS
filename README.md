# Spectral Comparison Module for PaddockTS

This workflow compares Sentinel-2 spectral time series for a boolean raster, a target paddock polygon, and their overlap.

It does four things:

1. downloads a Sentinel-2 NDVI time series for the full extent of an AOI raster (your DEM),
2. compares NDVI through time for:
   - all pixels where a boolean raster equals `1`
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
- `src/run_workflow.py` – runs the full workflow end-to-end
- `requirements.txt` – Python dependencies

## Important note about your uploaded shapefile

Your uploaded shapefile only included the `.shp` component. A complete shapefile normally also includes `.shx`, `.dbf`, and usually `.prj`. The code tries to recover a missing `.shx` automatically and assumes `EPSG:4326` if the CRS is missing, but it is still better to provide the full shapefile set if you can. The uploaded geometry coordinates look like longitude/latitude, so `EPSG:4326` is a reasonable fallback here.

## Inputs expected

### 1) AOI raster
Use your DEM for the overall AOI extent.

Example:

- `/mnt/data/PetersPond_dem_5m_2.tif`

### 2) Boolean raster
This should be a raster where the pixels you want to extract are coded as `1`.

Examples:

- `1 = include, 0 = exclude`
- `1 = treatment area, 0 = not treatment`

If your true values are not `1`, you can pass a different value with `--include-values`.

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
- `comparison_areas.png` – map of boolean-raster pixels, target-polygon pixels, and their overlap on the analysis grid
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

## Assumptions built into the code

- the DEM defines the overall download extent
- the polygon is the comparison area
- the boolean raster can be in a different CRS/resolution; it is reprojected to the NDVI grid with nearest-neighbour resampling
- the polygon is rasterised to the NDVI grid
- summaries are based on all valid NDVI pixels per date after cloud/shadow masking and scene-level NaN filtering

## Practical advice

- Keep the AOI reasonably small. Multi-year Sentinel-2 downloads can get large.
- Start with a shorter test period first, e.g. one year.
- If Dask reports worker memory errors, retry with smaller chunks and fewer workers, for example add `--chunk-x 512 --chunk-y 512 --num-workers 2 --threads-per-worker 1`.
- If downloads are slow or memory-heavy, reduce the date range before scaling up.
- If the polygon result looks shifted, check the CRS of the source vector and upload the missing `.prj` file.
