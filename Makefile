PYTHON ?= python
PYTHONPATH ?= src
AMOS_POSTGRES_PORT ?= 55432
POSTGRES_DSN ?= postgresql://amos:amos@localhost:$(AMOS_POSTGRES_PORT)/amos

.PHONY: test test-postgres postgres-up postgres-down run docker-build

test:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m unittest discover -s tests -v

postgres-up:
	docker compose up -d --wait postgres

postgres-down:
	docker compose down

test-postgres: postgres-up
	AMOS_STORAGE_BACKEND=postgres \
	AMOS_POSTGRES_DSN=$(POSTGRES_DSN) \
	AMOS_EMBEDDING_MODEL=hash \
	AMOS_RUN_INTEGRATION=1 \
	PYTHONPATH=$(PYTHONPATH) \
	$(PYTHON) -m unittest discover -s tests -v

run:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m amos

docker-build:
	docker build -t amos-memory .
