"""Extracción LOCAL de texto de adjuntos (sesión 05, CAMINO B).

Convierte los bytes de un fichero adjunto en texto plano, según su extensión:
  - .pdf  -> pypdf.PdfReader (concatena el texto de cada página).
  - .docx -> python-docx (concatena el texto de cada párrafo).
  - .txt  -> decodificado directo (UTF-8 con fallback tolerante).
  - otros -> se IGNORAN con un aviso (no abortamos la petición por un tipo raro).

CAMINO B = extracción local con parsers ligeros, sin mandar el binario a un
servicio externo (más barato, privado y sin dependencias de red). La contrapartida
es que no hacemos OCR ni entendemos PDFs escaneados como imagen; para texto nativo
es más que suficiente en esta fase.

DEFENSIVO: si un fichero concreto no se puede parsear (corrupto, formato raro), lo
saltamos con un log en vez de tumbar toda la petición. Un adjunto problemático no
debe impedir estimar con el resto del contexto.
"""

from __future__ import annotations

import io

from app.logging_config import get_logger

logger = get_logger(component="attachments")


def extract_text(filename: str, data: bytes) -> str:
    """Extrae el texto de UN adjunto a partir de su nombre y sus bytes.

    Args:
        filename: Nombre del fichero (se usa la extensión para elegir el parser).
        data:     Contenido binario del fichero.

    Returns:
        El texto extraído (puede ser ""), o "" si el tipo no está soportado o si
        el parseo falla (se registra un aviso en ambos casos).
    """
    name = (filename or "").lower()

    try:
        if name.endswith(".pdf"):
            return _extract_pdf(data)
        if name.endswith(".docx"):
            return _extract_docx(data)
        if name.endswith(".txt"):
            # Texto plano: decodificamos tolerando bytes inválidos.
            return data.decode("utf-8", errors="replace").strip()
    except Exception as exc:  # noqa: BLE001 — un adjunto roto no debe tumbar la petición
        logger.warning("attachment_parse_failed", filename=filename, reason=type(exc).__name__)
        return ""

    # Tipo no soportado: lo ignoramos con un aviso (no es un error fatal).
    logger.info("attachment_unsupported_type", filename=filename)
    return ""


def _extract_pdf(data: bytes) -> str:
    """Extrae el texto de un PDF con pypdf, concatenando todas las páginas."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages).strip()


def _extract_docx(data: bytes) -> str:
    """Extrae el texto de un .docx con python-docx, concatenando los párrafos."""
    import docx  # python-docx se importa como 'docx'

    document = docx.Document(io.BytesIO(data))
    paragraphs = [p.text for p in document.paragraphs]
    return "\n".join(paragraphs).strip()


def extract_attachments(files: list[tuple[str, bytes]]) -> str:
    """Extrae y CONCATENA el texto de varios adjuntos con separadores legibles.

    Cada adjunto se precede de un separador que identifica su nombre, para que el
    LLM sepa de qué documento procede cada bloque de texto:

        --- attachment: brief.pdf ---
        <texto del PDF>

        --- attachment: notas.txt ---
        <texto del TXT>

    Args:
        files: Lista de tuplas (filename, data_bytes).

    Returns:
        Texto concatenado de todos los adjuntos con texto útil (los vacíos o de tipo
        no soportado se omiten). Cadena vacía si no hay nada que aportar.
    """
    blocks: list[str] = []
    for filename, data in files:
        text = extract_text(filename, data)
        if not text:
            continue
        blocks.append(f"--- attachment: {filename} ---\n{text}")
    return "\n\n".join(blocks)
