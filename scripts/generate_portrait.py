#!/usr/bin/env python3
"""Convert a source portrait (with a transparent background) into the
braille/"ASCII-fetch" style PNG portraits used by dark_mode.svg and
light_mode.svg.

This preserves the original project's visual style: a monospace grid of
Unicode Braille glyphs (2x4 dots per character), colorized to match the
photo, sitting on a flat background that matches each theme's background
color -- the same technique used by the original profile_ascii_dark.png /
profile_ascii_light.png assets.

Usage:
    python3 scripts/generate_portrait.py path/to/your-portrait.png

Re-run this any time you swap in a new source photo -- it regenerates
both profile_ascii_dark.png and profile_ascii_light.png in the project
root, which update_readme.py then embeds into the SVGs.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = True

ROOT = Path(__file__).resolve().parents[1]

# Output canvas size — matches the aspect ratio of the <image> box in the
# generated SVG (462 x 610) so the portrait fills it with no letterboxing.
CANVAS_W, CANVAS_H = 1830, 2418

# Monospace font + size used to draw the Braille grid. Size 23 gives a
# ~14 x 28px cell, matching the original assets' character spacing.
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_SIZE = 23

# Braille dot bit layout (2 cols x 4 rows per character):
#  (col,row) -> bit
DOT_BITS = {
    (0, 0): 0x01,
    (0, 1): 0x02,
    (0, 2): 0x04,
    (0, 3): 0x40,
    (1, 0): 0x08,
    (1, 1): 0x10,
    (1, 2): 0x20,
    (1, 3): 0x80,
}

THEME_BACKGROUNDS = {
    "profile_ascii_dark.png": (22, 27, 34),      # #161b22
    "profile_ascii_light.png": (246, 248, 250),  # #f6f8fa
}


def cover_resize(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Resize + center-crop so img fully covers target_w x target_h."""
    src_ratio = img.width / img.height
    dst_ratio = target_w / target_h
    if src_ratio > dst_ratio:
        new_h = target_h
        new_w = round(new_h * src_ratio)
    else:
        new_w = target_w
        new_h = round(new_w / src_ratio)
    resized = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def composite_on_background(portrait: Image.Image, bg_rgb: tuple[int, int, int]) -> Image.Image:
    base = Image.new("RGB", portrait.size, bg_rgb)
    if portrait.mode != "RGBA":
        portrait = portrait.convert("RGBA")
    base.paste(portrait, (0, 0), portrait)
    return base


def render_braille(image_rgb: Image.Image, bg_rgb: tuple[int, int, int]) -> Image.Image:
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    advance = font.getlength("X")
    ascent, descent = font.getmetrics()
    cell_w = advance
    cell_h = ascent + descent

    cols = max(1, round(CANVAS_W / cell_w))
    rows = max(1, round(CANVAS_H / cell_h))

    # Downsample for per-dot luminance (2 dots wide x 4 dots tall per cell)
    dot_w, dot_h = cols * 2, rows * 4
    lum_small = image_rgb.convert("L").resize((dot_w, dot_h), Image.LANCZOS)
    # Push contrast a bit so mid-tones still produce visible dot texture,
    # then Floyd-Steinberg dither down to 1-bit on/off dots.
    lum_small = lum_small.point(lambda p: max(0, min(255, int((p - 128) * 1.15 + 128))))
    dots = lum_small.convert("1", dither=Image.FLOYDSTEINBERG)
    dot_px = dots.load()

    # Downsample for per-character color
    color_small = image_rgb.resize((cols, rows), Image.LANCZOS).convert("RGB")
    color_px = color_small.load()

    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), bg_rgb)
    draw = ImageDraw.Draw(canvas)

    x_scale = CANVAS_W / cols
    y_scale = CANVAS_H / rows

    for row in range(rows):
        for col in range(cols):
            bits = 0
            for (dc, dr), bit in DOT_BITS.items():
                px = col * 2 + dc
                py = row * 4 + dr
                if px < dot_w and py < dot_h and dot_px[px, py] == 0:  # 0 = black = "on"
                    bits |= bit
            if bits == 0:
                continue
            char = chr(0x2800 + bits)
            r, g, b = color_px[col, row]
            # Skip cells that are essentially background color (keeps edges clean)
            if abs(r - bg_rgb[0]) + abs(g - bg_rgb[1]) + abs(b - bg_rgb[2]) < 12:
                continue
            x = col * x_scale
            y = row * y_scale
            draw.text((x, y), char, font=font, fill=(r, g, b))

    return canvas


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python3 scripts/generate_portrait.py path/to/portrait.png")
        raise SystemExit(1)

    source_path = Path(sys.argv[1])
    source = Image.open(source_path)
    source.load()
    if source.mode != "RGBA":
        source = source.convert("RGBA")
    source = cover_resize(source, CANVAS_W, CANVAS_H)

    for filename, bg_rgb in THEME_BACKGROUNDS.items():
        flat = composite_on_background(source, bg_rgb)
        rendered = render_braille(flat, bg_rgb)
        out_path = ROOT / filename
        rendered.save(out_path)
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
