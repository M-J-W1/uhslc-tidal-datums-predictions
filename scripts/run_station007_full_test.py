from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
import sys
import gc

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import (
    cap_prediction_end,
    build_netcdf_dataset,
    clean_hourly_dataframe,
    compute_datums,
    fetch_fd_hourly,
    fetch_rq_hourly,
    fit_harmonics,
    load_harmonic_result,
    predict_fd_high_low,
    predict_from_harmonics,
    save_harmonic_result,
    save_netcdf,
    select_epochs,
    strip_harmonic_result,
    get_station_metadata,
    get_station_switch_levels,
)


OUTPUT_ROOT = Path("artifacts/station007_full_test")


def _plot_hourly_comparison(plot_path: Path, merged: pd.DataFrame, title: str) -> dict:
    plot_df = merged.head(24 * 31).copy()
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(plot_df["time"], plot_df["sea_level"], label="Observed", linewidth=1.0)
    ax.plot(plot_df["time"], plot_df["prediction_mm"], label="Predicted", linewidth=1.0)
    ax.set_title(title)
    ax.set_ylabel("Sea Level (mm, station zero)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(plot_path, dpi=150)
    plt.close(fig)
    residual = plot_df["sea_level"] - plot_df["prediction_mm"]
    return {
        "comparison_plot": str(plot_path),
        "comparison_rows": int(len(plot_df)),
        "rmse_mm": float(np.sqrt(np.mean(np.square(residual)))),
    }


def _plot_datums(plot_path: Path, series: pd.DataFrame, datum, switch_levels, title: str) -> str:
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
    return str(plot_path)


def _plot_residuals(plot_path: Path, merged: pd.DataFrame, title: str) -> str:
    plot_df = merged.head(24 * 31).copy()
    residual = plot_df["sea_level"] - plot_df["prediction_mm"]
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(plot_df["time"], residual, color="black", linewidth=0.9)
    ax.axhline(0.0, color="tab:red", linestyle="--", linewidth=1.0)
    ax.set_title(title)
    ax.set_ylabel("Observed - Predicted (mm)")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(plot_path, dpi=150)
    plt.close(fig)
    return str(plot_path)


def _plot_fd_high_low(plot_path: Path, high_low: pd.DataFrame, title: str) -> str | None:
    if high_low.empty:
        return None
    plot_df = high_low.head(120).copy()
    colors = plot_df["type"].map({"H": "tab:blue", "L": "tab:orange"}).to_numpy()
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.scatter(plot_df["time"], plot_df["height_mm"], c=colors, s=18)
    ax.plot(plot_df["time"], plot_df["height_mm"], color="0.5", linewidth=0.8, alpha=0.7)
    ax.set_title(title)
    ax.set_ylabel("Predicted Tide (mm relative to station zero)")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(plot_path, dpi=150)
    plt.close(fig)
    return str(plot_path)


def _run_record(
    station_id: str,
    station_kind: str,
    outdir: Path,
    version: str | None = None,
) -> dict:
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

    datum_by_epoch = {}
    harmonics_by_epoch = {}
    hourly_predictions = {}
    harmonic_artifacts = {}
    minute_highlow_by_epoch = {}
    epoch_summaries = []
    plot_dir = outdir / "plots" / record_id
    plot_dir.mkdir(parents=True, exist_ok=True)

    for ep in epochs:
        sub = df[(df["time"] >= ep.start) & (df["time"] <= ep.end)].copy()
        fitted_harmonics = fit_harmonics(sub, latitude=latitude)
        harmonic_path = outdir / "harmonics" / record_id / f"{ep.name}_harmonics.pkl"
        harmonic_artifacts[ep.name] = save_harmonic_result(
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
        harmonics_summary = strip_harmonic_result(fitted_harmonics)
        del fitted_harmonics
        gc.collect()

        harmonics = load_harmonic_result(harmonic_artifacts[ep.name]["pickle"])
        epoch_hourly_pred = predict_from_harmonics(harmonics, ep.start, ep.end, freq="1h")
        datum = compute_datums(sub, epoch_prediction=epoch_hourly_pred)
        pred_end = cap_prediction_end(pd.Timestamp("2035-12-31 23:00:00") if station_kind == "FD" else ep.end)
        if pred_end == ep.end:
            hourly_pred = epoch_hourly_pred
        else:
            hourly_pred = predict_from_harmonics(harmonics, ep.start, pred_end, freq="1h")

        datum_by_epoch[ep.name] = datum
        harmonics_by_epoch[ep.name] = harmonics_summary
        hourly_predictions[ep.name] = hourly_pred
        if station_kind == "FD":
            minute_highlow = predict_fd_high_low(harmonics)
            minute_highlow_by_epoch[ep.name] = minute_highlow
        else:
            minute_highlow = pd.DataFrame(columns=["time", "height_mm", "type"])

        observed = sub.dropna(subset=["sea_level"])[["time", "sea_level"]].copy()
        datum_plot = _plot_datums(
            plot_dir / f"{ep.name}_datums.png",
            sub,
            datum,
            switch_levels,
            f"{record_id} {ep.name}: tidal datums",
        )
        within_epoch_pred = epoch_hourly_pred.copy()
        merged = observed.merge(within_epoch_pred, on="time", how="inner")
        compare_meta = _plot_hourly_comparison(
            plot_dir / f"{ep.name}_hourly_observed_vs_predicted.png",
            merged,
            f"{record_id} {ep.name}: observed vs predicted",
        )
        residual_plot = _plot_residuals(
            plot_dir / f"{ep.name}_hourly_residuals.png",
            merged,
            f"{record_id} {ep.name}: hourly residuals",
        )

        minute_plot = None
        minute_rows = int(len(minute_highlow))
        if station_kind == "FD" and not minute_highlow.empty:
            minute_plot = _plot_fd_high_low(
                plot_dir / f"{ep.name}_fd_high_low.png",
                minute_highlow,
                f"{record_id} {ep.name}: FD high/low minute prediction",
            )

        epoch_summaries.append(
            {
                "epoch": asdict(ep),
                "datum": asdict(datum),
                "harmonic_constituent_count": int(len(harmonics.constituent)),
                "top_constituents": harmonics.constituent[:12],
                "harmonic_artifact": harmonic_artifacts[ep.name],
                "hourly_prediction_rows": int(len(hourly_pred)),
                "hourly_observed_rows": int(len(observed)),
                "hourly_overlap_rows": int(len(merged)),
                "plots": {
                    "datums": datum_plot,
                    "hourly_observed_vs_predicted": compare_meta["comparison_plot"],
                    "hourly_residuals": residual_plot,
                    "fd_high_low": minute_plot,
                },
                "comparison_window_rows": compare_meta["comparison_rows"],
                "comparison_window_rmse_mm": compare_meta["rmse_mm"],
                "fd_high_low_rows": minute_rows,
                "switch_levels": None if switch_levels is None else asdict(switch_levels),
            }
        )
        del harmonics, sub, epoch_hourly_pred, minute_highlow
        gc.collect()

    ds = build_netcdf_dataset(
        record_id,
        station_name,
        station_kind,
        epochs,
        datum_by_epoch,
        harmonics_by_epoch,
        hourly_predictions,
        switch_levels=switch_levels,
    )
    for ep_name, hl in minute_highlow_by_epoch.items():
        if not hl.empty:
            ds[f"fd_highlow_time_{ep_name}"] = ([f"fd_hl_{ep_name}"], hl["time"].to_numpy(dtype="datetime64[ns]"))
            ds[f"fd_highlow_height_mm_{ep_name}"] = ([f"fd_hl_{ep_name}"], np.rint(hl["height_mm"].to_numpy(dtype=float)).astype(np.int32))
            ds[f"fd_highlow_type_{ep_name}"] = ([f"fd_hl_{ep_name}"], hl["type"].astype(str).to_numpy())

    nc_path = outdir / "netcdf" / f"{record_id}.nc"
    nc_path.parent.mkdir(parents=True, exist_ok=True)
    save_netcdf(ds, str(nc_path))

    return {
        "record_id": record_id,
        "station_name": station_name,
        "station_kind": station_kind,
        "netcdf": str(nc_path),
        "harmonic_artifacts": harmonic_artifacts,
        "epochs": epoch_summaries,
    }


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    summary = {
        "station_id": "007",
        "records": [],
    }

    summary["records"].append(_run_record("007", "FD", OUTPUT_ROOT))
    summary["records"].append(_run_record("007", "RQ", OUTPUT_ROOT, version="A"))
    summary["records"].append(_run_record("007", "RQ", OUTPUT_ROOT, version="B"))

    summary_path = OUTPUT_ROOT / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str))

    md_lines = [
        "# Station 007 Full Test",
        "",
        f"Output root: `{OUTPUT_ROOT}`",
        "",
    ]
    for record in summary["records"]:
        md_lines.append(f"## {record['record_id']}")
        md_lines.append(f"- Station name: {record['station_name']}")
        md_lines.append(f"- Station kind: {record['station_kind']}")
        md_lines.append(f"- NetCDF: `{record['netcdf']}`")
        for epoch in record["epochs"]:
            md_lines.append(
                f"- {epoch['epoch']['name']}: constituents={epoch['harmonic_constituent_count']}, "
                f"hourly_overlap_rows={epoch['hourly_overlap_rows']}, "
                f"rmse_mm={epoch['comparison_window_rmse_mm']:.2f}"
            )
        md_lines.append("")
    (OUTPUT_ROOT / "summary.md").write_text("\n".join(md_lines))


if __name__ == "__main__":
    main()
