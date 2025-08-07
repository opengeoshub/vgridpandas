# VgridPandas
**VgridPandas - Integrates [Vgrid DGGS](https://github.com/opengeoshub/vgrid) with [GeoPandas](https://github.com/geopandas/geopandas) and [Pandas](https://github.com/pandas-dev/pandas), inspired by [H3-Pandas](https://github.com/DahnJ/H3-Pandas/)**

VgridPandas supports a wide range of popular geodesic DGGS including H3, S2, A5, rHEALPix, Open-EAGGR ISEA4T, EASE-DGGS, QTM, as well as graticule-based DGGS such as OLC, Geohash, MGRS, GEOREF, TileCode, Quadkey, Maidenhead, and GARS.

[![logo](https://raw.githubusercontent.com/opengeoshub/vgridtools/refs/heads/main/images/vgridpandas.svg)](https://github.com/opengeoshub/vgridtools/blob/main/images/vgridpandas.svg)


[![image](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/opengeoshub/vgridpandas/blob/main)
[![image](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/opengeoshub/vgridpandas/HEAD?filepath=docs/notebooks)
[![image](https://studiolab.sagemaker.aws/studiolab.svg)](https://studiolab.sagemaker.aws/import/github/opengeoshub/vgridpandas/blob/main/docs/notebooks/00_intro.ipynb)
[![image](https://jupyterlite.rtfd.io/en/latest/_static/badge.svg)](https://demo.gishub.vn/lab/index.html?path=notebooks/vgridpandas/00_intro.ipynb)
[![PyPI version](https://badge.fury.io/py/vgridpandas.svg)](https://badge.fury.io/py/vgridpandas)
[![image](https://static.pepy.tech/badge/vgridpandas)](https://pepy.tech/project/vgridpandas)
[![image](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)


Full VgridPandas DGGS documentation is available at [vgridpandas document](https://vgridpandas.gishub.vn).

To work with Vgrid in Python or CLI, use [vgrid](https://pypi.org/project/vgrid/) package. Full Vgrid DGGS documentation is available at [vgrid document](https://vgrid.gishub.vn).

To work with Vgrid DGGS in QGIS, install the [Vgrid Plugin](https://plugins.qgis.org/plugins/vgridtools/).

To visualize DGGS in Maplibre GL JS, try the [vgrid-maplibre](https://www.npmjs.com/package/vgrid-maplibre) library.

For an interactive demo, visit the [Vgrid Homepage](https://vgrid.vn).


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
- **DGGS binning:** Aggregate points into DGGS cells, supporting common statistics (count, min, max, etc.) and category-based groups.

## Usage examples

### Latlong to DGGS

```python
import pandas as pd
from vgridpandas import h3pandas
df = pd.DataFrame({'lat': [10, 11], 'lon': [106, 107]})
resolution = 10
df = df.h3.latlon2h3(resolution)
df

| h3              |   lat |   lon |
|-----------------|-------|-------|
| 8a65a212199ffff |    10 |   106 |
| 8a65b0b68237fff |    11 |   107 |
```

### DGGS to geo boundary
```python
df = df.h3.h32geo()
df

| h3              |   lat |   lon | geometry        |
|-----------------|-------|-------|-----------------|
| 8a65a212199ffff |    10 |   106 | POLYGON ((...)) |
| 8a65b0b68237fff |    11 |   107 | POLYGON ((...)) |
```

### (Multi)Linestring/ (Multi)Polygon to DGGS
```python
import geopandas as gpd
from vgridpandas import s2pandas

gdf = gpd.read_file('https://raw.githubusercontent.com/opengeoshub/vopendata/refs/heads/main/shape/polygon.geojson')
resolution = 18
gdf_polyfill = gdf.s2.polyfill(resolution, compact = True, predicate = "largest_overlap", explode = True)
gdf_polyfill.head()
gdf_polyfill = gdf_polyfill.s2.s22geo("s2")
gdf_polyfill.plot(edgecolor = "white")
```
<div align="center">
  <img src="https://raw.githubusercontent.com/thangqd/vgridtools/main/images/readme/vector2s2_compacted.png">
</div>

### DGGS Binning
```python
import pandas as pd
import geopandas as gpd
from vgridpandas import a5pandas
resolution = 15
df = pd.read_csv("https://raw.githubusercontent.com/opengeoshub/vopendata/refs/heads/main/csv/dist1_pois.csv")
# df = gpd.read_file("https://raw.githubusercontent.com/opengeoshub/vopendata/refs/heads/main/shape/dist1_pois.geojson")
stats = "count"
df_bin = df.a5.a5bin(resolution=resolution, stats = stats, 
                    # numeric_column="confidence",
                    # category_column="category",
                    return_geometry=True)
df_bin.plot(
    column=stats,        # numeric column to base the colors on
    cmap='Spectral_r',   # color scheme (matplotlib colormap)
    legend=True,  
    linewidth=0.2         # boundary width (optional)
)
```
<div align="center">
  <img src="https://raw.githubusercontent.com/thangqd/vgridtools/main/images/readme/a5bin.png">
</div>

### Further examples
For more examples, see the 
[example notebooks](https://nbviewer.jupyter.org/github/opengeoshub/vgridpandas/tree/main/docs/notebooks/).