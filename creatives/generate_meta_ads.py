#!/usr/bin/env python3
"""
Generate 15 Meta Ads images (1080x1920 PNG, <150KB each)
Downloads from Pexels, crops to 9:16, adds branding overlay.
"""

import os
import io
import requests
from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# Verified working Pexels URLs for each creative
IMAGES = [
    # === Campaign 1: Laundry Service - Family (Ad Set 1) ===
    {
        "filename": "laundry-family-a.png",
        "url": "https://images.pexels.com/photos/5591581/pexels-photo-5591581.jpeg?auto=compress&w=1200",
        "desc": "Happy family, clean clothes lifestyle",
    },
    {
        "filename": "laundry-family-b.png",
        "url": "https://images.pexels.com/photos/3807517/pexels-photo-3807517.jpeg?auto=compress&w=1200",
        "desc": "Woman relaxing on couch, stress-free",
    },
    {
        "filename": "laundry-family-c.png",
        "url": "https://images.pexels.com/photos/5591664/pexels-photo-5591664.jpeg?auto=compress&w=1200",
        "desc": "Fresh folded towels stacked neatly",
    },
    # === Campaign 1: Laundry Service - Rental (Ad Set 2) ===
    {
        "filename": "laundry-rental-a.png",
        "url": "https://images.pexels.com/photos/1743229/pexels-photo-1743229.jpeg?auto=compress&w=1200",
        "desc": "Modern apartment bedroom, crisp linens",
    },
    {
        "filename": "laundry-rental-b.png",
        "url": "https://images.pexels.com/photos/164595/pexels-photo-164595.jpeg?auto=compress&w=1200",
        "desc": "Hotel-fresh white bed sheets",
    },
    {
        "filename": "laundry-rental-c.png",
        "url": "https://images.pexels.com/photos/271624/pexels-photo-271624.jpeg?auto=compress&w=1200",
        "desc": "Clean white linens on bed",
    },
    # === Campaign 2: Carpet Cleaning - Home (Ad Set 1) ===
    {
        "filename": "carpet-home-a.png",
        "url": "https://images.pexels.com/photos/1571460/pexels-photo-1571460.jpeg?auto=compress&w=1200",
        "desc": "Beautiful living room with clean carpet",
    },
    {
        "filename": "carpet-home-b.png",
        "url": "https://images.pexels.com/photos/1457842/pexels-photo-1457842.jpeg?auto=compress&w=1200",
        "desc": "Bright modern living room, carpet floor",
    },
    {
        "filename": "carpet-home-c.png",
        "url": "https://images.pexels.com/photos/6969866/pexels-photo-6969866.jpeg?auto=compress&w=1200",
        "desc": "Professional carpet cleaning at home",
    },
    # === Campaign 2: Carpet Cleaning - Pets (Ad Set 2) ===
    {
        "filename": "carpet-pets-a.png",
        "url": "https://images.pexels.com/photos/1108099/pexels-photo-1108099.jpeg?auto=compress&w=1200",
        "desc": "Dog lying on carpet at home",
    },
    {
        "filename": "carpet-pets-b.png",
        "url": "https://images.pexels.com/photos/2253275/pexels-photo-2253275.jpeg?auto=compress&w=1200",
        "desc": "Golden retriever on clean floor",
    },
    {
        "filename": "carpet-pets-c.png",
        "url": "https://images.pexels.com/photos/2071882/pexels-photo-2071882.jpeg?auto=compress&w=1200",
        "desc": "Cat relaxing on clean carpet",
    },
    # === Campaign 3: Vacation Rental Turnover ===
    {
        "filename": "turnover-airbnb-a.png",
        "url": "https://images.pexels.com/photos/1571468/pexels-photo-1571468.jpeg?auto=compress&w=1200",
        "desc": "Airbnb-style bedroom, clean and modern",
    },
    {
        "filename": "turnover-airbnb-b.png",
        "url": "https://images.pexels.com/photos/1910472/pexels-photo-1910472.jpeg?auto=compress&w=1200",
        "desc": "Clean vacation rental bathroom",
    },
    {
        "filename": "turnover-airbnb-c.png",
        "url": "https://images.pexels.com/photos/4239091/pexels-photo-4239091.jpeg?auto=compress&w=1200",
        "desc": "Professional cleaning team at work",
    },
]

TARGET_W = 1080
TARGET_H = 1920
MAX_SIZE_KB = 150

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


def download_image(url):
    """Download image from URL."""
    resp = requests.get(url, timeout=30, allow_redirects=True, headers=HEADERS)
    if resp.status_code == 200 and len(resp.content) > 5000:
        return Image.open(io.BytesIO(resp.content))
    raise Exception(f"HTTP {resp.status_code}, {len(resp.content)} bytes")


def crop_to_ratio(img, target_w, target_h):
    """Center-crop image to target aspect ratio, then resize."""
    w, h = img.size
    target_ratio = target_w / target_h  # 0.5625 for 9:16

    if w / h > target_ratio:
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    else:
        new_h = int(w / target_ratio)
        top = (h - new_h) // 2
        img = img.crop((0, top, w, top + new_h))

    return img.resize((target_w, target_h), Image.LANCZOS)


def add_overlay(img):
    """Add gradient overlay and A7 branding."""
    overlay = Image.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Bottom gradient (stronger for text readability)
    for y in range(TARGET_H - 500, TARGET_H):
        alpha = int(200 * ((y - (TARGET_H - 500)) / 500))
        draw.rectangle([(0, y), (TARGET_W, y)], fill=(0, 0, 0, alpha))

    # Top subtle gradient
    for y in range(0, 250):
        alpha = int(100 * (1 - y / 250))
        draw.rectangle([(0, y), (TARGET_W, y)], fill=(0, 0, 0, alpha))

    # Composite
    img = img.convert("RGBA")
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    # Load fonts
    font_paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSDisplay.ttf",
        "/System/Library/Fonts/HelveticaNeue.ttc",
    ]
    font_large = font_small = None
    for fp in font_paths:
        try:
            font_large = ImageFont.truetype(fp, 56)
            font_small = ImageFont.truetype(fp, 30)
            break
        except:
            continue
    if not font_large:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # "A7 LAUNDRY" branding
    draw.text(
        (TARGET_W // 2, TARGET_H - 200),
        "A7 LAUNDRY",
        fill=(255, 255, 255, 245),
        font=font_large,
        anchor="mm",
    )

    # Contact line
    draw.text(
        (TARGET_W // 2, TARGET_H - 135),
        "Orlando, FL  |  (407) 670-8839",
        fill=(255, 255, 255, 210),
        font=font_small,
        anchor="mm",
    )

    # Blue accent bar
    bar_y = TARGET_H - 100
    draw.rectangle(
        [(TARGET_W // 2 - 50, bar_y), (TARGET_W // 2 + 50, bar_y + 4)],
        fill=(37, 99, 235, 255),  # #2563eb
    )

    return img.convert("RGB")


def save_optimized(img, filepath, max_kb=MAX_SIZE_KB):
    """Save as optimized PNG under max_kb. Falls back to JPEG if needed."""
    # Try PNG first
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    size_kb = buf.tell() / 1024

    if size_kb <= max_kb:
        with open(filepath, "wb") as f:
            f.write(buf.getvalue())
        return size_kb

    # Quantize colors to reduce PNG size
    for colors in [128, 96, 64, 48]:
        img_q = img.quantize(colors=colors, method=2).convert("RGB")
        buf = io.BytesIO()
        img_q.save(buf, format="PNG", optimize=True)
        size_kb = buf.tell() / 1024
        if size_kb <= max_kb:
            with open(filepath, "wb") as f:
                f.write(buf.getvalue())
            return size_kb
        print(f"    {colors} colors = {size_kb:.0f}KB")

    # Last resort: save JPEG as .png extension (still works for Meta Ads)
    for q in [85, 75, 65]:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=q, optimize=True)
        size_kb = buf.tell() / 1024
        if size_kb <= max_kb:
            # Actually save as JPEG with .png extension won't work well
            # Save the quantized version instead
            with open(filepath, "wb") as f:
                f.write(buf.getvalue())
            filepath_jpg = filepath.replace(".png", ".jpg")
            os.rename(filepath, filepath_jpg)
            return size_kb

    # Save whatever we have
    with open(filepath, "wb") as f:
        f.write(buf.getvalue())
    return size_kb


def main():
    print(f"Generating {len(IMAGES)} Meta Ads images...")
    print(f"Target: {TARGET_W}x{TARGET_H} PNG, <{MAX_SIZE_KB}KB each")
    print(f"Output: {OUTPUT_DIR}\n")

    success = 0
    failed = []

    for i, cfg in enumerate(IMAGES):
        name = cfg["filename"]
        filepath = os.path.join(OUTPUT_DIR, name)
        print(f"[{i+1}/{len(IMAGES)}] {name} — {cfg['desc']}")

        try:
            img = download_image(cfg["url"])
            print(f"  Downloaded: {img.size[0]}x{img.size[1]}")

            img = crop_to_ratio(img, TARGET_W, TARGET_H)
            img = add_overlay(img)

            size_kb = save_optimized(img, filepath)
            print(f"  Saved: {size_kb:.0f}KB\n")
            success += 1

        except Exception as e:
            print(f"  FAILED: {e}\n")
            failed.append(name)

    print(f"{'='*50}")
    print(f"Done! {success}/{len(IMAGES)} images generated")
    if failed:
        print(f"Failed: {', '.join(failed)}")

    # List generated files
    print(f"\nFiles in {OUTPUT_DIR}:")
    for f in sorted(os.listdir(OUTPUT_DIR)):
        if f.endswith((".png", ".jpg")):
            size = os.path.getsize(os.path.join(OUTPUT_DIR, f))
            print(f"  {f} — {size/1024:.0f}KB")


if __name__ == "__main__":
    main()
