SHELL := /bin/bash
VENV_DIR = venv
PYTHON = $(VENV_DIR)/bin/python
PIP = $(VENV_DIR)/bin/pip


# Default target
all:
	@echo "Use: make activate | make install | make deactivate"

# Create venv if not exists, then activate (drop into subshell)
activate:
	@if [ ! -d "$(VENV_DIR)" ]; then \
		echo "Creating virtual environment..."; \
		python3 -m venv $(VENV_DIR); \
	fi
	@echo "To activate the virtual environment, run: source $(VENV_DIR)/bin/activate"

# Install dependencies (edit requirements.txt if you have one)
install: $(VENV_DIR)/bin/activate
	@echo "Installing dependencies..."
	@if [ -f requirements.txt ]; then \
		$(PIP) install -r requirements.txt; \
	else \
		echo "No requirements.txt found. Install packages manually using 'make pkg PKG=package'"; \
	fi

# Helper: install a single package
pkg: $(VENV_DIR)/bin/activate
	@$(PIP) install $(PKG)

# Deactivate (just prints instructions, since Make can’t control parent shell)
deactivate:
	@echo "To deactivate, type: deactivate"
