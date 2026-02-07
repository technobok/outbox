.PHONY: help sync install init-db bootstrap-key run rundev worker check clean config-list config-set config-import config-export

SHELL := /bin/bash
VENV_DIR := $(or $(VIRTUAL_ENV),.venv)
ADMIN := $(VENV_DIR)/bin/outbox-admin
WEB := $(VENV_DIR)/bin/outbox-web
PYTHON := $(VENV_DIR)/bin/python
GUNICORN := $(VENV_DIR)/bin/gunicorn
RUFF := $(VENV_DIR)/bin/ruff
TY := $(VENV_DIR)/bin/ty

help:
	@echo "Outbox - Mail Queue Service"
	@echo "---------------------------"
	@echo "sync     - Sync dependencies with uv (creates venv if needed)"
	@echo "install  - Alias for sync"
	@echo "init-db  - Create a blank database"
	@echo "bootstrap-key [DESC=description]"
	@echo "           - Generate an API key for service bootstrap (prints to console)"
	@echo "run      - Run server via gunicorn (0.0.0.0:5200)"
	@echo "rundev   - Run Flask dev server (DEV_HOST:DEV_PORT, debug=True)"
	@echo "worker   - Run the queue worker process"
	@echo "config-list  - Show all config settings"
	@echo "config-set KEY=key VAL=value  - Set a config value"
	@echo "config-import FILE=path  - Import settings from INI file"
	@echo "config-export FILE=path  - Export all settings as a shell script"
	@echo "check    - Run ruff and ty for code quality"
	@echo "clean    - Remove temporary files and database"
	@echo ""
	@echo "Database: instance/outbox.sqlite3 (default)"
	@echo "Set OUTBOX_DB to override, e.g.:"
	@echo "  export OUTBOX_DB=/data/outbox.sqlite3"

sync:
	@uv sync --extra dev

install: sync

init-db:
	@$(ADMIN) init-db

bootstrap-key:
	@$(ADMIN) generate-api-key --description "$(or $(DESC),bootstrap)"

run:
	@$(GUNICORN) wsgi:app --bind 0.0.0.0:5200 --workers 2 --preload

rundev:
	@$(WEB) --dev

worker:
	@$(PYTHON) -m worker.queue_worker

config-list:
	@$(ADMIN) config list

config-set:
	@$(ADMIN) config set $(KEY) '$(VAL)'

config-import:
	@$(ADMIN) config import $(or $(FILE),$(file))

config-export:
	@$(ADMIN) config export $(or $(FILE),$(file))

check:
	@$(RUFF) format src
	@$(RUFF) check src --fix
	@if [ -z "$$VIRTUAL_ENV" ]; then unset VIRTUAL_ENV; fi; $(TY) check src

clean:
	@find . -type f -name '*.py[co]' -delete
	@find . -type d -name '__pycache__' -delete
	@rm -f instance/outbox.sqlite3
	@rm -rf instance/blobs
