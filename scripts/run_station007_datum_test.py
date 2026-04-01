from __future__ import annotations

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

from core import clean_hourly_dataframe, compute_datums, fetch_fd_hourly, fetch_rq_hourly, fit_harmonics, load_harmonic_result, predict_from_harmonics, save_harmonic_result, select_epochs


OUTPUT_ROOT = Path("artifacts/station007_datum_test")


def _plot_datums(plot_path: Path, series: pd.DataFrame, datum, title: str) -> None:
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


def _run_record(station_id: str, station_kind: str, version: str | None = None) -> dict:
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

    plot_dir = OUTPUT_ROOT / "plots" / record_id
    plot_dir.mkdir(parents=True, exist_ok=True)
    summaries = []

    for ep in epochs:
        sub = df[(df["time"] >= ep.start) & (df["time"] <= ep.end)].copy()
        harmonic_path = OUTPUT_ROOT / "harmonics" / record_id / f"{ep.name}_harmonics.pkl"
        fitted_harmonics = fit_harmonics(sub, latitude=7.33)
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
                "latitude": 7.33,
            },
        )
        del fitted_harmonics
        gc.collect()
        harmonics = load_harmonic_result(harmonic_artifact["pickle"])
        epoch_prediction = predict_from_harmonics(harmonics, ep.start, ep.end, freq="1h")
        datum = compute_datums(sub, epoch_prediction=epoch_prediction)
        plot_path = plot_dir / f"{ep.name}_datums.png"
        _plot_datums(plot_path, sub, datum, f"{record_id} {ep.name}: tidal datums")
        summaries.append(
            {
                "epoch": asdict(ep),
                "datum": asdict(datum),
                "harmonic_artifact": harmonic_artifact,
                "plot": str(plot_path),
            }
        )
        del harmonics, sub, epoch_prediction
        gc.collect()

    return {
        "record_id": record_id,
        "station_name": station_name,
        "station_kind": station_kind,
        "epochs": summaries,
    }


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    summary = {
        "station_id": "007",
        "records": [
            _run_record("007", "FD"),
            _run_record("007", "RQ", version="A"),
            _run_record("007", "RQ", version="B"),
        ],
    }
    (OUTPUT_ROOT / "summary.json").write_text(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
