#!/bin/bash
# Quick benchmark script: pass target dir, get token savings report

set -e

if [ $# -eq 0 ]; then
    echo "Usage: ./benchmarks/run_benchmark.sh <target_dir|@path> [--models model1 model2 ...]"
    echo ""
    echo "Examples:"
    echo "  ./benchmarks/run_benchmark.sh ./src"
    echo "  ./benchmarks/run_benchmark.sh ~/my_project --models claude-opus-4-7 claude-sonnet-4-6"
    echo "  ./benchmarks/run_benchmark.sh @~/my_project  (@ syntax supported)"
    echo ""
    echo "Output: benchmarks/results/benchmark_*.json"
    exit 1
fi

TARGET_DIR="$1"
# Remove @ prefix if present
TARGET_DIR="${TARGET_DIR#@}"
shift

# Default models
MODELS=(claude-opus-4-7 claude-sonnet-4-6)

# Parse optional models
if [ "$1" == "--models" ]; then
    shift
    MODELS=()
    while [ $# -gt 0 ] && [[ "$1" != -* ]]; do
        MODELS+=("$1")
        shift
    done
fi

echo "🔍 Benchmarking target: $TARGET_DIR"
echo "📊 Models: ${MODELS[@]}"
echo ""

# Find venv
if [ -d "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "✓ Activated venv"
fi

# Run benchmark
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python "$SCRIPT_DIR/benchmark_runner.py" "$TARGET_DIR" \
    --output-dir "$SCRIPT_DIR/results" \
    --models "${MODELS[@]}"

# List latest result
LATEST=$(ls -t "$SCRIPT_DIR/results"/benchmark_*.json 2>/dev/null | head -1)
if [ -n "$LATEST" ]; then
    echo ""
    echo "📈 Analyzing results..."
    python "$SCRIPT_DIR/analyze_results.py" "$LATEST"
    echo ""
    echo "✓ Full results: $LATEST"
fi
