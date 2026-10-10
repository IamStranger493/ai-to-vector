import os
import math
import numpy as np
from PIL import Image, ImageDraw


def generate_flat_illustration(path: str):
    """Creates a geometric flat illustration with clean colors and shapes."""
    w, h = 400, 300
    img = Image.new("RGB", (w, h), (240, 244, 248))
    draw = ImageDraw.Draw(img)

    # Sky sun
    draw.ellipse([260, 40, 340, 120], fill=(255, 180, 50))

    # Mountains
    draw.polygon([(0, 220), (120, 90), (250, 220)], fill=(70, 90, 140))
    draw.polygon([(180, 220), (290, 110), (400, 220)], fill=(90, 115, 170))

    # Hills
    draw.ellipse([-50, 180, 250, 350], fill=(60, 160, 105))
    draw.ellipse([150, 190, 450, 360], fill=(45, 135, 85))

    # Tiny details: cabin with roof, window, door
    draw.rectangle([180, 190, 220, 225], fill=(210, 160, 120))
    draw.polygon([(175, 190), (200, 165), (225, 190)], fill=(160, 50, 45))
    draw.rectangle([195, 205, 205, 225], fill=(80, 50, 30))  # door
    draw.rectangle([185, 198, 192, 208], fill=(255, 240, 180))  # window

    img.save(path)


def generate_desert_scene(path: str):
    """Creates a 2-person desert scene with warm tones, hair, and figures."""
    w, h = 500, 350
    arr = np.zeros((h, w, 3), dtype=np.uint8)

    # Desert sky gradient
    for y in range(160):
        t = y / 160.0
        r = int(120 * (1 - t) + 245 * t)
        g = int(170 * (1 - t) + 200 * t)
        b = int(230 * (1 - t) + 150 * t)
        arr[y, :] = [r, g, b]

    # Dunes (curved sand contours)
    for y in range(160, h):
        for x in range(w):
            dune_wave = math.sin(x * 0.02) * 20.0 + math.cos(x * 0.008) * 15.0
            if y < 220 + dune_wave:
                arr[y, x] = [230, 165, 85]  # sunlit sand
            elif y < 270 + dune_wave:
                arr[y, x] = [195, 130, 65]  # mid dune
            else:
                arr[y, x] = [160, 100, 50]  # foreground dune

    img = Image.fromarray(arr)
    draw = ImageDraw.Draw(img)

    # Figure 1 (Left - Blue Turban, warm skin, dark robe)
    draw.ellipse([140, 150, 190, 205], fill=(215, 145, 110))  # Face
    draw.ellipse([135, 135, 195, 175], fill=(30, 80, 180))    # Vivid Blue turban
    draw.rectangle([150, 170, 160, 175], fill=(40, 30, 25))   # Eye 1
    draw.rectangle([170, 170, 180, 175], fill=(40, 30, 25))   # Eye 2
    draw.polygon([(120, 200), (210, 200), (225, 330), (105, 330)], fill=(45, 40, 55))  # Robe

    # Figure 2 (Right - White Turban, ochre robe, dark hair)
    draw.ellipse([270, 160, 315, 215], fill=(205, 135, 100))  # Face
    draw.ellipse([265, 145, 320, 185], fill=(245, 240, 230))  # White turban
    draw.rectangle([280, 180, 288, 185], fill=(35, 25, 20))   # Eye 1
    draw.rectangle([297, 180, 305, 185], fill=(35, 25, 20))   # Eye 2
    draw.polygon([(250, 210), (335, 210), (350, 330), (235, 330)], fill=(190, 110, 40))  # Robe

    img.save(path)


def generate_village_scene(path: str):
    """Creates a village group scene with multiple distinct figures and buildings."""
    w, h = 450, 320
    img = Image.new("RGB", (w, h), (210, 225, 235))
    draw = ImageDraw.Draw(img)

    # Village buildings
    draw.rectangle([40, 120, 150, 240], fill=(215, 200, 180))
    draw.polygon([(30, 120), (95, 70), (160, 120)], fill=(180, 90, 70))
    draw.rectangle([70, 160, 120, 240], fill=(120, 80, 60))

    draw.rectangle([280, 100, 410, 230], fill=(225, 215, 195))
    draw.polygon([(270, 100), (345, 60), (420, 100)], fill=(160, 80, 60))
    draw.rectangle([320, 150, 360, 230], fill=(90, 65, 50))

    # Ground
    draw.rectangle([0, 220, w, h], fill=(175, 160, 135))

    # Multiple figures with diverse clothing
    colors = [
        (220, 60, 60), (40, 140, 200), (240, 170, 30),
        (60, 160, 90), (140, 70, 160), (220, 110, 40)
    ]
    for i, x in enumerate([80, 140, 200, 250, 310, 370]):
        c = colors[i % len(colors)]
        # Head
        draw.ellipse([x - 12, 190, x + 12, 218], fill=(210, 140, 110))
        # Hair
        draw.ellipse([x - 12, 186, x + 12, 200], fill=(30, 25, 20))
        # Body
        draw.polygon([(x - 18, 218), (x + 18, 218), (x + 22, 290), (x - 22, 290)], fill=c)

    img.save(path)


if __name__ == "__main__":
    golden_dir = os.path.join(os.path.dirname(__file__), "golden")
    os.makedirs(golden_dir, exist_ok=True)
    generate_flat_illustration(os.path.join(golden_dir, "illustration.png"))
    generate_desert_scene(os.path.join(golden_dir, "desert_scene.png"))
    generate_village_scene(os.path.join(golden_dir, "village_scene.png"))
    print("Generated 3 golden images in tests/golden/")
