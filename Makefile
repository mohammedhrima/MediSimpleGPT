.PHONY: install-backend install-frontend install backend frontend clean

install: install-backend install-frontend

install-backend:
	cd backend && uv sync && uv run playwright install chromium

install-frontend:
	cd frontend && npm install

backend:
	cd backend && uv run uvicorn api_server:app --host 127.0.0.1 --port 8000

frontend:
	cd frontend && npm run dev

clean:
	rm -rf backend/.venv backend/__pycache__
	rm -rf frontend/node_modules frontend/dist
