.PHONY: install run test docker clean

install:
	pip install -r requirements.txt

run:
	python main.py

test:
	pytest tests/ -v

docker:
	docker compose up --build

clean:
	rm -rf hive.db __pycache__ .pytest_cache hive/__pycache__ hive/core/__pycache__ hive/api/__pycache__
