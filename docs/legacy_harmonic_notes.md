# Legacy Harmonic Notes

This note summarizes the harmonic-analysis behavior described in the extracted
legacy Matlab instructions in [`instructions_extracted.txt`](/home/mwidlansky/UHSLC/DataProcessing/Tidal_Datums_Predictions/docs/instructions_extracted.txt).

## Legacy UTide configuration

The legacy Matlab workflow uses UTide with these settings:

- analysis mode: `epoch`
- statistics option: `nostats`
- annual constituents: enabled (`SAopt = 1`, meaning include `Sa` and `Ssa`)
- minimum signal-to-noise ratio: `2`
- nodal corrections: enabled (`NodsatNone = 0`)
- trend: included in the solve

The legacy reconstruction logic then explicitly zeroes the fitted trend before
generating tide predictions or harmonic extremes.

## Implications for the Python port

The Python port should therefore:

- fit harmonics over each epoch as one solve, not year-by-year
- keep nodal corrections enabled during the solve
- keep the linear trend in the fitted coefficients
- remove the trend only for prediction and astronomical-extreme reconstruction
- avoid UTide confidence-interval estimation when mirroring the legacy
  `nostats` workflow, because those calculations add substantial cost on long
  hourly epochs and are not part of the legacy configuration

## Important UTide time handling detail

The Python `utide` package accepts datetime arrays directly and internally
converts them to its Gregorian day basis. This is the safest path when porting
the Matlab code.

Do not pass Matplotlib date numbers directly into `utide.solve()` or
`utide.reconstruct()` unless you also provide the matching `epoch`. In this
project, that caused UTide to misread the sampling interval, emit divide-by-zero
 warnings from the periodogram step, and return an empty constituent list.

## Current project status

The code in [`core.py`](/home/mwidlansky/UHSLC/DataProcessing/Tidal_Datums_Predictions/core.py) now follows the legacy pattern above for:

- harmonic fitting
- trend-free reconstruction for predictions
- retaining the original fitted coefficient object without mutating it in place
