# Welcome to vgridpandas

[![image](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/opengeoshub/vgridpandas/blob/master)
[![image](https://studiolab.sagemaker.aws/studiolab.svg)](https://studiolab.sagemaker.aws/import/github/opengeoshub/vgridpandas/blob/master/docs/notebooks/00_intro.ipynb)
[![image](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/opengeoshub/vgridpandas/HEAD)
[![image](https://img.shields.io/pypi/v/vgridpandas.svg)](https://pypi.python.org/pypi/vgridpandas)
[![image](https://static.pepy.tech/badge/vgridpandas)](https://pepy.tech/project/vgridpandas)
[![image](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

[![logo](https://raw.githubusercontent.com/opengeoshub/vgridtools/refs/heads/main/images/vgridpandas.svg)](https://github.com/opengeoshub/vgridtools/blob/main/images/vgridpandas.svg)


**VgridPands - Integrates [Vgrid DGGS](https://github.com/opengeoshub/vgrid) with [GeoPandas](https://github.com/geopandas/geopandas) and [Pandas](https://github.com/pandas-dev/pandas), inspired by [H3-Pandas](https://github.com/DahnJ/H3-Pandas/)**

Vgridpandas supports popular geodesic DGGS such as H3, S2, rHEALPix, Open-Eaggr ISEA4T, EASE-DGGS, QTM, and graticule DGGS such as OLC, Geohash, MGRS, GEOREF, Tilecode, Quadkey, Maidenhead, GARS



-   GitHub repo: <https://github.com/opengeoshub/vgridpandas>
-   Documentation: <https://github.com/opengeoshub/vgridpandas>
-   PyPI: <https://pypi.org/project/vgridpandas>
-   Conda-forge: <https://anaconda.org/conda-forge/vgridpandas>
-   Free software: [MIT license](https://opensource.org/licenses/MIT)


## Introduction
[![vgridpandas](https://raw.githubusercontent.com/opengeoshub/vgridtools/main/images/readme/dggs.png)](https://github.com/opengeoshub/vgridtools/blob/main/images/readme/dggs.png)


**vgridpandas** 

## Acknowledgments

This doc is inspired by ([leafmap](https://leafmap.org/)).

## Statement of Need


## Usage

Launch the interactive notebook tutorial for the **vgridpandas** Python package with Amazon SageMaker Studio Lab, Microsoft Planetary Computer, Google Colab, or Binder:

[![image](https://studiolab.sagemaker.aws/studiolab.svg)](https://studiolab.sagemaker.aws/import/github/opengeoshub/vgridpandas/blob/master/docs/notebooks/00_intro.ipynb)
[![image](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/opengeoshub/vgridpandas/blob/master)
[![image](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/opengeoshub/vgridpandas/HEAD)


## Key Features

- **Latlong to DGGS:** Convert latlon to DGGS ID.
- **DGGS to geo boundary:** Convert DGGS ID to Geometry.
- **(Multi)Linestring/ (Multi)Polygon to DGGS:** Convert vector (Multi)Linestring/ (Multi)Polygon to DGGS, supporting compact option.
- **DGGS point binning:** Convert point to DGGS, supporting popular statistics such as count, min, max, etc by category.


## Citations

If you find **vgridpandas** useful in your research, please consider citing the following paper to support my work. Thank you for your support.

## Demo

[Vgrid Homepage](https://vgrid.vn)
