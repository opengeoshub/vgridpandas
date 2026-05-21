"""Shared helpers for DGGS bin aggregation."""

from collections import Counter

import pandas as pd


def value_col_name(stats, numeric_col, category_value=None):
    if category_value is not None:
        if str(category_value) == "NaN_category":
            category_value = "NaN"
        prefix = f"{category_value}_"
    else:
        prefix = ""
    if numeric_col:
        return f"{prefix}{numeric_col}_{stats}"
    return f"{prefix}{stats}"


def aggregate_bin(
    df,
    dggs_col: str,
    stats: str,
    numeric_col: str = None,
    category_col: str = None,
):
    """Aggregate point rows by DGGS cell (and optional category)."""
    if category_col is not None and category_col not in df.columns:
        raise ValueError(f"Category column '{category_col}' not found in DataFrame")
    if numeric_col is not None and numeric_col not in df.columns:
        raise ValueError(f"Numeric column '{numeric_col}' not found in DataFrame")

    group_cols = [dggs_col]
    if category_col:
        df = df.copy()
        df[category_col] = df[category_col].fillna("NaN_category")
        group_cols.append(category_col)

    if stats == "count":
        result = (
            df.groupby(group_cols)
            .size()
            .reset_index(name=value_col_name(stats, numeric_col))
        )

    elif stats in ["sum", "min", "max", "mean", "median", "std", "var"]:
        if not numeric_col:
            raise ValueError(f"numeric_col must be provided for stats='{stats}'")
        result = (
            df.groupby(group_cols)[numeric_col]
            .agg(stats)
            .reset_index(name=value_col_name(stats, numeric_col))
        )

    elif stats == "range":
        if not numeric_col:
            raise ValueError(f"numeric_col must be provided for stats='{stats}'")
        result = df.groupby(group_cols)[numeric_col].agg(["min", "max"]).reset_index()
        result[value_col_name(stats, numeric_col)] = result["max"] - result["min"]
        result = result.drop(["min", "max"], axis=1)

    elif stats in ["minority", "majority", "variety"]:
        if not numeric_col:
            raise ValueError(f"numeric_col must be provided for stats='{stats}'")

        def cat_agg_func(x):
            values = x[numeric_col].dropna()
            freq = Counter(values)
            if not freq:
                return None
            if stats == "minority":
                return min(freq.items(), key=lambda y: y[1])[0]
            if stats == "majority":
                return max(freq.items(), key=lambda y: y[1])[0]
            return values.nunique()

        if category_col:
            all_categories = sorted([str(cat) for cat in df[category_col].unique()])
            result = (
                df.groupby([dggs_col, category_col])
                .apply(cat_agg_func, include_groups=False)
                .reset_index(name=value_col_name(stats, numeric_col))
            )
            result = result.pivot(
                index=dggs_col,
                columns=category_col,
                values=value_col_name(stats, numeric_col),
            )
            result = result.reindex(
                columns=all_categories, fill_value=0 if stats == "variety" else None
            )
            result = result.reset_index()
            result.columns = [dggs_col] + [
                value_col_name(stats, numeric_col, cat) for cat in all_categories
            ]
        else:
            result = (
                df.groupby([dggs_col])
                .apply(cat_agg_func, include_groups=False)
                .reset_index(name=value_col_name(stats, numeric_col))
            )
    else:
        raise ValueError(f"Unknown stats: {stats}")

    if category_col and stats not in ["minority", "majority", "variety"]:
        value_name = value_col_name(stats, numeric_col)
        if len(result) == 0:
            result = pd.DataFrame(columns=[dggs_col, category_col, value_name])
        else:
            try:
                result = result.pivot(
                    index=dggs_col, columns=category_col, values=value_name
                )
                numeric_cols = result.select_dtypes(include=["number"]).columns
                result[numeric_cols] = result[numeric_cols].fillna(0)
                result = result.reset_index()
                result.columns = [dggs_col] + [
                    value_col_name(stats, numeric_col, col)
                    for col in sorted(result.columns[1:])
                ]
            except Exception:
                result = (
                    df.groupby(dggs_col)
                    .size()
                    .reset_index(name=value_col_name(stats, numeric_col))
                )

    return result
