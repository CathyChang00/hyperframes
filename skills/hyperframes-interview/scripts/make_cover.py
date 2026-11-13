#!/usr/bin/env python3
"""Render Cathy's 16:9 interview cover from a JSON config.

Layout is defined on a 1920x1080 logical canvas and rendered at 2560x1440: photo crop,
bottom dark gradient, top lockup (official logo + `Interview | <Full Name>`), and a two-line
left-aligned title whose words may include inline logos written as `{key}`. Dark logos can
get a shape-following white halo. See references/cover-workflow.md for when to use each option.
Relative paths in the config resolve against the config file.
"""

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

LOGICAL = (1920, 1080)
DEFAULT_FONTS = {
    "title": {"path": "/System/Library/Fonts/Optima.ttc", "index": 1, "name": ["Optima", "Bold"]},
    "lockup": {"path": "/System/Library/Fonts/Avenir Next.ttc", "index": 2, "name": ["Avenir Next", "Demi Bold"]},
}


class Cover:
    def __init__(self, cfg, root):
        self.cfg, self.root = cfg, root
        size = cfg.get("size", [2560, 1440])
        if (not isinstance(size, (list, tuple)) or len(size) != 2
                or any(type(value) is not int or value <= 0 for value in size)
                or size[0] * 9 != size[1] * 16):
            raise ValueError(
                "size must contain two positive integers in exact landscape 16:9. "
                "This renderer supports English landscape 16:9 covers only; "
                "Chinese 3:4 and 4:3 covers require separate layouts."
            )
        self.size = tuple(size)
        self.s = self.size[0] / LOGICAL[0]

    def px(self, v):
        return round(v * self.s)

    def path(self, p):
        p = Path(p).expanduser()
        return p if p.is_absolute() else self.root / p

    def font(self, role, size):
        spec = {**DEFAULT_FONTS[role], **self.cfg.get("fonts", {}).get(role, {})}
        font = ImageFont.truetype(spec["path"], self.px(size), index=spec["index"])
        if list(font.getname()) != list(spec["name"]):
            raise ValueError(f"Expected {spec['name']}, got {font.getname()}; no silent font substitution")
        return font

    def logo(self, spec, height=None, word_height=None, baseline_mode="dense"):
        """Crop to ink, then scale by total height or by the wordmark's ink height. Returns image, baseline row.

        baseline_mode "dense" ignores thin descenders (Paradigm's g); "ink_bottom" uses the lowest
        wordmark ink, right for all-caps wordmarks such as OPENCLAW."""
        im = Image.open(self.path(spec["path"])).convert("RGBA")
        im = im.crop(im.getbbox())
        alpha = np.asarray(im)[..., 3]
        word = alpha[:, int(im.width * spec.get("wordmark_from_x", 0.3)):] > 128
        rows = word.sum(1)
        ys = np.nonzero(rows)[0]
        mode = spec.get("baseline", baseline_mode)
        baseline = int(ys[-1]) if mode == "ink_bottom" else int(np.nonzero(rows > rows.max() * 0.25)[0][-1])
        k = self.px(height) / im.height if height else self.px(word_height) / (ys[-1] - ys[0] + 1)
        im = im.resize((round(im.width * k), round(im.height * k)), Image.Resampling.LANCZOS)
        if spec.get("color"):
            tint = Image.new("RGBA", im.size, spec["color"])
            tint.putalpha(im.getchannel("A"))
            im = tint
        return im, round(baseline * k)

    def halo(self, canvas, im, xy, spec):
        """White light that follows the logo silhouette (dilate, then blur)."""
        if not spec:
            return
        mask = Image.new("L", self.size)
        mask.paste(im.getchannel("A"), xy)
        grow = 2 * (self.px(spec["spread"]) // 2) + 1
        mask = mask.point(lambda v: 255 if v > 60 else 0).filter(ImageFilter.MaxFilter(grow))
        mask = mask.point(lambda v: round(v * spec["peak"] / 255)).filter(ImageFilter.GaussianBlur(self.px(spec["blur"])))
        white = Image.new("RGBA", self.size, (255, 255, 255, 0))
        white.putalpha(mask)
        canvas.alpha_composite(white)

    def base(self):
        x0, y0, w = self.cfg["crop"]
        im = Image.open(self.path(self.cfg["photo"])).convert("RGB")
        h = round(w * 9 / 16)
        if x0 < 0 or y0 < 0 or x0 + w > im.width or y0 + h > im.height:
            raise ValueError(f"Crop {x0},{y0},{w}x{h} leaves the {im.width}x{im.height} photo; do not pad or stretch people")
        upscale = self.size[0] / w
        if upscale > self.cfg.get("max_upscale", 2.0):
            raise ValueError(f"Crop needs {upscale:.2f}x upscale; faces go soft, widen the crop")
        im = im.crop((x0, y0, x0 + w, y0 + h)).resize(self.size, Image.Resampling.LANCZOS)
        return im.filter(ImageFilter.UnsharpMask(radius=2, percent=55, threshold=2)).convert("RGBA")

    def gradient(self, canvas):
        g = self.cfg.get("gradient", {})
        start, strength, power = g.get("start", 0.40), g.get("strength", 0.92), g.get("power", 1.25)
        t = np.clip((np.linspace(0, 1, self.size[1], dtype=np.float32) - start) / (1 - start), 0, 1)
        layer = np.zeros((self.size[1], self.size[0], 4), np.uint8)
        layer[..., :3] = g.get("rgb", [14, 11, 8])
        layer[..., 3] = ((strength * t ** power)[:, None] * 255).astype(np.uint8)
        canvas.alpha_composite(Image.fromarray(layer))

    def lockup(self, canvas):
        c = self.cfg["lockup"]
        color = c.get("color", "#1B1713")
        im, baseline = self.logo({**c["logo"], "color": c["logo"].get("color", color)}, height=c.get("logo_height", 72))
        x0, y0 = (self.px(v) for v in c.get("xy", [88, 29]))
        self.halo(canvas, im, (x0, y0), c.get("halo"))
        canvas.alpha_composite(im, (x0, y0))
        f = self.font("lockup", c.get("font_size", 60))
        d = ImageDraw.Draw(canvas)
        base_y = y0 + baseline
        x = x0 + im.width + self.px(c.get("gap", 30))
        left, right = c.get("text", ["Interview", ""])
        d.text((x, base_y), left, font=f, anchor="ls", fill=color)
        x += f.getlength(left) + self.px(22)
        cap = f.getbbox("I", anchor="ls")
        d.line([(x, base_y + cap[1] - self.px(4)), (x, base_y + self.px(8))], fill=color, width=max(2, self.px(3)))
        x += self.px(22)
        d.text((x, base_y), right, font=f, anchor="ls", fill=color)
        return [x0, y0, round(x + f.getlength(right)), base_y + self.px(14)]

    def title(self, canvas):
        t = self.cfg["title"]
        f = self.font("title", t.get("font_size", 124))
        accent = set(t.get("accent", []))
        cream, orange = t.get("color", "#FCF8F0"), t.get("accent_color", "#FF4900")
        ink = Image.new("RGBA", self.size)
        d = ImageDraw.Draw(ink)
        logos = []
        for line, top in zip(t["lines"], t.get("tops", [752, 897])):
            base_y = self.px(top) + f.getmetrics()[0]              # shared baseline for every word
            x = self.px(t.get("x", 88))
            words = line.split(" ")
            for i, word in enumerate(words):
                last = i == len(words) - 1
                if word.startswith("{") and word.endswith("}"):
                    spec = self.cfg["inline_logos"][word[1:-1]]
                    im, baseline = self.logo(spec, word_height=spec.get("word_height", 100), baseline_mode="ink_bottom")
                    logos.append((im, (round(x), base_y - baseline), spec.get("halo")))
                    x += im.width + (0 if last else self.px(spec.get("gap", 34)))
                    continue
                color = orange if word.strip("?.,!") in accent else cream
                d.text((x, base_y), word, font=f, anchor="ls", fill=color, stroke_width=self.px(2), stroke_fill=color)
                x += f.getlength(word if last else word + " ")
        shadow = Image.new("RGBA", self.size)
        shadow.putalpha(ink.getchannel("A").point(lambda p: round(p * 0.55)))
        canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(self.px(6))), (0, self.px(3)))
        canvas.alpha_composite(ink)
        for im, xy, halo in logos:
            self.halo(canvas, im, xy, halo)
        box = list(ink.getbbox())
        for im, (x, y), _ in logos:
            canvas.alpha_composite(im, (x, y))
            box = [min(box[0], x), min(box[1], y), max(box[2], x + im.width), max(box[3], y + im.height)]
        return box

    def check(self, name, box):
        margin = self.px(self.cfg.get("safe_margin", 24))
        if box[0] < margin or box[1] < margin or box[2] > self.size[0] - margin or box[3] > self.size[1] - margin:
            raise ValueError(f"{name} {box} leaves the safe area; shorten copy or change the break, do not shrink the title")
        for face in self.cfg.get("protect", []):
            f = [self.px(v) for v in face]
            if box[0] < f[2] and f[0] < box[2] and box[1] < f[3] and f[1] < box[3]:
                raise ValueError(f"{name} {box} overlaps protected face box {face}")

    def render(self, text=True):
        canvas = self.base()
        if not text:
            return canvas.convert("RGB"), {}
        self.gradient(canvas)
        boxes = {"lockup": self.lockup(canvas), "title": self.title(canvas)}
        for name, box in boxes.items():
            self.check(name, box)
        return canvas.convert("RGB"), boxes


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", type=Path)
    parser.add_argument("--out", type=Path, required=True, help="2560x1440 PNG")
    parser.add_argument("--jpg", type=Path, help="also write a 1280x720 JPG")
    parser.add_argument("--thumb", type=Path, help="also write the ~480x270 thumbnail to review legibility")
    parser.add_argument("--base", type=Path, help="also write the text-free crop")
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    try:
        cover = Cover(cfg, args.config.resolve().parent)
        image, boxes = cover.render()
        for path in (args.out, args.jpg, args.thumb, args.base):
            if path:
                path.parent.mkdir(parents=True, exist_ok=True)
        image.save(args.out)
        if args.jpg:
            image.resize((1280, 720), Image.Resampling.LANCZOS).save(args.jpg, quality=92)
        if args.thumb:
            image.resize((480, 270), Image.Resampling.LANCZOS).save(args.thumb)
        if args.base:
            cover.render(text=False)[0].save(args.base)
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    print(json.dumps({"out": str(args.out.resolve()), **boxes}))


if __name__ == "__main__":
    main()
