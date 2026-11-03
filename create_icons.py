"""Generate modern high-resolution application icons (.ico and .png) for the Truth Table Synthesizer."""

import os
import math
from PIL import Image, ImageDraw, ImageFilter


def create_app_icon(size: int = 512) -> Image.Image:
    # 512x512 master RGBA canvas
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad = int(size * 0.06)
    radius = int(size * 0.22)

    # 1. Outer Glow / Shadow
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow)
    s_draw.rounded_rectangle(
        [pad + 8, pad + 16, size - pad - 8, size - pad],
        radius=radius,
        fill=(0, 0, 0, 160),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=int(size * 0.04)))
    img = Image.alpha_composite(img, shadow)
    draw = ImageDraw.Draw(img)

    # 2. Main squircle background with vertical dark-slate gradient
    badge = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    b_draw = ImageDraw.Draw(badge)
    box = [pad, pad, size - pad, size - pad]
    b_draw.rounded_rectangle(box, radius=radius, fill=(15, 23, 42, 255))

    # Add gradient overlay
    for y in range(pad, size - pad):
        factor = (y - pad) / (size - 2 * pad)
        r = int(15 * (1 - factor) + 30 * factor)
        g = int(23 * (1 - factor) + 41 * factor)
        b = int(42 * (1 - factor) + 59 * factor)
        # 1-pixel scanline clipped by badge mask
        b_draw.line([(pad, y), (size - pad, y)], fill=(r, g, b, 255))

    # Mask the gradient inside the squircle
    mask = Image.new("L", (size, size), 0)
    m_draw = ImageDraw.Draw(mask)
    m_draw.rounded_rectangle(box, radius=radius, fill=255)
    badge.putalpha(mask)

    # Border glow
    b_draw.rounded_rectangle(box, radius=radius, outline=(56, 189, 248, 220), width=int(size * 0.022))
    img = Image.alpha_composite(img, badge)
    draw = ImageDraw.Draw(img)

    # 3. Inner Circuit Grid Lines (subtle)
    grid_col = (51, 65, 85, 90)
    for gx in range(pad + 40, size - pad, int(size * 0.12)):
        draw.line([(gx, pad + 20), (gx, size - pad - 20)], fill=grid_col, width=2)
    for gy in range(pad + 40, size - pad, int(size * 0.12)):
        draw.line([(pad + 20, gy), (size - pad - 20, gy)], fill=grid_col, width=2)

    # 4. Stylized Logic Gate Outline (AND/XOR hybrid)
    # Center bounds
    gx1 = int(size * 0.22)
    gy1 = int(size * 0.28)
    gx2 = int(size * 0.68)
    gy2 = int(size * 0.72)
    stroke_w = max(4, int(size * 0.028))

    # Wire 1 (top input)
    draw.line([(pad + 20, gy1 + int((gy2 - gy1) * 0.25)), (gx1, gy1 + int((gy2 - gy1) * 0.25))], fill=(34, 197, 94, 255), width=stroke_w)
    draw.ellipse([pad + 14, gy1 + int((gy2 - gy1) * 0.25) - 8, pad + 30, gy1 + int((gy2 - gy1) * 0.25) + 8], fill=(34, 197, 94, 255))

    # Wire 2 (bottom input)
    draw.line([(pad + 20, gy1 + int((gy2 - gy1) * 0.75)), (gx1, gy1 + int((gy2 - gy1) * 0.75))], fill=(96, 165, 250, 255), width=stroke_w)
    draw.ellipse([pad + 14, gy1 + int((gy2 - gy1) * 0.75) - 8, pad + 30, gy1 + int((gy2 - gy1) * 0.75) + 8], fill=(96, 165, 250, 255))

    # Wire 3 (output on right)
    draw.line([(gx2, int((gy1 + gy2) / 2)), (size - pad - 20, int((gy1 + gy2) / 2))], fill=(34, 197, 94, 255), width=stroke_w)
    draw.ellipse([size - pad - 30, int((gy1 + gy2) / 2) - 8, size - pad - 14, int((gy1 + gy2) / 2) + 8], fill=(34, 197, 94, 255))

    # Logic Gate Body (Curved back & dome)
    gate_pts = [
        (gx1, gy1),
        (gx1 + int((gx2 - gx1) * 0.45), gy1),
        (gx2, int((gy1 + gy2) / 2)),
        (gx1 + int((gx2 - gx1) * 0.45), gy2),
        (gx1, gy2),
    ]
    # Gate fill
    gate_overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(gate_overlay)
    g_draw.polygon(gate_pts, fill=(30, 58, 138, 200), outline=(96, 165, 250, 255))
    img = Image.alpha_composite(img, gate_overlay)
    draw = ImageDraw.Draw(img)

    # Gate border lines (smooth polygon stroke)
    draw.line([(gx1, gy1), (gx1 + int((gx2 - gx1) * 0.45), gy1)], fill=(147, 197, 253, 255), width=stroke_w)
    draw.line([(gx1 + int((gx2 - gx1) * 0.45), gy1), (gx2, int((gy1 + gy2) / 2))], fill=(147, 197, 253, 255), width=stroke_w)
    draw.line([(gx2, int((gy1 + gy2) / 2)), (gx1 + int((gx2 - gx1) * 0.45), gy2)], fill=(147, 197, 253, 255), width=stroke_w)
    draw.line([(gx1 + int((gx2 - gx1) * 0.45), gy2), (gx1, gy2)], fill=(147, 197, 253, 255), width=stroke_w)
    draw.line([(gx1, gy2), (gx1, gy1)], fill=(147, 197, 253, 255), width=stroke_w)

    # 5. Golden Lightning Bolt in center
    cx = int((gx1 + gx2) / 2) - 4
    cy = int((gy1 + gy2) / 2)
    s = int(size * 0.20)
    bolt_pts = [
        (cx + int(s * 0.05), cy - int(s * 0.70)),
        (cx - int(s * 0.45), cy + int(s * 0.05)),
        (cx - int(s * 0.05), cy + int(s * 0.05)),
        (cx - int(s * 0.25), cy + int(s * 0.75)),
        (cx + int(s * 0.45), cy - int(s * 0.10)),
        (cx + int(s * 0.05), cy - int(s * 0.10)),
    ]
    # Bolt glow
    bolt_glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(bolt_glow)
    bg_draw.polygon(bolt_pts, fill=(253, 224, 71, 230))
    bolt_glow = bolt_glow.filter(ImageFilter.GaussianBlur(radius=int(size * 0.02)))
    img = Image.alpha_composite(img, bolt_glow)

    # Crisp bolt on top
    draw = ImageDraw.Draw(img)
    draw.polygon(bolt_pts, fill=(250, 204, 21, 255), outline=(254, 240, 138, 255))

    return img


def generate_all_icons(assets_dir: str = "assets") -> None:
    os.makedirs(assets_dir, exist_ok=True)
    master = create_app_icon(512)

    # 1. Save high-res PNGs
    png_path_512 = os.path.join(assets_dir, "icon_512.png")
    png_path_256 = os.path.join(assets_dir, "icon_256.png")
    png_path_main = os.path.join(assets_dir, "icon.png")

    master.save(png_path_512, format="PNG")
    master.resize((256, 256), Image.Resampling.LANCZOS).save(png_path_256, format="PNG")
    master.resize((128, 128), Image.Resampling.LANCZOS).save(png_path_main, format="PNG")

    # 2. Save multi-resolution Windows ICO
    # Windows Explorer / Taskbar standard sizes
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    ico_images = [master.resize(sz, Image.Resampling.LANCZOS) for sz in sizes]

    ico_path = os.path.join(assets_dir, "icon.ico")
    master.save(
        ico_path,
        format="ICO",
        sizes=sizes,
        append_images=ico_images[1:],
    )
    print(f"Generated icons in '{assets_dir}':")
    print(f"  - {ico_path} (Multi-resolution: {', '.join(f'{w}x{h}' for w, h in sizes)})")
    print(f"  - {png_path_main} (128x128)")
    print(f"  - {png_path_256} (256x256)")
    print(f"  - {png_path_512} (512x512)")


if __name__ == "__main__":
    generate_all_icons()

