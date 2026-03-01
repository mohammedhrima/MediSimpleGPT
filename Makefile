.PHONY: install-backend install-frontend install backend frontend clean setup-env

install: setup-env install-backend install-frontend

setup-env:
	@echo "Setting up environment file..."
	@if [ ! -f .env ]; then cp .env.example .env; echo "Created .env from example"; fi

install-backend:
	cd backend && uv sync && uv run python -m playwright install chromium

install-frontend:
	cd frontend && npm install

backend:
	cd backend && uv run python -m uvicorn api_server:app --host 127.0.0.1 --port 8000

frontend:
	cd frontend && npm run dev

clean:
	rm -rf backend/.venv backend/__pycache__
	rm -rf frontend/node_modules frontend/dist
