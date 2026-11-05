"""두 화면이 같이 쓰는 화면 꾸밈. 색과 글꼴의 기본값은 .streamlit/config.toml의 [theme]에 있다."""

from __future__ import annotations

import streamlit as st

INK = "#18222B"
SEA = "#0E6C73"
MUTED = "#5E6A72"
CHEAP = "#23875A"
PRICEY = "#C65A1E"

_CSS = f"""
<style>
[data-testid="stMainBlockContainer"] {{ max-width: 1360px; }}
h1 {{ letter-spacing: -0.02em; }}
[data-testid="stHeading"] h1 {{ font-size: 1.75rem; padding-bottom: 0; }}
[data-testid="stMetric"] {{ padding: 0; }}
[data-testid="stMetricLabel"] p {{ font-size: 0.82rem; color: {MUTED}; }}
[data-testid="stMetricValue"] {{ font-variant-numeric: tabular-nums; letter-spacing: -0.01em; }}

.rc {{ line-height: 1.35; }}
.rc-price {{ font-size: 1.2rem; font-weight: 800; color: {INK}; font-variant-numeric: tabular-nums;
  letter-spacing: -0.01em; }}
.rc-sub {{ font-size: 0.9rem; color: {INK}; margin-top: 2px; }}
.rc-name {{ font-size: 0.95rem; font-weight: 600; color: {INK}; margin-top: 6px; }}
.rc-meta {{ font-size: 0.82rem; color: {MUTED}; margin-top: 2px; }}
.rc-cmp {{ display: inline-block; font-size: 0.75rem; font-weight: 700; padding: 1px 7px; border-radius: 999px;
  margin-left: 6px; vertical-align: 3px; }}
.rc-cmp.cheap {{ color: {CHEAP}; background: #E3F2EA; }}
.rc-cmp.pricey {{ color: {PRICEY}; background: #F8E9DF; }}
.rc-cmp.neutral {{ color: {MUTED}; background: #ECEFEE; }}

.rd-price {{ font-size: 2rem; font-weight: 800; color: {INK}; font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em; line-height: 1.15; }}
.rd-name {{ font-size: 1.05rem; font-weight: 700; color: {INK}; margin-top: 4px; }}
.rd-meta {{ font-size: 0.85rem; color: {MUTED}; margin-top: 2px; }}

@media (max-width: 640px) {{
  [data-testid="stHeading"] h1 {{ font-size: 1.45rem; }}
  [data-testid="stMetricValue"] {{ font-size: 1.15rem; }}
  [data-testid="stMetricLabel"] p {{ font-size: 0.72rem; }}
  [data-testid="stPopover"] button {{ padding: 0.2rem 0.6rem; min-height: 2.1rem; }}
}}

.legend {{ display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 0.8rem; color: {MUTED}; }}
.legend i {{ display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 5px;
  vertical-align: -1px; }}
.legend i.cheap {{ background: {CHEAP}; }}
.legend i.pricey {{ background: {PRICEY}; }}
.legend i.neutral {{ background: #fff; border: 1.5px solid {INK}; }}
.legend i.transfer {{ background: #fff; border: 1.5px dashed {INK}; }}
.legend i.cluster {{ background: {SEA}; border-radius: 50%; }}
</style>
"""


def inject() -> None:
    st.html(_CSS)
