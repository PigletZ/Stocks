.PHONY: backend frontend install run build-public public

install:
	cd backend && python -m venv venv && source venv/bin/activate && pip install -r requirements.txt
	cd frontend && npm install

backend:
	cd backend && source venv/bin/activate && uvicorn app.main:app --reload --port 8000

backend-public:
	cd backend && source venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000

frontend:
	cd frontend && npm run dev

frontend-public:
	cd frontend && npm run dev -- --host

build-public:
	cd frontend && npm run build

public:
	cd frontend && npm run build
	cd backend && source venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000

run:
	make backend & make frontend
