.PHONY: install fetch backtest ablation test lint clean

install:
	pip install -e ".[dev,notebooks]"

fetch:
	python scripts/fetch_historical_data.py

backtest:
	python scripts/run_backtest.py

ablation:
	python scripts/run_ablation.py

test:
	pytest tests/ -v

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

format:
	ruff format src/ tests/

clean:
	rm -rf data/raw/* data/processed/* data/db/*
	find . -type d -name __pycache__ -exec rm -rf {} +
