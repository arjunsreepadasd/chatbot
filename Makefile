# ─────────────────────────────────────────────
#  Chatbot Makefile
# ─────────────────────────────────────────────

.PHONY: install run dev clean help

.DEFAULT_GOAL := help

install:
	pip3 install --break-system-packages -r requirements.txt
	@echo "✅ Dependencies installed"

run:
	python3 app.py

dev: install run

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf venv
	@echo "🧹 Cleaned up"

help:
	@echo ""
	@echo "  🤖 Chatbot — Available Commands"
	@echo "  ─────────────────────────────────"
	@echo "  make dev       Install + run (all in one)"
	@echo "  make install   Install dependencies"
	@echo "  make run       Start the Flask server"
	@echo "  make clean     Remove cache files"
	@echo ""
