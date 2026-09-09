"""Reading text out of the file types recruiters actually upload."""

import pytest

from backend.files import UnreadableFile, extract_text


def test_reads_a_text_file(tmp_path):
    path = tmp_path / "cv.txt"
    path.write_text("Priya Nair\nSenior Python Developer\n8 years experience")

    assert "Priya Nair" in extract_text(path)


def test_reads_a_docx_including_tables(tmp_path):
    docx = pytest.importorskip("docx")

    document = docx.Document()
    document.add_paragraph("Arjun Mehta")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Skills"
    table.rows[0].cells[1].text = "React, TypeScript"
    path = tmp_path / "cv.docx"
    document.save(str(path))

    text = extract_text(path)
    assert "Arjun Mehta" in text
    # Many resumes lay their skills out in a table, so those cells must be read.
    assert "React, TypeScript" in text


def test_rejects_an_unsupported_type(tmp_path):
    path = tmp_path / "cv.pages"
    path.write_bytes(b"not a resume")

    with pytest.raises(UnreadableFile, match="Unsupported file type"):
        extract_text(path)


def test_rejects_a_file_with_no_text(tmp_path):
    """A scanned/image-only document must fail loudly, not screen as an
    empty candidate."""
    path = tmp_path / "scan.txt"
    path.write_text("   \n  \n")

    with pytest.raises(UnreadableFile, match="No text found"):
        extract_text(path)
