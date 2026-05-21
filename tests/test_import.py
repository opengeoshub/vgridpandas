"""Smoke tests that DGGS pandas modules import."""

import importlib

import pytest

DGGS_MODULES = [
    "vgridpandas.a5pandas",
    "vgridpandas.h3pandas",
    "vgridpandas.s2pandas",
    "vgridpandas.rhealpixpandas",
    "vgridpandas.mgrspandas",
    "vgridpandas.geohashpandas",
]


@pytest.mark.parametrize("module_name", DGGS_MODULES)
def test_import_dggs_module(module_name):
    importlib.import_module(module_name)
