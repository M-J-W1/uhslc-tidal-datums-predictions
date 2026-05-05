from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
import sys
import gc

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import build_datums_only_dataset, clean_hourly_dataframe, compute_datums, fetch_fd_hourly, fetch_rq_hourly, fit_harmonics, get_station_metadata, get_station_switch_levels, list_rq_versions, load_harmonic_result, predict_from_harmonics, save_harmonic_result, save_netcdf, select_epochs


DEFAULT_STATION_ID = "007"


def _plot_datums(plot_path: Path, series: pd.DataFrame, datum, switch_levels, title: str) -> None:
    plot_df = series.dropna(subset=["sea_level"]).head(24 * 31).copy()
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(plot_df["time"], plot_df["sea_level"], color="0.25", linewidth=0.9, label="Observed hourly sea level")
    datum_lines = {
        "MHHW": datum.MHHW,
        "MHW": datum.MHW,
        "MSL": datum.MSL,
        "MLW": datum.MLW,
        "MLLW": datum.MLLW,
    }
    colors = {
        "MHHW": "tab:blue",
        "MHW": "tab:cyan",
        "MSL": "tab:green",
        "MLW": "tab:orange",
        "MLLW": "tab:red",
    }
    if switch_levels is not None:
        if switch_levels.LEV is not None:
            datum_lines["LEV"] = float(switch_levels.LEV)
            colors["LEV"] = "tab:purple"
        if switch_levels.LEVB is not None:
            datum_lines["LEVB"] = float(switch_levels.LEVB)
            colors["LEVB"] = "tab:brown"
    for name, value in datum_lines.items():
        ax.axhline(value, color=colors[name], linestyle="--", linewidth=1.1, label=f"{name} = {value:.1f} mm")
    ax.set_title(title)
    ax.set_ylabel("Sea Level (mm, station zero)")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(plot_path, dpi=150)
    plt.close(fig)


def _run_record(station_id: str, station_kind: str, output_root: Path, version: str | None = None) -> dict:
    station_meta = get_station_metadata(station_id)
    switch_levels = get_station_switch_levels(station_id)
    latitude = station_meta.latitude
    if station_kind == "FD":
        raw = fetch_fd_hourly(station_id)
        record_id = station_id
    else:
        assert version is not None
        raw = fetch_rq_hourly(station_id, version)
        record_id = f"{station_id}{version.lower()}"

    station_name = str(raw["station_name"].dropna().iloc[0])
    df = clean_hourly_dataframe(raw[["time", "sea_level"]])
    epochs = select_epochs(df)
    if not epochs:
        raise RuntimeError(f"No qualifying epochs found for {record_id}")

    plot_dir = output_root / "plots" / record_id
    plot_dir.mkdir(parents=True, exist_ok=True)
    netcdf_dir = output_root / "netcdf"
    netcdf_dir.mkdir(parents=True, exist_ok=True)
    datum_by_epoch = {}
    summaries = []

    for ep in epochs:
        sub = df[(df["time"] >= ep.start) & (df["time"] <= ep.end)].copy()
        harmonic_path = output_root / "harmonics" / record_id / f"{ep.name}_harmonics.pkl"
        fitted_harmonics = fit_harmonics(sub, latitude=latitude)
        harmonic_artifact = save_harmonic_result(
            fitted_harmonics,
            str(harmonic_path),
            metadata={
                "station_id": record_id,
                "station_name": station_name,
                "station_kind": station_kind,
                "epoch_name": ep.name,
                "epoch_start": str(ep.start),
                "epoch_end": str(ep.end),
                "latitude": float(latitude),
            },
        )
        del fitted_harmonics
        gc.collect()
        harmonics = load_harmonic_result(harmonic_artifact["pickle"])
        epoch_prediction = predict_from_harmonics(harmonics, ep.start, ep.end, freq="1h")
        datum = compute_datums(sub, epoch_prediction=epoch_prediction)
        datum_by_epoch[ep.name] = datum
        plot_path = plot_dir / f"{ep.name}_datums.png"
        _plot_datums(plot_path, sub, datum, switch_levels, f"{record_id} {ep.name}: tidal datums")
        summaries.append(
            {
                "epoch": asdict(ep),
                "datum": asdict(datum),
                "harmonic_artifact": harmonic_artifact,
                "plot": str(plot_path),
                "switch_levels": None if switch_levels is None else asdict(switch_levels),
            }
        )
        del harmonics, sub, epoch_prediction
        gc.collect()

    ds = build_datums_only_dataset(record_id, station_name, station_kind, epochs, datum_by_epoch, switch_levels=switch_levels)
    netcdf_path = netcdf_dir / f"{record_id}.nc"
    save_netcdf(ds, str(netcdf_path))
    ds.close()

    return {
        "record_id": record_id,
        "station_name": station_name,
        "station_kind": station_kind,
        "netcdf": str(netcdf_path),
        "epochs": summaries,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run datum-only diagnostics for one station.")
    parser.add_argument("--station-id", default=DEFAULT_STATION_ID)
    args = parser.parse_args()

    station_id = str(int(args.station_id)).zfill(3)
    output_root = Path("artifacts") / "datum_test" / f"station{station_id}"
    output_root.mkdir(parents=True, exist_ok=True)
    rq_versions = list_rq_versions([station_id])[station_id]
    summary = {
        "station_id": station_id,
        "records": [_run_record(station_id, "FD", output_root)],
    }
    for version in rq_versions:
        summary["records"].append(_run_record(station_id, "RQ", output_root, version=version))
    (output_root / "summary.json").write_text(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
