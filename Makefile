.PHONY: check mypy ruff

check: mypy ruff
	uv run pytest

mypy:
	uv run mypy .

ruff:
	uv run ruff check
	uv run ruff format --check
