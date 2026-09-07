.PHONY: help anchors test check clean

help:
	@echo "anchors  - rebuild financial anchors and docs/financial-anchors.md"
	@echo "test     - run the full validation suite"
	@echo "check    - rebuild anchors then validate (use this before committing)"

anchors:
	python src/anchors/build_anchors.py

test:
	python -m pytest tests -q

check: anchors test

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache
