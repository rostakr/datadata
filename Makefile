SHELL := /bin/bash

PYTHON ?= python
STREAMLIT_PORT ?= 8501
SMOKE_PORT ?= 8765
SMOKE_OUTPUT ?= artifacts/a6-viewport-smoke

.PHONY: setup setup-dev test compile check ui a6-smoke a6-launch a6-gate-local a6-launch-archive-local

setup:
	$(PYTHON) -m pip install -r requirements.txt

setup-dev:
	$(PYTHON) -m pip install -r requirements-dev.txt
	$(PYTHON) -m playwright install --with-deps chromium

test:
	$(PYTHON) -m pytest -q

compile:
	$(PYTHON) -m compileall -q src a6 tools app.py

check: test compile

ui:
	$(PYTHON) -m streamlit run app.py \
		--server.address 0.0.0.0 \
		--server.port $(STREAMLIT_PORT) \
		--server.headless true \
		--browser.gatherUsageStats false

a6-smoke:
	@set -euo pipefail; \
	rm -rf "$(SMOKE_OUTPUT)"; \
	$(PYTHON) -m streamlit run app.py \
		--server.headless true \
		--server.port $(SMOKE_PORT) \
		--server.address 127.0.0.1 \
		--browser.gatherUsageStats false \
		> /tmp/datadata-a6-smoke.log 2>&1 & \
	pid=$$!; \
	trap 'kill "$$pid" 2>/dev/null || true' EXIT; \
	healthy=0; \
	for attempt in $$(seq 1 30); do \
		if curl --fail --silent --show-error "http://127.0.0.1:$(SMOKE_PORT)/_stcore/health" >/dev/null; then healthy=1; break; fi; \
		sleep 1; \
	done; \
	if [ "$$healthy" -ne 1 ]; then cat /tmp/datadata-a6-smoke.log; exit 1; fi; \
	if ! $(PYTHON) tools/a6_viewport_smoke.py --url "http://127.0.0.1:$(SMOKE_PORT)" --output "$(SMOKE_OUTPUT)"; then \
		cat /tmp/datadata-a6-smoke.log; exit 1; \
	fi

a6-launch:
	@test -n "$(DATABASE)" || (echo "DATABASE=/path/to/messages.sqlite is required" >&2; exit 2)
	$(PYTHON) -m tools.local_app --database "$(DATABASE)"

a6-gate-local:
	@if [ -n "$$CODESPACES" ]; then echo "Refusing real chat.db processing in Codespaces; run this target on the trusted local machine." >&2; exit 2; fi
	@test -n "$(CHAT_DB)" || (echo "CHAT_DB=/path/to/chat.db is required" >&2; exit 2)
	@test -n "$(WORKDIR)" || (echo "WORKDIR=/new/empty/private/run-dir is required" >&2; exit 2)
	@if [ -n "$(TARGET)" ]; then \
		$(PYTHON) -m tools.real_archive_gate --chat-db "$(CHAT_DB)" --workdir "$(WORKDIR)" --target "$(TARGET)"; \
	elif [ -n "$(CONVERSATION_ID)" ]; then \
		$(PYTHON) -m tools.real_archive_gate --chat-db "$(CHAT_DB)" --workdir "$(WORKDIR)" --conversation-id "$(CONVERSATION_ID)"; \
	else \
		echo "TARGET=... or CONVERSATION_ID=... is required" >&2; exit 2; \
	fi

a6-launch-archive-local:
	@if [ -n "$$CODESPACES" ]; then echo "Refusing real chat.db processing in Codespaces; run this target on the trusted local machine." >&2; exit 2; fi
	@test -n "$(CHAT_DB)" || (echo "CHAT_DB=/path/to/chat.db is required" >&2; exit 2)
	@if [ -n "$(TARGET)" ]; then \
		$(PYTHON) -m tools.local_app --chat-db "$(CHAT_DB)" --target "$(TARGET)"; \
	elif [ -n "$(CONVERSATION_ID)" ]; then \
		$(PYTHON) -m tools.local_app --chat-db "$(CHAT_DB)" --conversation-id "$(CONVERSATION_ID)"; \
	else \
		echo "TARGET=... or CONVERSATION_ID=... is required" >&2; exit 2; \
	fi
