.PHONY: help anchors derive build validate faults test check clean

help:
	@echo "anchors  - rebuild financial anchors and docs/financial-anchors.md"
	@echo "derive   - re-derive the anchor inputs the generated data supplies, then rebuild anchors"
	@echo "build    - regenerate the Phase 2 source systems and reference data"
	@echo "validate - run the Phase 2 source controls"
	@echo "faults   - inject the fault fixtures and prove each is detected"
	@echo "test     - run the full validation suite"
	@echo "check    - rebuild anchors then validate (use this before committing)"

anchors:
	python src/anchors/build_anchors.py

derive:
	python tools/derive_anchor_inputs.py

build:
	python -m src.generation.build

validate:
	python -m src.generation.validate

faults:
	python -m src.generation.faults

test:
	python -m pytest tests -q

check: anchors test

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache
