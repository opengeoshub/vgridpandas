# VgridPandas
**VgridPands - Integrates [Vgrid DGGS](https://github.com/opengeoshub/vgrid) with [GeoPandas](https://github.com/geopandas/geopandas) and [Pandas](https://github.com/pandas-dev/pandas), inspired by [H3-Pandas](https://github.com/DahnJ/H3-Pandas/)**

VgridPandas supports a wide range of popular geodesic DGGS including H3, S2, A5, rHEALPix, Open-EAGGR ISEA4T, EASE-DGGS, QTM, as well as graticule-based systems such as OLC, Geohash, MGRS, GEOREF, TileCode, Quadkey, Maidenhead, and GARS.

[![logo](https://raw.githubusercontent.com/opengeoshub/vgridtools/refs/heads/main/images/vgridpandas.svg)](https://github.com/opengeoshub/vgridtools/blob/main/images/vgridpandas.svg)


[![image](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/opengeoshub/vgridpandas/blob/main/notebook/00-intro.ipynb)
[![image](https://studiolab.sagemaker.aws/studiolab.svg)](https://studiolab.sagemaker.aws/import/github/opengeoshub/vgridpandas/blob/main/docs/notebooks/00_intro.ipynb)
[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/opengeoshub/vgridpandas/HEAD?filepath=%2Fnotebook%2F00-intro.ipynb)
[![PyPI version](https://badge.fury.io/py/vgridpandas.svg)](https://badge.fury.io/py/vgridpandas)
[![image](https://static.pepy.tech/badge/vgridpandas)](https://pepy.tech/project/vgridpandas)
[![image](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)


## Installation
### pip
[![image](https://img.shields.io/pypi/v/vgridpandas.svg)](https://pypi.python.org/pypi/vgridpandas)
```bash
pip install vgridpandas --upgrade
```

## Key Features

- **Latlong to DGGS:** Convert latitude and longitude coordinates into DGGS cell IDs.
- **DGGS to geo boundary:** Convert DGGS cell IDs into their corresponding geographic boundaries.
- **(Multi)Linestring/ (Multi)Polygon to DGGS:** Convert (Multi)Linestring/ (Multi)Polygon to DGGS, supporting compact option.
- **DGGS point binning:** Aggregate points into DGGS cells, supporting common statistics like count, min, max, and category-based groups.

## Usage examples

### Latlong to DGGS

```python
# Prepare data
>>> import pandas as pd
>>> from vgridpandas import h3pandas
>>> df = pd.DataFrame({'lat': [10, 11], 'lon': [106, 107]})
```

```python
>>> resolution = 10
>>> df = df.h3.latlon2h3(resolution)
>>> df

| h3_10           |   lat |   lon |
|:----------------|------:|------:|
| 8a65a212199ffff |    10 |   106 |
| 8a65b0b68237fff |    11 |   107 |
```

### DGGS to geo boundary
```python

>>> df = df.h3.h32geo()
>>> df

| h3_10           |   lat |   lon | geometry        |
|:----------------|------:|------:|:----------------|
| 8a65a212199ffff |    10 |   106 | POLYGON ((...)) |
| 8a65b0b68237fff |    11 |   107 | POLYGON ((...)) |
```

### Further examples
For more examples, see the 
[example notebooks](https://nbviewer.jupyter.org/github/opengeoshub/vgridpandas/tree/main/docs/notebooks/).

## Vgridpandas Documentation
For a full Vgridpandas API documentation and more usage examples, see the 
[documentation](https://vgridpandas.gishub.vn).


**Any suggestions and contributions are very welcome**!

See [issues](https://github.com/opengeoshub/vgridpandas/issues) for more.
