"""Single-cell execution + env preparation + the run loop.

Mirrors how scripts/test-product-launch-video.sh launches LOCAL hyperframes (install the
repo's skills via `npx skills add <repo>`), and uses the plain `npx skills add
heygen-com/hyperframes[#ref]` form for ONLINE — the two run paths are just two `source`
values in an env config, nothing more.

Design commitments:
  * errors are data: a failed install / missing `claude` / timeout becomes a verdict row,
    never an exception that aborts the matrix.
  * content-addressed cache: a cell is re-used only if its prompt_hash (prompt+env+model)
    matches — edit a case and it re-runs automatically, no manual cache-busting.
  * env templates are built once and cloned per cell, so every cell gets a fresh workspace.
"""
import os
import json
import shutil
import hashlib
import tempfile
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

from core import (BENCH_ROOT, REPO_ROOT, load_json, load_jsonl, env_file, cache_dir)
from core import parse as parse_mod
from core import score as score_mod

LAUNCH_SH = os.path.join(BENCH_ROOT, "core", "launch.sh")
CELL_TIMEOUT_S = int(os.environ.get("BENCH_CELL_TIMEOUT", "300"))


# ---------------------------------------------------------------- env preparation

def resolve_source(entry):
    src = entry["source"]
    if src == "self":
        return REPO_ROOT
    ref = entry.get("ref")
    return f"{src}#{ref}" if ref else src


def _prune_meta(template_dir):
    meta = os.path.join(REPO_ROOT, "skills", "_meta")
    if os.path.isdir(meta):
        for name in os.listdir(meta):
            shutil.rmtree(os.path.join(template_dir, ".claude", "skills", name), ignore_errors=True)


def _installed_skills(template_dir):
    d = os.path.join(template_dir, ".claude", "skills")
    if not os.path.isdir(d):
        return []
    return sorted(n for n in os.listdir(d)
                  if not n.startswith(".") and os.path.isdir(os.path.join(d, n)))


def prepare_env(env_name, rebuild=True):
    """Build one installed-skills template for an env. By DEFAULT rebuilds from scratch on
    every run — re-installs the LOCAL working-tree skills AND re-fetches the remote competitor
    skills (remotion-dev/remotion, browser-use/video-use) so every run is tested against the
    LATEST of all sources. The old marker cache never invalidated, so a stale local edit or an
    upstream competitor update would silently leak. Pass rebuild=False (`bench run --reuse-env`)
    to reuse the last-built template for fast iteration. Returns {dir, installed[], ok, cached,
    error}."""
    env_cfg = load_json(env_file(env_name))
    tdir = os.path.join(cache_dir(), "templates", env_name)
    marker = os.path.join(tdir, ".bench-skills.txt")

    if not rebuild and os.path.exists(marker):
        installed = [s for s in open(marker).read().split("\n") if s]
        return {"dir": tdir, "installed": installed, "ok": True, "cached": True, "error": None}

    shutil.rmtree(tdir, ignore_errors=True)
    os.makedirs(tdir, exist_ok=True)
    for entry in env_cfg.get("install", []):
        source = resolve_source(entry)
        skill = entry.get("skill", "*")
        cmd = ["npx", "--yes", "skills", "add", source,
               "--skill", skill, "--agent", "claude-code", "--yes"]
        r = subprocess.run(cmd, cwd=tdir, capture_output=True, text=True)
        if r.returncode != 0:
            return {"dir": None, "installed": [], "ok": False, "cached": False,
                    "error": f"`skills add {source}` failed:\n{(r.stderr or r.stdout)[-800:]}"}

    _prune_meta(tdir)
    installed = _installed_skills(tdir)
    with open(marker, "w") as f:
        f.write("\n".join(installed) + ("\n" if installed else ""))
    return {"dir": tdir, "installed": installed, "ok": True, "cached": False, "error": None}


# ---------------------------------------------------------------- prompt rendering

def _fixtures_registry():
    path = os.path.join(BENCH_ROOT, "fixtures", "assets.registry.jsonl")
    if not os.path.exists(path):
        return {}
    return {e["asset_id"]: e for e in load_jsonl(path)}


def render_prompt(case, registry=None):
    """Turn typed inputs into the surface text a user would actually send. For routing only
    the surface handle matters (a URL string, 'an attached pdf'), not frozen file content."""
    registry = registry if registry is not None else _fixtures_registry()
    parts = []
    for inp in case.get("inputs", []):
        t = inp.get("type")
        if t in ("text", "link"):
            v = inp.get("value", "")
            if v:
                parts.append(v)
        elif t in ("pdf", "image", "video", "doc", "code", "file"):
            name = inp.get("value")
            if not name and inp.get("asset_id"):
                entry = registry.get(inp["asset_id"], {})
                name = entry.get("name", inp["asset_id"])
            label = {"image": "attached image", "video": "attached video"}.get(t, "attached file")
            parts.append(f"[{label}: {name}]")
    return " ".join(parts).strip()


def stage_assets(case, registry, workspace):
    """Copy each fixture an input references (by asset_id) into the workspace root as its
    `name`, so the agent actually finds the asset the prompt mentions instead of stalling on
    'I don't see it in the working directory'. Routing reads the surface handle + file type;
    the file just has to exist. Returns the staged filenames."""
    staged = []
    for inp in case.get("inputs", []):
        entry = registry.get(inp.get("asset_id")) if inp.get("asset_id") else None
        if not entry:
            continue
        src = os.path.join(BENCH_ROOT, "fixtures", entry["path"])
        if os.path.exists(src):
            shutil.copy(src, os.path.join(workspace, entry["name"]))
            staged.append(entry["name"])
    return staged


def _prompt_hash(prompt, env, model):
    return hashlib.sha256(f"{prompt}|{env}|{model}".encode()).hexdigest()[:16]


# ---------------------------------------------------------------- one cell

def run_cell(cell, env_state, cfg, out_dir, dry_run=False, force=False, keep=False, registry=None):
    case = cell["case"]
    cell_dir = os.path.join(out_dir, "cells", cell["key"])
    os.makedirs(cell_dir, exist_ok=True)
    prompt = render_prompt(case, registry)
    phash = _prompt_hash(prompt, cell["env"], cell["model"])
    result_path = os.path.join(cell_dir, "result.json")

    # content-addressed cache: reuse only if the prompt_hash matches
    if not force and os.path.exists(result_path):
        prev = load_json(result_path)
        if prev.get("prompt_hash") == phash and prev.get("status") == "ok":
            prev["cached"] = True
            return prev

    with open(os.path.join(cell_dir, "prompt.rendered.txt"), "w") as f:
        f.write(prompt + "\n")

    base = {
        "key": cell["key"], "case": case["id"], "category": case.get("category"),
        "tags": case.get("tags", []), "dataset": cell.get("dataset", "routing"),
        "env": cell["env"], "model": cell["model"], "repeat": cell["repeat"],
        "expected": case.get("expect", {}), "prompt_hash": phash,
        "installed": env_state.get("installed", []),
        "paths": {"prompt": f"cells/{cell['key']}/prompt.rendered.txt",
                  "raw": f"cells/{cell['key']}/raw.jsonl",
                  "trace": f"cells/{cell['key']}/trace.json"},
    }

    # env failed to install → every cell of this env is a verdict, not a crash
    if not env_state.get("ok"):
        base.update(status="env-setup-failed", skills_invoked=[], cost_usd=None, turns=None,
                    oracles=score_mod.run_oracles({"env_setup_failed": True, "skills_invoked": [],
                                                    "tools_used": [], "first_skill": None, "texts": [],
                                                    "final_text": ""}, case, env_state.get("installed", []), cfg))
        _write_cell(cell_dir, base, None)
        return base

    if dry_run:
        base.update(status="not-run", skills_invoked=[], cost_usd=None, turns=None, oracles={})
        _write_cell(cell_dir, base, None)
        return base

    # clone the env template into a fresh workspace, launch the agent there
    workspace = tempfile.mkdtemp(prefix="bench.")
    try:
        shutil.copytree(env_state["dir"], workspace, dirs_exist_ok=True)
        stage_assets(case, registry, workspace)   # drop referenced fixture files into cwd
        model_id = cfg["models"][cell["model"]]
        try:
            proc = subprocess.run(["bash", LAUNCH_SH, model_id, prompt], cwd=workspace,
                                  capture_output=True, text=True, stdin=subprocess.DEVNULL,
                                  timeout=CELL_TIMEOUT_S)
            raw, err = proc.stdout, proc.stderr
        except subprocess.TimeoutExpired:
            raw, err = "", f"TIMEOUT after {CELL_TIMEOUT_S}s"
        except FileNotFoundError:
            raw, err = "", "ENV_SETUP_FAILED: `claude` not on PATH"
    finally:
        if not keep:
            shutil.rmtree(workspace, ignore_errors=True)

    with open(os.path.join(cell_dir, "raw.jsonl"), "w") as f:
        f.write(raw or "")
    if err:
        with open(os.path.join(cell_dir, "stderr.log"), "w") as f:
            f.write(err)

    parsed = parse_mod.parse_trace(os.path.join(cell_dir, "raw.jsonl")) or {
        "skills_invoked": [], "tools_used": [], "first_skill": None, "texts": [],
        "final_text": "", "turns": None, "cost_usd": None, "error": True, "env_setup_failed": False}
    if not raw and "not on PATH" in (err or ""):
        parsed["env_setup_failed"] = True

    oracles = score_mod.run_oracles(parsed, case, env_state.get("installed", []), cfg)
    base.update(status="ok", skills_invoked=parsed.get("skills_invoked", []),
                cost_usd=parsed.get("cost_usd"), turns=parsed.get("turns"), oracles=oracles)
    _write_cell(cell_dir, base, parsed)
    return base


def _write_cell(cell_dir, result, parsed):
    if parsed is not None:
        with open(os.path.join(cell_dir, "trace.json"), "w") as f:
            json.dump(parsed, f, indent=2, ensure_ascii=False)
    with open(os.path.join(cell_dir, "verdict.json"), "w") as f:
        json.dump(result.get("oracles", {}), f, indent=2, ensure_ascii=False)
    with open(os.path.join(cell_dir, "result.json"), "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------- the run loop

def _git_describe(path):
    def g(args):
        try:
            return subprocess.run(["git", "-C", path, *args], capture_output=True, text=True).stdout.strip()
        except Exception:
            return ""
    return {"commit": g(["rev-parse", "--short", "HEAD"]), "branch": g(["rev-parse", "--abbrev-ref", "HEAD"])}


def run_matrix(cells, cfg, out_dir, label="run", concurrency=None, dry_run=False, force=False,
               keep=False, rebuild_env=True):
    os.makedirs(os.path.join(out_dir, "cells"), exist_ok=True)
    concurrency = concurrency or cfg.get("concurrency", 4)
    registry = _fixtures_registry()

    # prepare each unique env template once (serially — shared, mustn't race). Rebuilds fresh
    # by default so every run pulls the latest local + competitor skills (see prepare_env).
    envs = sorted({c["env"] for c in cells})
    env_states = {}
    for env in envs:
        st = prepare_env(env, rebuild=rebuild_env)
        env_states[env] = st
        tag = "reused" if st.get("cached") else ("FAILED" if not st["ok"] else "built fresh")
        print(f"  env {env}: {tag} ({len(st.get('installed', []))} skills)"
              + (f"\n    {st['error']}" if st.get("error") else ""))

    git = _git_describe(REPO_ROOT)
    manifest = {"label": label, "out_dir": out_dir, "cells": len(cells),
                "models": sorted({c["model"] for c in cells}), "envs": envs,
                "dry_run": dry_run, "local_hf": git,
                "env_installed": {e: env_states[e].get("installed", []) for e in envs}}
    with open(os.path.join(out_dir, "run_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    results = []
    if dry_run or concurrency <= 1:
        for c in cells:
            results.append(run_cell(c, env_states[c["env"]], cfg, out_dir, dry_run, force, keep, registry))
            print(f"  · {results[-1]['key']}  [{results[-1]['status']}]")
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            futs = {ex.submit(run_cell, c, env_states[c["env"]], cfg, out_dir, dry_run, force, keep, registry): c
                    for c in cells}
            for fut in as_completed(futs):
                r = fut.result()
                results.append(r)
                rv = (r.get("oracles", {}).get("route", {}) or {}).get("verdict", r["status"])
                print(f"  · {r['key']}  [{rv}]")

    results.sort(key=lambda r: r["key"])
    with open(os.path.join(out_dir, "results.jsonl"), "w") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    aggregate = score_mod.aggregate(results, cfg)
    with open(os.path.join(out_dir, "aggregate.json"), "w") as f:
        json.dump(aggregate, f, indent=2, ensure_ascii=False)

    from core import report as report_mod
    report_mod.write_report(out_dir, results, aggregate, cfg, manifest)
    return {"results": results, "aggregate": aggregate, "manifest": manifest}
