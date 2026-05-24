"""
email_engine/collage.py — Photo collage builder using Pillow.

Generates a 600px-wide JPEG collage from a list of manager-submitted photos
and returns it as a base64-encoded string for embedding directly in the
birthday email body.

Layout rules:
    1 photo  → single image centred, max 600×300
    2 photos → side by side (295×250 each) with 10px gap
    3–5 photos → first photo full-width top row (600×200),
                  remaining photos equal-width in a bottom row (10px gaps)
"""

import base64
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from utils.logger import logger, log_event

# Canvas settings
CANVAS_WIDTH = 600
GAP = 10
JPEG_QUALITY = 85
CORNER_RADIUS = 10
BG_COLOR = (255, 255, 255)  # White


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_image(path: str) -> Image.Image | None:
    """
    Load an image from disk, returning None on any error.

    Args:
        path: Absolute or relative path to an image file.

    Returns:
        PIL Image in RGB mode, or None if the file is missing/corrupt.
    """
    try:
        img = Image.open(path).convert("RGB")
        return img
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Skipping photo '{path}': {exc}")
        log_event("WARNING", "collage_photo_skipped", detail=f"{path}: {exc}")
        return None


def _fit_image(img: Image.Image, width: int, height: int) -> Image.Image:
    """
    Resize and centre-crop an image to exactly (width, height).

    Args:
        img:    Source PIL Image.
        width:  Target width in pixels.
        height: Target height in pixels.

    Returns:
        A new PIL Image of exactly (width, height).
    """
    img = ImageOps.fit(img, (width, height), method=Image.LANCZOS, centering=(0.5, 0.5))
    return img


def _round_corners(img: Image.Image, radius: int) -> Image.Image:
    """
    Apply a rounded-corner mask to an image.

    Args:
        img:    Source PIL Image (must be in RGB mode).
        radius: Corner radius in pixels.

    Returns:
        A new RGBA PIL Image with transparent rounded corners.
    """
    # Create a mask with rounded corners
    mask = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), img.size], radius=radius, fill=255)

    # Apply mask
    img_rgba = img.convert("RGBA")
    img_rgba.putalpha(mask)
    return img_rgba


def _paste_with_alpha(canvas: Image.Image, img_rgba: Image.Image, x: int, y: int) -> None:
    """
    Paste an RGBA image onto a canvas using its alpha channel as mask.

    Args:
        canvas:   The destination Image (RGB).
        img_rgba: The source RGBA image to paste.
        x, y:     Top-left position.
    """
    canvas.paste(img_rgba, (x, y), mask=img_rgba.split()[3])


# ---------------------------------------------------------------------------
# Layout builders
# ---------------------------------------------------------------------------

def _layout_one(images: list[Image.Image]) -> Image.Image:
    """Single photo: max 600×300, centred on white canvas."""
    w, h = CANVAS_WIDTH, 300
    img = _fit_image(images[0], w, h)
    canvas = Image.new("RGB", (w, h), BG_COLOR)
    _paste_with_alpha(canvas, _round_corners(img, CORNER_RADIUS), 0, 0)
    return canvas


def _layout_two(images: list[Image.Image]) -> Image.Image:
    """Two photos: side by side, 295×250 each with 10px gap."""
    cell_w = (CANVAS_WIDTH - GAP) // 2
    cell_h = 250
    canvas_h = cell_h
    canvas = Image.new("RGB", (CANVAS_WIDTH, canvas_h), BG_COLOR)

    for i, img in enumerate(images[:2]):
        fitted = _fit_image(img, cell_w, cell_h)
        x = i * (cell_w + GAP)
        _paste_with_alpha(canvas, _round_corners(fitted, CORNER_RADIUS), x, 0)

    return canvas


def _layout_multi(images: list[Image.Image]) -> Image.Image:
    """
    3–5 photos: first photo full-width top (600×200),
    remaining photos equal-width in a bottom row with 10px gaps.
    """
    top_h = 200
    bottom_h = 180
    canvas_h = top_h + GAP + bottom_h

    canvas = Image.new("RGB", (CANVAS_WIDTH, canvas_h), BG_COLOR)

    # Top photo — full width
    top = _fit_image(images[0], CANVAS_WIDTH, top_h)
    _paste_with_alpha(canvas, _round_corners(top, CORNER_RADIUS), 0, 0)

    # Bottom row — equal width cells
    remaining = images[1:]
    n = len(remaining)
    cell_w = (CANVAS_WIDTH - GAP * (n - 1)) // n
    y = top_h + GAP

    for i, img in enumerate(remaining):
        fitted = _fit_image(img, cell_w, bottom_h)
        x = i * (cell_w + GAP)
        _paste_with_alpha(canvas, _round_corners(fitted, CORNER_RADIUS), x, y)

    return canvas


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_collage(photo_paths: list[str]) -> str | None:
    """
    Build a photo collage from a list of file paths.

    Missing or corrupt photos are silently skipped (with a WARNING log).
    Returns None if no valid photos remain after filtering.

    Args:
        photo_paths: List of file paths to JPEG/PNG images.

    Returns:
        Base64-encoded JPEG string suitable for use in an <img src="data:...">
        tag, or None if the list is empty or all photos failed to load.
    """
    if not photo_paths:
        return None

    # Load all images, skipping failures
    images: list[Image.Image] = []
    for path in photo_paths[:5]:  # Hard cap at 5
        img = _load_image(path)
        if img is not None:
            images.append(img)

    if not images:
        log_event("WARNING", "collage_no_valid_photos", detail=str(photo_paths))
        return None

    # Choose layout based on photo count
    n = len(images)
    if n == 1:
        canvas = _layout_one(images)
    elif n == 2:
        canvas = _layout_two(images)
    else:
        canvas = _layout_multi(images)

    # Encode as base64 JPEG
    buffer = io.BytesIO()
    canvas.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    buffer.seek(0)
    encoded = base64.b64encode(buffer.read()).decode("utf-8")

    log_event("INFO", "collage_built", detail=f"{n} photos, canvas {canvas.size}")
    return encoded
