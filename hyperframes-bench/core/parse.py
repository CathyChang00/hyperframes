"""Parse a Claude Code stream-json trace into a small, stable dict.

This is the ONE seam between an agent framework's native log and the oracles. The
oracles read this dict; they never touch raw stream-json. When a second framework
arrives, write another parser that emits this same shape — that, not a directory of
harness ceremony, is all the abstraction a single-framework MVP needs.

stream-json = one JSON object per line. We care about:
  - assistant.message.content[] blocks: tool_use (esp. name=="Skill") and text
  - result line: subtype / is_error / num_turns / total_cost_usd / result(=final text)

Emitted shape:
  {
    "skills_invoked": [str, ...],   # every Skill tool_use, in call order (leading "/" stripped)
    "tools_used":     [str, ...],   # every tool name, in call order
    "first_skill":    str | None,   # first Skill invoked (router-first uses this)
    "texts":          [str, ...],   # assistant text blocks
    "final_text":     str,          # result.result if present else last assistant text
    "turns":          int | None,
    "cost_usd":       float | None,
    "subtype":        str | None,   # "success" | "error_max_turns" | ...
    "error":          bool,         # True only for NON-max-turns hard errors
    "env_setup_failed": bool,       # runner wrote an ENV_SETUP_FAILED sentinel instead of a trace
  }
"""
import json
import sys

# A max-turns stop is EXPECTED (we cap turns so the agent routes then stops) — not an error.
_OK_SUBTYPES = {None, "success", "error_max_turns"}


def parse_trace(path):
    skills, tools, texts = [], [], []
    turns = cost = subtype = None
    error = False
    result_text = None

    try:
        with open(path) as f:
            head = f.read()
    except FileNotFoundError:
        return None

    if "ENV_SETUP_FAILED" in head and head.strip().startswith("ENV_SETUP_FAILED"):
        return {"skills_invoked": [], "tools_used": [], "first_skill": None,
                "texts": [], "final_text": head.strip(), "turns": None, "cost_usd": None,
                "subtype": None, "error": True, "env_setup_failed": True}

    for line in head.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = obj.get("type")
        if t == "assistant":
            for block in obj.get("message", {}).get("content", []):
                bt = block.get("type")
                if bt == "tool_use":
                    name = block.get("name", "")
                    tools.append(name)
                    if name == "Skill":
                        inp = block.get("input") or {}
                        skill = inp.get("skill") or inp.get("command") or inp.get("name")
                        if skill:
                            skills.append(str(skill).lstrip("/"))
                elif bt == "text":
                    txt = (block.get("text") or "").strip()
                    if txt:
                        texts.append(txt)
        elif t == "result":
            turns = obj.get("num_turns", turns)
            cost = obj.get("total_cost_usd", obj.get("cost_usd", cost))
            subtype = obj.get("subtype", subtype)
            if isinstance(obj.get("result"), str):
                result_text = obj["result"]
            if obj.get("is_error") and subtype not in _OK_SUBTYPES:
                error = True

    return {
        "skills_invoked": skills,
        "tools_used": tools,
        "first_skill": skills[0] if skills else None,
        "texts": texts,
        "final_text": result_text if result_text else (texts[-1] if texts else ""),
        "turns": turns,
        "cost_usd": cost,
        "subtype": subtype,
        "error": error,
        "env_setup_failed": False,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.stderr.write("usage: parse.py <trace.jsonl>\n")
        sys.exit(2)
    print(json.dumps(parse_trace(sys.argv[1]), indent=2, ensure_ascii=False))
