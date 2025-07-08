ENV_NAME := vgridpandas
ENVIRONMENT := environment.yml
ENVIRONMENT_DEV := environment-dev.yml

install: _install _update_dev _install_package_editable

_install:
	mamba env create -n $(ENV_NAME) -f $(ENVIRONMENT)

_update_dev: 
	mamba env update -n $(ENV_NAME) -f $(ENVIRONMENT_DEV)

_install_package_editable: 
	mamba run -n $(ENV_NAME) python -m pip install -e .

docs:
	mamba run -n $(ENV_NAME) python build_docs.py

docs-clean:
	mamba run -n $(ENV_NAME) mkdocs build --clean

docs-serve:
	mamba run -n $(ENV_NAME) mkdocs serve
