.PHONY: install run-backend run-frontend test check-provider-isolation seed seed-reset clean

install:
	pip install -r requirements.txt

run-backend:
	uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

run-frontend:
	streamlit run frontend/app.py

test:
	pytest -v

llm-smoke:
	python scripts/llm_smoke_test.py $(ARGS)

# Populate the DB with a demo JD + scored candidates + a sample assessment -
# no LLM calls, no API key needed. Safe to run against an already-seeded DB
# (adds a second copy); use seed-reset to start clean instead.
seed:
	python scripts/seed_demo.py

seed-reset:
	python scripts/seed_demo.py --reset

# Guard for the LLM abstraction rule: provider SDKs may only be imported
# inside backend/llm/providers/. A hit here means the design has leaked.
# Anchored on `from X import` / `import X` so this doesn't false-positive on
# our own adapter module names (e.g. `from backend.llm.providers import openai`).
check-provider-isolation:
	@if grep -rlnE "^[[:space:]]*(from|import)[[:space:]]+(langchain_google_genai|langchain_openai|openai|google\.generativeai)\b" backend/ \
		--include="*.py" | grep -v "backend/llm/providers/"; then \
		echo "FAIL: provider-specific import found outside backend/llm/providers/"; \
		exit 1; \
	else \
		echo "OK: no provider-specific imports leaked outside backend/llm/providers/"; \
	fi

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache
