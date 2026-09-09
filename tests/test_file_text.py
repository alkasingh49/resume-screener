"""Tests for backend/utils/file_text.py against real sample files.

PDF/DOCX/TXT/RTF go through the real parsing libraries end to end. The
scanned-PDF and image paths use real pdf2image/poppler rendering (poppler is
installed) but mock pytesseract's OCR call, since tesseract-ocr itself isn't
installed on this machine - see README for the system dependency. A
dedicated test proves the missing-binary case is still wrapped in a clear
error rather than a raw traceback.
"""

from pathlib import Path

import pytest
import pytesseract

from backend.utils import file_text

FIXTURES = Path(__file__).parent / "fixtures"


def test_pdf_with_native_text_extracted_without_ocr():
    result = file_text.extract_text(FIXTURES / "sample_jd.pdf")
    assert "Backend Engineer" in result.text
    assert "Must-have skills" in result.text
    assert result.used_ocr is False


def test_docx_extracts_paragraphs_and_tables():
    result = file_text.extract_text(FIXTURES / "sample_resume.docx")
    assert "Priya Sharma" in result.text
    assert "priya.sharma@example.com" in result.text
    assert "Python" in result.text and "5" in result.text  # from the table


def test_txt_round_trips_content():
    result = file_text.extract_text(FIXTURES / "sample.txt")
    assert "Ada Lovelace" in result.text
    assert "ada@example.com" in result.text


def test_rtf_strips_markup():
    result = file_text.extract_text(FIXTURES / "sample.rtf")
    assert "Grace Hopper" in result.text
    assert r"\rtf1" not in result.text  # markup actually stripped


def test_unsupported_extension_raises(tmp_path):
    fake_doc = tmp_path / "legacy.doc"
    fake_doc.write_bytes(b"not a real doc file")
    with pytest.raises(file_text.UnsupportedFileTypeError, match="not supported"):
        file_text.extract_text(fake_doc)


def test_missing_file_raises():
    with pytest.raises(file_text.FileTextExtractionError, match="not found"):
        file_text.extract_text(FIXTURES / "does_not_exist.pdf")


def test_scanned_pdf_falls_back_to_ocr(monkeypatch):
    """scanned.pdf has no native text layer - real poppler rendering runs,
    the OCR text result itself is mocked (no tesseract binary here)."""
    monkeypatch.setattr(
        pytesseract, "image_to_string", lambda image: "Name: Alan Turing (OCR'd)"
    )
    result = file_text.extract_text(FIXTURES / "scanned.pdf")
    assert result.used_ocr is True
    assert "Alan Turing" in result.text


def test_image_file_always_goes_through_ocr(monkeypatch):
    monkeypatch.setattr(pytesseract, "image_to_string", lambda image: "Name: Alan Turing")
    result = file_text.extract_text(FIXTURES / "scanned_snippet.png")
    assert result.used_ocr is True
    assert "Alan Turing" in result.text


def test_missing_tesseract_binary_is_wrapped_in_a_clear_error(monkeypatch):
    def _raise(*args, **kwargs):
        raise pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(pytesseract, "image_to_string", _raise)
    with pytest.raises(file_text.FileTextExtractionError, match="tesseract-ocr"):
        file_text.extract_text(FIXTURES / "scanned_snippet.png")
