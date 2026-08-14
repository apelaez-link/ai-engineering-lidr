"""Generador de PDFs sintéticos para el stress test (sesión 06, BLOQUE 3).

Para medir cómo afecta el TAMAÑO del contexto enriquecido al CAG necesitamos adjuntos
de tamaños controlados. Este script genera PDFs de ~5, 20, 50 y 100 KB rellenos de
Lorem Ipsum repetido, usando fpdf2. La convención del ejercicio:

  - 0 KB  = AUSENCIA de adjunto (no se genera fichero; el runner manda solo el transcript).
  - 5/20/50/100 KB = PDFs reales con ese tamaño aproximado.

DETERMINISMO Y NO-COMMIT:
  Los PDFs NO se versionan (son binarios grandes y, sobre todo, redundantes: se
  regeneran a partir de este script en segundos). Por eso evals/stress/fixtures/*.pdf
  está en .gitignore y solo comiteamos ESTE script. El contenido es determinista
  (mismo Lorem Ipsum, misma semilla de repetición), así que dos ejecuciones producen
  PDFs equivalentes en tamaño y contenido.

  fpdf2 escribe metadatos de fecha de creación en el PDF, lo que haría variar los
  bytes entre ejecuciones; fijamos una fecha de creación constante para que el binario
  sea reproducible byte a byte (útil si alguien decidiera versionarlos en el futuro).

USO COMO SCRIPT (genera en disco, por defecto en la propia carpeta fixtures):
    uv run python -m evals.stress.fixtures.build_pdfs --out-dir /tmp/stress_pdfs

USO COMO LIBRERÍA (lo que hace el runner): generar los bytes en memoria sin tocar disco:
    from evals.stress.fixtures.build_pdfs import build_pdf_bytes
    data = build_pdf_bytes(20)   # ~20 KB de PDF
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

# Los tamaños objetivo (en KB) que pide el ejercicio. 0 no se genera (= sin adjunto).
TARGET_SIZES_KB: tuple[int, ...] = (5, 20, 50, 100)

# Fecha de creación FIJA para que el binario sea reproducible (sin esto, fpdf2 mete
# la fecha actual y los bytes cambian en cada ejecución).
_FIXED_CREATION_DATE = datetime(2026, 1, 1, tzinfo=timezone.utc)

# Un párrafo de Lorem Ipsum. Lo repetimos hasta alcanzar el tamaño objetivo.
_LOREM = (
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod "
    "tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, "
    "quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo "
    "consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse "
    "cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non "
    "proident, sunt in culpa qui officia deserunt mollit anim id est laborum."
)


def _new_pdf():
    """Crea un objeto FPDF base con fecha de creación fija (import perezoso de fpdf2)."""
    from fpdf import FPDF

    pdf = FPDF()
    # Fecha de creación constante -> binario reproducible.
    pdf.set_creation_date(_FIXED_CREATION_DATE) if hasattr(pdf, "set_creation_date") else None
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    return pdf


def _render_bytes(paragraphs: int) -> bytes:
    """Renderiza un PDF con N párrafos de Lorem Ipsum y devuelve sus bytes."""
    pdf = _new_pdf()
    for _ in range(paragraphs):
        # multi_cell con ancho 0 = hasta el margen derecho; reparte el texto en líneas.
        pdf.multi_cell(0, 6, _LOREM)
        pdf.ln(2)
    # fpdf2 devuelve un bytearray; lo normalizamos a bytes.
    return bytes(pdf.output())


@lru_cache(maxsize=None)
def build_pdf_bytes(target_kb: int) -> bytes:
    """Genera los bytes de un PDF de aproximadamente ``target_kb`` KB.

    Estrategia simple y determinista: empezamos con un párrafo e incrementamos el
    número de párrafos hasta que el PDF renderizado alcanza o supera el tamaño
    objetivo. Como el contenido es fijo, el resultado es reproducible.

    MEMOIZADO con @lru_cache: para un mismo tamaño el PDF es idéntico, así que el
    runner —que pide el mismo tamaño en cada turno de cada conversación— no paga el
    coste de re-renderizarlo decenas de veces (clave para que la matriz completa del
    stress test corra en segundos y no en minutos).

    Args:
        target_kb: Tamaño objetivo en KB. Debe ser > 0 (0 = sin adjunto, no se llama aquí).

    Returns:
        Los bytes del PDF (tamaño >= target_kb, lo más ajustado posible por arriba).

    Raises:
        ValueError: si target_kb <= 0 (0 significa "sin adjunto", no un PDF vacío).
    """
    if target_kb <= 0:
        raise ValueError(
            "target_kb debe ser > 0. El tamaño 0 representa AUSENCIA de adjunto: "
            "no se genera ningún PDF en ese caso."
        )

    target_bytes = target_kb * 1024
    paragraphs = 1
    data = _render_bytes(paragraphs)

    # Crecemos el nº de párrafos hasta alcanzar el objetivo. El salto inicial se
    # acelera (x1.5) para no iterar de uno en uno en los tamaños grandes, y luego
    # afinamos sumando de uno en uno. Mantiene el coste de generación bajo.
    while len(data) < target_bytes:
        # Estimación: ¿cuántos párrafos faltan según el tamaño medio por párrafo?
        bytes_per_paragraph = max(1, len(data) // paragraphs)
        remaining = target_bytes - len(data)
        step = max(1, remaining // bytes_per_paragraph)
        paragraphs += step
        data = _render_bytes(paragraphs)

    return data


def build_all_pdfs(out_dir: Path) -> dict[int, Path]:
    """Genera los PDFs de todos los tamaños objetivo en ``out_dir`` y devuelve sus rutas.

    Args:
        out_dir: Carpeta de salida (se crea si no existe).

    Returns:
        Dict {tamaño_kb -> ruta_del_pdf}.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[int, Path] = {}
    for size_kb in TARGET_SIZES_KB:
        data = build_pdf_bytes(size_kb)
        path = out_dir / f"lorem_{size_kb}kb.pdf"
        path.write_bytes(data)
        paths[size_kb] = path
    return paths


def main() -> None:
    """Punto de entrada CLI: genera los PDFs en disco e informa de sus tamaños reales."""
    parser = argparse.ArgumentParser(
        description="Genera PDFs sintéticos (Lorem Ipsum) de ~5/20/50/100 KB para el stress test."
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).parent,
        help="Carpeta de salida (por defecto, la propia carpeta fixtures/). Los PDFs están en .gitignore.",
    )
    args = parser.parse_args()

    paths = build_all_pdfs(args.out_dir)
    print(f"PDFs generados en {args.out_dir}:")
    for size_kb, path in paths.items():
        real_kb = path.stat().st_size / 1024
        print(f"  - {path.name}: objetivo ~{size_kb} KB, real {real_kb:.1f} KB")


if __name__ == "__main__":
    main()
