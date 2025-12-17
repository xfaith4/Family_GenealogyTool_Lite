"""Media utilities for thumbnail generation and file handling."""
import hashlib
import os
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image

THUMBNAIL_SIZE = (300, 300)
SUPPORTED_IMAGE_TYPES = {
    "image/jpeg": [".jpg", ".jpeg"],
    "image/png": [".png"],
    "image/webp": [".webp"],
}

def compute_sha256(content: bytes) -> str:
    """Compute SHA256 hash of file content."""
    return hashlib.sha256(content).hexdigest()

def is_image(mime_type: str) -> bool:
    """Check if mime type is a supported image format."""
    return mime_type in SUPPORTED_IMAGE_TYPES

def get_extension_for_mime(mime_type: str, filename: str) -> str:
    """Get file extension for mime type, falling back to filename extension."""
    if mime_type in SUPPORTED_IMAGE_TYPES:
        return SUPPORTED_IMAGE_TYPES[mime_type][0]
    
    ext = os.path.splitext(filename)[1].lower()
    return ext if ext else ".bin"

def create_thumbnail(
    source_path: str,
    thumbnail_dir: str,
    base_name: str,
) -> Optional[Tuple[str, int, int]]:
    """
    Create a thumbnail for an image.
    
    Returns:
        Tuple of (thumbnail_path, width, height) or None if creation fails
    """
    try:
        with Image.open(source_path) as img:
            # Convert RGBA to RGB if needed
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Create thumbnail
            img.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
            
            # Save thumbnail
            thumb_path = os.path.join(thumbnail_dir, f"thumb_{base_name}.jpg")
            img.save(thumb_path, "JPEG", quality=85, optimize=True)
            
            return (thumb_path, img.width, img.height)
    except Exception as e:
        # If thumbnail generation fails, log and continue
        print(f"Failed to create thumbnail for {source_path}: {e}")
        return None

def safe_filename(filename: str, sha256: str, mime_type: str) -> str:
    """
    Generate a safe filename using SHA256 hash and appropriate extension.
    
    Args:
        filename: Original filename
        sha256: SHA256 hash of the file
        mime_type: MIME type of the file
        
    Returns:
        Safe filename with extension
    """
    ext = get_extension_for_mime(mime_type, filename)
    return f"{sha256}{ext}"
