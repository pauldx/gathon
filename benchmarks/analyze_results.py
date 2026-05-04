#!/usr/bin/env python3
"""Analyze benchmark results: compare pre/post savings across models and queries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_results(result_file: str) -> dict:
    """Load benchmark result JSON."""
    with open(result_file) as f:
        return json.load(f)


def format_table(rows: list[list[str]], headers: list[str], widths: list[int] | None = None) -> str:
    """Format rows as ASCII table."""
    if not widths:
        widths = [max(len(str(h)), max((len(str(cell)) for cell in col), default=0))
                  for h, col in zip(headers, zip(*([headers] + rows)))]

    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    header_row = "|" + "|".join(f" {h:^{w}} " for h, w in zip(headers, widths)) + "|"

    lines = [sep, header_row, sep]
    for row in rows:
        lines.append("|" + "|".join(f" {str(cell):^{w}} " for cell, w in zip(row, widths)) + "|")
    lines.append(sep)

    return "\n".join(lines)


def analyze_by_query(results: dict) -> None:
    """Analyze savings by query."""
    pre_by_query = {}
    post_by_query = {}

    for result in results.get("pre_graph", []):
        qid = result["query_id"]
        total = result["input_tokens"] + result["output_tokens"]
        pre_by_query.setdefault(qid, []).append(total)

    for result in results.get("post_graph", []):
        qid = result["query_id"]
        total = result["input_tokens"] + result["output_tokens"]
        post_by_query.setdefault(qid, []).append(total)

    rows = []
    for qid in sorted(pre_by_query.keys()):
        pre_avg = sum(pre_by_query[qid]) / len(pre_by_query[qid])
        post_avg = sum(post_by_query.get(qid, [0])) / (len(post_by_query.get(qid, [1])) or 1)
        savings = pre_avg - post_avg
        savings_pct = (savings / pre_avg * 100) if pre_avg > 0 else 0

        rows.append([
            qid,
            f"{int(pre_avg):,}",
            f"{int(post_avg):,}",
            f"{int(savings):,}",
            f"{savings_pct:.1f}%",
        ])

    print("\nSavings by Query:")
    print(format_table(
        rows,
        ["Query", "Pre (avg)", "Post (avg)", "Saved", "% Saved"],
    ))


def analyze_by_model(results: dict) -> None:
    """Analyze savings by Claude model."""
    pre_by_model = {}
    post_by_model = {}

    for result in results.get("pre_graph", []):
        model = result.get("model", "unknown")
        pre_by_model.setdefault(model, []).append(result["input_tokens"])

    for result in results.get("post_graph", []):
        model = result.get("model", "unknown")
        post_by_model.setdefault(model, []).append(result["input_tokens"])

    rows = []
    for model in sorted(pre_by_model.keys()):
        pre_total = sum(pre_by_model[model])
        post_total = sum(post_by_model.get(model, [0]))
        savings = pre_total - post_total

        # Get cost savings
        cost_by_model = results.get("savings", {}).get("cost_by_model", {})
        model_costs = cost_by_model.get(model, {})

        rows.append([
            model.split("-")[-1],  # Shorter name
            f"{pre_total:,}",
            f"{post_total:,}",
            f"{savings:,}",
            f"${model_costs.get('pre_cost', 0):.4f}",
            f"${model_costs.get('post_cost', 0):.4f}",
            f"${model_costs.get('savings', 0):.4f}",
            f"{model_costs.get('savings_pct', 0):.1f}%",
        ])

    print("\nSavings by Model:")
    print(format_table(
        rows,
        ["Model", "Pre Tokens", "Post Tokens", "Token Saved", "Pre Cost", "Post Cost", "Cost Saved", "% Saved"],
        widths=[12, 12, 12, 12, 12, 12, 12, 10],
    ))


def analyze_graph_efficiency(results: dict) -> None:
    """Show graph building efficiency."""
    build_ms = results.get("graph_build_time_ms", 0)
    nodes = results.get("graph_stats", {}).get("total_nodes", 0)
    edges = results.get("graph_stats", {}).get("total_edges", 0)
    token_savings = results.get("savings", {}).get("token_savings", 0)

    # Cost per token saved
    cost_saved = results.get("savings", {}).get("cost_by_model", {})
    total_cost_saved = sum(m.get("savings", 0) for m in cost_saved.values())

    print("\nGraph Efficiency:")
    print(f"  Build time: {build_ms:,} ms")
    print(f"  Nodes: {nodes:,}")
    print(f"  Edges: {edges:,}")
    print(f"  Token savings: {token_savings:,}")
    if nodes > 0:
        print(f"  Tokens saved per node: {token_savings / nodes:.1f}")
    print(f"  Total cost saved: ${total_cost_saved:.4f}")


def analyze_results(result_file: str) -> None:
    """Run full analysis."""
    results = load_results(result_file)

    print("\n" + "=" * 100)
    print("BENCHMARK ANALYSIS".center(100))
    print("=" * 100)
    print(f"\nFile: {result_file}")
    print(f"Target: {results['target_dir']}")
    print(f"Timestamp: {results['timestamp']}")

    # Summary
    savings = results.get("savings", {})
    print(f"\nOverall Summary:")
    print(f"  Total tokens before: {savings.get('total_tokens_pre', 0):,}")
    print(f"  Total tokens after:  {savings.get('total_tokens_post', 0):,}")
    print(f"  Tokens saved:        {savings.get('token_savings', 0):,} ({savings.get('token_savings_pct', 0):.1f}%)")

    analyze_by_query(results)
    analyze_by_model(results)
    analyze_graph_efficiency(results)

    print("\n" + "=" * 100 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Analyze benchmark results")
    parser.add_argument("result_file", help="Benchmark result JSON file")
    args = parser.parse_args()

    if not Path(args.result_file).exists():
        print(f"Error: {args.result_file} not found")
        return 1

    analyze_results(args.result_file)
    return 0


if __name__ == "__main__":
    exit(main())
