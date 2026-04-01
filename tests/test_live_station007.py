import os
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import fetch_fd_hourly, fetch_rq_hourly, get_rq_metadata_span, list_rq_versions


RUN_LIVE = os.environ.get("RUN_LIVE_UHSLC") == "1"


@unittest.skipUnless(RUN_LIVE, "Set RUN_LIVE_UHSLC=1 to run live UHSLC integration tests.")
class TestLiveStation007(unittest.TestCase):
    station_id = "007"

    def test_station_007_fd_loads(self):
        df = fetch_fd_hourly(self.station_id)

        self.assertFalse(df.empty)
        self.assertEqual(
            list(df.columns),
            ["time", "sea_level", "uhslc_id", "record_id", "station_name", "station_country"],
        )
        self.assertEqual(int(df["time"].duplicated().sum()), 0)
        self.assertTrue((df["time"].dt.minute == 0).all())
        self.assertTrue((df["time"].dt.second == 0).all())
        self.assertEqual(sorted(df["station_name"].dropna().unique().tolist()), ["Malakal"])
        self.assertEqual(sorted(df["record_id"].dropna().unique().tolist()), [70])
        self.assertGreater(int(df["sea_level"].notna().sum()), 0)
        self.assertGreaterEqual(df["time"].min(), pd.Timestamp("1969-05-18 15:00:00"))

    def test_station_007_rq_versions_discover_and_load(self):
        versions = list_rq_versions([self.station_id])[self.station_id]
        self.assertEqual(versions, ["A", "B"])

        for version in versions:
            with self.subTest(version=version):
                meta_start, meta_end = get_rq_metadata_span(self.station_id, version)
                df = fetch_rq_hourly(self.station_id, version)

                self.assertFalse(df.empty)
                self.assertEqual(
                    list(df.columns),
                    ["time", "sea_level", "uhslc_id", "record_id", "station_name", "station_country", "version"],
                )
                self.assertEqual(int(df["time"].duplicated().sum()), 0)
                self.assertTrue((df["time"].dt.minute == 0).all())
                self.assertTrue((df["time"].dt.second == 0).all())
                self.assertEqual(sorted(df["version"].dropna().unique().tolist()), [version])
                self.assertEqual(sorted(df["station_name"].dropna().unique().tolist()), ["Malakal"])
                self.assertGreater(int(df["sea_level"].notna().sum()), 0)
                self.assertGreaterEqual(df["time"].max(), meta_start)
                self.assertGreaterEqual(meta_end, meta_start)


if __name__ == "__main__":
    unittest.main()
