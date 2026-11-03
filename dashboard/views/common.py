"""Shared display helpers for dashboard views."""
from __future__ import annotations

import pandas as pd


def minutes(value: float | None) -> str:
    return "—" if value is None or pd.isna(value) else f"{value / 60:.1f} min"


def percentage(value: float | None) -> str:
    return "—" if value is None or pd.isna(value) else f"{value:.0%}"


def parse_thresholds(raw: str) -> tuple[int, ...]:
    values = tuple(sorted({int(item.strip()) for item in raw.split(",") if item.strip()}))
    if not values or any(value <= 0 for value in values):
        raise ValueError("Thresholds must be positive whole minutes.")
    return values


def styled_dataframe(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    return df.style.apply(
        lambda row: [
            "background-color: rgba(128, 128, 128, 0.08)" if row.name % 2 else ""
            for _ in row
        ],
        axis=1,
    )


def styled_comparison_dataframe(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    styler = styled_dataframe(df)
    highlight_style = "background-color: rgba(46, 160, 67, 0.15); font-weight: 600"
    for column in ("P50", "P90", "P95"):
        if column not in df.columns:
            continue
        values = pd.to_numeric(
            df[column].astype(str).str.extract(r"([\\d.]+)")[0], errors="coerce"
        )
        if values.notna().any():
            best_indices = values[values == values.min()].index
            styler = styler.map(
                lambda _: highlight_style,
                subset=pd.IndexSlice[best_indices, [column]],
            )
    return styler
