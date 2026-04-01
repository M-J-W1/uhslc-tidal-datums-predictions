from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import SWITCH_LEVELS_CSV, ensure_switch_levels_csv


def main() -> None:
    parser = argparse.ArgumentParser(description='Refresh cached UHSLC switch elevation CSV from live .din files.')
    parser.add_argument('--output', default=str(SWITCH_LEVELS_CSV), help='Output CSV path')
    parser.add_argument('--force', action='store_true', help='Force regeneration even if the CSV is less than 30 days old')
    args = parser.parse_args()

    path = ensure_switch_levels_csv(path=Path(args.output), force=args.force)
    print(path)


if __name__ == '__main__':
    main()
