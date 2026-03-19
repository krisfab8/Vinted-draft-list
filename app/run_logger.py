"""
Run logger — structured per-listing JSONL logs for observability.

Log files:
  data/run_logs.jsonl     — one entry per listing run
  data/corrections.jsonl  — one entry per manual field correction
"""
import json
from collections import Counter
from pathlib import Path

_DATA_DIR = Path(__file__).parent.parent / "data"
LOG_PATH = _DATA_DIR / "run_logs.jsonl"
CORRECTIONS_PATH = _DATA_DIR / "corrections.jsonl"

# Error taxonomy categories
ERROR_CATEGORIES = [
    "brand",
    "category",
    "material",
    "pricing",
    "size",
    "condition",
    "title_quality",
]


def write_run_log(entry: dict) -> None:
    """Append a run log entry to run_logs.jsonl."""
    _DATA_DIR.mkdir(exist_ok=True)
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def read_run_logs() -> list[dict]:
    """Read all run log entries."""
    if not LOG_PATH.exists():
        return []
    entries = []
    for line in LOG_PATH.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def write_correction(entry: dict) -> None:
    """Append a correction event to corrections.jsonl."""
    _DATA_DIR.mkdir(exist_ok=True)
    with CORRECTIONS_PATH.open("a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def read_corrections() -> list[dict]:
    """Read all correction events."""
    if not CORRECTIONS_PATH.exists():
        return []
    entries = []
    for line in CORRECTIONS_PATH.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def summarize_logs(logs: list[dict] | None = None) -> dict:
    """Compute summary statistics from run logs."""
    if logs is None:
        logs = read_run_logs()
    if not logs:
        return {"total_runs": 0}

    total = len(logs)

    costs = [l["cost_gbp_total"] for l in logs if l.get("cost_gbp_total")]
    avg_cost = sum(costs) / len(costs) if costs else 0

    latencies = [l["latency_ms"] for l in logs if l.get("latency_ms")]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0

    reread_counts = [l.get("rereads_count", 0) for l in logs]
    avg_rereads = sum(reread_counts) / total

    all_warnings: list[str] = []
    for l in logs:
        all_warnings.extend(l.get("warnings", []))
    warning_counts = Counter(all_warnings).most_common(10)

    price_matches = [l for l in logs if l.get("price_memory_match_level")]
    price_hit_rate = len(price_matches) / total if total else 0
    match_level_counts = Counter(
        l.get("price_memory_match_level") for l in price_matches
    ).most_common()

    escalated = sum(1 for l in logs if l.get("escalated"))

    return {
        "total_runs": total,
        "avg_cost_gbp": round(avg_cost, 5),
        "avg_latency_ms": round(avg_latency),
        "avg_rereads_per_item": round(avg_rereads, 2),
        "escalation_rate": round(escalated / total, 3),
        "price_memory_hit_rate": round(price_hit_rate, 3),
        "price_memory_match_levels": dict(match_level_counts),
        "top_warnings": dict(warning_counts),
    }
