# UHSLC Tidal Datums and Predictions Handoff Package

## Purpose
This package contains the current prototype implementation developed from the uploaded instructions for:
- tidal datum calculation,
- harmonic fitting,
- tide prediction generation,
- NetCDF output,
- and batch-style processing for UHSLC FD/RQ station records.

It is prepared for handoff into another repository or another computer.

## Included Files

### Core scripts
- `core.py` — main processing logic
- `tidal_batch.py` — command-line driver
- `tests/test_core_unittest.py` — unit tests using `unittest`

### Local support / driver data
- `data/fd_metadata.geojson` — copied from the local IDEA environment because it may not be conveniently available in the target repo/environment

### Documentation
- `docs/HumanPreparedInstructions_TidalDatumsPredictions.md` — Markdown transcription of the human-authored instruction document
- `docs/instructions_extracted.txt` — raw extracted text from the original instruction document
- `docs/instructions_summary.txt` — line-numbered instruction dump
- `docs/rq_full_span_probe_001.json` — evidence from RQ ERDDAP probing for station 001
- `docs/rq_full_span_probe_002.json` — evidence from RQ ERDDAP probing for station 002
- `docs/fd_run_summary.json` — summary from FD real-data prototype runs

## Environment Assumptions
This prototype was developed in Python 3.11 and used:
- `numpy`
- `pandas`
- `xarray`
- `netCDF4`
- `scipy`
- `matplotlib`
- `utide`
- `requests`
- `PyYAML`
- `beautifulsoup4`

Suggested install example:

```bash
pip install numpy pandas xarray netCDF4 scipy matplotlib utide requests pyyaml beautifulsoup4
```

## Current Functional Status

### Working
- Unit tests pass for the synthetic/prototype workflow.
- Real FD ERDDAP loading works.
- Full available FD ERDDAP span for station `001` was confirmed.
- Real FD prototype outputs were successfully generated earlier for stations `001`, `002`, `003`, and `007` using shorter operational windows.
- Full RQ ERDDAP spans were confirmed for station `002` versions `A`, `B`, `C`, `D`.
- Live loader integration tests now pass for station `007` FD and RQ versions `A` and `B`.
- FD outputs now save chunked minute-derived daily high/low prediction events through `2035-12-31 23:00`.

### Known limitations
- Full-record end-to-end processing for FD `001` was killed by the OS (`return code -9`), likely due to resource pressure in the current implementation.
- RQ availability through ERDDAP appears inconsistent for station `001`; ERDDAP exposed `001C` but not `001A` or `001B`, even though the YAML metadata index lists those versions.
- The harmonic implementation now matches the core legacy UTide setup more closely, but it is still not a full legacy-equivalent production workflow.
- The current code should still be monitored for memory pressure during long UTide solves, even though prediction generation now uses persisted harmonic artifacts and chunked FD minute extraction.

## Recommended Next Refactors
1. **Process full records lazily/in chunks** instead of building very large in-memory arrays.
2. **Continue reducing solve-time memory pressure** during epoch harmonic fitting, which remains the main peak-memory step.
3. **Refine RQ mapping** to reconcile ERDDAP exposure vs YAML metadata records.
4. **Expand harmonic constituents** and align more closely with legacy software behavior.
5. **Add integration tests** for real ERDDAP station runs.

## Basic Usage

### Run unit tests
```bash
python3 -m unittest discover -s tests -v
```

### Run live station 007 loader integration test
```bash
RUN_LIVE_UHSLC=1 MPLCONFIGDIR=/tmp/mplconfig python3 -m unittest tests.test_live_station007 -v
```

### FD example
```bash
python tidal_batch.py   --mode fd   --station-id 001   --station-name Pohnpei   --station-kind FD   --latitude 6.9833   --output-dir outputs
```

### RQ example
```bash
python tidal_batch.py   --mode rq   --station-id 002   --station-name "Tarawa, Bairiki"   --station-kind RQ   --version A   --latitude 1.33   --output-dir outputs
```

## Important Notes for the Handoff Repo
- `fd_metadata.geojson` is included locally in `data/` because it is a key support file.
- The current code relies on direct ERDDAP access to:
  - `global_hourly_fast`
  - `global_hourly_rqds`
- If the receiving environment has stricter memory limits, full-record runs may need chunking immediately.
- The legacy Matlab instructions use UTide with epoch-wide solves, nodal corrections enabled, annual constituents enabled, and trend removed only at prediction time. The Python implementation now follows that same pattern.
- To reduce long-epoch memory and CPU pressure, the harmonic solve now follows the legacy Matlab `opt = 'nostats'` approach rather than computing UTide confidence intervals.
- FD hourly predictions are capped at `2035-12-31 23:00`, and FD minute predictions are reduced to saved daily high/low event times and heights over `2025-01-01 00:00` through `2030-12-31 23:59`.
- For Python `utide`, pass datetime arrays directly into `solve()` and `reconstruct()`. Passing Matplotlib day numbers without an explicit epoch can yield empty constituent sets and invalid sampling diagnostics.

## Source Context
This package was assembled from work performed in an IDEA/SEA environment and is intended as a **prototype handoff**, not a final production release.
