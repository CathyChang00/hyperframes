"""Expand a selection (named plan and/or explicit axes) into a flat list of cells.

A cell is the minimal unit of work: (case, env, model, repeat). For the single-framework
routing MVP every (model) is valid, so there is no n/a skipping yet — that hook lands with
the second harness.
"""
import os

from core import load_jsonl, dataset_dir


def load_cases(dataset, case_ids=None, tags=None):
    cases = load_jsonl(os.path.join(dataset_dir(dataset), "cases.jsonl"))
    if case_ids:
        want = set(case_ids)
        cases = [c for c in cases if c["id"] in want]
    if tags:
        want = set(tags)
        cases = [c for c in cases if want & set(c.get("tags", [])) or c.get("category") in want]
    return cases


def expand(selection):
    """selection: {dataset, models[], envs[], cases(list|None), tags(list|None), repeats}"""
    cases = load_cases(selection["dataset"], selection.get("cases"), selection.get("tags"))
    cells = []
    for case in cases:
        for env in selection["envs"]:
            for model in selection["models"]:
                for rep in range(1, int(selection["repeats"]) + 1):
                    cells.append({
                        "case": case,
                        "env": env,
                        "model": model,
                        "repeat": rep,
                        "key": f'{case["id"]}__{env}__{model}__r{rep}',
                    })
    return cells
