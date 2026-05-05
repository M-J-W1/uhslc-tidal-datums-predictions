# UHSLC Tidal Datums and Predictions

## Purpose

Update datums and tide predictions for all Fast Delivery and Research Quality
hourly data served via ERDDAP.

## Protocol

Learn best practices from the legacy software, and make improvements where
necessary. The deliverable is a Python script that may be run in batch mode to
cover groups of stations: all, FD, RQ, subsets, or individual stations.

## Output Files

- NetCDF
- One file per station record

Current project note:

- NetCDF outputs may also include Skill discovery attributes that identify the
  Skill name, description, and local/remote location. The Skill itself lives in
  `artifacts/skills/uhslc-tidal-datums-predictions/SKILL.md`.

Examples:

- `001`
- `001a`
- `001b`
- `001c`

These would cover Pohnpei for FD and its three RQ versions.

## Reference Frames and Units

- Station zero
- GMT
- mm integer

## Epochs and Data Completion

The primary epochs are:

- `NTDE_1983-2001`
- `NTDE_2002-2020`
- `IPCC-AR6_1995-2014`

Attempt to calculate datums and tidal harmonics/predictions for each of the
primary 19-year epochs. This will be impossible for many station records
because of incomplete coverage.

Rules:

- Use a 75% hourly-data completion criterion.
- If a particular epoch is below 75% coverage, skip it.
- If at least one primary epoch qualifies by total completion, but none of the
  qualifying primary epochs has at least 75% hourly-data completion in every
  calendar year within the epoch, add one prediction-specific 19-calendar-year
  epoch named `PRED_YYYY_YYYY` when such a window has at least 75% completion
  in every year. This preserves the standard epoch for datum comparability
  while allowing a better-conditioned harmonic fit for predictions.
- For all records with at least 6 months of hourly data and more than 75%
  completion, define at least one epoch.
- That fallback epoch should be the most recent data span, not to exceed 19
  years.
- Most station records should have no more than three epochs. Rare edge cases
  may have a fourth `PRED_YYYY_YYYY` epoch.

Example:

- `001a` should have one epoch spanning `1969-05-09` to `1971-02-27`.

## Datums

You do not have access to the switch elevations, so it is acceptable to omit
them. Otherwise, use the legacy software to determine which datums should be
calculated and saved.

Current project note:

- The implementation now includes switch elevations where available, using
  `LEV` and `LEVB` names consistently.
- These are currently extracted from the interim live `.din` directory and
  cached into `data/switch_levels.csv`.
- That source should later be replaced with a more permanent switch-metadata
  location.

## Tidal Harmonics

Harmonics should be calculated for each epoch. Include the tidal harmonics in
the output file. Follow best practices learned from the legacy software,
especially for treatment of the nodal cycle and trends.

## Tide Predictions

Tide predictions should be calculated for each set of harmonics.

For FD stations:

- Output hourly predictions spanning the epoch start through
  `2035-12-31 23:00`.
- Also calculate minute predictions from `2025-01-01 00:00` through
  `2030-12-31 23:59`.
- To reduce file size, save only the times and heights of the daily high/low
  tides derived from the minute predictions.
- Review the legacy procedure for the high/low extraction behavior.

For RQ stations:

- Only calculate and save hourly tide predictions spanning the available epoch.

Example:

- The prediction for `001a` should cover the hours from `1969-05-09` to
  `1971-02-27`.

## Test Stations

Run tests and generate plots for the following stations, including FD and all
RQ versions:

- `001`
- `002`
- `003`
- `007`

Plot types:

- datums
- hourly predictions/residuals
- minute predictions where applicable

## Legacy Context

The original instruction package also included legacy Matlab examples and notes
used to guide the Python implementation. Those remain available in:

- [`instructions_extracted.txt`](instructions_extracted.txt)
- [`instructions_summary.txt`](instructions_summary.txt)
- [`legacy_harmonic_notes.md`](legacy_harmonic_notes.md)
