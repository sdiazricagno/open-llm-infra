COMPOSE := docker compose -f deploy/compose/docker-compose.yml
PYTHON ?= python
MODELS ?= qwen2.5-0.5b llama3.2-1b qwen2.5-1.5b

.PHONY: help install gateway up up-gpu down ps logs pull smoke bench bench-cpu report lint test tf-check helm-check check

help:  ## List targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

install:  ## Install the Python tooling
	$(PYTHON) -m pip install -r requirements-dev.txt

gateway:  ## Re-render the gateway config from config/models.yaml
	$(PYTHON) -m openllm gateway

up:  ## Start the CPU stack: Ollama, llama.cpp, gateway, Prometheus, Grafana
	$(COMPOSE) up -d --wait

up-gpu:  ## Start the CPU stack plus vLLM on a local NVIDIA GPU
	$(COMPOSE) --profile gpu up -d --wait

down:  ## Stop everything
	$(COMPOSE) --profile gpu down

ps:  ## Show service health
	$(COMPOSE) ps

logs:  ## Tail logs
	$(COMPOSE) logs -f --tail=100

pull:  ## Pull Ollama models (OLLAMA_MODELS="qwen2.5:0.5b llama3.2:1b")
	$(COMPOSE) run --rm model-puller

smoke:  ## One request through the gateway
	curl -s http://localhost:4000/v1/chat/completions -H 'Content-Type: application/json' \
	  -d '{"model":"fast","messages":[{"role":"user","content":"Say hello in five words."}],"max_tokens":32}'

bench:  ## Benchmark models through the running gateway
	for m in $(MODELS); do $(PYTHON) -m openllm bench --base-url http://localhost:4000/v1 --model $$m \
	  --registry-name $$m --backend gateway --wait --out results/gateway/$$m.json; done

bench-cpu:  ## Benchmark GGUF models directly with a local llama-server binary
	scripts/bench_cpu.sh $(MODELS)

report:  ## Rebuild docs/ charts and the README table from results/
	$(PYTHON) -m openllm report

lint:  ## Ruff lint and format check
	ruff check . && ruff format --check .

test:  ## Unit tests
	$(PYTHON) -m pytest -q

tf-check:  ## terraform fmt + validate for every environment
	terraform fmt -recursive -check deploy/terraform
	for d in deploy/terraform/envs/*; do (cd $$d && terraform init -backend=false -input=false >/dev/null && terraform validate); done

helm-check:  ## Lint and render the chart
	helm lint deploy/helm/open-llm && helm template t deploy/helm/open-llm >/dev/null

check: lint test tf-check helm-check  ## Everything CI runs
	$(PYTHON) -m openllm gateway --check
	$(COMPOSE) config -q
