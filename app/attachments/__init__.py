"""Paquete de ADJUNTOS del estimador conversacional (sesión 05).

"Contexto enriquecido" por la vía de los documentos: el cliente puede subir PDFs,
Word o textos (briefs, especificaciones, actas de reunión) y su contenido se
inyecta en el prompt junto al mensaje de texto.

Decisión de diseño (CAMINO B): la extracción de texto se hace LOCALMENTE con
parsers ligeros (pypdf para PDF, python-docx para Word, lectura directa para .txt),
sin enviar el binario a ningún servicio externo. Más simple, más barato y privado.
"""

from app.attachments.extractor import extract_attachments, extract_text

__all__ = ["extract_attachments", "extract_text"]
