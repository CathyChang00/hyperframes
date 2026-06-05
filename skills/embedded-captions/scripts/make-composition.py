#!/usr/bin/env python3
"""
Compile plan.json + template → index.html for hyperframes render.

Used in TEMPLATE MODE only. Custom mode skips this script and writes
index.html by hand (see modes/custom/skeleton.html + examples/).

Usage:
  python make-composition.py <project-dir>

Reads:  <project-dir>/plan.json
Writes: <project-dir>/index.html

Plan.json schema (template mode):

{
  "mode": "template",                      // optional, defaults to "template"
  "template": "memory-wall",               // dir name in modes/template/
  "duration": 8.04,
  "fps": 24,
  "width": 1280, "height": 720,

  // Layout (agent decides per scene). Field names depend on template.
  // Common patterns:
  //   memory-wall: "plane" with top/right/width/height/rotateY/rotateX
  //   champion:    "plane" with top/left/...; "crown_top"
  //   portrait-header: "header" with top/height; "crown_top"
  "plane": { "top": 90, "right": 30, "width": 720, "height": 520,
             "rotateY": -13, "rotateX": 1 },

  "font_scale": 1.0,                       // multiplies template's locked sizes

  "groups": [
    {
      "id": "cg-0",
      "slot": "1",                         // template-specific slot name
                                           //   memory-wall: 1/2/3/4
                                           //   champion/portrait-header: intro/phrase/emph/dream
                                           //   becomes class="cap-<slot>"
      "tone": "soft",                      // "soft" | "present" — drives motion
      "in": 0.10, "out": 4.85,
      "words": [{"text": "Some", "start": 0.24, "end": 0.44}, ...]
    }
  ],

  "crown_group": null                      // or {id, in, out, words} for templates
                                           //   that support a crown plane
}
"""
import os, sys, json, pathlib
import html as htmllib

SCRIPT_DIR = pathlib.Path(__file__).parent
SKILL_ROOT = SCRIPT_DIR.parent
TEMPLATES_NEW = SKILL_ROOT / "modes" / "template"
TEMPLATES_OLD = SKILL_ROOT / "templates"  # legacy fallback


def _hex_luminance(hex_color: str) -> float:
    """Approx perceived luminance 0..1 from a #rrggbb string."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r, g, b = int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255
    except ValueError:
        return 0.9
    return 0.299 * r + 0.587 * g + 0.114 * b


def _default_text_shadow(cap_color: str) -> str:
    """Pick a sensible text-shadow based on text-color luminance."""
    lum = _hex_luminance(cap_color)
    if lum < 0.45:
        # Dark text (assumed to be placed on a bright bg). A bright HALO
        # around dark letters would fill the letter interior via the blur
        # and make dark text look light. So we use a SOFT DARK DROP only,
        # keeping the letter fill pure and legible.
        return "0 2px 6px rgba(0, 0, 0, 0.28)"
    # Light text (default) — warm glow + dark drop for depth on mid/dark bg.
    return "0 0 18px rgba(255, 220, 170, 0.55), 0 3px 8px rgba(0, 0, 0, 0.85)"


def _default_text_filter(cap_color: str) -> str:
    """Filter: brightness boost helps light text pop; HURTS dark text."""
    lum = _hex_luminance(cap_color)
    if lum < 0.45:
        # No brightness boost for dark text — it'd shift toward neutral.
        return "contrast(1.08)"
    return "brightness(1.1) contrast(1.05)"


def find_template(name: str) -> pathlib.Path:
    """Locate <name>/template.html in modes/template/, with legacy fallback."""
    new_path = TEMPLATES_NEW / name / "template.html"
    if new_path.exists():
        return new_path
    legacy = TEMPLATES_OLD / f"{name}.html"
    if legacy.exists():
        return legacy
    sys.exit(f"[compile] unknown template: {name} (looked in {new_path} and {legacy})")


def _escape_with_br(text: str) -> str:
    """Escape text but preserve <br> / <br/> for agent-authored line breaks."""
    escaped = htmllib.escape(text)
    # Restore <br> tags from their escaped forms.
    escaped = escaped.replace("&lt;br&gt;", "<br>").replace("&lt;br/&gt;", "<br>").replace("&lt;br /&gt;", "<br>")
    return escaped


def _render_cap(g):
    """Render one caption group as a <div> with word <span>s."""
    slot = g.get("slot", g.get("style", ""))
    layer = g.get("layer", "")
    layer_attr = f' data-layer="{layer}"' if layer else ''
    class_attr = f"cap cap-{slot}" if slot else "cap"
    spans = "\n            ".join(
        f'<span class="w" data-i="{i}">{_escape_with_br(w["text"])}</span>'
        for i, w in enumerate(g["words"])
    )
    return f'<div id="{g["id"]}" class="{class_attr}"{layer_attr}>\n            {spans}\n          </div>'


def build_groups_html(groups, planes=None):
    """Emit groups HTML. If `planes` is provided (dict of plane-id → css),
    each group with a `plane: <id>` field is nested inside that plane's div.
    Groups without a `plane` field stay at stage level (free-mode).
    The plane container owns the spatial layout (flex/grid/absolute anchor).
    """
    if not planes:
        # Free mode (legacy): all caps are direct children of #stage, each
        # with its own position via per-group css.
        return "\n        ".join(_render_cap(g) for g in groups)

    parts = []
    # Emit each plane with its nested caps, in the order planes appear.
    plane_order = list(planes.keys())
    grouped = {pid: [] for pid in plane_order}
    free_caps = []
    for g in groups:
        pid = g.get("plane")
        if pid and pid in grouped:
            grouped[pid].append(g)
        else:
            free_caps.append(g)

    for pid in plane_order:
        inner = "\n          ".join(_render_cap(g) for g in grouped[pid])
        parts.append(
            f'<div id="plane-{pid}" class="plane plane-{pid}">\n          {inner}\n        </div>'
        )
    # Any group not assigned to a plane renders free-mode at stage level.
    for g in free_caps:
        parts.append(_render_cap(g))
    return "\n        ".join(parts)


def build_planes_css(planes):
    """Emit `.plane-<id> { ... }` rules from plan.planes[id].css."""
    if not planes:
        return ""
    rules = []
    for pid, p in planes.items():
        css = (p or {}).get("css", "").strip()
        if css:
            if not css.endswith(";"):
                css += ";"
            rules.append(f"      .plane-{pid} {{ {css} }}")
    return "\n".join(rules)


def build_per_group_css(groups):
    """Generate `#cg-N { ... }` CSS rules from each group's `css` + `scale`.
    Position/layer come from the agent per scene; scale is a multiplier on
    the slot's locked typography size.
    """
    rules = []
    for g in groups:
        parts = []
        scale = g.get("scale")
        if scale is not None:
            parts.append(f"--s: {scale};")
        css = g.get("css", "").strip()
        if css:
            parts.append(css if css.endswith(";") else css + ";")
        if parts:
            rules.append(f'      #{g["id"]} {{ {" ".join(parts)} }}')
    return "\n".join(rules)


def build_groups_json(groups):
    return json.dumps(
        [
            {
                "id": g["id"],
                "in": g["in"],
                "out": g["out"],
                "tone": g.get("tone", "soft"),
                "words": [
                    {"text": w["text"], "start": w["start"], "end": w["end"]}
                    for w in g["words"]
                ],
            }
            for g in groups
        ],
        indent=10,
    )


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: make-composition.py <project-dir>")
    project = pathlib.Path(sys.argv[1]).resolve()
    plan_path = project / "plan.json"
    if not plan_path.exists():
        sys.exit(f"[compile] missing {plan_path}")
    plan = json.load(open(plan_path))

    if plan.get("mode") == "custom":
        sys.exit("[compile] mode=custom — skip this script and hand-write index.html. "
                 "See modes/custom/skeleton.html + examples/.")

    template_name = plan["template"]
    tpl_path = find_template(template_name)
    src = tpl_path.read_text()

    # Geometry placeholders. Templates use whichever ones they need; missing
    # ones in plan.json substitute as empty string (template should default).
    plane = plan.get("plane", {})
    header = plan.get("header", {})

    # Legacy: older plans used "wall_position" for both wall-embed and
    # portrait-header. Map it to both plane and header so templates find it.
    legacy = plan.get("wall_position", {})
    if legacy and not plane:
        plane = dict(legacy)
    if legacy and not header:
        header = {"top": legacy.get("top", 0),
                  "height": legacy.get("height", 0)}

    subs = {
        "DURATION": f"{plan['duration']}",
        "FPS": f"{plan.get('fps', 24)}",
        "WIDTH": f"{plan['width']}",
        "HEIGHT": f"{plan['height']}",
        "FONT_SCALE": f"{plan.get('font_scale', 1.0)}",

        # Plane geometry — template picks what it needs
        "PLANE_TOP":     f"{plane.get('top', 0)}",
        "PLANE_LEFT":    f"{plane.get('left', '')}",
        "PLANE_RIGHT":   f"{plane.get('right', '')}",
        "PLANE_WIDTH":   f"{plane.get('width', 0)}",
        "PLANE_HEIGHT":  f"{plane.get('height', 0)}",
        "ROTATE_Y":      f"{plane.get('rotateY', 0)}",
        "ROTATE_X":      f"{plane.get('rotateX', 0)}",

        # Header strip (portrait-header)
        "HEADER_TOP":    f"{header.get('top', 0)}",
        "HEADER_HEIGHT": f"{header.get('height', 0)}",

        # Crown plane (champion + portrait-header). Support either scalar
        # `crown_top` (legacy) or rich `crown: { top, left, right, align, scale }`
        # for clean-zone crown placement when center would be body-occluded.
        "CROWN_TOP":     f"{(plan.get('crown') or {}).get('top', plan.get('crown_top', plan.get('crown_position', {}).get('top', 440)))}",
        "CROWN_LEFT":    f"{(plan.get('crown') or {}).get('left', 0)}",
        "CROWN_RIGHT":   f"{(plan.get('crown') or {}).get('right', 0)}",
        "CROWN_ALIGN":   f"{(plan.get('crown') or {}).get('align', 'center')}",
        "CROWN_SCALE":   f"{(plan.get('crown') or {}).get('scale', 1.0)}",

        # Legacy alias support — old plans used wall_position
        "WALL_TOP":      f"{plane.get('top', plan.get('wall_position', {}).get('top', 0))}",
        "WALL_LEFT":     f"{plane.get('left', plan.get('wall_position', {}).get('left', ''))}",
        "WALL_RIGHT":    f"{plane.get('right', plan.get('wall_position', {}).get('right', ''))}",
        "WALL_WIDTH":    f"{plane.get('width', plan.get('wall_position', {}).get('width', 0))}",
        "WALL_HEIGHT":   f"{plane.get('height', plan.get('wall_position', {}).get('height', 0))}",
        "WALL_ROTATE_Y": f"{plane.get('rotateY', plan.get('wall_position', {}).get('rotateY', 0))}",
        "WALL_ROTATE_X": f"{plane.get('rotateX', plan.get('wall_position', {}).get('rotateX', 0))}",

        # Default blend / color / text-shadow.
        # text_shadow auto-adapts if cap_color is dark (luminance < 0.4) —
        # swap warm-glow+dark-drop default for a light-halo (helps dark text
        # on bright backgrounds like sunset/sky scenes).
        "BLEND_MODE":    plan.get("blend_mode", "screen"),
        "CAP_COLOR":     plan.get("cap_color", "#fff5df"),
        "TEXT_SHADOW":   plan.get("text_shadow", _default_text_shadow(plan.get("cap_color", "#fff5df"))),
        "TEXT_FILTER":   plan.get("text_filter", _default_text_filter(plan.get("cap_color", "#fff5df"))),

        "GROUPS_HTML":   build_groups_html(plan["groups"], plan.get("planes")),
        "PLANES_CSS":    build_planes_css(plan.get("planes")),
        "CUSTOM_CSS":    build_per_group_css(plan["groups"]),
        "GROUPS_JSON":   build_groups_json(plan["groups"]),
    }

    if plan.get("crown_group"):
        cg = plan["crown_group"]
        crown_layer = cg.get("layer", "")
        crown_layer_attr = f' data-layer="{crown_layer}"' if crown_layer else ''
        spans = "\n          ".join(
            f'<span class="w" data-i="{i}">{htmllib.escape(w["text"])}</span>'
            for i, w in enumerate(cg["words"])
        )
        subs["CROWN_HTML"] = (
            f'<div id="{cg["id"]}" class="cap cap-crown"{crown_layer_attr}>\n          {spans}\n        </div>'
        )
        subs["CROWN_JSON"] = json.dumps({
            "id": cg["id"],
            "in": cg["in"],
            "out": cg["out"],
            "tone": cg.get("tone", "present"),
            "words": [
                {"text": w["text"], "start": w["start"], "end": w["end"]}
                for w in cg["words"]
            ],
        }, indent=10)
    else:
        subs["CROWN_HTML"] = ""
        subs["CROWN_JSON"] = "null"

    out = src
    for k, v in subs.items():
        out = out.replace("{{" + k + "}}", v)

    (project / "index.html").write_text(out)
    print(f"[compile] template={template_name} → {project/'index.html'}")

    # Per-group FG: if ANY group has `layer: "fg"`, emit a second HTML
    # index_fg.html where:
    #   - <html class="fg-only"> triggers CSS overrides that:
    #       * hide #a-roll (background goes black)
    #       * hide caps without data-layer="fg"
    #   - The a-roll + bg caps render through index.html (normal pass);
    #   - The fg caps render through index_fg.html on black bg;
    #   - render-and-composite.sh composites: bg_plus_caps + matte + fg_caps[screen]
    #
    # This lets a video have SOME captions embedded (BG — intro/context)
    # and SOME captions announced (FG — climax breakthroughs). Aesthetic.
    fg_groups = [g for g in plan["groups"] if g.get("layer") == "fg"]
    if fg_groups or (plan.get("crown_group") or {}).get("layer") == "fg":
        # Strategy for FG-only render:
        # - Keep a-roll <video> intact (hyperframes needs metadata to load)
        # - Cover it with a full-screen black <div> at z-index between a-roll
        #   and #stage — hides the video visually, doesn't break metadata
        # - Hide caps that aren't data-layer="fg"
        fg_css = """
    <style>
      /* FG-only render: cover video with black; only fg-marked caps visible */
      html.fg-only body { background: #000 !important; }
      html.fg-only #fg-cover {
        position: absolute; inset: 0;
        background: #000;
        z-index: 1;
        pointer-events: none;
      }
      html.fg-only .cap:not([data-layer="fg"]) { display: none !important; }
    </style>
"""
        fg_out = out.replace("<html ", '<html class="fg-only" ', 1)
        fg_out = fg_out.replace("</head>", fg_css + "  </head>", 1)
        # Inject the black cover div right before #stage
        fg_out = fg_out.replace(
            '<div id="stage"',
            '<div id="fg-cover"></div>\n      <div id="stage"',
            1)
        (project / "index_fg.html").write_text(fg_out)
        print(f"[compile] {len(fg_groups)} fg group(s) → {project/'index_fg.html'}")


if __name__ == "__main__":
    main()
