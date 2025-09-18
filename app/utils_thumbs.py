import hashlib
import os
from PIL import Image, ImageOps, ImageFile

# Allow loading truncated images to avoid failures on some JPEGs
ImageFile.LOAD_TRUNCATED_IMAGES = True


def _thumb_key(path: str, size: int) -> str:
    st = os.stat(path)
    key = f"{path}|{st.st_mtime_ns}|{st.st_size}|{size}".encode("utf-8", errors="ignore")
    return hashlib.sha1(key).hexdigest()


def get_thumbnail_path(cache_dir: str, path: str, size: int) -> str:
    key = _thumb_key(path, size)
    return os.path.join(cache_dir, f"{key}.jpg")


def build_thumbnail(src_path: str, dest_path: str, size: int = 256) -> None:
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with Image.open(src_path) as im:
        # Ensure we always have an Image after exif transpose which may return None in type hints
        transposed = ImageOps.exif_transpose(im) or im
        fitted = ImageOps.fit(transposed, (size, size), method=Image.Resampling.LANCZOS)
        fitted.convert("RGB").save(dest_path, format="JPEG", quality=85)
