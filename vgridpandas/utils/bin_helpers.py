"""Shared helpers for DGGS bin aggregation."""

from collections import Counter

import pandas as pd


def value_col_name(agg, numeric_col, category_value=None):
    if category_value is not None:
        if str(category_value) == "NaN_category":
            category_value = "NaN"
        prefix = f"{category_value}_"
    else:
        prefix = ""
    if numeric_col:
        return f"{prefix}{numeric_col}_{agg}"
    return f"{prefix}{agg}"


def aggregate_bin(
    df,
    dggs_col: str,
    agg: str,
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

    if agg == "count":
        result = (
            df.groupby(group_cols)
            .size()
            .reset_index(name=value_col_name(agg, numeric_col))
        )

    elif agg in ["sum", "min", "max", "mean", "median", "std", "var"]:
        if not numeric_col:
            raise ValueError(f"numeric_col must be provided for agg='{agg}'")
        result = (
            df.groupby(group_cols)[numeric_col]
            .agg(agg)
            .reset_index(name=value_col_name(agg, numeric_col))
        )

    elif agg == "range":
        if not numeric_col:
            raise ValueError(f"numeric_col must be provided for agg='{agg}'")
        result = df.groupby(group_cols)[numeric_col].agg(["min", "max"]).reset_index()
        result[value_col_name(agg, numeric_col)] = result["max"] - result["min"]
        result = result.drop(["min", "max"], axis=1)

    elif agg in ["minority", "majority", "variety"]:
        if not numeric_col:
            raise ValueError(f"numeric_col must be provided for agg='{agg}'")

        def cat_agg_func(x):
            values = x[numeric_col].dropna()
            freq = Counter(values)
            if not freq:
                return None
            if agg == "minority":
                return min(freq.items(), key=lambda y: y[1])[0]
            if agg == "majority":
                return max(freq.items(), key=lambda y: y[1])[0]
            return values.nunique()

        if category_col:
            all_categories = sorted([str(cat) for cat in df[category_col].unique()])
            result = (
                df.groupby([dggs_col, category_col])
                .apply(cat_agg_func, include_groups=False)
                .reset_index(name=value_col_name(agg, numeric_col))
            )
            result = result.pivot(
                index=dggs_col,
                columns=category_col,
                values=value_col_name(agg, numeric_col),
            )
            result = result.reindex(
                columns=all_categories, fill_value=0 if agg == "variety" else None
            )
            result = result.reset_index()
            result.columns = [dggs_col] + [
                value_col_name(agg, numeric_col, cat) for cat in all_categories
            ]
        else:
            result = (
                df.groupby([dggs_col])
                .apply(cat_agg_func, include_groups=False)
                .reset_index(name=value_col_name(agg, numeric_col))
            )
    else:
        raise ValueError(f"Unknown agg: {agg}")

    if category_col and agg not in ["minority", "majority", "variety"]:
        value_name = value_col_name(agg, numeric_col)
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
                    value_col_name(agg, numeric_col, col)
                    for col in sorted(result.columns[1:])
                ]
            except Exception:
                result = (
                    df.groupby(dggs_col)
                    .size()
                    .reset_index(name=value_col_name(agg, numeric_col))
                )

    return result
