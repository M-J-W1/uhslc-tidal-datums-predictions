from __future__ import annotations

import argparse
import gc
from pathlib import Path
import json
import pandas as pd
import numpy as np

from core import (
    cap_prediction_end, clean_hourly_dataframe, select_epochs, compute_datums,
    fit_harmonics, load_harmonic_result, predict_from_harmonics,
    predict_fd_high_low,
    build_datums_only_dataset, build_netcdf_dataset, save_harmonic_result,
    save_netcdf, strip_harmonic_result, fetch_fd_hourly, fetch_rq_hourly,
    get_station_metadata,
    get_rq_metadata_span
)


def process_df(df, station_id, station_name, station_kind, latitude, output_dir, end_hourly_fd='2035-12-31 23:00:00', include_fd_minute_highlow=True, datums_only=False):
    outdir = Path(output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    df = clean_hourly_dataframe(df)
    epochs = select_epochs(df)
    if not epochs:
        raise RuntimeError(f'No qualifying epochs found for {station_id}')

    datum_by_epoch = {}
    harmonics_by_epoch = {}
    hourly_predictions = {}
    harmonic_artifacts = {}
    minute_highlow_by_epoch = {}
    harmonics_dir = outdir / 'harmonics'

    for ep in epochs:
        sub = df[(df['time'] >= ep.start) & (df['time'] <= ep.end)].copy()
        fitted_harmonics = fit_harmonics(sub, latitude=latitude)
        harmonic_path = harmonics_dir / f'{station_id}_{ep.name}_harmonics.pkl'
        harmonic_artifacts[ep.name] = save_harmonic_result(
            fitted_harmonics,
            str(harmonic_path),
            metadata={
                'station_id': station_id,
                'station_name': station_name,
                'station_kind': station_kind,
                'epoch_name': ep.name,
                'epoch_start': str(ep.start),
                'epoch_end': str(ep.end),
                'latitude': float(latitude),
            },
        )
        harmonics_summary = strip_harmonic_result(fitted_harmonics)
        del fitted_harmonics
        gc.collect()

        harmonics = load_harmonic_result(harmonic_artifacts[ep.name]['pickle'])
        epoch_prediction = predict_from_harmonics(harmonics, ep.start, ep.end, freq='1h')
        datum_by_epoch[ep.name] = compute_datums(sub, epoch_prediction=epoch_prediction)
        if datums_only:
            del harmonics, sub, epoch_prediction
            gc.collect()
            continue
        harmonics_by_epoch[ep.name] = harmonics_summary
        pred_end = cap_prediction_end(pd.Timestamp(end_hourly_fd) if station_kind == 'FD' else ep.end)
        if pred_end == ep.end:
            hourly_predictions[ep.name] = epoch_prediction
        else:
            hourly_predictions[ep.name] = predict_from_harmonics(harmonics, ep.start, pred_end, freq='1h')
        if station_kind == 'FD' and include_fd_minute_highlow:
            minute_highlow_by_epoch[ep.name] = predict_fd_high_low(harmonics)
        del harmonics, sub, epoch_prediction
        gc.collect()

    if datums_only:
        ds = build_datums_only_dataset(station_id, station_name, station_kind, epochs, datum_by_epoch)
    else:
        ds = build_netcdf_dataset(station_id, station_name, station_kind, epochs, datum_by_epoch, harmonics_by_epoch, hourly_predictions)
    for ep_name, hl in minute_highlow_by_epoch.items():
        if not hl.empty:
            ds[f'fd_highlow_time_{ep_name}'] = ([f'fd_hl_{ep_name}'], hl['time'].to_numpy(dtype='datetime64[ns]'))
            ds[f'fd_highlow_height_mm_{ep_name}'] = ([f'fd_hl_{ep_name}'], np.rint(hl['height_mm'].to_numpy(dtype=float)).astype(np.int32))
            ds[f'fd_highlow_type_{ep_name}'] = ([f'fd_hl_{ep_name}'], hl['type'].astype(str).to_numpy())

    outpath = outdir / f'{station_id}.nc'
    save_netcdf(ds, str(outpath))
    return {
        'output_netcdf': str(outpath),
        'harmonic_artifacts': harmonic_artifacts,
        'epochs': [e.name for e in epochs],
        'station_name': station_name,
        'station_kind': station_kind,
    }


def main():
    parser = argparse.ArgumentParser(description='Batch tidal datums and predictions processor')
    parser.add_argument('--mode', choices=['csv','fd','rq'], default='csv')
    parser.add_argument('--input-csv')
    parser.add_argument('--station-id', required=True)
    parser.add_argument('--station-name', default=None)
    parser.add_argument('--station-kind', choices=['FD','RQ'], default='FD')
    parser.add_argument('--version', help='RQ version letter, e.g. A')
    parser.add_argument('--latitude', type=float)
    parser.add_argument('--start')
    parser.add_argument('--end')
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--datums-only', action='store_true')
    args = parser.parse_args()

    if args.mode == 'csv':
        if not args.input_csv:
            raise SystemExit('--input-csv is required for csv mode')
        df = pd.read_csv(args.input_csv)
        try:
            meta = get_station_metadata(args.station_id)
        except KeyError:
            meta = None
        station_name = args.station_name or (meta.name if meta is not None else 'Unknown Station')
        latitude = args.latitude if args.latitude is not None else (meta.latitude if meta is not None else None)
        if latitude is None:
            raise SystemExit('--latitude is required when station metadata is unavailable')
        result = process_df(df, args.station_id, station_name, args.station_kind, latitude, args.output_dir, datums_only=args.datums_only)
    elif args.mode == 'fd':
        start = args.start or '1800-01-01'
        end = args.end or '2035-12-31'
        df = fetch_fd_hourly(args.station_id, start, end)
        meta = get_station_metadata(args.station_id)
        station_name = str(df['station_name'].dropna().iloc[0]) if len(df.dropna(subset=['station_name'])) else (args.station_name or meta.name)
        latitude = args.latitude if args.latitude is not None else meta.latitude
        result = process_df(df[['time','sea_level']], args.station_id, station_name, 'FD', latitude, args.output_dir, datums_only=args.datums_only)
    else:
        if not args.version:
            raise SystemExit('--version is required for rq mode')
        start = args.start
        end = args.end
        if start and end:
            df = fetch_rq_hourly(args.station_id, args.version, start, end)
        else:
            df = fetch_rq_hourly(args.station_id, args.version)
        meta = get_station_metadata(args.station_id)
        station_name = str(df['station_name'].dropna().iloc[0]) if len(df.dropna(subset=['station_name'])) else (args.station_name or meta.name)
        latitude = args.latitude if args.latitude is not None else meta.latitude
        station_record = f"{args.station_id}{args.version.lower()}"
        result = process_df(df[['time','sea_level']], station_record, station_name, 'RQ', latitude, args.output_dir, datums_only=args.datums_only)

    print(json.dumps(result))


if __name__ == '__main__':
    main()
