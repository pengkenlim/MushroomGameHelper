from PIL import Image

SOURCE = "C:\\Users\\limpe\\MushroomGameHelper\\visual_assets\\green_blob.png"   # Your square, high-res PNG (256x256 or larger)
OUTPUT = "C:\\Users\\limpe\\MushroomGameHelper\\visual_assets\\green_blob.ico"

img = Image.open(SOURCE).convert("RGBA")

# Crop to a perfect square if the source is rectangular
w, h = img.size
side = min(w, h)
left, top = (w - side) // 2, (h - side) // 2
img = img.crop((left, top, left + side, top + side))

sizes = [(16, 16), (32, 32), (48, 48), (256, 256)]
img.save(OUTPUT, format="ICO", sizes=sizes)
print(f"Saved {OUTPUT} with embedded sizes: {sizes}")