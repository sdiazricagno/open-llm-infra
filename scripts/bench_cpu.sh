#!/usr/bin/env bash
# Benchmark registry models on CPU with llama.cpp's OpenAI-compatible server.
# Usage: LLAMA_SERVER=/path/to/llama-server MODELS_DIR=./models scripts/bench_cpu.sh qwen2.5-0.5b llama3.2-1b
set -euo pipefail

LLAMA_SERVER="${LLAMA_SERVER:-llama-server}"
MODELS_DIR="${MODELS_DIR:-./models}"
RESULTS_DIR="${RESULTS_DIR:-./results}"
PORT="${PORT:-18080}"
THREADS="${THREADS:-$(nproc)}"
PARALLEL="${PARALLEL:-4}"
CTX="${CTX:-8192}"
PYTHON="${PYTHON:-python}"
CONCURRENCY="${CONCURRENCY:-1 2 4}"
REQUESTS="${REQUESTS:-8}"
MAX_TOKENS="${MAX_TOKENS:-128}"

mkdir -p "$RESULTS_DIR" "$MODELS_DIR"

for name in "$@"; do
  file=$($PYTHON -c "from openllm.registry import load_registry; print(load_registry().get('$name').gguf.file)")
  url=$($PYTHON -c "from openllm.registry import load_registry; print(load_registry().get('$name').gguf.url)")
  [[ -f "$MODELS_DIR/$file" ]] || curl -fL --retry 3 -o "$MODELS_DIR/$file" "$url"

  "$LLAMA_SERVER" -m "$MODELS_DIR/$file" --host 127.0.0.1 --port "$PORT" -t "$THREADS" \
    --parallel "$PARALLEL" -c "$CTX" --metrics > "$RESULTS_DIR/$name.server.log" 2>&1 &
  pid=$!
  trap 'kill $pid 2>/dev/null || true' EXIT

  $PYTHON -m openllm bench --base-url "http://127.0.0.1:$PORT/v1" --model "$name" --registry-name "$name" \
    --backend "llama.cpp (CPU, Q4_K_M)" --wait --concurrency $CONCURRENCY --requests "$REQUESTS" \
    --max-tokens "$MAX_TOKENS" --out "$RESULTS_DIR/$name.json"

  kill "$pid"
  wait "$pid" 2>/dev/null || true
  trap - EXIT
done
