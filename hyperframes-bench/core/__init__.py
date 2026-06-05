"""hyperframes-bench engine.

Primary consumer is an AGENT driving routing tests via the `bench` CLI — so the
engine favours a discoverable, machine-readable contract (`bench list`,
`results.jsonl`, `aggregate.json`) and treats every failure as data (a verdict),
never a crash mid-matrix.

This package holds the framework/oracle-agnostic core. The only thing that knows
about Claude Code's native log format is `core/parse.py`; oracles read the small
dict it emits, never the raw stream-json.
"""
import os
import json

CORE_DIR = os.path.dirname(os.path.abspath(__file__))
BENCH_ROOT = os.path.dirname(CORE_DIR)            # hyperframes-bench/
REPO_ROOT = os.path.dirname(BENCH_ROOT)           # hyperframes/   (the "self" skills source)


def load_config():
    with open(os.path.join(BENCH_ROOT, "bench.config.json")) as f:
        return json.load(f)


def load_json(path):
    with open(path) as f:
        return json.load(f)


def load_jsonl(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def dataset_dir(name):
    return os.path.join(BENCH_ROOT, "datasets", name)


def env_file(name):
    return os.path.join(BENCH_ROOT, "envs", f"{name}.json")


def plan_file(name):
    return os.path.join(BENCH_ROOT, "plans", f"{name}.json")


def cache_dir():
    return os.path.join(BENCH_ROOT, ".cache")
