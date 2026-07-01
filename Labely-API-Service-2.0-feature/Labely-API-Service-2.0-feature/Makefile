.PHONY: help install dev test lint clean docker-build docker-up docker-down

help:
	@echo "Available commands:"
	@echo "  install      Install dependencies"
	@echo "  dev         Run development server"
	@echo "  test        Run tests"
	@echo "  lint        Run linters"
	@echo "  clean       Clean cache files"
	@echo "  docker-build Build Docker image"
	@echo "  docker-up   Start Docker services"
	@echo "  docker-down Stop Docker services"

install:
	pip install -r requirements.txt

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest tests/ -v --cov=app --cov-report=term-missing

lint:
	flake8 app/
	black app/ --check
	mypy app/

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".coverage" -exec rm -rf {} +

docker-build:
	docker-compose build

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

db-init:
	python scripts/init_db.py

db-migrate:
	alembic upgrade head

db-rollback:
	alembic downgrade -1