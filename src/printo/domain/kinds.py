"""The only file kinds printO accepts, and the extensions it stores them under."""

PDF, IMAGE, OFFICE = "pdf", "image", "office"
KINDS = frozenset({PDF, IMAGE, OFFICE})

# Stored extension is chosen from the file contents, never from the name the phone sent.
EXTENSIONS = {
    ".pdf": PDF,
    ".jpg": IMAGE,
    ".png": IMAGE,
    ".webp": IMAGE,
    ".gif": IMAGE,
    ".bmp": IMAGE,
    ".tif": IMAGE,
    ".tiff": IMAGE,
    ".heic": IMAGE,
    ".heif": IMAGE,
    ".docx": OFFICE,
    ".doc": OFFICE,
    ".odt": OFFICE,
    ".rtf": OFFICE,
}
