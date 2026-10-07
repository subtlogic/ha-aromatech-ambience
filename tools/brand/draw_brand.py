"""Draw the integration's brand images: icon, logo and dark_logo, each @1x and @2x.

The icon is our own stylised drawing of the Ambience: a barrel capsule with
three pill-shaped slots cut out and two wisps of mist. The logos pair it with
"AROMATECH / AMBIENCE" in DIN Condensed Bold capitals. Nothing here uses the
vendor's artwork or lettering, and nothing is traced from a photo.

Usage (needs Pillow; the default font path is macOS's):

    python tools/brand/draw_brand.py [--out DIR] [--font PATH] [--font-index N]
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "custom_components" / "aromatech_ambience" / "brand"
DEFAULT_FONT = "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf"

BODY = (196, 112, 44, 255)   # warm amber
MIST = (234, 176, 112, 255)  # lighter amber
TEXT = {"logo": (43, 43, 43, 255), "dark_logo": (232, 232, 232, 255)}
LINES = ("AROMATECH", "AMBIENCE")
SCALE = 4  # supersample, then downscale for smooth edges

# Capsule geometry on a 256-unit canvas.
CX, TOP, BOTTOM, HW_MID, END_R = 128, 84, 248, 40, 30


def half_width(t: float) -> float:
    """Barrel profile: slightly wider in the middle than at the ends."""
    return HW_MID * (0.88 + 0.12 * math.sin(math.pi * t))


def capsule_outline(s: float) -> list[tuple[float, float]]:
    """Barrel sides with superellipse shoulders, as a closed polygon."""
    left, right = [], []
    steps = 400
    for i in range(steps + 1):
        t = i / steps
        y = TOP + t * (BOTTOM - TOP)
        hw = half_width(t)
        d = min(y - TOP, BOTTOM - y)
        if d < END_R:  # flat ends, rounded corners
            hw *= max(0.0, 1 - ((END_R - d) / END_R) ** 2.4) ** (1 / 2.4)
        left.append(((CX - hw) * s, y * s))
        right.append(((CX + hw) * s, y * s))
    return left + right[::-1]


def draw_icon(size: int) -> Image.Image:
    big = size * SCALE
    s = big / 256
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon(capsule_outline(s), fill=BODY)

    # Three pill-shaped slots of different lengths, cut out so the background
    # shows through.
    h = BOTTOM - TOP
    r = 3.5  # half the slot width
    for col, t0, t1 in ((-0.45, 0.24, 0.62), (0.0, 0.16, 0.80), (0.45, 0.36, 0.72)):
        x = CX + col * half_width((t0 + t1) / 2)
        d.rounded_rectangle([(x - r) * s, (TOP + t0 * h) * s, (x + r) * s, (TOP + t1 * h) * s],
                            radius=r * s, fill=(0, 0, 0, 0))

    # Two wisps of mist, stamped as discs because wide PIL polylines leave seams.
    w = 6 * s
    for x0, phase in ((116, 0.0), (140, math.pi)):
        for i in range(22 * 8, 72 * 8):
            y = i / 8
            x = (x0 + 4 * math.sin(y / 8 + phase)) * s
            d.ellipse([x - w / 2, y * s - w / 2, x + w / 2, y * s + w / 2], fill=MIST)

    return img.resize((size, size), Image.LANCZOS)


def draw_logo(height: int, color, font_path: str, font_index: int) -> Image.Image:
    icon = draw_icon(height)
    # The capsule is narrow inside a square canvas; crop to its real width so
    # the text sits at a normal distance from it.
    left_edge, _, right_edge, _ = icon.getbbox()
    icon = icon.crop((left_edge, 0, right_edge, height))

    # Size the font by its capital height, and space the lines by it too, so
    # the layout does not depend on each font's own line metrics.
    probe = ImageFont.truetype(font_path, 100, index=font_index)
    cap_probe = probe.getbbox("H")[3] - probe.getbbox("H")[1]
    cap = height * 0.25
    font = ImageFont.truetype(font_path, round(100 * cap / cap_probe), index=font_index)
    pitch = cap * 1.42  # baseline to baseline
    boxes = [font.getbbox(line) for line in LINES]

    gap = int(height * 0.16)
    text_width = max(right for _, _, right, _ in boxes)
    img = Image.new("RGBA", (icon.width + gap + text_width + int(height * 0.08), height), (0, 0, 0, 0))
    img.alpha_composite(icon, (0, 0))
    d = ImageDraw.Draw(img)

    # Sit the last line's ink bottom on the capsule's bottom edge, lifted by an
    # optical overshoot because the round base reads higher than a flat
    # baseline on the same row. Earlier lines stack above.
    base = height * BOTTOM / 256 - height * 0.03
    for i, line in enumerate(LINES):
        ink_bottom = base - (len(LINES) - 1 - i) * pitch
        d.text((icon.width + gap, round(ink_bottom - boxes[i][3])), line, font=font, fill=color)
    return img


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--font", default=DEFAULT_FONT)
    parser.add_argument("--font-index", type=int, default=0)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    draw_icon(256).save(args.out / "icon.png")
    draw_icon(512).save(args.out / "icon@2x.png")
    for name, color in TEXT.items():
        draw_logo(128, color, args.font, args.font_index).save(args.out / f"{name}.png")
        draw_logo(256, color, args.font, args.font_index).save(args.out / f"{name}@2x.png")
    print(f"wrote 6 images to {args.out}")


if __name__ == "__main__":
    main()
