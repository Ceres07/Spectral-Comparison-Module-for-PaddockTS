from __future__ import annotations

import argparse
import os
from io import StringIO
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd
from geopandas import GeoSeries

from io_utils import ensure_dir, read_vector


SILO_URL = "https://www.longpaddock.qld.gov.au/cgi-bin/silo/DataDrillDataset.php"


def polygon_centroid_latlon(vector_path: str | Path) -> tuple[float, float]:
    gdf = read_vector(vector_path).to_crs("EPSG:4326")
    if gdf.empty:
        raise ValueError(f"No geometry found in {vector_path}")

    # Project before centroid calculation to avoid lon/lat centroid warnings.
    projected = gdf.to_crs("EPSG:6933")
    union = projected.geometry.union_all() if hasattr(projected.geometry, "union_all") else projected.geometry.unary_union
    centroid = union.centroid
    centroid_ll = GeoSeries([centroid], crs="EPSG:6933").to_crs("EPSG:4326").iloc[0]
    return float(centroid_ll.y), float(centroid_ll.x)


def download_silo_rainfall(
    target_polygon: str | Path,
    start: str,
    end: str,
    out_csv: str | Path,
    email: str | None = None,
) -> Path:
    """Download SILO daily rainfall for the centroid of the selected polygon."""
    email = email or os.environ.get("SILO_EMAIL")
    if not email:
        raise ValueError("SILO rainfall download requires --silo-email or the SILO_EMAIL environment variable.")

    out_csv = Path(out_csv)
    ensure_dir(out_csv.parent)
    if out_csv.exists():
        return out_csv

    lat, lon = polygon_centroid_latlon(target_polygon)
    params = {
        "lat": lat,
        "lon": lon,
        "start": pd.to_datetime(start).strftime("%Y%m%d"),
        "finish": pd.to_datetime(end).strftime("%Y%m%d"),
        "format": "csv",
        "comment": "R",
        "username": email,
        "password": "apirequest",
    }
    with urlopen(f"{SILO_URL}?{urlencode(params)}") as response:
        text = response.read().decode("utf-8")

    df = pd.read_csv(StringIO(text))
    source_cols = [column for column in df.columns if column.endswith("_source")]
    df = df.drop(columns=source_cols + ["metadata", "latitude", "longitude"], errors="ignore")
    df = df.rename(columns={"YYYY-MM-DD": "date"})
    df["date"] = pd.to_datetime(df["date"])
    if "daily_rain" not in df.columns:
        raise ValueError("SILO response did not include a daily_rain column.")
    df[["date", "daily_rain"]].to_csv(out_csv, index=False)
    return out_csv


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download SILO daily rainfall for a target polygon centroid.")
    parser.add_argument("--target-polygon", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--out-csv", required=True)
    parser.add_argument("--silo-email")
    args = parser.parse_args()

    out = download_silo_rainfall(
        target_polygon=args.target_polygon,
        start=args.start,
        end=args.end,
        out_csv=args.out_csv,
        email=args.silo_email,
    )
    print(f"Saved rainfall to: {out}")
