"""File -> plain text, with an OCR fallback for scanned PDFs and images.

This is the ONLY module shared between the JD and resume ingestion flows.
It is a dumb format-handling helper: given a file path, return the text in
it. It knows nothing about job descriptions, resumes, or any other business
concept - callers (backend/services/jd/, backend/services/resume/) own all
of that.

Supported extensions: .pdf .docx .txt .rtf .png .jpg .jpeg
.doc (legacy binary Word) is deliberately NOT supported - there's no reliable
pure-Python parser for it without adding a system dependency (antiword /
LibreOffice headless), which isn't worth it for a POC. Callers should catch
UnsupportedFileTypeError and tell the user to convert to .docx or PDF.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber
import pytesseract
from docx import Document
from pdf2image import convert_from_path
from PIL import Image
from striprtf.striprtf import rtf_to_text

logger = logging.getLogger(__name__)

# Below this many characters, a PDF page is treated as image-only (scanned)
# and re-extracted via OCR instead of trusted as-is.
_MIN_CHARS_PER_PAGE = 20

_OCR_DPI = 300

# Public - the resume bulk-upload route checks this to reject an obviously
# unsupported file immediately (before any DB row is even worth PARSING).
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".rtf", ".png", ".jpg", ".jpeg"}


class UnsupportedFileTypeError(Exception):
    """The file extension isn't one we know how to parse."""


class FileTextExtractionError(Exception):
    """We recognized the format but couldn't get usable text out of it."""


@dataclass
class ExtractedText:
    """Result of extract_text(). `warnings` surfaces soft problems (e.g. an
    empty page) that didn't stop extraction but the caller may want to show.
    """

    text: str
    used_ocr: bool = False
    warnings: list[str] = field(default_factory=list)


def extract_text(file_path: str | Path) -> ExtractedText:
    """Extract plain text from `file_path`, dispatching on its extension.

    Raises UnsupportedFileTypeError for an unrecognized/unsupported
    extension, FileTextExtractionError if the format is supported but
    extraction genuinely fails (corrupt file, missing OCR binary, etc).
    """
    path = Path(file_path)
    if not path.exists():
        raise FileTextExtractionError(f"File not found: {path}")

    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileTypeError(
            f"Unsupported file type '{suffix or '(no extension)'}' for {path.name}. "
            f"Supported: {sorted(SUPPORTED_EXTENSIONS)}. "
            "Legacy .doc is not supported - please convert to .docx or PDF."
        )

    try:
        if suffix == ".pdf":
            return _extract_pdf(path)
        if suffix == ".docx":
            return ExtractedText(text=_extract_docx(path))
        if suffix == ".txt":
            return ExtractedText(text=_extract_txt(path))
        if suffix == ".rtf":
            return ExtractedText(text=_extract_rtf(path))
        return ExtractedText(text=_ocr_image_file(path), used_ocr=True)  # .png/.jpg/.jpeg
    except (UnsupportedFileTypeError, FileTextExtractionError):
        raise
    except pytesseract.TesseractNotFoundError as exc:
        raise FileTextExtractionError(
            "OCR requires the 'tesseract-ocr' system package, which isn't installed. "
            "Install it (e.g. `sudo apt-get install tesseract-ocr`) and retry."
        ) from exc
    except Exception as exc:
        raise FileTextExtractionError(f"Failed to extract text from {path.name}: {exc}") from exc


def _extract_pdf(path: Path) -> ExtractedText:
    """Native text per page, OCR'ing any page whose native text is too sparse
    (i.e. it's a scanned image, not real text) - so a mixed native/scanned
    PDF only pays the (slow) OCR cost on the pages that actually need it.
    """
    warnings: list[str] = []
    used_ocr = False
    page_texts: list[str] = []
    ocr_page_images: list[Image.Image] | None = None  # lazy: only rendered if a page needs it

    try:
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = (page.extract_text() or "").strip()
                if len(text) < _MIN_CHARS_PER_PAGE:
                    if ocr_page_images is None:
                        ocr_page_images = convert_from_path(str(path), dpi=_OCR_DPI)
                    if i < len(ocr_page_images):
                        text = pytesseract.image_to_string(ocr_page_images[i]).strip()
                        used_ocr = True
                        if not text:
                            warnings.append(f"Page {i + 1} produced no text even after OCR.")
                page_texts.append(text)
    except pytesseract.TesseractNotFoundError:
        raise
    except Exception as exc:
        # pdfplumber couldn't open it at all (corrupt/unusual PDF) - last
        # resort: render every page as an image and OCR the lot.
        logger.warning("pdfplumber failed to open %s (%s); falling back to full-document OCR", path, exc)
        images = convert_from_path(str(path), dpi=_OCR_DPI)
        page_texts = [pytesseract.image_to_string(image).strip() for image in images]
        used_ocr = True
        warnings.append("Native PDF parsing failed; the whole document was OCR'd instead.")

    return ExtractedText(text="\n\n".join(page_texts), used_ocr=used_ocr, warnings=warnings)


def _extract_docx(path: Path) -> str:
    document = Document(path)
    parts = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if row_text:
                parts.append(row_text)
    return "\n".join(parts)


def _extract_txt(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def _extract_rtf(path: Path) -> str:
    raw = _extract_txt(path)
    return rtf_to_text(raw)


def _ocr_image_file(path: Path) -> str:
    with Image.open(path) as image:
        return pytesseract.image_to_string(image).strip()
