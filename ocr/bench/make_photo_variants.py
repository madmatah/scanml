"""Build the OCR test set from the downloaded page scans.

For every page in ``<testdata>/originals`` it writes a clean "scanner" version
(``pages/``, A4 at 300 dpi), and for selected pages realistic phone-photo
variants (``photos/``): perspective, open-book curvature with gutter shadow,
uneven lighting, a 90-degree rotation, and a combination. ``variants.json``
lists every generated image with its source page and transformations.

The pages to photograph are listed in ``<testdata>/sources.json`` (see
fetch_testdata.py), whose ``pages`` entries may hold, besides their ``id``
(``originals/<id>.jpg``)::

    "variants": ["perspective", "curved", "lighting", "rotated90", "combined"],
    "spine": "left"

``variants``: the photos to make of the page (none by default). ``spine``:
the side of the book's spine on the page, for the curvature; odd (recto)
pages have it on their left, even (verso) pages on their right (``left`` by
default). Without sources.json, only the clean scans are made.

The inputs are untrusted downloads: run with numpy/OpenCV/Pillow in a
throw-away container without network, e.g.::

    docker run --rm --network none --read-only --cap-drop ALL --user 1000:1000 \
      -v "$SANDBOX_DIR":/opt/sandbox:ro -v /data/user/scanmylib/testdata:/testdata \
      -v "$PWD/ocr/bench":/bench:ro scanmylib-ocr:latest \
      /opt/sandbox/venv-paddle/bin/python -I /bench/make_photo_variants.py /testdata
"""

from __future__ import annotations

import json
import sys
import zlib
from pathlib import Path

import cv2
import numpy as np

SCAN_WIDTH = 2480
PHOTO_SIZE = (3000, 4000)  # width, height of a 12 Mpx portrait phone photo
JPEG_QUALITY_SCAN = 92
JPEG_QUALITY_PHOTO = 85

VARIANT_NAMES = ("perspective", "curved", "lighting", "rotated90", "combined")
SPINE_SIDES = ("left", "right")


def load_page_options(testdata: Path) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Photo variants and spine side of each page, by page id, from ``<testdata>/sources.json``."""
    path = testdata / "sources.json"
    if not path.is_file():
        print(f"{path} not found: clean scans only", flush=True)
        return {}, {}
    variants: dict[str, list[str]] = {}
    spines: dict[str, str] = {}
    for page in json.loads(path.read_text(encoding="utf-8"))["pages"]:
        page_id = page["id"]
        variants[page_id] = list(page.get("variants", []))
        spines[page_id] = page.get("spine", "left")
        unknown = [name for name in variants[page_id] if name not in VARIANT_NAMES]
        if unknown or spines[page_id] not in SPINE_SIDES:
            raise ValueError(f"page {page_id}: unknown variant {unknown} or spine side {spines[page_id]!r}")
    return variants, spines


def read_gray(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f"cannot decode {path}")
    return image


def to_paper_color(gray: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Grayscale scan -> BGR photo of slightly yellowed paper."""
    tint = np.array([0.80, 0.92, 1.0]) * rng.uniform(0.95, 1.0)  # B, G, R
    ink = np.array([40.0, 38.0, 35.0])
    level = gray.astype(np.float32)[..., None] / 255.0
    return (ink + level * (255.0 * tint - ink)).clip(0, 255).astype(np.uint8)


def curve_page(page: np.ndarray, spine: str, strength: float) -> np.ndarray:
    """Bend the page like an open book: lines bow and the gutter is compressed and shaded."""
    height, width = page.shape[:2]
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    s = xs / width if spine == "left" else (width - 1 - xs) / width  # 0 at the spine
    curl = np.exp(-s / 0.2)
    away = 1.0 if spine == "left" else -1.0
    # Content near the spine comes from further inside the gutter (foreshortening).
    map_x = xs - away * strength * 0.08 * width * curl
    # Text lines bow: strongly near the spine, gently across the whole page.
    bow = strength * height * (0.07 * curl + 0.025 * np.sin(np.pi * s))
    map_y = ys + bow * ((ys - height / 2) / (height / 2)) - strength * 0.02 * height * curl
    warped = cv2.remap(page, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    shade = 1.0 - 0.55 * strength * curl
    return (warped.astype(np.float32) * shade[..., None]).clip(0, 255).astype(np.uint8)


def uneven_lighting(photo: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Light falling from one side, plus the soft shadow of the phone or a hand."""
    height, width = photo.shape[:2]
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    angle = rng.uniform(0, 2 * np.pi)
    ramp = (np.cos(angle) * (xs / width - 0.5) + np.sin(angle) * (ys / height - 0.5)) + 0.5
    light = 0.5 + 0.6 * ramp
    cx, cy = rng.uniform(0.3, 0.7) * width, rng.uniform(0.55, 0.85) * height
    rx, ry = 0.28 * width, 0.18 * height
    blob = np.exp(-(((xs - cx) / rx) ** 2 + ((ys - cy) / ry) ** 2))
    light *= 1.0 - 0.5 * blob
    warm = np.array([0.86, 0.95, 1.0], dtype=np.float32)
    return (photo.astype(np.float32) * light[..., None] * warm).clip(0, 255).astype(np.uint8)


def place_in_photo(page: np.ndarray, rng: np.random.Generator, tilt: float) -> np.ndarray:
    """Project the page onto a table surface as seen by a slightly tilted phone."""
    photo_w, photo_h = PHOTO_SIZE
    height, width = page.shape[:2]
    scale = min(photo_w * 0.86 / width, photo_h * 0.86 / height)
    w, h = width * scale, height * scale
    x0, y0 = (photo_w - w) / 2, (photo_h - h) / 2
    jitter = lambda: rng.uniform(-1, 1) * 0.02 * w  # noqa: E731
    shrink = tilt * w  # the far (top) edge looks narrower
    corners = np.float32([
        [x0 + shrink + jitter(), y0 + jitter()],
        [x0 + w - shrink * 0.7 + jitter(), y0 + jitter()],
        [x0 + w + jitter(), y0 + h + jitter()],
        [x0 + jitter(), y0 + h + jitter()],
    ])  # fmt: skip
    source = np.float32([[0, 0], [width, 0], [width, height], [0, height]])
    homography = cv2.getPerspectiveTransform(source, corners)
    desk = np.array([60.0, 85.0, 110.0]) + rng.normal(0, 6, (photo_h, photo_w, 3))  # wooden desk
    table = desk.clip(0, 255).astype(np.uint8)
    return cv2.warpPerspective(page, homography, (photo_w, photo_h), dst=table, borderMode=cv2.BORDER_TRANSPARENT)


def camera_noise(photo: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    blurred = cv2.GaussianBlur(photo, (0, 0), rng.uniform(0.8, 1.3))
    noise = rng.normal(0, 3.5, photo.shape)
    return (blurred.astype(np.float32) + noise).clip(0, 255).astype(np.uint8)


def make_variant(gray: np.ndarray, spine: str, variant: str, rng: np.random.Generator) -> np.ndarray:
    page = to_paper_color(gray, rng)
    if variant in ("curved", "combined"):
        page = curve_page(page, spine, strength=1.0 if variant == "curved" else 0.8)
    tilt = {"perspective": 0.07, "combined": 0.05}.get(variant, 0.015)
    photo = place_in_photo(page, rng, tilt)
    if variant in ("lighting", "combined"):
        photo = uneven_lighting(photo, rng)
    photo = camera_noise(photo, rng)
    if variant == "rotated90":
        photo = cv2.rotate(photo, cv2.ROTATE_90_CLOCKWISE)
    return photo


def main(testdata: Path) -> None:
    variants, spines = load_page_options(testdata)
    originals = sorted((testdata / "originals").glob("*.jpg"))
    (testdata / "pages").mkdir(exist_ok=True)
    (testdata / "photos").mkdir(exist_ok=True)
    entries = []
    for original in originals:
        page_id = original.stem
        gray = read_gray(original)
        scan = cv2.resize(gray, (SCAN_WIDTH, round(gray.shape[0] * SCAN_WIDTH / gray.shape[1])), interpolation=cv2.INTER_AREA)
        scan_path = testdata / "pages" / f"{page_id}.jpg"
        cv2.imwrite(str(scan_path), scan, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY_SCAN])
        entries.append({"file": f"pages/{scan_path.name}", "page": page_id, "variant": "scan"})
        for variant in variants.get(page_id, []):
            rng = np.random.default_rng(zlib.crc32(f"{page_id}/{variant}".encode()))
            photo = make_variant(gray, spines.get(page_id, "left"), variant, rng)
            photo_path = testdata / "photos" / f"{page_id}__{variant}.jpg"
            cv2.imwrite(str(photo_path), photo, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY_PHOTO])
            entries.append({"file": f"photos/{photo_path.name}", "page": page_id, "variant": variant})
        print(f"{page_id}: scan + {len(variants.get(page_id, []))} photo variants", flush=True)
    (testdata / "variants.json").write_text(json.dumps(entries, indent=2) + "\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
