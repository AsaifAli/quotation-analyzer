.PHONY: install test run-api run-ui docker-up docker-ollama docker-gpu

install:
	python -m pip install -r requirements.txt

test:
	pytest -q

run-api:
	uvicorn app:app --reload --port 8000

run-ui:
	streamlit run streamlit_app.py

docker-up:
	cp -n .env.example .env 2>/dev/null || true
	docker compose up --build

docker-ollama:
	cp -n .env.example .env 2>/dev/null || true
	docker compose -f docker-compose.yml -f docker-compose.ollama.yml up --build

docker-gpu:
	cp -n .env.example .env 2>/dev/null || true
	docker compose -f docker-compose.yml -f docker-compose.ollama.yml -f docker-compose.gpu.yml up --build
