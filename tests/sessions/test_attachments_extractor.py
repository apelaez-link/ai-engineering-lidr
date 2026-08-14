"""Tests de la extracción LOCAL de texto de adjuntos (sesión 05, CAMINO B).

Mockeamos pypdf.PdfReader y docx.Document para no depender de ficheros binarios
reales: comprobamos que cada parser se invoca para su extensión y que
extract_attachments concatena con los separadores esperados. También verificamos
el caso de tipo no soportado (se ignora sin romper).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.attachments.extractor import extract_attachments, extract_text


def test_extract_text_txt_decodes_directly() -> None:
    """Un .txt se decodifica directo a string."""
    text = extract_text("notes.txt", "Hello world".encode("utf-8"))
    assert text == "Hello world"


@patch("pypdf.PdfReader")
def test_extract_text_pdf_uses_pypdf(mock_reader_cls: MagicMock) -> None:
    """Un .pdf se parsea con pypdf.PdfReader, concatenando el texto de las páginas."""
    page1 = SimpleNamespace(extract_text=lambda: "Page one text")
    page2 = SimpleNamespace(extract_text=lambda: "Page two text")
    mock_reader_cls.return_value = SimpleNamespace(pages=[page1, page2])

    text = extract_text("brief.pdf", b"%PDF-fake-bytes")

    mock_reader_cls.assert_called_once()
    assert "Page one text" in text
    assert "Page two text" in text


@patch("docx.Document")
def test_extract_text_docx_uses_python_docx(mock_document: MagicMock) -> None:
    """Un .docx se parsea con docx.Document, concatenando los párrafos."""
    para1 = SimpleNamespace(text="First paragraph")
    para2 = SimpleNamespace(text="Second paragraph")
    mock_document.return_value = SimpleNamespace(paragraphs=[para1, para2])

    text = extract_text("spec.docx", b"PK-fake-docx-bytes")

    mock_document.assert_called_once()
    assert "First paragraph" in text
    assert "Second paragraph" in text


def test_extract_text_unsupported_type_is_ignored() -> None:
    """Un tipo no soportado (p. ej. .png) se ignora y devuelve cadena vacía."""
    assert extract_text("image.png", b"\x89PNG...") == ""


@patch("docx.Document")
@patch("pypdf.PdfReader")
def test_extract_attachments_concatenates_with_separators(
    mock_reader_cls: MagicMock, mock_document: MagicMock
) -> None:
    """extract_attachments une los textos con los separadores '--- attachment: ... ---'."""
    mock_reader_cls.return_value = SimpleNamespace(
        pages=[SimpleNamespace(extract_text=lambda: "PDF content")]
    )
    mock_document.return_value = SimpleNamespace(
        paragraphs=[SimpleNamespace(text="DOCX content")]
    )

    files = [
        ("brief.pdf", b"%PDF"),
        ("spec.docx", b"PK"),
        ("notes.txt", b"TXT content"),
        ("logo.png", b"\x89PNG"),  # no soportado: se omite
    ]
    combined = extract_attachments(files)

    # Cada adjunto con texto útil aparece con su separador.
    assert "--- attachment: brief.pdf ---" in combined
    assert "--- attachment: spec.docx ---" in combined
    assert "--- attachment: notes.txt ---" in combined
    assert "PDF content" in combined
    assert "DOCX content" in combined
    assert "TXT content" in combined
    # El tipo no soportado NO añade separador.
    assert "logo.png" not in combined


def test_extract_attachments_empty_list_returns_empty_string() -> None:
    """Sin adjuntos, el resultado es cadena vacía (no estorba en el prompt)."""
    assert extract_attachments([]) == ""
