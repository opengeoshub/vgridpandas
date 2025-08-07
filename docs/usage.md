# Usage

You can try out vgridpandas by using [![image](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/opengeoshub/vgridpandas/blob/master), [![image](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/opengeoshub/vgridpandas/HEAD), [![image](https://studiolab.sagemaker.aws/studiolab.svg)](https://studiolab.sagemaker.aws/import/github/opengeoshub/vgridpandas/blob/main/docs/notebooks/00_intro.ipynb)
[![image](https://jupyterlite.rtfd.io/en/latest/_static/badge.svg)](https://demo.gishub.vn/lab/index.html?path=notebooks/vgridpandas/00_intro.ipynb) without having to install anything on your computer.

## Launch Jupyter Lab

```bash
jupyter lab
```

## Try vgridpandas

```python
import pandas as pd
from vgridpandas import h3pandas
df = pd.DataFrame({'lat': [14.6657293, -187.5088058], 'lon': [14, 15]})
resolution = 0
df = df.h3.latlon2h3(resolution)
df.head()
```
