#!/usr/bin/env python3
"""
Deterministic ETL & Star-Schema Builder for Project 02: Iran Car Market (Divar Listings).

Reads the untouched Kaggle raw CSV (`data/raw/final2024.csv`, arianghasemi/divar-cars v5)
and deterministically produces:
  - data/processed/fact_listing.csv
  - data/processed/dim_brand.csv
  - data/processed/dim_city.csv
  - data/processed/dim_date.csv
  - data/processed/summary_stats.json

Zero randomness (no seed). Every step is reproducible from raw.
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

import jdatetime
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths & Constants
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_CSV = PROJECT_ROOT / "data" / "raw" / "final2024.csv"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

PRICE_TOMAN_MIN = 10_000_000          # 10M Toman = 100M IRR
PRICE_TOMAN_MAX = 100_000_000_000     # 100B Toman = 1,000B IRR
MILEAGE_MIN = 0
MILEAGE_MAX = 2_500_000
MODEL_YEAR_MIN = 1300
MODEL_YEAR_MAX = 1403
WAVE_2_START_ISO = "2023-03-21"       # 1402/01/01 Jalali

FA_AR_TO_EN = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

JALALI_MONTH_NAMES = {
    1: "فروردین",
    2: "اردیبهشت",
    3: "خرداد",
    4: "تیر",
    5: "مرداد",
    6: "شهریور",
    7: "مهر",
    8: "آبان",
    9: "آذر",
    10: "دی",
    11: "بهمن",
    12: "اسفند",
}

# ---------------------------------------------------------------------------
# 55 Ordered Boundary-Safe Brand Rules -> 40 Named Brands + "سایر" = 41 Brands
# Format: (regex_pattern, brand_fa, brand_en, origin_type, manufacturer_group)
# ---------------------------------------------------------------------------
BRAND_RULES: List[Tuple[str, str, str, str, str]] = [
    # Domestic / Iranian platforms (14 brands)
    (r"پژو", "پژو", "Peugeot", "داخلی", "ایران‌خودرو"),
    (r"پراید", "پراید", "Pride", "داخلی", "سایپا"),
    (r"سمند", "سمند", "Samand", "داخلی", "ایران‌خودرو"),
    (r"سورن", "سمند", "Samand", "داخلی", "ایران‌خودرو"),
    (r"کوییک", "کوییک", "Quick", "داخلی", "سایپا"),
    (r"پیکان", "پیکان", "Paykan", "داخلی", "ایران‌خودرو"),
    (r"تیبا", "تیبا", "Tiba", "داخلی", "سایپا"),
    (r"ساینا", "ساینا", "Saina", "داخلی", "سایپا"),
    (r"دنا", "دنا", "Dena", "داخلی", "ایران‌خودرو"),
    (r"زامیاد", "زامیاد", "Zamyad", "داخلی", "سایپا / زامیاد"),
    (r"رانا", "رانا", "Runna", "داخلی", "ایران‌خودرو"),
    (r"شاهین", "شاهین", "Shahin", "داخلی", "سایپا"),
    (r"تارا", "تارا", "Tara", "داخلی", "ایران‌خودرو"),
    (r"آریسان", "آریسان", "Arisun", "داخلی", "ایران‌خودرو"),
    (r"سایپا", "سایپا", "Saipa", "داخلی", "سایپا"),
    (r"اطلس", "سایپا", "Saipa", "داخلی", "سایپا"),
    (r"سهند", "سایپا", "Saipa", "داخلی", "سایپا"),
    # Foreign / Joint-Venture Assembly (26 brands)
    (r"رنو", "رنو", "Renault", "خارجی", "رنو"),
    (r"تندر", "رنو", "Renault", "خارجی", "رنو"),
    (r"مگان", "رنو", "Renault", "خارجی", "رنو"),
    (r"ساندرو", "رنو", "Renault", "خارجی", "رنو"),
    (r"ال[\s\u200c]*۹۰|L90", "رنو", "Renault", "خارجی", "رنو"),
    (r"ام[\s\u200c]+وی[\s\u200c]+ام", "ام‌وی‌ام", "MVM", "خارجی", "مدیران‌خودرو / چری"),
    (r"MVM", "ام‌وی‌ام", "MVM", "خارجی", "مدیران‌خودرو / چری"),
    (r"نیسان", "نیسان", "Nissan", "خارجی", "نیسان"),
    (r"پاترول", "نیسان", "Nissan", "خارجی", "نیسان"),
    (r"هیوندای", "هیوندای", "Hyundai", "خارجی", "هیوندای"),
    (r"هیوندا", "هیوندای", "Hyundai", "خارجی", "هیوندای"),
    (r"جک", "جک", "JAC", "خارجی", "کرمان‌موتور / جک"),
    (r"فونیکس", "فونیکس", "Fownix", "خارجی", "مدیران‌خودرو / چری"),
    (r"کیا", "کیا", "Kia", "خارجی", "کیا"),
    (r"چری", "چری", "Chery", "خارجی", "مدیران‌خودرو / چری"),
    (r"تیگو", "چری", "Chery", "خارجی", "مدیران‌خودرو / چری"),
    (r"آریزو", "چری", "Chery", "خارجی", "مدیران‌خودرو / چری"),
    (r"تویوتا", "تویوتا", "Toyota", "خارجی", "تویوتا"),
    (r"کی[\s\u200c]+ام[\s\u200c]+سی", "کی‌ام‌سی", "KMC", "خارجی", "کرمان‌موتور / جک"),
    (r"هایما", "هایما", "Haima", "خارجی", "ایران‌خودرو / هایما"),
    (r"مزدا", "مزدا", "Mazda", "خارجی", "بهمن‌موتور / مزدا"),
    (r"کارا", "مزدا", "Mazda", "خارجی", "بهمن‌موتور / مزدا"),
    (r"سیتروئن", "سیتروئن", "Citroen", "خارجی", "سیتروئن"),
    (r"زانتیا", "سیتروئن", "Citroen", "خارجی", "سیتروئن"),
    (r"لیفان", "لیفان", "Lifan", "خارجی", "کرمان‌موتور / لیفان"),
    (r"برلیانس", "برلیانس", "Brilliance", "خارجی", "پارس‌خودرو / برلیانس"),
    (r"دوو", "دوو", "Daewoo", "خارجی", "دوو"),
    (r"فیدلیتی", "فیدلیتی", "Fidelity", "خارجی", "بهمن‌موتور"),
    (r"دانگ[\s\u200c]+فنگ", "دانگ‌فنگ", "Dongfeng", "خارجی", "ایران‌خودرو / دانگ‌فنگ"),
    (r"لاماری", "لاماری", "Lamari", "خارجی", "آرین‌پارس‌موتور"),
    (r"چانگان", "چانگان", "Changan", "خارجی", "سایپا / چانگان"),
    (r"فولکس", "فولکس‌واگن", "Volkswagen", "خارجی", "فولکس‌واگن"),
    (r"دیگنیتی", "دیگنیتی", "Dignity", "خارجی", "بهمن‌موتور"),
    (r"بی[\s\u200c]+ام[\s\u200c]+و", "بی‌ام‌و", "BMW", "خارجی", "بی‌ام‌و"),
    (r"مرسدس", "مرسدس‌بنز", "Mercedes-Benz", "خارجی", "مرسدس‌بنز"),
    (r"بنز", "مرسدس‌بنز", "Mercedes-Benz", "خارجی", "مرسدس‌بنز"),
    (r"جیلی", "جیلی", "Geely", "خارجی", "جیلی"),
    (r"میتسوبیشی", "میتسوبیشی", "Mitsubishi", "خارجی", "میتسوبیشی"),
]

assert len(BRAND_RULES) == 55, f"Expected 55 brand rules, got {len(BRAND_RULES)}"

# ---------------------------------------------------------------------------
# Top 90 Frequent Cities Mapped to Persian (~91.7% listing coverage)
# Remaining 244 cities keep their cleaned Latin slug transparently.
# ---------------------------------------------------------------------------
CITY_FA_MAP: Dict[str, str] = {
    "tehran": "تهران",
    "mashhad": "مشهد",
    "isfahan": "اصفهان",
    "shiraz": "شیراز",
    "karaj": "کرج",
    "tabriz": "تبریز",
    "ahvaz": "اهواز",
    "kermanshah": "کرمانشاه",
    "kerman": "کرمان",
    "qom": "قم",
    "urmia": "ارومیه",
    "rasht": "رشت",
    "bandar-abbas": "بندرعباس",
    "zahedan": "زاهدان",
    "ardabil": "اردبیل",
    "qazvin": "قزوین",
    "arak": "اراک",
    "gorgan": "گرگان",
    "sanandaj": "سنندج",
    "khorramabad": "خرم‌آباد",
    "zanjan": "زنجان",
    "bushehr": "بوشهر",
    "eslamshahr": "اسلامشهر",
    "ilam": "ایلام",
    "bojnurd": "بجنورد",
    "shahrekord": "شهرکرد",
    "dezful": "دزفول",
    "neyshabur": "نیشابور",
    "sirjan": "سیرجان",
    "sabzevar": "سبزوار",
    "abadan": "آبادان",
    "kashan": "کاشان",
    "borujerd": "بروجرد",
    "saveh": "ساوه",
    "zabol": "زابل",
    "gonbad-kavus": "گنبد کاووس",
    "najafabad": "نجف‌آباد",
    "robat-karim": "رباط‌کریم",
    "semnan": "سمنان",
    "sari": "ساری",
    "rafsanjan": "رفسنجان",
    "golestan-baharestan": "گلستان (بهارستان)",
    "jiroft": "جیرفت",
    "shahin-shahr": "شاهین‌شهر",
    "khoy": "خوی",
    "torbat-heydariyeh": "تربت حیدریه",
    "bam": "بم",
    "saravan": "سراوان",
    "behbahan": "بهبهان",
    "malayer": "ملایر",
    "chabahar": "چابهار",
    "kuhdasht": "کوهدشت",
    "kazeroon": "کازرون",
    "saqqez": "سقز",
    "torbat-jam": "تربت جام",
    "amol": "آمل",
    "miandoab": "میاندوآب",
    "andisheh-new-town": "اندیشه",
    "dorud": "دورود",
    "bukan": "بوکان",
    "nasimshahr": "نسیم‌شهر",
    "babol": "بابل",
    "parsabad": "پارس‌آباد",
    "marivan": "مریوان",
    "lahijan": "لاهیجان",
    "minab": "میناب",
    "izeh": "ایذه",
    "kahnooj": "کهنوج",
    "lordegan": "لردگان",
    "foolad-shahr": "فولادشهر",
    "borazjan": "برازجان",
    "darab": "داراب",
    "nazarabad": "نظرآباد",
    "abhar": "ابهر",
    "tonekabon": "تنکابن",
    "aligudarz": "الیگودرز",
    "shirvan": "شیروان",
    "maku": "ماکو",
    "qeshm": "قشم",
    "maragheh": "مراغه",
    "jahrom": "جهرم",
    "dogonbadan": "دوگنبدان",
    "nahavand": "نهاوند",
    "qorveh": "قروه",
    "eslamabad-gharb": "اسلام‌آباد غرب",
    "marand": "مرند",
    "ahar": "اهر",
    "baneh": "بانه",
    "bumehen": "بومهن",
    "kish": "کیش",
}

assert len(CITY_FA_MAP) == 90, f"Expected 90 Persian city mappings, got {len(CITY_FA_MAP)}"

METROPOLIS_SLUGS = {
    "tehran", "mashhad", "isfahan", "shiraz", "karaj", "tabriz", "ahvaz", "qom", "kermanshah"
}


# ---------------------------------------------------------------------------
# Normalization Helpers
# ---------------------------------------------------------------------------
def norm_persian_text(val: object) -> str:
    if pd.isna(val):
        return ""
    s = str(val).replace("ي", "ی").replace("ك", "ک").strip()
    return s


def clean_model_year(series: pd.Series) -> pd.Series:
    raw = series.astype(str).str.translate(FA_AR_TO_EN).str.strip()
    # Explicitly treat "قبل از 1366" and non-numeric strings as NaN
    num = pd.to_numeric(raw, errors="coerce")
    jalali = num.copy()
    greg_mask = num >= 1800
    jalali.loc[greg_mask] = num.loc[greg_mask] - 621
    valid_mask = (jalali >= MODEL_YEAR_MIN) & (jalali <= MODEL_YEAR_MAX)
    jalali = jalali.where(valid_mask, np.nan)
    return jalali.astype("Int64")


def clean_mileage(series: pd.Series) -> pd.Series:
    raw = (
        series.astype(str)
        .str.translate(FA_AR_TO_EN)
        .str.replace("٬", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.strip()
    )
    num = pd.to_numeric(raw, errors="coerce")
    valid = num.where((num >= MILEAGE_MIN) & (num <= MILEAGE_MAX), np.nan)
    return valid.round().astype("Int64")


def clean_gearbox(series: pd.Series) -> pd.Series:
    norm = series.map(norm_persian_text)
    out = np.where(
        norm.isin(["دنده‌ای", "دنده ای"]),
        "دنده‌ای",
        np.where(norm == "اتوماتیک", "اتوماتیک", "نامشخص"),
    )
    return pd.Series(out, index=series.index, dtype="object")


def clean_selling_method(series: pd.Series) -> pd.Series:
    norm = series.map(norm_persian_text)
    valid = {"نقدی", "قسطی", "توافقی", "نقدی و قسطی"}
    return norm.where(norm.isin(valid), "سایر/نامشخص")


def clean_fuel_type(series: pd.Series) -> pd.Series:
    norm = series.map(norm_persian_text)
    valid = {"بنزینی", "دوگانه‌سوز شرکتی", "دوگانه‌سوز دستی", "گازوئیل"}
    return norm.where(norm.isin(valid), np.nan)


def clean_body_condition(series: pd.Series) -> pd.Series:
    norm = series.map(norm_persian_text)
    def _map_body(s: str) -> str:
        if not s:
            return "نامشخص"
        if "سالم" in s and ("بی‌خط" in s or "بی خط" in s):
            return "سالم و بی‌خط و خش"
        if "خط و خش" in s:
            return "خط و خش جزیی"
        if "صافکاری" in s:
            return "صافکاری بی‌رنگ"
        if "دوررنگ" in s or "دور رنگ" in s:
            return "دوررنگ"
        if "تمام‌رنگ" in s or "تمام رنگ" in s:
            return "تمام‌رنگ"
        if "رنگ‌شدگی" in s or "رنگ شدگی" in s:
            return "رنگ‌شدگی جزئی"
        if "تصادفی" in s:
            return "تصادفی"
        if "اوراقی" in s:
            return "اوراقی"
        return "سایر/نامشخص"
    unique_vals = norm.unique()
    lookup = {v: _map_body(v) for v in unique_vals}
    return norm.map(lookup)


def clean_engine_condition(series: pd.Series) -> pd.Series:
    norm = series.map(norm_persian_text)
    valid_map = {
        "سالم": "سالم",
        "سالم و پلمپ": "سالم",
        "نیاز به تعمیر": "نیاز به تعمیر",
        "تعویض شده": "تعویض شده",
    }
    return norm.map(lambda s: valid_map.get(s, "نامشخص"))


def clean_chassis_condition(series: pd.Series) -> pd.Series:
    norm = series.map(norm_persian_text)
    valid_map = {
        "سالم و پلمپ": "سالم و پلمپ",
        "ضربه‌خورده": "ضربه‌خورده",
        "ضربه خورده": "ضربه‌خورده",
        "رنگ‌شده": "رنگ‌شده",
        "رنگ شده": "رنگ‌شده",
    }
    return norm.map(lambda s: valid_map.get(s, "نامشخص"))


def clean_color(series: pd.Series) -> pd.Series:
    norm = series.map(norm_persian_text)
    fixes = {
        "نقره ای": "نقره‌ای",
        "نوک مدادی": "نوک‌مدادی",
        "سرمه ای": "سرمه‌ای",
        "قهوه ای": "قهوه‌ای",
        "": "نامشخص",
    }
    return norm.map(lambda s: fixes.get(s, s))


def extract_brand_column(series: pd.Series) -> Tuple[pd.Series, pd.DataFrame]:
    compiled = [
        (re.compile(r"(?:^|[\s،,\-\u200c/()])" + pat + r"(?:$|[\s،,\-\u200c/()])"), b_fa)
        for pat, b_fa, _, _, _ in BRAND_RULES
    ]
    # Build metadata table for each brand
    meta: Dict[str, Tuple[str, str, str]] = {}
    for _, b_fa, b_en, orig, grp in BRAND_RULES:
        if b_fa not in meta:
            meta[b_fa] = (b_en, orig, grp)
    meta["سایر"] = ("Other / Unmatched", "نامشخص", "سایر")

    norm = series.map(norm_persian_text)
    lookup: Dict[str, str] = {}
    for val in norm.unique():
        matched = "سایر"
        if val:
            for rx, b_fa in compiled:
                if rx.search(val):
                    matched = b_fa
                    break
        lookup[val] = matched

    mapped = norm.map(lookup)
    vc = mapped.value_counts()

    # Order brands by descending listing count (keeping "سایر" last)
    named_brands = [b for b in vc.index if b != "سایر"]
    ordered_brands = named_brands + ["سایر"]

    dim_rows = []
    for idx, b_fa in enumerate(ordered_brands, start=1):
        b_en, orig, grp = meta[b_fa]
        dim_rows.append(
            {
                "brand_key": idx,
                "brand_name_fa": b_fa,
                "brand_name_en": b_en,
                "origin_type": orig,
                "manufacturer_group": grp,
            }
        )
    dim_brand = pd.DataFrame(dim_rows)
    return mapped, dim_brand


def build_dim_city(city_slugs: pd.Series) -> pd.DataFrame:
    vc = city_slugs.value_counts()
    rows = []
    for idx, slug in enumerate(vc.index, start=1):
        if slug in CITY_FA_MAP:
            name_fa = CITY_FA_MAP[slug]
            is_mapped = True
        else:
            name_fa = slug.replace("-", " ").title()
            is_mapped = False

        if slug == "tehran":
            tier = "تهران"
        elif slug in METROPOLIS_SLUGS:
            tier = "کلان‌شهر"
        elif is_mapped:
            tier = "شهر پرتکرار (نگاشت فارسی)"
        else:
            tier = "سایر شهرها (نام لاتین منبع)"

        rows.append(
            {
                "city_key": idx,
                "city_slug": slug,
                "city_name_fa": name_fa,
                "is_persian_mapped": is_mapped,
                "is_tehran": slug == "tehran",
                "city_tier": tier,
            }
        )
    return pd.DataFrame(rows)


def build_dim_date(min_dt: date, max_dt: date) -> pd.DataFrame:
    rows = []
    cur = min_dt
    wave2_date = date.fromisoformat(WAVE_2_START_ISO)
    while cur <= max_dt:
        jd = jdatetime.date.fromgregorian(year=cur.year, month=cur.month, day=cur.day)
        quarter = (jd.month - 1) // 3 + 1
        wave = "موج اول (پیش از ۱۴۰۲)" if cur < wave2_date else "موج دوم (۱۴۰۲ به بعد)"
        wave_code = 1 if cur < wave2_date else 2
        rows.append(
            {
                "date_key": int(cur.strftime("%Y%m%d")),
                "date_iso": cur.isoformat(),
                "jalali_date": f"{jd.year:04d}/{jd.month:02d}/{jd.day:02d}",
                "jalali_year": jd.year,
                "jalali_month": jd.month,
                "jalali_month_name": JALALI_MONTH_NAMES[jd.month],
                "jalali_day": jd.day,
                "jalali_quarter": f"Q{quarter}",
                "jalali_year_month": f"{jd.year:04d}/{jd.month:02d}",
                "scrape_wave_code": wave_code,
                "scrape_wave": wave,
            }
        )
        cur += timedelta(days=1)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Main Pipeline
# ---------------------------------------------------------------------------
def main() -> None:
    if not RAW_CSV.exists():
        raise FileNotFoundError(
            f"Raw dataset not found at {RAW_CSV}. See data/raw/README.md for download instructions."
        )

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[1/6] Loading raw dataset from {RAW_CSV} ...")
    raw = pd.read_csv(RAW_CSV, low_memory=False)
    raw_row_count = len(raw)
    raw_col_count = raw.shape[1]
    print(f"      Raw shape: {raw_row_count:,} rows x {raw_col_count} columns")

    # Step 1: Price cleaning & filtering
    print("[2/6] Filtering price to [10M, 100B] Toman and converting to IRR (x10) ...")
    price_raw_str = raw["Price"].astype(str).str.translate(FA_AR_TO_EN).str.replace(",", "", regex=False).str.strip()
    price_toman = pd.to_numeric(price_raw_str, errors="coerce")
    price_null_count = int(price_toman.isna().sum())
    price_zero_or_neg = int((price_toman <= 0).sum())
    price_below_min = int(((price_toman > 0) & (price_toman < PRICE_TOMAN_MIN)).sum())
    price_above_max = int((price_toman > PRICE_TOMAN_MAX).sum())

    valid_price_mask = (
        price_toman.notna()
        & (price_toman >= PRICE_TOMAN_MIN)
        & (price_toman <= PRICE_TOMAN_MAX)
    )
    df = raw.loc[valid_price_mask].copy().reset_index(drop=True)
    price_toman_clean = price_toman.loc[valid_price_mask].round().astype("int64").reset_index(drop=True)
    dropped_rows = raw_row_count - len(df)
    print(
        f"      Kept {len(df):,} rows (dropped {dropped_rows:,} rows = {dropped_rows/raw_row_count*100:.2f}%)"
    )

    # Step 2: Date & dim_date
    print("[3/6] Parsing dates and building contiguous Jalali dim_date ...")
    dt_series = pd.to_datetime(df["Time"], errors="coerce")
    if dt_series.isna().any():
        raise ValueError(f"Found {int(dt_series.isna().sum())} invalid Time values after price filter.")

    min_dt = dt_series.min().date()
    max_dt = dt_series.max().date()
    dim_date = build_dim_date(min_dt, max_dt)

    date_key_series = dt_series.dt.strftime("%Y%m%d").astype("int64")
    date_to_jyear = dict(zip(dim_date["date_key"], dim_date["jalali_year"]))
    listing_j_year = date_key_series.map(date_to_jyear)

    # Step 3: Numeric & categorical cleaning
    print("[4/6] Cleaning model_year, car_age, mileage, brand, city, gearbox, selling_method, fuel_type ...")
    model_year_jalali = clean_model_year(df["Model_Year"])
    car_age = (listing_j_year - model_year_jalali).clip(lower=0).astype("Int64")
    mileage_km = clean_mileage(df["Mileage"])

    brand_fa_series, dim_brand = extract_brand_column(df["Brand"])
    brand_to_key = dict(zip(dim_brand["brand_name_fa"], dim_brand["brand_key"]))
    brand_key_series = brand_fa_series.map(brand_to_key).astype("int64")

    city_slug_series = df["City"].astype(str).str.strip().str.lower()
    dim_city = build_dim_city(city_slug_series)
    city_to_key = dict(zip(dim_city["city_slug"], dim_city["city_key"]))
    city_key_series = city_slug_series.map(city_to_key).astype("int64")

    gearbox_clean = clean_gearbox(df["Gearbox"])
    selling_method_clean = clean_selling_method(df["Selling_Method"])
    fuel_type_clean = clean_fuel_type(df["Fuel_Type"])
    body_clean = clean_body_condition(df["Body_Condition"])
    engine_clean = clean_engine_condition(df["Engine_Condition"])
    chassis_clean = clean_chassis_condition(df["Chassis_Condition"])
    color_clean = clean_color(df["Color"])

    # Step 4: Assemble fact_listing (PII columns id/title/Location and sparse insurance/front-rear chassis dropped)
    print("[5/6] Assembling fact_listing and exporting star-schema CSVs ...")
    fact_listing = pd.DataFrame(
        {
            "listing_id": np.arange(1, len(df) + 1, dtype="int64"),
            "date_key": date_key_series.values,
            "brand_key": brand_key_series.values,
            "city_key": city_key_series.values,
            "price_irr": (price_toman_clean * 10).values,
            "model_year_jalali": model_year_jalali.values,
            "car_age": car_age.values,
            "mileage_km": mileage_km.values,
            "gearbox": gearbox_clean.values,
            "fuel_type": fuel_type_clean.values,
            "selling_method": selling_method_clean.values,
            "body_condition": body_clean.values,
            "engine_condition": engine_clean.values,
            "chassis_condition": chassis_clean.values,
            "color": color_clean.values,
        }
    )

    fact_listing.to_csv(PROCESSED_DIR / "fact_listing.csv", index=False)
    dim_brand.to_csv(PROCESSED_DIR / "dim_brand.csv", index=False)
    dim_city.to_csv(PROCESSED_DIR / "dim_city.csv", index=False)
    dim_date.to_csv(PROCESSED_DIR / "dim_date.csv", index=False)

    # Step 5: Compute summary_stats.json
    print("[6/6] Computing summary_stats.json ...")
    wave_lookup = dict(zip(dim_date["date_key"], dim_date["scrape_wave_code"]))
    wave_col = fact_listing["date_key"].map(wave_lookup)
    w1_mask = wave_col == 1
    w2_mask = wave_col == 2

    tehran_key = int(dim_city.loc[dim_city["city_slug"] == "tehran", "city_key"].iloc[0])
    tehran_count = int((fact_listing["city_key"] == tehran_key).sum())
    mapped_city_keys = set(dim_city.loc[dim_city["is_persian_mapped"], "city_key"])
    mapped_city_coverage = float(fact_listing["city_key"].isin(mapped_city_keys).mean())

    brand_key_to_fa = dict(zip(dim_brand["brand_key"], dim_brand["brand_name_fa"]))
    brand_key_to_origin = dict(zip(dim_brand["brand_key"], dim_brand["origin_type"]))
    city_key_to_fa = dict(zip(dim_city["city_key"], dim_city["city_name_fa"]))

    top_brands = []
    for bk, cnt in fact_listing["brand_key"].value_counts().head(10).items():
        sub_b = fact_listing.loc[fact_listing["brand_key"] == bk, "price_irr"]
        top_brands.append(
            {
                "brand_key": int(bk),
                "brand_name_fa": brand_key_to_fa[int(bk)],
                "origin_type": brand_key_to_origin[int(bk)],
                "listings": int(cnt),
                "share_pct": round(float(cnt) / len(fact_listing) * 100, 2),
                "median_price_irr": int(sub_b.median()),
            }
        )

    top_cities = []
    for ck, cnt in fact_listing["city_key"].value_counts().head(10).items():
        sub_c = fact_listing.loc[fact_listing["city_key"] == ck, "price_irr"]
        top_cities.append(
            {
                "city_key": int(ck),
                "city_name_fa": city_key_to_fa[int(ck)],
                "listings": int(cnt),
                "share_pct": round(float(cnt) / len(fact_listing) * 100, 2),
                "median_price_irr": int(sub_c.median()),
            }
        )

    origin_series = fact_listing["brand_key"].map(brand_key_to_origin)
    origin_counts = origin_series.value_counts().to_dict()
    gearbox_counts = fact_listing["gearbox"].value_counts().to_dict()
    selling_counts = fact_listing["selling_method"].value_counts().to_dict()
    fuel_missing_count = int(fact_listing["fuel_type"].isna().sum())

    summary = {
        "project": "بازار خودروی ایران — تحلیل آگهی‌های دیوار",
        "source_dataset": "arianghasemi/divar-cars (v5, final2024.csv)",
        "source_url": "https://www.kaggle.com/datasets/arianghasemi/divar-cars",
        "snapshot_iso": max_dt.isoformat(),
        "snapshot_jalali": str(dim_date.loc[dim_date["date_iso"] == max_dt.isoformat(), "jalali_date"].iloc[0]),
        "date_min_iso": min_dt.isoformat(),
        "date_max_iso": max_dt.isoformat(),
        "date_min_jalali": str(dim_date.loc[dim_date["date_iso"] == min_dt.isoformat(), "jalali_date"].iloc[0]),
        "date_max_jalali": str(dim_date.loc[dim_date["date_iso"] == max_dt.isoformat(), "jalali_date"].iloc[0]),
        "dim_date_days": int(len(dim_date)),
        "raw_rows": int(raw_row_count),
        "raw_columns": int(raw_col_count),
        "dropped_rows_price_filter": int(dropped_rows),
        "dropped_pct": round(float(dropped_rows) / raw_row_count * 100, 2),
        "price_drop_breakdown": {
            "null_price": price_null_count,
            "zero_or_negative": price_zero_or_neg,
            "below_10m_toman": price_below_min,
            "above_100b_toman": price_above_max,
        },
        "clean_rows": int(len(fact_listing)),
        "brands_count": int(len(dim_brand)),
        "brand_rules_count": int(len(BRAND_RULES)),
        "cities_count": int(len(dim_city)),
        "cities_persian_mapped": int(dim_city["is_persian_mapped"].sum()),
        "cities_latin_preserved": int((~dim_city["is_persian_mapped"]).sum()),
        "cities_persian_coverage_pct": round(mapped_city_coverage * 100, 2),
        "price_irr": {
            "median": int(fact_listing["price_irr"].median()),
            "mean": round(float(fact_listing["price_irr"].mean()), 2),
            "p25": int(fact_listing["price_irr"].quantile(0.25)),
            "p75": int(fact_listing["price_irr"].quantile(0.75)),
            "p90": int(fact_listing["price_irr"].quantile(0.90)),
            "min": int(fact_listing["price_irr"].min()),
            "max": int(fact_listing["price_irr"].max()),
        },
        "mileage_km": {
            "median": int(fact_listing["mileage_km"].median()),
            "mean": round(float(fact_listing["mileage_km"].mean()), 2),
            "null_count": int(fact_listing["mileage_km"].isna().sum()),
            "null_pct": round(float(fact_listing["mileage_km"].isna().mean()) * 100, 2),
        },
        "model_year_jalali": {
            "min": int(fact_listing["model_year_jalali"].min()),
            "max": int(fact_listing["model_year_jalali"].max()),
            "median": int(fact_listing["model_year_jalali"].median()),
            "null_count": int(fact_listing["model_year_jalali"].isna().sum()),
            "null_pct": round(float(fact_listing["model_year_jalali"].isna().mean()) * 100, 2),
        },
        "car_age": {
            "min": int(fact_listing["car_age"].min()),
            "max": int(fact_listing["car_age"].max()),
            "median": int(fact_listing["car_age"].median()),
            "mean": round(float(fact_listing["car_age"].mean()), 2),
        },
        "tehran_listings": tehran_count,
        "tehran_share_pct": round(float(tehran_count) / len(fact_listing) * 100, 2),
        "gearbox_counts": {k: int(v) for k, v in gearbox_counts.items()},
        "gearbox_manual_share_pct": round(
            float(gearbox_counts.get("دنده‌ای", 0)) / len(fact_listing) * 100, 2
        ),
        "gearbox_auto_share_pct": round(
            float(gearbox_counts.get("اتوماتیک", 0)) / len(fact_listing) * 100, 2
        ),
        "gearbox_unknown_share_pct": round(
            float(gearbox_counts.get("نامشخص", 0)) / len(fact_listing) * 100, 2
        ),
        "selling_method_counts": {k: int(v) for k, v in selling_counts.items()},
        "selling_method_other_share_pct": round(
            float(selling_counts.get("سایر/نامشخص", 0)) / len(fact_listing) * 100, 2
        ),
        "fuel_type_missing_count": fuel_missing_count,
        "fuel_type_missing_pct": round(float(fuel_missing_count) / len(fact_listing) * 100, 2),
        "origin_counts": {k: int(v) for k, v in origin_counts.items()},
        "waves": {
            "wave_1_before_1402": {
                "label": "موج اول (پیش از ۱۴۰۲)",
                "listings": int(w1_mask.sum()),
                "share_pct": round(float(w1_mask.mean()) * 100, 2),
                "median_price_irr": int(fact_listing.loc[w1_mask, "price_irr"].median()),
                "mean_price_irr": round(float(fact_listing.loc[w1_mask, "price_irr"].mean()), 2),
                "median_mileage_km": int(fact_listing.loc[w1_mask, "mileage_km"].median()),
            },
            "wave_2_1402_onwards": {
                "label": "موج دوم (۱۴۰۲ به بعد)",
                "listings": int(w2_mask.sum()),
                "share_pct": round(float(w2_mask.mean()) * 100, 2),
                "median_price_irr": int(fact_listing.loc[w2_mask, "price_irr"].median()),
                "mean_price_irr": round(float(fact_listing.loc[w2_mask, "price_irr"].mean()), 2),
                "median_mileage_km": int(fact_listing.loc[w2_mask, "mileage_km"].median()),
            },
        },
        "top_brands": top_brands,
        "top_cities": top_cities,
    }

    with open(PROCESSED_DIR / "summary_stats.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("Done! Summary:")
    print(f"  clean_rows        = {summary['clean_rows']:,}")
    print(f"  brands_count      = {summary['brands_count']}")
    print(f"  cities_count      = {summary['cities_count']} (FA mapped: {summary['cities_persian_mapped']}, coverage: {summary['cities_persian_coverage_pct']}%)")
    print(f"  dim_date_days     = {summary['dim_date_days']} ({summary['date_min_jalali']} -> {summary['date_max_jalali']})")
    print(f"  median_price_irr  = {summary['price_irr']['median']:,} IRR")
    print(f"  wave_1 / wave_2   = {summary['waves']['wave_1_before_1402']['listings']:,} / {summary['waves']['wave_2_1402_onwards']['listings']:,}")


if __name__ == "__main__":
    main()
