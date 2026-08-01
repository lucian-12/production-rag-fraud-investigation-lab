.PHONY: demo fixture test evaluate down

demo:
	docker compose up --build

fixture:
	DEMO_STORAGE=fixture uvicorn app.main:app --reload

test:
	python3 -m unittest discover -s tests -v

evaluate:
	python3 scripts/evaluate.py

down:
	docker compose down
