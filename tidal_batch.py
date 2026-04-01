from __future__ import annotations

import argparse
from pathlib import Path
import json
import pandas as pd
import numpy as np

from core import (
    clean_hourly_dataframe, select_epochs, compute_datums, fit_harmonics,
    predict_from_harmonics, extract_daily_high_low, build_netcdf_dataset,
    save_netcdf, fetch_fd_hourly, fetch_rq_hourly, get_rq_metadata_span
)


def process_df(df, station_id, station_name, station_kind, latitude, output_dir, end_hourly_fd='2100-12-31 23:00:00'):
    outdir = Path(output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    df = clean_hourly_dataframe(df)
    epochs = select_epochs(df)
    if not epochs:
        raise RuntimeError(f'No qualifying epochs found for {station_id}')

    datum_by_epoch = {}
    harmonics_by_epoch = {}
    hourly_predictions = {}
    minute_highlow_by_epoch = {}

    for ep in epochs:
        sub = df[(df['time'] >= ep.start) & (df['time'] <= ep.end)].copy()
        datum_by_epoch[ep.name] = compute_datums(sub)
        harmonics_by_epoch[ep.name] = fit_harmonics(sub, latitude=latitude)
        pred_end = pd.Timestamp(end_hourly_fd) if station_kind == 'FD' else ep.end
        hourly_predictions[ep.name] = predict_from_harmonics(harmonics_by_epoch[ep.name], ep.start, pred_end, freq='1h')
        if station_kind == 'FD':
            minute_end = pd.Timestamp('2030-12-31 23:00:00')
            if ep.end <= minute_end:
                minute_df = predict_from_harmonics(harmonics_by_epoch[ep.name], ep.end, minute_end, freq='1min')
                minute_highlow_by_epoch[ep.name] = extract_daily_high_low(minute_df)

    ds = build_netcdf_dataset(station_id, station_name, station_kind, epochs, datum_by_epoch, harmonics_by_epoch, hourly_predictions)
    for ep_name, hl in minute_highlow_by_epoch.items():
        if not hl.empty:
            ds[f'fd_highlow_time_{ep_name}'] = ([f'fd_hl_{ep_name}'], hl['time'].to_numpy(dtype='datetime64[ns]'))
            ds[f'fd_highlow_height_mm_{ep_name}'] = ([f'fd_hl_{ep_name}'], np.rint(hl['height_mm'].to_numpy(dtype=float)).astype(np.int32))
            ds[f'fd_highlow_type_{ep_name}'] = ([f'fd_hl_{ep_name}'], hl['type'].astype(str).to_numpy())

    outpath = outdir / f'{station_id}.nc'
    save_netcdf(ds, str(outpath))
    return {'output_netcdf': str(outpath), 'epochs': [e.name for e in epochs], 'station_name': station_name, 'station_kind': station_kind}


def main():
    parser = argparse.ArgumentParser(description='Batch tidal datums and predictions processor')
    parser.add_argument('--mode', choices=['csv','fd','rq'], default='csv')
    parser.add_argument('--input-csv')
    parser.add_argument('--station-id', required=True)
    parser.add_argument('--station-name', default='Unknown Station')
    parser.add_argument('--station-kind', choices=['FD','RQ'], default='FD')
    parser.add_argument('--version', help='RQ version letter, e.g. A')
    parser.add_argument('--latitude', type=float, required=True)
    parser.add_argument('--start')
    parser.add_argument('--end')
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()

    if args.mode == 'csv':
        if not args.input_csv:
            raise SystemExit('--input-csv is required for csv mode')
        df = pd.read_csv(args.input_csv)
        result = process_df(df, args.station_id, args.station_name, args.station_kind, args.latitude, args.output_dir)
    elif args.mode == 'fd':
        start = args.start or '1800-01-01'
        end = args.end or '2100-12-31'
        df = fetch_fd_hourly(args.station_id, start, end)
        station_name = str(df['station_name'].dropna().iloc[0]) if len(df.dropna(subset=['station_name'])) else args.station_name
        result = process_df(df[['time','sea_level']], args.station_id, station_name, 'FD', args.latitude, args.output_dir)
    else:
        if not args.version:
            raise SystemExit('--version is required for rq mode')
        start = args.start
        end = args.end
        if start and end:
            df = fetch_rq_hourly(args.station_id, args.version, start, end)
        else:
            df = fetch_rq_hourly(args.station_id, args.version)
        station_name = str(df['station_name'].dropna().iloc[0]) if len(df.dropna(subset=['station_name'])) else args.station_name
        station_record = f"{args.station_id}{args.version.lower()}"
        result = process_df(df[['time','sea_level']], station_record, station_name, 'RQ', args.latitude, args.output_dir)

    print(json.dumps(result))


if __name__ == '__main__':
    main()
