"""Basic S2Pandas accessor tests."""

import pandas as pd
import pytest


@pytest.fixture
def basic_dataframe():
    return pd.DataFrame({"lat": [50, 51], "lon": [14, 15]})


def test_latlon2s2_adds_columns(basic_dataframe):
    result = basic_dataframe.s2.latlon2s2(9)
    assert "s2" in result.columns
    assert "s2_res" in result.columns
    assert result["s2_res"].tolist() == [9, 9]
    assert len(result["s2"]) == 2
    assert result["s2"].notna().all()


def test_latlon2s2_set_index(basic_dataframe):
    result = basic_dataframe.s2.latlon2s2(9, set_index=True)
    assert result.index.name == "s2"
    assert len(result) == 2
