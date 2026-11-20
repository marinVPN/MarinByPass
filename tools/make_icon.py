"""Генерация иконки MarinByPass (розово-фиолетовая)."""
from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "assets"
OUT.mkdir(parents=True, exist_ok=True)

S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

# --- фон: скруглённый квадрат с градиентом розовый → фиолетовый ---
grad = Image.new("RGBA", (S, S))
gd = ImageDraw.Draw(grad)
c1 = (236, 72, 153)    # pink
c2 = (139, 92, 246)    # violet
for y in range(S):
    t = y / (S - 1)
    gd.line([(0, y), (S, y)], fill=(
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
        255,
    ))

mask = Image.new("L", (S, S), 0)
md = ImageDraw.Draw(mask)
md.rounded_rectangle([24, 24, S - 24, S - 24], radius=232, fill=255)
img.paste(grad, (0, 0), mask)

# лёгкий блик сверху
shine = Image.new("RGBA", (S, S), (0, 0, 0, 0))
sd = ImageDraw.Draw(shine)
sd.ellipse([-S * 0.25, -S * 0.75, S * 1.25, S * 0.42], fill=(255, 255, 255, 40))
img = Image.alpha_composite(img, Image.composite(shine, Image.new("RGBA", (S, S), (0, 0, 0, 0)), mask))

# --- щит ---
d = ImageDraw.Draw(img)
pts = [
    (512, 160),
    (812, 258),
    (812, 520),
    (790, 610),
    (742, 700),
    (672, 776),
    (592, 834),
    (512, 862),
    (432, 834),
    (352, 776),
    (282, 700),
    (234, 610),
    (212, 520),
    (212, 258),
]
d.polygon(pts, fill=(255, 255, 255, 255))

# --- молния (вырез) ---
bolt = [
    (556, 330),
    (392, 552),
    (486, 552),
    (450, 706),
    (632, 470),
    (532, 470),
    (572, 330),
]
bolt_mask = Image.new("L", (S, S), 0)
bd = ImageDraw.Draw(bolt_mask)
bd.polygon(bolt, fill=255)
r, g, b, a = img.split()
a = Image.composite(Image.new("L", (S, S), 0), a, bolt_mask)
img.putalpha(a)

img.resize((256, 256), Image.LANCZOS).save(OUT / "icon.png")
sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)]
img.save(OUT / "icon.ico", sizes=sizes)
print("saved", OUT / "icon.ico")
