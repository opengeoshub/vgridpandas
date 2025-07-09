# VgridPandas
Integrates [Vgrid DGGS](https://github.com/opengeoshub/vgrid) with [GeoPandas](https://github.com/geopandas/geopandas) and [Pandas](https://github.com/pandas-dev/pandas), inspired by [H3-Pandas](https://github.com/DahnJ/H3-Pandas/)

Vgridpandas supports popular geodesic DGGS such as H3, S2, rHEALPix, Open-Eaggr ISEA4T, EASE-DGGS, QTM, and graticule DGGS such as OLC, Geohash, MGRS, GEOREF, Tilecode, Quadkey, Maidenhead, GARS

<div align="center">
  <img src="docs/assets/logo.png" alt="vgridpandas logo">
</div>

[![image](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/opengeoshub/vgridpandas/blob/master/notebook/00-intro.ipynb)
[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/opengeoshub/vgridpandas/HEAD?filepath=%2Fnotebook%2F00-intro.ipynb)
[![image](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI version](https://badge.fury.io/py/vgridpandas.svg)](https://badge.fury.io/py/vgridpandas)
[![PyPI downloads](https://img.shields.io/pypi/dm/vgridpandas.svg)](https://pypistats.org/packages/vgridpandas)
![Total downloads](https://static.pepy.tech/personalized-badge/vgridpandas?period=total&units=international_system&left_color=grey&right_color=blue&left_text=total)


---

<h3 align="center">
  ⬢ <a href="https://mybinder.org/v2/gh/opengeoshub/vgridpandas/HEAD?filepath=%2Fnotebook%2F00-intro.ipynb">Try it out</a> ⬢
</h3>


## Installation
### pip
[![image](https://img.shields.io/pypi/v/vgridpandas.svg)](https://pypi.python.org/pypi/vgridpandas)
```bash
pip install vgridpandas
```

## Usage examples

### vgridpandas.h3pandas API
`vgiridpandas.h3pandas` automatically applies H3 functions to both Pandas Dataframes and GeoPandas Geodataframes

```python
# Prepare data
>>> import pandas as pd
>>> from vgridpandas import h3pandas
>>> df = pd.DataFrame({'lat': [50, 51], 'lon': [14, 15]})
```

```python
>>> resolution = 10
>>> df = df.h3.latlon2h3(resolution)
>>> df

| h3_10           |   lat |   lon |
|:----------------|------:|------:|
| 8a1e30973807fff |    50 |    14 |
| 8a1e2659c2c7fff |    51 |    15 |

>>> df = df.h3.h32geo()
>>> df

| h3_10           |   lat |   lon | geometry        |
|:----------------|------:|------:|:----------------|
| 8a1e30973807fff |    50 |    14 | POLYGON ((...)) |
| 8a1e2659c2c7fff |    51 |    15 | POLYGON ((...)) |
```

### Further examples
For more examples, see the 
[example notebooks](https://nbviewer.jupyter.org/github/opengeoshub/vgridpandas/tree/master/docs/notebooks/).

## VgridPandas API
For a full API documentation and more usage examples, see the 
[documentation](https://vgridpandas.gishub.vn).


**Any suggestions and contributions are very welcome**!

See [issues](https://github.com/opengeoshub/vgridpandas/issues) for more.
