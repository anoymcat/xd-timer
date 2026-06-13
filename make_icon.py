"""Generate a polished DeskTimer app icon (deep-blue + gold clock face).

Programmatic, no external art. Run with the venv python:
    venv\\Scripts\\python.exe make_icon.py
Writes a multi-size ico/icon.ico used by the desktop shortcut.
"""
import math
from PIL import Image, ImageDraw

SS = 4            # supersample factor for anti-aliasing
S = 256           # final icon size
sz = S * SS
c = sz // 2
m = int(sz * 0.05)

img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# --- disc: dark-gold edge -> gold ring -> deep-blue face ---
d.ellipse([m, m, sz - m, sz - m], fill=(70, 55, 20, 255))          # dark gold rim
g = int(sz * 0.015)
d.ellipse([m + g, m + g, sz - m - g, sz - m - g], fill=(200, 170, 110, 255))  # gold ring
ring = int(sz * 0.06)
d.ellipse([m + ring, m + ring, sz - m - ring, sz - m - ring], fill=(11, 26, 48, 255))  # face #0B1A30
face_r = (sz - 2 * (m + ring)) // 2

# --- hour ticks (12), majors at quarters ---
for i in range(12):
    a = math.radians(i * 30 - 90)
    big = (i % 3 == 0)
    r1 = face_r * (0.74 if big else 0.80)
    r2 = face_r * 0.90
    w = int(sz * 0.022) if big else int(sz * 0.011)
    col = (230, 205, 150, 255) if big else (170, 150, 100, 255)
    d.line([c + r1 * math.cos(a), c + r1 * math.sin(a),
            c + r2 * math.cos(a), c + r2 * math.sin(a)], fill=col, width=w)

# --- hands ---
def hand(deg, length, w, col):
    a = math.radians(deg - 90)
    d.line([c, c, c + length * math.cos(a), c + length * math.sin(a)],
           fill=col, width=w, joint="curve")

hand(310, face_r * 0.42, int(sz * 0.028), (240, 240, 245, 255))   # hour ~10
hand(70,  face_r * 0.66, int(sz * 0.020), (240, 240, 245, 255))   # minute ~2
cap = int(sz * 0.028)
d.ellipse([c - cap, c - cap, c + cap, c + cap], fill=(230, 205, 150, 255))

# --- glossy highlight (top half), subtle glass feel ---
gloss = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
ImageDraw.Draw(gloss).ellipse([m + ring, m + ring, sz - m - ring, c], fill=(255, 255, 255, 38))
img = Image.alpha_composite(img, gloss)

img = img.resize((S, S), Image.LANCZOS)
img.save("ico/icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("icon saved -> ico/icon.ico")
