# Installation

## Install from PyPI

**vgridpandas** is available on [PyPI](https://pypi.org/project/vgridpandas/). To install **vgridpandas**, run this command in your terminal:

```bash
pip install vgridpandas
```

## Install from conda-forge

**vgridpandas** is also available on [conda-forge](https://anaconda.org/conda-forge/vgridpandas). If you have
[Anaconda](https://www.anaconda.com/distribution/#download-section) or [Miniconda](https://docs.conda.io/en/latest/miniconda.html) installed on your computer, you can install vgridpandas using the following command:

```bash
conda install vgridpandas -c conda-forge
```

```bash
conda install -n base mamba -c conda-forge
mamba create -n geo vgridpandas geopandas localtileserver python -c conda-forge
```

## Install from GitHub

To install the development version from GitHub using [Git](https://git-scm.com/), run the following command in your terminal:

```bash
pip install git+https://github.com/opengeoshub/vgridpandas
```


## Upgrade vgridpandas

If you have installed **vgridpandas** before and want to upgrade to the latest version, you can run the following command in your terminal:

```bash
pip install -U vgridpandas
```

If you use conda, you can update vgridpandas to the latest version by running the following command in your terminal:

```bash
conda update -c conda-forge vgridpandas
```