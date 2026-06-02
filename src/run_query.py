from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any

from run_workflow import main as run_workflow_main


OPTION_MAP = {
    "aoi_raster": "--aoi-raster",
    "boolean_raster": "--boolean-raster",
    "target_polygon": "--target-polygon",
    "comparison_mode": "--comparison-mode",
    "buffer_m": "--buffer-m",
    "start": "--start",
    "end": "--end",
    "outdir": "--outdir",
    "include_values": "--include-values",
    "out_crs": "--out-crs",
    "resolution": "--resolution",
    "max_cloud_cover": "--max-cloud-cover",
    "max_nan_fraction": "--max-nan-fraction",
    "chunk_x": "--chunk-x",
    "chunk_y": "--chunk-y",
    "num_workers": "--num-workers",
    "threads_per_worker": "--threads-per-worker",
    "fc_model_n": "--fc-model-n",
    "silo_email": "--silo-email",
    "plot_group": "--plot-group",
    "comparison_group": "--comparison-group",
    "plot_method": "--plot-method",
}
FLAG_MAP = {
    "save_pixel_values": "--save-pixel-values",
    "all_touched": "--all-touched",
    "skip_fractional_cover": "--skip-fractional-cover",
    "fc_correction": "--fc-correction",
}


def load_config(query_path: str | Path) -> dict[str, Any]:
    query_path = Path(query_path).expanduser().resolve()
    spec = importlib.util.spec_from_file_location("workflow_query", query_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Could not load query file: {query_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "CONFIG"):
        raise ValueError(f"Query file must define CONFIG: {query_path}")
    config = getattr(module, "CONFIG")
    if not isinstance(config, dict):
        raise ValueError("CONFIG must be a dictionary.")
    return config


def config_to_argv(config: dict[str, Any]) -> list[str]:
    argv = ["run_workflow.py"]
    for key, option in OPTION_MAP.items():
        value = config.get(key)
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            if not value:
                continue
            argv.append(option)
            argv.extend(str(item) for item in value)
        else:
            argv.extend([option, str(value)])

    for key, option in FLAG_MAP.items():
        if config.get(key):
            argv.append(option)
    return argv


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the workflow from an editable Python query file.")
    parser.add_argument("--query", default="workflow_query.py", help="Path to a Python file defining CONFIG")
    args = parser.parse_args()

    config = load_config(args.query)
    sys.argv = config_to_argv(config)
    run_workflow_main()


if __name__ == "__main__":
    main()
