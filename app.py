#!/usr/bin/env python3
"""
بازار خودروی ایران — تحلیل آگهی‌های دیوار (پیش‌نمایش تعاملی گزارش Power BI)

- طراحی طبیعی، کاملاً فارسی و راست‌چین با فونت محلی Vazirmatn FD (صفر درخواست شبکهٔ خارجی)
- تم رسمی «Iran Car Market Fa»: سرمه‌ای #123a5f، طلایی #f2a900، پس‌زمینه #f5f7fa
- ۵ صفحه: نمای کلی بازار / تحلیل برند و سازنده / قیمت، سن و کارکرد / شهرها / دربارهٔ داده
- نمودارهای افقی تمام‌راست‌چین (برچسب‌ها در راست، میله‌ها از راست به چپ، محورها تمام‌فارسی بدون k انگلیسی)
- بدون هیچ نمودار روند قیمتی زمانی (دو موج اسکرپ ≠ سری زمانی)
"""

from __future__ import annotations

import base64
import html
import json
import math
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# Paths & Palette ("Iran Car Market Fa")
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
FONTS_DIR = PROJECT_ROOT / "assets" / "fonts"

NAVY = "#123a5f"
NAVY_MID = "#235480"
NAVY_SOFT = "#3d6e99"
GOLD = "#f2a900"
GOLD_DARK = "#b47b00"
TEAL = "#0f766e"
SLATE = "#64748b"
MUTED = "#718096"
BG_COLOR = "#f5f7fa"
CARD_BG = "#ffffff"
BORDER_COLOR = "#e4e9f0"
TEXT_PRIMARY = "#102033"
TEXT_SECONDARY = "#4a5a6a"

EN_TO_FA = str.maketrans("0123456789.,", "۰۱۲۳۴۵۶۷۸۹٫٬")

PAGES = [
    "نمای کلی بازار",
    "تحلیل برند و سازنده",
    "قیمت، سن و کارکرد",
    "شهرها",
    "دربارهٔ داده",
]


# ---------------------------------------------------------------------------
# Persian Formatting Helpers
# ---------------------------------------------------------------------------
def fa_digits(text: object) -> str:
    return str(text).translate(EN_TO_FA)


def fmt_int(val: float | int | None) -> str:
    if val is None or pd.isna(val):
        return "—"
    # Standard comma renders natively and cleanly inside Vazirmatn FD
    return f"{int(round(float(val))):,}".replace(",", "،").translate(
        str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    )


def fmt_pct(val: float | None, decimals: int = 1) -> str:
    if val is None or pd.isna(val):
        return "—"
    return f"{float(val):.{decimals}f}٪".translate(EN_TO_FA)


def fmt_bn_irr(val_irr: float | int | None, decimals: int = 2) -> str:
    if val_irr is None or pd.isna(val_irr):
        return "—"
    bn = float(val_irr) / 1_000_000_000
    s = f"{bn:,.{decimals}f}".replace(",", "،").replace(".", "٫")
    return f"{s.translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))} میلیارد ریال"


def fmt_short_bn(val_irr: float | int | None, decimals: int = 1) -> str:
    if val_irr is None or pd.isna(val_irr):
        return "—"
    bn = float(val_irr) / 1_000_000_000
    s = f"{bn:.{decimals}f}".replace(".", "٫")
    return f"{s.translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))} م‌ر"


def rtl_svg(text: object) -> str:
    """Wrap Persian text with Unicode RLE..PDF so Plotly's LTR SVG preserves exact RTL word/number order."""
    return f"\u202b{text}\u202c"


def persian_count_ticks(max_val: float, n_ticks: int = 5) -> Tuple[List[float], List[str]]:
    """Build clean Persian numeric ticks (zero English '50k' / '100k')."""
    if max_val <= 0:
        return [0], [rtl_svg("۰")]
    raw_step = max_val / max(n_ticks - 1, 1)
    mag = 10 ** math.floor(math.log10(raw_step))
    norm = raw_step / mag
    if norm <= 1.2:
        step = 1 * mag
    elif norm <= 2.2:
        step = 2 * mag
    elif norm <= 2.7:
        step = 2.5 * mag
    elif norm <= 5.5:
        step = 5 * mag
    else:
        step = 10 * mag

    vals = []
    cur = 0.0
    while cur <= max_val * 1.02:
        vals.append(cur)
        cur += step

    labels = []
    for v in vals:
        if v == 0:
            labels.append(rtl_svg("۰"))
        elif v >= 1_000_000:
            num = v / 1_000_000
            lbl = f"{num:g} میلیون".replace(".", "٫")
            labels.append(rtl_svg(lbl.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))))
        elif v >= 1_000:
            num = v / 1_000
            lbl = f"{num:g} هزار".replace(".", "٫")
            labels.append(rtl_svg(lbl.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))))
        else:
            labels.append(rtl_svg(fmt_int(v)))
    return vals, labels


def persian_decimal_ticks(max_val: float, n_ticks: int = 5, suffix: str = "") -> Tuple[List[float], List[str]]:
    if max_val <= 0:
        return [0], [rtl_svg("۰")]
    raw_step = max_val / max(n_ticks - 1, 1)
    mag = 10 ** math.floor(math.log10(raw_step))
    norm = raw_step / mag
    if norm <= 1.2:
        step = 1 * mag
    elif norm <= 2.2:
        step = 2 * mag
    elif norm <= 5.5:
        step = 5 * mag
    else:
        step = 10 * mag

    vals = []
    cur = 0.0
    while cur <= max_val * 1.02:
        vals.append(round(cur, 4))
        cur += step

    labels = []
    for v in vals:
        if v == 0:
            labels.append(rtl_svg("۰"))
        else:
            s = f"{v:g}".replace(".", "٫").translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
            labels.append(rtl_svg(f"{s}{suffix}"))
    return vals, labels


# ---------------------------------------------------------------------------
# Local Font Embedding (Zero External Network Requests)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def build_font_css() -> str:
    weights = [
        ("Vazirmatn-FD-Regular.woff2", 400),
        ("Vazirmatn-FD-Medium.woff2", 500),
        ("Vazirmatn-FD-SemiBold.woff2", 600),
        ("Vazirmatn-FD-Bold.woff2", 700),
    ]
    blocks = []
    for fname, weight in weights:
        fpath = FONTS_DIR / fname
        if fpath.exists():
            b64 = base64.b64encode(fpath.read_bytes()).decode("ascii")
            blocks.append(
                f"""
                @font-face {{
                    font-family: 'Vazirmatn FD';
                    src: url('data:font/woff2;base64,{b64}') format('woff2');
                    font-weight: {weight};
                    font-style: normal;
                    font-display: swap;
                }}
                """
            )
    return "\n".join(blocks)


def inject_theme_css() -> None:
    font_css = build_font_css()
    st.markdown(
        f"""
        <style>
        {font_css}

        /* 1. Hide Streamlit default English chrome & stray sidebar collapse icon text */
        #MainMenu,
        footer,
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        [data-testid="stSidebarHeader"],
        [data-testid="stSidebarCollapseButton"],
        header[data-testid="stHeader"] {{
            display: none !important;
            visibility: hidden !important;
            height: 0 !important;
            min-height: 0 !important;
            overflow: hidden !important;
        }}

        /* 2. Universal Vazirmatn FD + True RTL across every Streamlit wrapper */
        html, body, .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        [data-testid="stMainBlockContainer"],
        [data-testid="stMarkdownContainer"],
        [data-testid="stMarkdownContainer"] *,
        section[data-testid="stSidebar"],
        section[data-testid="stSidebar"] *,
        .stSelectbox, .stMultiSelect, .stSlider, .stCheckbox, .stRadio,
        button, input, textarea, select, label, p, span, div, h1, h2, h3, h4, td, th {{
            font-family: 'Vazirmatn FD', Tahoma, sans-serif !important;
        }}

        /* Preserve Streamlit Material icons */
        [data-testid="stIconMaterial"],
        span[class*="material-symbols"],
        .material-icons {{
            font-family: 'Material Symbols Rounded', 'Material Icons', sans-serif !important;
            direction: ltr !important;
        }}

        html, body, .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        [data-testid="stMainBlockContainer"],
        [data-testid="stMarkdownContainer"],
        [data-testid="stMarkdownContainer"] p,
        [data-testid="stMarkdownContainer"] div,
        [data-testid="stMarkdownContainer"] li,
        section[data-testid="stSidebar"],
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] p {{
            direction: rtl !important;
            text-align: right !important;
        }}

        .stApp {{
            background-color: {BG_COLOR} !important;
            color: {TEXT_PRIMARY} !important;
        }}

        .block-container,
        [data-testid="stMainBlockContainer"] {{
            padding-top: 1.25rem !important;
            padding-bottom: 2.5rem !important;
            padding-left: 1.75rem !important;
            padding-right: 1.75rem !important;
            max-width: 1420px !important;
        }}

        /* 3. Mandatory Plotly LTR container isolation */
        .js-plotly-plot,
        .js-plotly-plot *,
        .plotly,
        .plot-container {{
            direction: ltr !important;
        }}

        /* 4. Sidebar styling — clean editorial panel on the RIGHT */
        section[data-testid="stSidebar"] {{
            background-color: #ffffff !important;
            border-left: 1px solid {BORDER_COLOR} !important;
            border-right: none !important;
            min-width: 280px !important;
            max-width: 295px !important;
        }}
        section[data-testid="stSidebar"] > div:first-child {{
            padding-top: 1.15rem !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
        }}

        .brand-lockup {{
            padding: 0.25rem 0.1rem 0.9rem 0.1rem;
            border-bottom: 1px solid {BORDER_COLOR};
            margin-bottom: 1rem;
            direction: rtl !important;
            text-align: right !important;
        }}
        .brand-lockup-top {{
            display: flex;
            align-items: center;
            gap: 0.55rem;
            margin-bottom: 0.25rem;
        }}
        .brand-dot {{
            width: 10px;
            height: 26px;
            border-radius: 4px;
            background: linear-gradient(180deg, {NAVY} 0%, {NAVY} 68%, {GOLD} 68%, {GOLD} 100%);
            flex-shrink: 0;
        }}
        .brand-name {{
            font-size: 1.06rem;
            font-weight: 700;
            color: {NAVY};
            line-height: 1.3;
        }}
        .brand-desc {{
            font-size: 0.78rem;
            color: {MUTED};
            margin-right: 1.05rem;
        }}

        /* Style sidebar radio as sleek RTL navigation items (hide raw radio dots) */
        section[data-testid="stSidebar"] div[role="radiogroup"] {{
            gap: 0.28rem !important;
            direction: rtl !important;
        }}
        section[data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"] {{
            background: transparent;
            border-radius: 8px !important;
            padding: 0.5rem 0.78rem !important;
            margin: 0 !important;
            cursor: pointer;
            transition: background-color 0.15s ease, color 0.15s ease;
            border-right: 3px solid transparent;
            width: 100%;
            display: flex !important;
            flex-direction: row !important;
            justify-content: flex-start !important;
            align-items: center !important;
        }}
        section[data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"]:hover {{
            background-color: #f1f5f9 !important;
        }}
        section[data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"] > div:first-of-type {{
            display: none !important;
        }}
        section[data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"]:has(input:checked) {{
            background-color: #edf3f9 !important;
            border-right: 3px solid {NAVY} !important;
        }}
        section[data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"]:has(input:checked) p {{
            color: {NAVY} !important;
            font-weight: 700 !important;
        }}
        section[data-testid="stSidebar"] div[role="radiogroup"] label[data-baseweb="radio"] p {{
            font-size: 0.88rem !important;
            color: {TEXT_SECONDARY} !important;
            font-weight: 500 !important;
            margin: 0 !important;
        }}

        .sidebar-section-label {{
            font-size: 0.78rem;
            font-weight: 700;
            color: {MUTED};
            margin: 0.9rem 0 0.45rem 0;
            letter-spacing: 0;
        }}

        /* Clean RTL styling for Streamlit select/multiselect/checkbox */
        [data-baseweb="select"] > div {{
            direction: rtl !important;
            text-align: right !important;
            border-radius: 8px !important;
            border-color: #d7dfe8 !important;
            background-color: #fafbfd !important;
            font-size: 0.84rem !important;
        }}
        span[data-baseweb="tag"] {{
            background-color: #e8eff6 !important;
            color: {NAVY} !important;
            border: 1px solid #cedbe8 !important;
            border-radius: 6px !important;
            font-size: 0.78rem !important;
            font-weight: 600 !important;
        }}
        span[data-baseweb="tag"] span,
        span[data-baseweb="tag"] svg {{
            color: {NAVY} !important;
            fill: {NAVY} !important;
        }}
        [data-testid="stWidgetLabel"] p {{
            font-size: 0.82rem !important;
            font-weight: 600 !important;
            color: {TEXT_PRIMARY} !important;
            text-align: right !important;
        }}
        /* Hide default Latin slider min/max labels; we render clean Persian range caption instead */
        [data-testid="stSliderTickBarMin"],
        [data-testid="stSliderTickBarMax"],
        [data-testid="stThumbValue"] {{
            display: none !important;
        }}
        .year-pill-row {{
            display: flex;
            justify-content: space-between;
            font-size: 0.78rem;
            color: {TEXT_SECONDARY};
            margin-top: -0.35rem;
            margin-bottom: 0.55rem;
            direction: rtl !important;
        }}
        .year-pill {{
            background: #eef3f8;
            color: {NAVY};
            padding: 0.12rem 0.5rem;
            border-radius: 6px;
            font-weight: 600;
        }}

        /* 5. Natural Executive Page Header (clean surface, right-anchored) */
        .page-header {{
            background: {CARD_BG};
            border: 1px solid {BORDER_COLOR};
            border-right: 4px solid {NAVY};
            border-radius: 12px;
            padding: 1.05rem 1.35rem;
            margin-bottom: 1rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 0.75rem;
            box-shadow: 0 1px 2px rgba(16, 24, 40, 0.035);
            direction: rtl !important;
        }}
        .page-header-main {{
            text-align: right !important;
            direction: rtl !important;
        }}
        .page-title {{
            font-size: 1.32rem !important;
            font-weight: 700 !important;
            color: {NAVY} !important;
            margin: 0 !important;
            line-height: 1.35 !important;
            text-align: right !important;
        }}
        .page-subtitle {{
            font-size: 0.84rem !important;
            color: {TEXT_SECONDARY} !important;
            margin-top: 0.22rem !important;
            text-align: right !important;
        }}
        .page-meta {{
            display: flex;
            align-items: center;
            gap: 0.65rem;
            flex-wrap: wrap;
            direction: rtl !important;
        }}
        .meta-chip {{
            background: #f4f7fb;
            border: 1px solid #dce4ee;
            color: {TEXT_PRIMARY};
            padding: 0.34rem 0.78rem;
            border-radius: 8px;
            font-size: 0.8rem;
            font-weight: 500;
        }}
        .meta-chip strong {{
            color: {NAVY};
            font-weight: 700;
        }}
        .meta-chip.accent {{
            background: #fef9eb;
            border-color: #f3d47c;
            color: #6b4b00;
        }}

        /* 6. Refined, Natural KPI Cards (strictly right-aligned) */
        .kpi-card {{
            background: {CARD_BG};
            border: 1px solid {BORDER_COLOR};
            border-radius: 12px;
            padding: 1rem 1.15rem;
            box-shadow: 0 1px 2px rgba(16, 24, 40, 0.035);
            min-height: 114px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            direction: rtl !important;
            text-align: right !important;
            position: relative;
        }}
        .kpi-card::before {{
            content: "";
            position: absolute;
            top: 14px;
            bottom: 14px;
            right: 0;
            width: 3.5px;
            border-radius: 4px 0 0 4px;
            background-color: {NAVY};
        }}
        .kpi-card.gold-accent::before {{
            background-color: {GOLD};
        }}
        .kpi-label {{
            font-size: 0.82rem !important;
            color: {TEXT_SECONDARY} !important;
            font-weight: 500 !important;
            text-align: right !important;
            margin-bottom: 0.32rem !important;
        }}
        .kpi-value {{
            font-size: 1.44rem !important;
            font-weight: 700 !important;
            color: {TEXT_PRIMARY} !important;
            line-height: 1.3 !important;
            text-align: right !important;
        }}
        .kpi-note {{
            font-size: 0.76rem !important;
            color: {MUTED} !important;
            margin-top: 0.3rem !important;
            text-align: right !important;
            line-height: 1.45 !important;
        }}

        /* 7. Quiet Editorial Methodological Note (replaces loud yellow alert) */
        .editorial-note {{
            background: #fbfaf6;
            border: 1px solid #ebe2c5;
            border-right: 3.5px solid {GOLD};
            border-radius: 10px;
            padding: 0.72rem 1.05rem;
            margin: 0.85rem 0 1.05rem 0;
            font-size: 0.83rem !important;
            color: #443c2a !important;
            line-height: 1.75 !important;
            direction: rtl !important;
            text-align: right !important;
        }}
        .editorial-note strong {{
            color: {NAVY};
        }}
        .editorial-info {{
            background: #f5f8fc;
            border: 1px solid #dce6f2;
            border-right: 3.5px solid {NAVY};
            border-radius: 10px;
            padding: 0.78rem 1.1rem;
            margin: 0.8rem 0 1rem 0;
            font-size: 0.84rem !important;
            color: {TEXT_PRIMARY} !important;
            line-height: 1.8 !important;
            direction: rtl !important;
            text-align: right !important;
        }}

        /* 8. Unified Chart Card Header (native HTML RTL above Plotly canvas) */
        .chart-header {{
            background: {CARD_BG};
            border: 1px solid {BORDER_COLOR};
            border-bottom: none;
            border-radius: 12px 12px 0 0;
            padding: 0.88rem 1.15rem 0.2rem 1.15rem;
            direction: rtl !important;
            text-align: right !important;
            margin-top: 0.2rem;
        }}
        .chart-title {{
            font-size: 0.96rem !important;
            font-weight: 700 !important;
            color: {NAVY} !important;
            margin: 0 !important;
            text-align: right !important;
            line-height: 1.4 !important;
        }}
        .chart-sub {{
            font-size: 0.77rem !important;
            color: {MUTED} !important;
            margin-top: 0.14rem !important;
            text-align: right !important;
        }}

        /* Seamlessly attach Plotly container beneath .chart-header */
        div[data-testid="stPlotlyChart"] {{
            background: {CARD_BG};
            border: 1px solid {BORDER_COLOR};
            border-top: none;
            border-radius: 0 0 12px 12px;
            padding: 0.1rem 0.5rem 0.45rem 0.5rem;
            box-shadow: 0 1px 2px rgba(16, 24, 40, 0.035);
            margin-top: -1rem !important;
            margin-bottom: 0.85rem !important;
        }}

        /* Section Heading */
        .section-heading {{
            margin: 1.1rem 0 0.6rem 0;
            padding-bottom: 0.35rem;
            border-bottom: 1px solid {BORDER_COLOR};
            direction: rtl !important;
            text-align: right !important;
        }}
        .section-heading-title {{
            font-size: 1rem !important;
            font-weight: 700 !important;
            color: {NAVY} !important;
            text-align: right !important;
        }}
        .section-heading-sub {{
            font-size: 0.78rem !important;
            color: {MUTED} !important;
            margin-top: 0.12rem !important;
            text-align: right !important;
        }}

        /* Wave Comparison Card */
        .wave-card {{
            background: {CARD_BG};
            border: 1px solid {BORDER_COLOR};
            border-radius: 12px;
            padding: 1rem 1.15rem;
            box-shadow: 0 1px 2px rgba(16, 24, 40, 0.035);
            direction: rtl !important;
            text-align: right !important;
            height: 100%;
        }}
        .wave-card.w2 {{
            border-right: 3.5px solid {GOLD};
        }}
        .wave-card.w1 {{
            border-right: 3.5px solid {NAVY};
        }}
        .wave-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.65rem;
            padding-bottom: 0.45rem;
            border-bottom: 1px solid #edf2f7;
        }}
        .wave-title {{
            font-size: 0.94rem !important;
            font-weight: 700 !important;
            color: {NAVY} !important;
        }}
        .wave-tag {{
            font-size: 0.74rem;
            background: #f1f5f9;
            color: {TEXT_SECONDARY};
            padding: 0.14rem 0.5rem;
            border-radius: 6px;
            font-weight: 600;
        }}
        .wave-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.42rem 0;
            border-bottom: 1px dashed #edf2f7;
            font-size: 0.84rem;
        }}
        .wave-row:last-child {{
            border-bottom: none;
            padding-bottom: 0;
        }}
        .wave-row span {{
            color: {TEXT_SECONDARY};
        }}
        .wave-row strong {{
            color: {TEXT_PRIMARY};
            font-weight: 700;
        }}

        /* 9. Clean Native RTL Persian Tables */
        .rtl-table-wrap {{
            background: {CARD_BG};
            border: 1px solid {BORDER_COLOR};
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 1px 2px rgba(16, 24, 40, 0.035);
            margin-bottom: 1rem;
            direction: rtl !important;
        }}
        .rtl-table-scroll {{
            max-height: 380px;
            overflow-y: auto;
            direction: rtl !important;
        }}
        table.rtl-table {{
            width: 100%;
            border-collapse: collapse;
            direction: rtl !important;
            text-align: right !important;
            font-size: 0.84rem;
        }}
        table.rtl-table thead th {{
            position: sticky;
            top: 0;
            background: #f4f7fb;
            color: {NAVY};
            font-weight: 700;
            padding: 0.68rem 0.9rem;
            border-bottom: 1.5px solid #d7e1ec;
            text-align: right !important;
            white-space: nowrap;
            z-index: 2;
        }}
        table.rtl-table tbody td {{
            padding: 0.6rem 0.9rem;
            border-bottom: 1px solid #eef2f6;
            color: {TEXT_PRIMARY};
            text-align: right !important;
            white-space: nowrap;
        }}
        table.rtl-table tbody tr:hover {{
            background-color: #f8fafd;
        }}
        table.rtl-table tbody tr:last-child td {{
            border-bottom: none;
        }}
        .pill-dom {{
            background: #e9f0f7;
            color: {NAVY};
            padding: 0.14rem 0.55rem;
            border-radius: 6px;
            font-size: 0.76rem;
            font-weight: 600;
        }}
        .pill-for {{
            background: #fef5dc;
            color: #7c5200;
            padding: 0.14rem 0.55rem;
            border-radius: 6px;
            font-size: 0.76rem;
            font-weight: 600;
        }}
        .pill-unk {{
            background: #f1f5f9;
            color: #64748b;
            padding: 0.14rem 0.55rem;
            border-radius: 6px;
            font-size: 0.76rem;
            font-weight: 500;
        }}

        .sidebar-footer {{
            margin-top: 1.1rem;
            padding-top: 0.75rem;
            border-top: 1px solid {BORDER_COLOR};
            font-size: 0.74rem;
            color: {MUTED};
            line-height: 1.75;
            direction: rtl !important;
            text-align: right !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# UI Building Blocks & Centralized Plotly Styling (Owns ALL Margins)
# ---------------------------------------------------------------------------
def chart_header(title: str, subtitle: str = "") -> None:
    sub_html = f'<div class="chart-sub">{html.escape(subtitle)}</div>' if subtitle else ""
    st.markdown(
        f"""
        <div class="chart-header">
            <div class="chart-title">{html.escape(title)}</div>
            {sub_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def style_fig(
    fig: go.Figure,
    height: int = 360,
    left: int = 24,
    right: int = 105,
    top: int = 16,
    bottom: int = 44,
    show_legend: bool = False,
) -> go.Figure:
    """Centralized Plotly layout styling — single owner of chart margins."""
    fig.update_layout(
        font=dict(family="Vazirmatn FD, Tahoma, sans-serif", size=12, color=TEXT_PRIMARY),
        paper_bgcolor=CARD_BG,
        plot_bgcolor=CARD_BG,
        height=height,
        margin=dict(l=left, r=right, t=top, b=bottom),
        showlegend=show_legend,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.06,
            xanchor="center",
            x=0.5,
            font=dict(size=11.5, color=TEXT_SECONDARY),
        ),
        hoverlabel=dict(
            bgcolor="#ffffff",
            bordercolor=NAVY,
            font=dict(family="Vazirmatn FD, Tahoma, sans-serif", size=12, color=TEXT_PRIMARY),
        ),
    )
    fig.update_xaxes(
        showgrid=True,
        gridcolor="#eef2f6",
        zeroline=False,
        linecolor="#dce4ee",
        tickfont=dict(size=11.5, color=TEXT_SECONDARY),
        title_font=dict(size=11.5, color=MUTED),
    )
    fig.update_yaxes(
        showgrid=False,
        zeroline=False,
        linecolor="#dce4ee",
        tickfont=dict(size=12, color=TEXT_PRIMARY),
        title_font=dict(size=11.5, color=MUTED),
    )
    return fig


def render_kpi(label: str, value: str, note: str, gold: bool = False) -> None:
    cls = "kpi-card gold-accent" if gold else "kpi-card"
    st.markdown(
        f"""
        <div class="{cls}">
            <div>
                <div class="kpi-label">{html.escape(label)}</div>
                <div class="kpi-value">{html.escape(value)}</div>
            </div>
            <div class="kpi-note">{html.escape(note)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_rtl_table(headers: List[str], rows: List[List[str]], raw_html_cols: set[int] | None = None) -> None:
    raw_cols = raw_html_cols or set()
    ths = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body_rows = []
    for r in rows:
        tds = []
        for idx, cell in enumerate(r):
            content = cell if idx in raw_cols else html.escape(str(cell))
            tds.append(f"<td>{content}</td>")
        body_rows.append(f"<tr>{''.join(tds)}</tr>")
    st.markdown(
        f"""
        <div class="rtl-table-wrap">
            <div class="rtl-table-scroll">
                <table class="rtl-table">
                    <thead><tr>{ths}</tr></thead>
                    <tbody>{''.join(body_rows)}</tbody>
                </table>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def make_rtl_hbar(
    categories: List[str],
    values: List[float],
    colors: List[str],
    text_labels: List[str],
    x_title: str,
    x_mode: str = "count",
    x_range_mult: float = 1.32,
    height: int = 370,
    right_margin: int = 96,
    left_margin: int = 24,
) -> go.Figure:
    """Create a genuine RTL horizontal bar chart: labels on RIGHT, bars grow RIGHT->LEFT, Persian ticks."""
    max_v = float(max(values)) if len(values) else 10.0
    upper = max_v * x_range_mult
    if x_mode == "count":
        t_vals, t_txt = persian_count_ticks(max_v * 1.15, n_ticks=4)
    elif x_mode == "pct":
        t_vals, t_txt = [0, 25, 50, 75, 100], ["۰٪", "۲۵٪", "۵۰٪", "۷۵٪", "۱۰۰٪"]
        upper = 114.0
    else:
        t_vals, t_txt = persian_decimal_ticks(max_v * 1.12, n_ticks=4, suffix="")

    fig = go.Figure(
        go.Bar(
            x=values,
            y=[rtl_svg(c) for c in categories],
            orientation="h",
            marker=dict(color=colors, line=dict(width=0)),
            text=[f"{rtl_svg(t)}  " for t in text_labels],
            textposition="outside",
            textfont=dict(size=11.5, color=TEXT_PRIMARY),
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>%{text}<extra></extra>",
        )
    )
    fig.update_yaxes(side="right", ticklabelposition="outside")
    fig.update_xaxes(
        range=[upper, 0],  # Reversed: 0 on right, growing right -> left!
        tickmode="array",
        tickvals=t_vals,
        ticktext=t_txt,
        title_text=rtl_svg(x_title),
    )
    return style_fig(fig, height=height, left=left_margin, right=right_margin, top=14, bottom=44)


# ---------------------------------------------------------------------------
# Cached Data Loader & Filter Logic
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_star_schema() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict]:
    fact = pd.read_csv(
        PROCESSED_DIR / "fact_listing.csv",
        dtype={
            "listing_id": "int32",
            "date_key": "int32",
            "brand_key": "int16",
            "city_key": "int16",
            "price_irr": "int64",
            "gearbox": "category",
            "fuel_type": "category",
            "selling_method": "category",
            "body_condition": "category",
            "engine_condition": "category",
            "chassis_condition": "category",
            "color": "category",
        },
    )
    dim_brand = pd.read_csv(PROCESSED_DIR / "dim_brand.csv")
    dim_city = pd.read_csv(PROCESSED_DIR / "dim_city.csv")
    dim_date = pd.read_csv(PROCESSED_DIR / "dim_date.csv")
    with open(PROCESSED_DIR / "summary_stats.json", encoding="utf-8") as f:
        summary = json.load(f)

    wave_map = dict(zip(dim_date["date_key"], dim_date["scrape_wave_code"]))
    fact["scrape_wave_code"] = fact["date_key"].map(wave_map).astype("int8")
    return fact, dim_brand, dim_city, dim_date, summary


def apply_filters(
    fact: pd.DataFrame,
    dim_brand: pd.DataFrame,
    dim_city: pd.DataFrame,
    wave_choice: str,
    selected_cities: List[str],
    selected_brands: List[str],
    year_range: Tuple[int, int],
    include_null_year: bool,
    selected_gearboxes: List[str],
) -> pd.DataFrame:
    mask = pd.Series(True, index=fact.index)

    if wave_choice == "موج اول (پیش از ۱۴۰۲)":
        mask &= fact["scrape_wave_code"] == 1
    elif wave_choice == "موج دوم (۱۴۰۲ به بعد)":
        mask &= fact["scrape_wave_code"] == 2

    if selected_cities:
        c_keys = dim_city.loc[dim_city["city_name_fa"].isin(selected_cities), "city_key"]
        mask &= fact["city_key"].isin(c_keys)

    if selected_brands:
        b_keys = dim_brand.loc[dim_brand["brand_name_fa"].isin(selected_brands), "brand_key"]
        mask &= fact["brand_key"].isin(b_keys)

    y_min, y_max = year_range
    if y_min > 1366 or y_max < 1403 or not include_null_year:
        y_col = fact["model_year_jalali"]
        in_range = (y_col >= y_min) & (y_col <= y_max)
        if include_null_year:
            mask &= in_range | y_col.isna()
        else:
            mask &= in_range

    if selected_gearboxes and len(selected_gearboxes) < 3:
        mask &= fact["gearbox"].isin(selected_gearboxes)

    return fact.loc[mask]


# ---------------------------------------------------------------------------
# Page 1: نمای کلی بازار
# ---------------------------------------------------------------------------
def page_overview(
    df: pd.DataFrame,
    dim_brand: pd.DataFrame,
    dim_city: pd.DataFrame,
    summary: Dict,
) -> None:
    tehran_key = int(dim_city.loc[dim_city["city_slug"] == "tehran", "city_key"].iloc[0])
    tehran_count = int((df["city_key"] == tehran_key).sum())
    tehran_share = float(tehran_count / len(df) * 100) if len(df) else 0.0
    med_price = df["price_irr"].median() if len(df) else np.nan
    mean_price = df["price_irr"].mean() if len(df) else np.nan
    med_mileage = df["mileage_km"].median() if len(df) else np.nan
    med_age = df["car_age"].median() if len(df) else np.nan

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        render_kpi(
            "تعداد آگهی تمیز",
            fmt_int(len(df)),
            f"از مجموع {fmt_int(summary['clean_rows'])} آگهی پاک‌سازی‌شده",
        )
    with k2:
        render_kpi(
            "میانهٔ قیمت آگهی",
            fmt_bn_irr(med_price),
            f"میانگین: {fmt_bn_irr(mean_price)} (ریال آگهی)",
            gold=True,
        )
    with k3:
        render_kpi(
            "میانهٔ کارکرد خودرو",
            f"{fmt_int(med_mileage)} کیلومتر",
            f"میانهٔ سن در زمان ثبت آگهی: {fmt_int(med_age)} سال",
        )
    with k4:
        render_kpi(
            "سهم شهر تهران",
            fmt_pct(tehran_share),
            f"{fmt_int(tehran_count)} آگهی ثبت‌شده در تهران",
            gold=True,
        )

    st.markdown(
        """
        <div class="editorial-note">
            <strong>شفافیت روش‌شناختی:</strong>
            دادهٔ حاضر از <strong>دو موج اسکرپ مجزا</strong> (پیش از ۱۴۰۲ و ۱۴۰۲ به بعد) تشکیل شده و <strong>سری زمانی پیوسته نیست</strong>؛
            به‌همین دلیل هیچ نمودار «روند قیمت» یا «رشد بازار» در گزارش وجود ندارد. تمام مبالغ بر پایهٔ <strong>ریال آگهی</strong> (تومان × ۱۰) و قیمت پیشنهادی فروشنده هستند، نه قیمت قطعی معامله.
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Row 1: Top 10 Brands (RTL horizontal bar) + Gearbox Donut
    col_brands, col_gb = st.columns([1.45, 1.0])
    with col_brands:
        chart_header(
            "پرتکرارترین برندها در آگهی‌ها",
            "۱۰ برند نخست بر حسب تعداد آگهی (سرمه‌ای: داخلی • آبی: خارجی • طلایی: بیشترین فراوانی)",
        )
        b_vc = df["brand_key"].value_counts().head(10).reset_index()
        b_vc.columns = ["brand_key", "count"]
        b_vc = b_vc.merge(dim_brand[["brand_key", "brand_name_fa", "origin_type"]], on="brand_key", how="left")
        b_vc = b_vc.sort_values("count", ascending=True)
        top_b = b_vc["brand_name_fa"].iloc[-1] if len(b_vc) else ""
        b_colors = [
            GOLD if b == top_b else (NAVY if o == "داخلی" else (NAVY_SOFT if o == "خارجی" else "#94a3b8"))
            for b, o in zip(b_vc["brand_name_fa"], b_vc["origin_type"])
        ]
        fig_brands = make_rtl_hbar(
            categories=list(b_vc["brand_name_fa"]),
            values=list(b_vc["count"]),
            colors=b_colors,
            text_labels=[f"{fmt_int(v)} ({fmt_pct(v/len(df)*100)})" for v in b_vc["count"]],
            x_title="تعداد آگهی",
            x_mode="count",
            x_range_mult=1.35,
            height=370,
            right_margin=78,
        )
        st.plotly_chart(fig_brands, width="stretch", config={"displayModeBar": False})

    with col_gb:
        chart_header(
            "ترکیب نوع گیربکس",
            "سهم آگهی‌ها به تفکیک دنده‌ای، اتوماتیک و نامشخص",
        )
        gb_vc = df["gearbox"].value_counts()
        gb_labels = list(gb_vc.index)
        gb_vals = list(gb_vc.values)
        gb_colors = {"دنده‌ای": NAVY, "اتوماتیک": GOLD, "نامشخص": "#cbd5e1"}
        fig_gb = go.Figure(
            go.Pie(
                labels=gb_labels,
                values=gb_vals,
                hole=0.58,
                sort=False,
                marker=dict(colors=[gb_colors.get(k, SLATE) for k in gb_labels], line=dict(color="#ffffff", width=2)),
                text=[f"{lbl}<br>{fmt_pct(v/len(df)*100)}" for lbl, v in zip(gb_labels, gb_vals)],
                textinfo="text",
                textfont=dict(size=12, family="Vazirmatn FD, Tahoma, sans-serif"),
                hovertemplate="<b>%{label}</b><br>تعداد: %{value:,}<extra></extra>",
            )
        )
        style_fig(fig_gb, height=370, left=16, right=16, top=16, bottom=52, show_legend=True)
        st.plotly_chart(fig_gb, width="stretch", config={"displayModeBar": False})

    # Row 2: Top 10 Cities (RTL horizontal bar) + Median Price by Car Age
    col_cities, col_age = st.columns([1.15, 1.15])
    with col_cities:
        chart_header(
            "پرتکرارترین شهرها در آگهی‌ها",
            "۱۰ شهر نخست از نظر حجم عرضه (تمرکز بالای کلان‌شهرها)",
        )
        c_vc = df["city_key"].value_counts().head(10).reset_index()
        c_vc.columns = ["city_key", "count"]
        c_vc = c_vc.merge(dim_city[["city_key", "city_name_fa", "is_tehran"]], on="city_key", how="left")
        c_vc = c_vc.sort_values("count", ascending=True)
        fig_cities = make_rtl_hbar(
            categories=list(c_vc["city_name_fa"]),
            values=list(c_vc["count"]),
            colors=[GOLD if t else NAVY for t in c_vc["is_tehran"]],
            text_labels=[f"{fmt_int(v)} ({fmt_pct(v/len(df)*100)})" for v in c_vc["count"]],
            x_title="تعداد آگهی",
            x_mode="count",
            x_range_mult=1.38,
            height=360,
            right_margin=84,
        )
        st.plotly_chart(fig_cities, width="stretch", config={"displayModeBar": False})

    with col_age:
        chart_header(
            "میانهٔ قیمت آگهی بر حسب سن خودرو",
            "خودروهای صفر تا ۲۰ ساله در زمان ثبت آگهی (میلیارد ریال)",
        )
        ov_age = (
            df.dropna(subset=["car_age"])
            .loc[lambda d: d["car_age"] <= 20]
            .groupby("car_age", as_index=False)
            .agg(median_price=("price_irr", "median"))
        )
        ov_age["median_bn"] = ov_age["median_price"] / 1_000_000_000
        max_bn = float(ov_age["median_bn"].max()) if len(ov_age) else 10.0
        yt_vals, yt_txt = persian_decimal_ticks(max_bn * 1.15, n_ticks=5)
        age_x_vals = [0, 5, 10, 15, 20]
        fig_age = go.Figure(
            go.Bar(
                x=ov_age["car_age"],
                y=ov_age["median_bn"],
                marker_color=[GOLD if a <= 2 else NAVY_MID for a in ov_age["car_age"]],
                text=[f"{v:.1f}".replace(".", "٫").translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")) if a % 2 == 0 else "" for a, v in zip(ov_age["car_age"], ov_age["median_bn"])],
                textposition="outside",
                textfont=dict(size=10.5, color=TEXT_SECONDARY),
                cliponaxis=False,
                hovertemplate="سن: %{x} سال<br>میانهٔ قیمت: %{y:.2f} میلیارد ریال<extra></extra>",
            )
        )
        fig_age.update_xaxes(
            title_text="سن خودرو (سال)",
            autorange="reversed",
            tickmode="array",
            tickvals=age_x_vals,
            ticktext=[fmt_int(v) for v in age_x_vals],
        )
        fig_age.update_yaxes(
            side="right",
            title_text="میلیارد ریال",
            showgrid=True,
            gridcolor="#eef2f6",
            range=[0, max_bn * 1.2],
            tickmode="array",
            tickvals=yt_vals,
            ticktext=yt_txt,
        )
        style_fig(fig_age, height=360, left=18, right=56, top=14, bottom=44)
        st.plotly_chart(fig_age, width="stretch", config={"displayModeBar": False})

    # Row 3: Two Scrape Waves (Descriptive, Unadjusted) + Origin Mix
    st.markdown(
        """
        <div class="section-heading">
            <div class="section-heading-title">مقایسهٔ توصیفی دو موج اسکرپ و ترکیب مبدا برند</div>
            <div class="section-heading-sub">مقایسهٔ زیر صرفاً توصیفی و بدون تعدیل ترکیب خودرو (مدل، برند، سن و تورم) است و بیانگر روند زمانی قیمت نیست.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    w1 = df.loc[df["scrape_wave_code"] == 1]
    w2 = df.loc[df["scrape_wave_code"] == 2]
    wc1, wc2, wc3 = st.columns([1.0, 1.0, 1.3])
    with wc1:
        st.markdown(
            f"""
            <div class="wave-card w1">
                <div class="wave-header">
                    <span class="wave-title">موج اول (پیش از ۱۴۰۲)</span>
                    <span class="wave-tag">پنجرهٔ اول اسکرپ</span>
                </div>
                <div class="wave-row"><span>تعداد آگهی</span><strong>{fmt_int(len(w1))}</strong></div>
                <div class="wave-row"><span>سهم از نمای فعلی</span><strong>{fmt_pct(len(w1)/len(df)*100 if len(df) else 0)}</strong></div>
                <div class="wave-row"><span>میانهٔ قیمت آگهی</span><strong>{fmt_bn_irr(w1['price_irr'].median() if len(w1) else np.nan)}</strong></div>
                <div class="wave-row"><span>میانهٔ کارکرد</span><strong>{fmt_int(w1['mileage_km'].median() if len(w1) else np.nan)} کیلومتر</strong></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with wc2:
        st.markdown(
            f"""
            <div class="wave-card w2">
                <div class="wave-header">
                    <span class="wave-title">موج دوم (۱۴۰۲ به بعد)</span>
                    <span class="wave-tag">پنجرهٔ دوم اسکرپ</span>
                </div>
                <div class="wave-row"><span>تعداد آگهی</span><strong>{fmt_int(len(w2))}</strong></div>
                <div class="wave-row"><span>سهم از نمای فعلی</span><strong>{fmt_pct(len(w2)/len(df)*100 if len(df) else 0)}</strong></div>
                <div class="wave-row"><span>میانهٔ قیمت آگهی</span><strong>{fmt_bn_irr(w2['price_irr'].median() if len(w2) else np.nan)}</strong></div>
                <div class="wave-row"><span>میانهٔ کارکرد</span><strong>{fmt_int(w2['mileage_km'].median() if len(w2) else np.nan)} کیلومتر</strong></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with wc3:
        chart_header(
            "سهم آگهی‌ها بر حسب مبدا برند",
            "داخلی، خارجی (وارداتی/مونتاژی) و نامشخص (ردهٔ سایر)",
        )
        origin_map = dict(zip(dim_brand["brand_key"], dim_brand["origin_type"]))
        orig_vc = df["brand_key"].map(origin_map).value_counts().reset_index()
        orig_vc.columns = ["origin_type", "count"]
        orig_vc = orig_vc.sort_values("count", ascending=True)
        orig_colors = {"داخلی": NAVY, "خارجی": GOLD, "نامشخص": "#94a3b8"}
        fig_orig = make_rtl_hbar(
            categories=list(orig_vc["origin_type"]),
            values=list(orig_vc["count"]),
            colors=[orig_colors.get(o, SLATE) for o in orig_vc["origin_type"]],
            text_labels=[f"{fmt_int(v)} ({fmt_pct(v/len(df)*100)})" for v in orig_vc["count"]],
            x_title="تعداد آگهی",
            x_mode="count",
            x_range_mult=1.38,
            height=195,
            right_margin=84,
        )
        st.plotly_chart(fig_orig, width="stretch", config={"displayModeBar": False})


# ---------------------------------------------------------------------------
# Page 2: تحلیل برند و سازنده
# ---------------------------------------------------------------------------
def page_brands(df: pd.DataFrame, dim_brand: pd.DataFrame) -> None:
    grp = (
        df.groupby("brand_key", observed=True)
        .agg(
            listings=("listing_id", "count"),
            median_price_irr=("price_irr", "median"),
            median_mileage=("mileage_km", "median"),
            median_age=("car_age", "median"),
            auto_share=("gearbox", lambda s: float((s == "اتوماتیک").mean() * 100)),
        )
        .reset_index()
        .merge(dim_brand, on="brand_key", how="left")
        .sort_values("listings", ascending=False)
    )
    grp["share_pct"] = grp["listings"] / len(df) * 100
    grp["median_bn"] = grp["median_price_irr"] / 1_000_000_000

    dom_mask = df["brand_key"].isin(grp.loc[grp["origin_type"] == "داخلی", "brand_key"])
    for_mask = df["brand_key"].isin(grp.loc[grp["origin_type"] == "خارجی", "brand_key"])

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        render_kpi("برندهای فعال در نما", fmt_int(len(grp)), "از ۴۱ برند (۴۰ برند نام‌دار + سایر)")
    with k2:
        render_kpi(
            "سهم برندهای داخلی",
            fmt_pct(dom_mask.mean() * 100),
            f"میانهٔ قیمت: {fmt_bn_irr(df.loc[dom_mask, 'price_irr'].median() if dom_mask.any() else np.nan)}",
        )
    with k3:
        render_kpi(
            "سهم برندهای خارجی",
            fmt_pct(for_mask.mean() * 100),
            f"میانهٔ قیمت: {fmt_bn_irr(df.loc[for_mask, 'price_irr'].median() if for_mask.any() else np.nan)}",
            gold=True,
        )
    with k4:
        other_share = float(grp.loc[grp["brand_name_fa"] == "سایر", "share_pct"].sum())
        render_kpi(
            "سهم ردهٔ «سایر»",
            fmt_pct(other_share),
            "آگهی‌های فاقد برند خام یا برندهای کم‌تکرار",
        )

    c1, c2 = st.columns(2)
    with c1:
        chart_header(
            "میانهٔ قیمت آگهی در ۱۵ برند پرتکرار",
            "سرمه‌ای: برند داخلی • طلایی: برند خارجی/مونتاژی (میلیارد ریال)",
        )
        top15 = grp.loc[grp["brand_name_fa"] != "سایر"].head(15).sort_values("median_bn", ascending=True)
        fig_med = make_rtl_hbar(
            categories=list(top15["brand_name_fa"]),
            values=list(top15["median_bn"]),
            colors=[NAVY if o == "داخلی" else GOLD for o in top15["origin_type"]],
            text_labels=[fmt_short_bn(v * 1_000_000_000, 2) for v in top15["median_bn"]],
            x_title="میانهٔ قیمت آگهی (میلیارد ریال)",
            x_mode="decimal",
            x_range_mult=1.28,
            height=440,
            right_margin=86,
        )
        st.plotly_chart(fig_med, width="stretch", config={"displayModeBar": False})

    with c2:
        chart_header(
            "جایگاه برندها: حجم عرضه در برابر میانهٔ قیمت",
            "برندهای دارای حداقل ۵۰۰ آگهی (محور افقی لگاریتمی)",
        )
        sc = grp.loc[(grp["brand_name_fa"] != "سایر") & (grp["listings"] >= 500)]
        fig_sc = go.Figure()
        for origin, color in [("داخلی", NAVY), ("خارجی", GOLD)]:
            sub_o = sc.loc[sc["origin_type"] == origin]
            fig_sc.add_trace(
                go.Scatter(
                    x=sub_o["listings"],
                    y=sub_o["median_bn"],
                    mode="markers+text",
                    name=origin,
                    text=sub_o["brand_name_fa"],
                    textposition="top center",
                    textfont=dict(size=10.5, color=TEXT_PRIMARY),
                    marker=dict(
                        size=np.clip(np.sqrt(sub_o["listings"]) * 0.23, 9, 28),
                        color=color,
                        opacity=0.88,
                        line=dict(color="#ffffff", width=1.2),
                    ),
                    hovertemplate="<b>%{text}</b><br>آگهی: %{x:,}<br>میانهٔ قیمت: %{y:.2f} میلیارد ریال<extra></extra>",
                )
            )
        max_sc_y = float(sc["median_bn"].max()) if len(sc) else 30.0
        yt_v, yt_t = persian_decimal_ticks(max_sc_y * 1.15, n_ticks=5)
        fig_sc.update_xaxes(
            title_text=rtl_svg("تعداد آگهی (مقیاس لگاریتمی)"),
            type="log",
            tickmode="array",
            tickvals=[500, 1000, 3000, 10000, 30000, 100000],
            ticktext=[rtl_svg(t) for t in ["۵۰۰", "۱ هزار", "۳ هزار", "۱۰ هزار", "۳۰ هزار", "۱۰۰ هزار"]],
        )
        fig_sc.update_yaxes(
            side="right",
            title_text=rtl_svg("میلیارد ریال"),
            showgrid=True,
            gridcolor="#eef2f6",
            tickmode="array",
            tickvals=yt_v,
            ticktext=yt_t,
        )
        style_fig(fig_sc, height=440, left=22, right=58, top=36, bottom=48, show_legend=True)
        fig_sc.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0))
        st.plotly_chart(fig_sc, width="stretch", config={"displayModeBar": False})

    st.markdown(
        """
        <div class="section-heading">
            <div class="section-heading-title">جدول تفصیلی برندها و گروه‌های سازنده</div>
            <div class="section-heading-sub">مرتب‌شده بر اساس تعداد آگهی؛ تمام مبالغ بر پایهٔ ریال آگهی</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    rows = []
    for _, r in grp.iterrows():
        pill_cls = "pill-dom" if r["origin_type"] == "داخلی" else ("pill-for" if r["origin_type"] == "خارجی" else "pill-unk")
        origin_html = f'<span class="{pill_cls}">{html.escape(str(r["origin_type"]))}</span>'
        rows.append([
            str(r["brand_name_fa"]),
            origin_html,
            str(r["manufacturer_group"]),
            fmt_int(r["listings"]),
            fmt_pct(r["share_pct"], 2),
            fmt_bn_irr(r["median_price_irr"]),
            f"{fmt_int(r['median_mileage'])} کیلومتر",
            f"{fmt_int(r['median_age'])} سال",
            fmt_pct(r["auto_share"], 1),
        ])
    render_rtl_table(
        headers=["برند", "مبدا", "گروه سازنده", "تعداد آگهی", "سهم بازار", "میانهٔ قیمت آگهی", "میانهٔ کارکرد", "میانهٔ سن", "سهم اتوماتیک"],
        rows=rows,
        raw_html_cols={1},
    )


# ---------------------------------------------------------------------------
# Page 3: قیمت، سن و کارکرد
# ---------------------------------------------------------------------------
def page_price_age_mileage(df: pd.DataFrame) -> None:
    p25 = df["price_irr"].quantile(0.25)
    p50 = df["price_irr"].median()
    p75 = df["price_irr"].quantile(0.75)
    p90 = df["price_irr"].quantile(0.90)

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        render_kpi("چارک اول قیمت (۲۵٪)", fmt_bn_irr(p25), "یک‌چهارم آگهی‌ها پایین‌تر از این رقم")
    with k2:
        render_kpi("میانهٔ قیمت آگهی (۵۰٪)", fmt_bn_irr(p50), "معیار مقاوم در برابر داده‌های پرت", gold=True)
    with k3:
        render_kpi("چارک سوم قیمت (۷۵٪)", fmt_bn_irr(p75), f"دامنهٔ بین‌چارکی: {fmt_bn_irr(p75 - p25)}")
    with k4:
        render_kpi("صدک نهم قیمت (۹۰٪)", fmt_bn_irr(p90), "۱۰٪ گران‌ترین آگهی‌ها بالاتر از این سطح", gold=True)

    c1, c2 = st.columns(2)
    with c1:
        chart_header(
            "رابطهٔ سن خودرو با میانهٔ قیمت آگهی",
            "سن ۰ تا ۲۵ سال در زمان ثبت آگهی (میلیارد ریال)",
        )
        age_df = (
            df.dropna(subset=["car_age"])
            .loc[lambda d: d["car_age"] <= 25]
            .groupby("car_age", as_index=False)
            .agg(listings=("listing_id", "count"), median_price=("price_irr", "median"))
        )
        age_df["median_bn"] = age_df["median_price"] / 1_000_000_000
        max_bn = float(age_df["median_bn"].max()) if len(age_df) else 10.0
        yt_v, yt_t = persian_decimal_ticks(max_bn * 1.15, n_ticks=5)
        age_ticks = [0, 5, 10, 15, 20, 25]
        fig_age = go.Figure(
            go.Bar(
                x=age_df["car_age"],
                y=age_df["median_bn"],
                marker_color=[GOLD if a <= 2 else NAVY for a in age_df["car_age"]],
                text=[f"{v:.1f}".replace(".", "٫").translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")) if a % 3 == 0 else "" for a, v in zip(age_df["car_age"], age_df["median_bn"])],
                textposition="outside",
                textfont=dict(size=10.5, color=TEXT_SECONDARY),
                cliponaxis=False,
                hovertemplate="سن: %{x} سال<br>میانهٔ قیمت: %{y:.2f} میلیارد ریال<extra></extra>",
            )
        )
        fig_age.update_xaxes(
            title_text="سن خودرو (سال)",
            autorange="reversed",
            tickmode="array",
            tickvals=age_ticks,
            ticktext=[fmt_int(v) for v in age_ticks],
        )
        fig_age.update_yaxes(
            side="right",
            title_text="میلیارد ریال",
            showgrid=True,
            gridcolor="#eef2f6",
            range=[0, max_bn * 1.2],
            tickmode="array",
            tickvals=yt_v,
            ticktext=yt_t,
        )
        style_fig(fig_age, height=390, left=18, right=56, top=14, bottom=44)
        st.plotly_chart(fig_age, width="stretch", config={"displayModeBar": False})

    with c2:
        chart_header(
            "میانهٔ قیمت آگهی بر حسب بازهٔ کارکرد",
            "به‌همراه تعداد آگهی در هر بازهٔ کیلومتری",
        )
        m_valid = df.dropna(subset=["mileage_km"]).copy()
        bins = [-1, 0, 30_000, 80_000, 150_000, 250_000, 400_000, 2_500_000]
        labels = ["صفر کیلومتر", "۱ تا ۳۰ هزار", "۳۰ تا ۸۰ هزار", "۸۰ تا ۱۵۰ هزار", "۱۵۰ تا ۲۵۰ هزار", "۲۵۰ تا ۴۰۰ هزار", "بیش از ۴۰۰ هزار"]
        m_valid["mileage_bin"] = pd.cut(m_valid["mileage_km"], bins=bins, labels=labels)
        m_grp = (
            m_valid.groupby("mileage_bin", observed=False)
            .agg(listings=("listing_id", "count"), median_price=("price_irr", "median"))
            .reset_index()
        )
        m_grp["median_bn"] = m_grp["median_price"] / 1_000_000_000
        # Reverse so صفر کیلومتر sits at top
        m_grp = m_grp.iloc[::-1].reset_index(drop=True)
        fig_mil = make_rtl_hbar(
            categories=list(m_grp["mileage_bin"].astype(str)),
            values=list(m_grp["median_bn"].fillna(0)),
            colors=[GOLD if lb == "صفر کیلومتر" else NAVY_MID for lb in m_grp["mileage_bin"].astype(str)],
            text_labels=[f"{fmt_short_bn(p, 2)} ({fmt_int(n)})" for p, n in zip(m_grp["median_price"], m_grp["listings"])],
            x_title="میانهٔ قیمت آگهی (میلیارد ریال)",
            x_mode="decimal",
            x_range_mult=1.42,
            height=390,
            right_margin=118,
        )
        st.plotly_chart(fig_mil, width="stretch", config={"displayModeBar": False})

    c3, c4 = st.columns(2)
    with c3:
        chart_header(
            "میانهٔ قیمت بر حسب گیربکس",
            "مقایسهٔ توصیفی بدون کنترل برند و سال ساخت",
        )
        gb_grp = (
            df.groupby("gearbox", observed=True)
            .agg(listings=("listing_id", "count"), median_price=("price_irr", "median"))
            .reset_index()
        )
        gb_grp["median_bn"] = gb_grp["median_price"] / 1_000_000_000
        gb_grp = gb_grp.sort_values("median_bn", ascending=True)
        fig_gbp = make_rtl_hbar(
            categories=list(gb_grp["gearbox"].astype(str)),
            values=list(gb_grp["median_bn"]),
            colors=[GOLD if g == "اتوماتیک" else (NAVY if g == "دنده‌ای" else "#94a3b8") for g in gb_grp["gearbox"]],
            text_labels=[fmt_bn_irr(p) for p in gb_grp["median_price"]],
            x_title="میانهٔ قیمت آگهی (میلیارد ریال)",
            x_mode="decimal",
            x_range_mult=1.38,
            height=330,
            right_margin=76,
        )
        st.plotly_chart(fig_gbp, width="stretch", config={"displayModeBar": False})

    with c4:
        chart_header(
            "میانهٔ قیمت بر حسب وضعیت بدنه",
            "۸ وضعیت پرتکرار بدنه در آگهی‌ها",
        )
        body_grp = (
            df.groupby("body_condition", observed=True)
            .agg(listings=("listing_id", "count"), median_price=("price_irr", "median"))
            .reset_index()
            .sort_values("listings", ascending=False)
            .head(8)
        )
        body_grp["median_bn"] = body_grp["median_price"] / 1_000_000_000
        body_grp = body_grp.sort_values("median_bn", ascending=True)
        fig_body = make_rtl_hbar(
            categories=list(body_grp["body_condition"].astype(str)),
            values=list(body_grp["median_bn"]),
            colors=[NAVY if i >= len(body_grp) - 2 else NAVY_SOFT for i in range(len(body_grp))],
            text_labels=[fmt_short_bn(p, 2) for p in body_grp["median_price"]],
            x_title="میانهٔ قیمت آگهی (میلیارد ریال)",
            x_mode="decimal",
            x_range_mult=1.3,
            height=330,
            right_margin=128,
        )
        st.plotly_chart(fig_body, width="stretch", config={"displayModeBar": False})


# ---------------------------------------------------------------------------
# Page 4: شهرها
# ---------------------------------------------------------------------------
def page_cities(df: pd.DataFrame, dim_city: pd.DataFrame) -> None:
    c_grp = (
        df.groupby("city_key", observed=True)
        .agg(
            listings=("listing_id", "count"),
            median_price_irr=("price_irr", "median"),
            median_mileage=("mileage_km", "median"),
            median_age=("car_age", "median"),
        )
        .reset_index()
        .merge(dim_city, on="city_key", how="left")
        .sort_values("listings", ascending=False)
    )
    c_grp["share_pct"] = c_grp["listings"] / len(df) * 100
    c_grp["median_bn"] = c_grp["median_price_irr"] / 1_000_000_000

    tehran_row = c_grp.loc[c_grp["is_tehran"]]
    tehran_share = float(tehran_row["share_pct"].iloc[0]) if len(tehran_row) else 0.0
    tehran_med = float(tehran_row["median_price_irr"].iloc[0]) if len(tehran_row) else np.nan
    top5_share = float(c_grp.head(5)["share_pct"].sum())
    mapped_cov = float(c_grp.loc[c_grp["is_persian_mapped"], "share_pct"].sum())

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        render_kpi("شهرهای فعال در نما", fmt_int(len(c_grp)), "۹۰ شهر نگاشت فارسی + ۲۴۴ نام لاتین منبع")
    with k2:
        render_kpi("سهم کلان‌شهر تهران", fmt_pct(tehran_share), f"میانهٔ قیمت تهران: {fmt_bn_irr(tehran_med)}", gold=True)
    with k3:
        render_kpi("تمرکز ۵ شهر نخست", fmt_pct(top5_share), "تهران، مشهد، اصفهان، شیراز و کرج")
    with k4:
        render_kpi("پوشش نگاشت فارسی", fmt_pct(mapped_cov), "بدون ترجمهٔ حدسی برای شهرهای کم‌تکرار")

    col1, col2 = st.columns(2)
    with col1:
        chart_header(
            "۱۵ شهر برتر از نظر حجم آگهی",
            "تهران با رنگ طلایی متمایز شده است",
        )
        top15_c = c_grp.head(15).sort_values("listings", ascending=True)
        fig_cv = make_rtl_hbar(
            categories=list(top15_c["city_name_fa"]),
            values=list(top15_c["listings"]),
            colors=[GOLD if t else NAVY for t in top15_c["is_tehran"]],
            text_labels=[f"{fmt_int(v)} ({fmt_pct(s)})" for v, s in zip(top15_c["listings"], top15_c["share_pct"])],
            x_title="تعداد آگهی",
            x_mode="count",
            x_range_mult=1.38,
            height=450,
            right_margin=88,
        )
        st.plotly_chart(fig_cv, width="stretch", config={"displayModeBar": False})

    with col2:
        chart_header(
            "میانهٔ قیمت آگهی در ۱۵ شهر پرتکرار",
            "توصیفی و بدون تعدیل ترکیب برند و سن خودرو (میلیارد ریال)",
        )
        top15_p = c_grp.head(15).sort_values("median_bn", ascending=True)
        fig_cp = make_rtl_hbar(
            categories=list(top15_p["city_name_fa"]),
            values=list(top15_p["median_bn"]),
            colors=[GOLD if t else NAVY_MID for t in top15_p["is_tehran"]],
            text_labels=[fmt_short_bn(p, 2) for p in top15_p["median_price_irr"]],
            x_title="میانهٔ قیمت آگهی (میلیارد ریال)",
            x_mode="decimal",
            x_range_mult=1.28,
            height=450,
            right_margin=88,
        )
        st.plotly_chart(fig_cp, width="stretch", config={"displayModeBar": False})

    st.markdown(
        """
        <div class="editorial-info">
            <strong>شفافیت نام شهرها:</strong>
            ۹۰ شهر پرتکرار (پوشش حدود ۹۱٫۷٪ کل آگهی‌ها) با نام رسمی فارسی نگاشت شده‌اند.
            برای ۲۴۴ شهر دیگر، جهت پرهیز از خطای املایی یا ترجمهٔ حدسی، نام لاتین منبع پس از جایگزینی خط‌تیره با فاصله حفظ شده است.
        </div>
        """,
        unsafe_allow_html=True,
    )

    rows = []
    for _, r in c_grp.head(100).iterrows():
        rows.append([
            str(r["city_name_fa"]),
            str(r["city_tier"]),
            fmt_int(r["listings"]),
            fmt_pct(r["share_pct"], 2),
            fmt_bn_irr(r["median_price_irr"]),
            f"{fmt_int(r['median_mileage'])} کیلومتر",
            f"{fmt_int(r['median_age'])} سال",
        ])
    render_rtl_table(
        headers=["شهر", "ردهٔ شهری", "تعداد آگهی", "سهم بازار", "میانهٔ قیمت آگهی", "میانهٔ کارکرد", "میانهٔ سن"],
        rows=rows,
    )


# ---------------------------------------------------------------------------
# Page 5: دربارهٔ داده
# ---------------------------------------------------------------------------
def page_about(df: pd.DataFrame, summary: Dict) -> None:
    st.markdown(
        f"""
        <div class="editorial-info">
            <strong>شناسنامهٔ مجموعهٔ داده و پروژه:</strong><br>
            • نام «بازار خودروی ایران» صرفاً توصیفی است و هیچ وابستگی به هیچ شرکت، نمایشگاه یا نهاد واقعی ندارد.<br>
            • منبع دادهٔ واقعی: دیتاست عمومی Kaggle با شناسهٔ <code>arianghasemi/divar-cars</code> (نسخهٔ <strong>v5</strong>، فایل <code>final2024.csv</code>).<br>
            • بازهٔ اسنپ‌شات تمیز: <strong>{fa_digits(summary['date_min_jalali'])}</strong> تا <strong>{fa_digits(summary['date_max_jalali'])}</strong>
            ({summary['date_min_iso']} تا {summary['date_max_iso']}).<br>
            • وضعیت مجوز: در صفحهٔ Kaggle مجوز صریحی ثبت نشده است؛ استفاده در این پروژه صرفاً آموزشی و نمونه‌کار با انتساب کامل است و پیش از هرگونه استفادهٔ تجاری بررسی مجوز الزامی است.<br>
            • حریم خصوصی: ستون‌های هویتی و متنی آزاد (<code>id</code>، <code>title</code> و <code>Location</code>) در پایپ‌لاین ETL به‌طور کامل حذف شده‌اند.
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        chart_header(
            "شفافیت کیفیت ستون‌ها (نرخ خالی / نامشخص)",
            "ستون‌های ضعیف بدون پرکردن ساختگی و صرفاً به‌صورت توصیفی گزارش شده‌اند",
        )
        dq_items = [
            ("روش فروش (سایر/نامشخص)", summary["selling_method_other_share_pct"]),
            ("نوع سوخت (خالی)", summary["fuel_type_missing_pct"]),
            ("گیربکس (نامشخص)", summary["gearbox_unknown_share_pct"]),
            ("برند (ردهٔ سایر)", round(summary["origin_counts"]["نامشخص"] / summary["clean_rows"] * 100, 2)),
            ("سال مدل / سن (خالی یا قبل ۱۳۶۶)", summary["model_year_jalali"]["null_pct"]),
            ("کارکرد (خالی/نامعتبر)", summary["mileage_km"]["null_pct"]),
        ]
        dq_df = pd.DataFrame(dq_items, columns=["field", "pct"]).sort_values("pct", ascending=True)
        fig_dq = make_rtl_hbar(
            categories=list(dq_df["field"]),
            values=list(dq_df["pct"]),
            colors=["#b91c1c" if p > 35 else (GOLD if p > 10 else NAVY) for p in dq_df["pct"]],
            text_labels=[fmt_pct(p) for p in dq_df["pct"]],
            x_title="درصد نبود یا نامشخص بودن",
            x_mode="pct",
            x_range_mult=1.15,
            height=360,
            right_margin=196,
        )
        st.plotly_chart(fig_dq, width="stretch", config={"displayModeBar": False})

    with c2:
        chart_header(
            "توزیع نوع سوخت (صرفاً توصیفی)",
            "بیش از ۴۱ درصد آگهی‌ها فاقد مقدار نوع سوخت در دادهٔ منبع هستند",
        )
        fuel_vc = df["fuel_type"].astype(str).replace("nan", "نامشخص / خالی").value_counts().reset_index()
        fuel_vc.columns = ["fuel", "count"]
        fuel_vc = fuel_vc.sort_values("count", ascending=True)
        fig_fuel = make_rtl_hbar(
            categories=list(fuel_vc["fuel"]),
            values=list(fuel_vc["count"]),
            colors=["#94a3b8" if f == "نامشخص / خالی" else TEAL for f in fuel_vc["fuel"]],
            text_labels=[f"{fmt_int(v)} ({fmt_pct(v/len(df)*100)})" for v in fuel_vc["count"]],
            x_title="تعداد آگهی",
            x_mode="count",
            x_range_mult=1.38,
            height=360,
            right_margin=124,
        )
        st.plotly_chart(fig_fuel, width="stretch", config={"displayModeBar": False})

    st.markdown(
        """
        <div class="section-heading">
            <div class="section-heading-title">قیف پاک‌سازی رکوردها و محدودیت‌های اصلی</div>
            <div class="section-heading-sub">تمامی گام‌ها به‌صورت قطعی و بدون تصادف در scripts/build_data.py قابل بازتولید هستند</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    lim_c1, lim_c2 = st.columns([1.05, 1.15])
    with lim_c1:
        funnel_rows = [
            ["رکوردهای خام ورودی (final2024.csv)", fmt_int(summary["raw_rows"]), "۱۰۰٫۰٪"],
            ["حذف قیمت خالی", fmt_int(summary["price_drop_breakdown"]["null_price"]), "۳٫۲٪"],
            ["حذف قیمت صفر یا منفی", fmt_int(summary["price_drop_breakdown"]["zero_or_negative"]), "۲٫۱٪"],
            ["حذف قیمت زیر ۱۰ میلیون تومان", fmt_int(summary["price_drop_breakdown"]["below_10m_toman"]), "۰٫۴٪"],
            ["آگهی‌های تمیز نهایی (fact_listing)", fmt_int(summary["clean_rows"]), "۹۴٫۲٪"],
        ]
        render_rtl_table(["مرحلهٔ پایپ‌لاین", "تعداد ردیف", "سهم از خام"], funnel_rows)

    with lim_c2:
        st.markdown(
            """
            <div class="editorial-note" style="margin-top: 0;">
                <strong>محدودیت‌های کلیدی (خلاصهٔ LIMITATIONS.md):</strong><br>
                ۱. <strong>آگهی ≠ معامله:</strong> قیمت‌ها رقم پیشنهادی فروشنده هستند و بیانگر قیمت قطعی معامله نیستند.<br>
                ۲. <strong>دو موج ≠ سری زمانی:</strong> تمرکز برداشت در دو پنجرهٔ مجزا (پیش از ۱۴۰۲ و ۱۴۰۲+) اجازهٔ ادعای روند قیمت نمی‌دهد.<br>
                ۳. <strong>تبدیل سادهٔ ریال:</strong> <code>price_irr = تومان × ۱۰</code> بدون نرخ تسعیر ارز و بدون تعدیل تورم ۱۴۰۰ تا ۱۴۰۳.<br>
                ۴. <strong>ستون‌های ضعیف:</strong> <code>selling_method</code> در ۸۹٫۳٪ و <code>fuel_type</code> در ۴۱٫۱٪ ردیف‌ها نامشخص یا خالی است.<br>
                ۵. <strong>فاقد فایل .pbix:</strong> تمام اجزای Power BI (مدل، DAX، تم و راهنمای ساخت) به‌صورت متن‌باز ارائه شده‌اند.
            </div>
            """,
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Main Application Entrypoint
# ---------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(
        page_title="بازار خودروی ایران — تحلیل آگهی‌های دیوار",
        page_icon="🚗",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_theme_css()

    fact, dim_brand, dim_city, dim_date, summary = load_star_schema()

    with st.sidebar:
        st.markdown(
            """
            <div class="brand-lockup">
                <div class="brand-lockup-top">
                    <div class="brand-dot"></div>
                    <div class="brand-name">بازار خودروی ایران</div>
                </div>
                <div class="brand-desc">تحلیل آگهی‌های دیوار • نمونه‌کار Power BI</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown('<div class="sidebar-section-label">بخش‌های گزارش</div>', unsafe_allow_html=True)
        selected_page = st.radio(
            "صفحهٔ گزارش",
            PAGES,
            index=0,
            label_visibility="collapsed",
        )

        st.markdown('<div class="sidebar-section-label" style="margin-top:1.1rem;padding-top:0.75rem;border-top:1px solid #e4e9f0;">فیلترهای تحلیلی</div>', unsafe_allow_html=True)

        wave_choice = st.selectbox(
            "موج اسکرپ",
            ["همهٔ موج‌ها", "موج دوم (۱۴۰۲ به بعد)", "موج اول (پیش از ۱۴۰۲)"],
            index=0,
        )

        selected_cities = st.multiselect(
            "شهر",
            options=list(dim_city["city_name_fa"]),
            default=[],
            placeholder="همهٔ شهرها (جست‌وجو یا انتخاب)",
        )

        selected_brands = st.multiselect(
            "برند",
            options=list(dim_brand["brand_name_fa"]),
            default=[],
            placeholder="همهٔ برندها (جست‌وجو یا انتخاب)",
        )

        year_range = st.slider(
            "بازهٔ سال مدل (شمسی)",
            min_value=1366,
            max_value=1403,
            value=(1366, 1403),
            step=1,
        )
        st.markdown(
            f"""
            <div class="year-pill-row">
                <span>از سال <span class="year-pill">{fa_digits(year_range[0])}</span></span>
                <span>تا سال <span class="year-pill">{fa_digits(year_range[1])}</span></span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        include_null_year = st.checkbox("شامل آگهی‌های فاقد سال مدل یا قبل از ۱۳۶۶", value=True)

        selected_gearboxes = st.multiselect(
            "نوع گیربکس",
            options=["دنده‌ای", "اتوماتیک", "نامشخص"],
            default=["دنده‌ای", "اتوماتیک", "نامشخص"],
            placeholder="انتخاب نوع گیربکس",
        )

        st.markdown(
            f"""
            <div class="sidebar-footer">
                اسنپ‌شات داده: <strong>{fa_digits(summary['snapshot_jalali'])}</strong><br>
                منبع: Kaggle (arianghasemi/divar-cars v5)<br>
                تم: Iran Car Market Fa • آفلاین (صفر درخواست خارجی)
            </div>
            """,
            unsafe_allow_html=True,
        )

    filtered = apply_filters(
        fact=fact,
        dim_brand=dim_brand,
        dim_city=dim_city,
        wave_choice=wave_choice,
        selected_cities=selected_cities,
        selected_brands=selected_brands,
        year_range=year_range,
        include_null_year=include_null_year,
        selected_gearboxes=selected_gearboxes,
    )

    # Clean, Natural Executive Page Header
    st.markdown(
        f"""
        <div class="page-header">
            <div class="page-header-main">
                <div class="page-title">{html.escape(selected_page)}</div>
                <div class="page-subtitle">تحلیل {fmt_int(summary['clean_rows'])} آگهی پاک‌سازی‌شدهٔ دیوار • مدل ستاره‌ای Power BI (واحد: ریال آگهی)</div>
            </div>
            <div class="page-meta">
                <span class="meta-chip accent">اسنپ‌شات داده: <strong>{fa_digits(summary['snapshot_jalali'])}</strong></span>
                <span class="meta-chip">آگهی‌های نمای فعلی: <strong>{fmt_int(len(filtered))}</strong></span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if len(filtered) == 0 and selected_page != "دربارهٔ داده":
        st.warning("با ترکیب فیلترهای انتخاب‌شده هیچ آگهی‌ای یافت نشد. لطفاً محدودهٔ فیلترها را گسترده‌تر کنید.")
        return

    if selected_page == PAGES[0]:
        page_overview(filtered, dim_brand, dim_city, summary)
    elif selected_page == PAGES[1]:
        page_brands(filtered, dim_brand)
    elif selected_page == PAGES[2]:
        page_price_age_mileage(filtered)
    elif selected_page == PAGES[3]:
        page_cities(filtered, dim_city)
    else:
        page_about(filtered, summary)


if __name__ == "__main__":
    main()
