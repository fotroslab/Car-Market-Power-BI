#!/usr/bin/env python3
"""
Automated Data Quality & Star-Schema Integrity Test Suite (15 tests).
Run with:
    cd project_02_iran_car_market && python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_CSV = PROJECT_ROOT / "data" / "raw" / "final2024.csv"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


class TestIranCarMarketDataQuality(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fact = pd.read_csv(PROCESSED_DIR / "fact_listing.csv", low_memory=False)
        cls.dim_brand = pd.read_csv(PROCESSED_DIR / "dim_brand.csv")
        cls.dim_city = pd.read_csv(PROCESSED_DIR / "dim_city.csv")
        cls.dim_date = pd.read_csv(PROCESSED_DIR / "dim_date.csv")
        with open(PROCESSED_DIR / "summary_stats.json", encoding="utf-8") as f:
            cls.summary = json.load(f)

    def test_01_clean_row_count(self) -> None:
        self.assertEqual(len(self.fact), 383_454)

    def test_02_unique_listing_id(self) -> None:
        ids = self.fact["listing_id"]
        self.assertFalse(ids.isna().any())
        self.assertTrue(ids.is_unique)
        self.assertTrue((ids > 0).all())

    def test_03_foreign_key_date(self) -> None:
        self.assertTrue(self.dim_date["date_key"].is_unique)
        missing = set(self.fact["date_key"].unique()) - set(self.dim_date["date_key"].unique())
        self.assertEqual(missing, set())

    def test_04_foreign_key_brand(self) -> None:
        self.assertTrue(self.dim_brand["brand_key"].is_unique)
        self.assertEqual(len(self.dim_brand), 41)
        missing = set(self.fact["brand_key"].unique()) - set(self.dim_brand["brand_key"].unique())
        self.assertEqual(missing, set())

    def test_05_foreign_key_city(self) -> None:
        self.assertTrue(self.dim_city["city_key"].is_unique)
        self.assertEqual(len(self.dim_city), 334)
        self.assertEqual(int(self.dim_city["is_persian_mapped"].sum()), 90)
        missing = set(self.fact["city_key"].unique()) - set(self.dim_city["city_key"].unique())
        self.assertEqual(missing, set())

    def test_06_price_positive_and_multiple_of_10(self) -> None:
        p = self.fact["price_irr"]
        self.assertFalse(p.isna().any())
        self.assertTrue((p > 0).all())
        self.assertTrue((p % 10 == 0).all())
        self.assertGreaterEqual(int(p.min()), 100_000_000)
        self.assertLessEqual(int(p.max()), 1_000_000_000_000)

    def test_07_model_year_bounds(self) -> None:
        y = self.fact["model_year_jalali"].dropna()
        self.assertGreater(len(y), 375_000)
        self.assertGreaterEqual(int(y.min()), 1300)
        self.assertLessEqual(int(y.max()), 1403)

    def test_08_car_age_bounds(self) -> None:
        age = self.fact["car_age"].dropna()
        self.assertGreater(len(age), 375_000)
        self.assertGreaterEqual(int(age.min()), 0)
        self.assertLessEqual(int(age.max()), 75)
        self.assertEqual(int(age.median()), 8)

    def test_09_mileage_bounds(self) -> None:
        m = self.fact["mileage_km"].dropna()
        self.assertGreater(len(m), 380_000)
        self.assertGreaterEqual(int(m.min()), 0)
        self.assertLessEqual(int(m.max()), 2_500_000)
        self.assertEqual(int(m.median()), 110_000)

    def test_10_gearbox_domain_and_coverage(self) -> None:
        allowed = {"دنده‌ای", "اتوماتیک", "نامشخص"}
        actual = set(self.fact["gearbox"].unique())
        self.assertTrue(actual.issubset(allowed), f"Unexpected gearbox values: {actual - allowed}")
        manual_share = float((self.fact["gearbox"] == "دنده‌ای").mean())
        known_share = float(self.fact["gearbox"].isin(["دنده‌ای", "اتوماتیک"]).mean())
        self.assertAlmostEqual(manual_share * 100, 70.22, delta=0.1)
        self.assertGreater(known_share, 0.80)

    def test_11_selling_method_domain(self) -> None:
        allowed = {"نقدی", "قسطی", "توافقی", "نقدی و قسطی", "سایر/نامشخص"}
        actual = set(self.fact["selling_method"].unique())
        self.assertTrue(actual.issubset(allowed), f"Unexpected selling_method: {actual - allowed}")
        other_share = float((self.fact["selling_method"] == "سایر/نامشخص").mean())
        self.assertGreater(other_share, 0.85)

    def test_12_jalali_date_format(self) -> None:
        pattern = re.compile(r"^\d{4}/\d{2}/\d{2}$")
        self.assertTrue(self.dim_date["jalali_date"].map(lambda s: bool(pattern.match(str(s)))).all())
        self.assertEqual(self.dim_date["jalali_date"].iloc[-1], "1403/04/04")

    def test_13_dim_date_contiguity(self) -> None:
        dates = pd.to_datetime(self.dim_date["date_iso"])
        self.assertTrue(dates.is_monotonic_increasing)
        expected_len = (dates.max() - dates.min()).days + 1
        self.assertEqual(len(dates), expected_len)
        self.assertEqual(str(dates.min().date()), "2021-09-25")
        self.assertEqual(str(dates.max().date()), "2024-06-24")

    def test_14_summary_stats_consistency(self) -> None:
        self.assertEqual(self.summary["clean_rows"], len(self.fact))
        self.assertEqual(self.summary["brands_count"], len(self.dim_brand))
        self.assertEqual(self.summary["cities_count"], len(self.dim_city))
        self.assertEqual(self.summary["dim_date_days"], len(self.dim_date))
        self.assertEqual(self.summary["price_irr"]["median"], int(self.fact["price_irr"].median()))
        self.assertEqual(self.summary["mileage_km"]["median"], int(self.fact["mileage_km"].median()))

        wave_map = dict(zip(self.dim_date["date_key"], self.dim_date["scrape_wave_code"]))
        waves = self.fact["date_key"].map(wave_map)
        w1 = self.fact.loc[waves == 1, "price_irr"]
        w2 = self.fact.loc[waves == 2, "price_irr"]
        self.assertEqual(self.summary["waves"]["wave_1_before_1402"]["listings"], len(w1))
        self.assertEqual(self.summary["waves"]["wave_1_before_1402"]["median_price_irr"], int(w1.median()))
        self.assertEqual(self.summary["waves"]["wave_2_1402_onwards"]["listings"], len(w2))
        self.assertEqual(self.summary["waves"]["wave_2_1402_onwards"]["median_price_irr"], int(w2.median()))

    def test_15_pii_and_dropped_columns_absent(self) -> None:
        forbidden = {"id", "title", "Location", "Third_party_insurance", "Front_Chassis", "Rear_Chassis"}
        self.assertEqual(forbidden.intersection(set(self.fact.columns)), set())
        self.assertTrue(RAW_CSV.exists(), "Raw dataset data/raw/final2024.csv must remain present.")


if __name__ == "__main__":
    unittest.main()
