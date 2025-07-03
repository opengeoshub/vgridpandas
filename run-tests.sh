#/bin/bash
pytest --cov-report html --cov vgridpandas
flake8 . 
# xdg-open htmlcov/vgridpandas_h3_py.html
