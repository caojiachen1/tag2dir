import os

ALLOWED_EXT = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tif', '.tiff'}


def is_allowed_image(path: str) -> bool:
    _, ext = os.path.splitext(path.lower())
    return ext in ALLOWED_EXT


def scan_images(root: str):
    root = os.path.abspath(root)
    for base, _, files in os.walk(root):
        for name in files:
            path = os.path.join(base, name)
            if is_allowed_image(path):
                yield path
