"""Runner de la evaluación de recuperación (sesión 10).

Compara 4 configuraciones sobre el golden set y mide precisión@5 + latencia:

    A  vectorial      / sin rerank      (línea base = sesión 08)
    B  híbrida (RRF)   / sin rerank
    C  vectorial      / rerank cross-encoder
    D  híbrida (RRF)   / rerank cross-encoder

Ejecuta contra Postgres REAL (los 37 chunks ya ingeridos) y usa embeddings REALES de
OpenAI para la consulta y el cross-encoder REAL para el rerank. Escribe:
    evals/retrieval/results.csv   (una fila por config×consulta)
    evals/retrieval/REPORT.md     (tablas comparativas + resumen)

Uso:
    docker compose up -d postgres
    DATABASE_URL=postgresql+asyncpg://estimator:estimator@localhost:5433/estimator \\
      uv run python -m evals.retrieval.run

NOTA SOBRE EL POOL DE RECALL (importante para leer los números): el patrón
recall-then-rerank recupera un pool ANCHO y reordena a k. El enunciado sugiere 50->5,
pensado para un corpus grande. El nuestro tiene 37 chunks: con pool=50 el recall
devolvería TODO el corpus y las configs C y D reordenarían el MISMO conjunto (idéntico
resultado), anulando la comparación. Por eso medimos con pool=15 (< 37): así la etapa
de recall filtra de verdad y vectorial-vs-híbrida alimentan candidatos DISTINTOS al
reranker. Es una adaptación consciente al tamaño del corpus, no un cambio de la técnica.
"""

from __future__ import annotations

import asyncio
import csv
import statistics
import time
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.embedding_pipeline.embedder import OpenAIEmbedder
from app.embedding_pipeline.hybrid import hybrid_search
from app.embedding_pipeline.repository import search_chunks
from app.embedding_pipeline.reranker import CrossEncoderReranker

from .golden_set import GOLDEN_SET, GoldenQuery
from .metrics import mean, precision_at_k

K = 5  # corte de la métrica (precisión@5) y top-k final que ve el usuario.
POOL = 15  # anchura de recall antes de rerank/fusión (< 37 = tamaño del corpus; ver módulo).
REPS = 3  # repeticiones por medida de latencia; nos quedamos con la MEDIANA.

_HERE = Path(__file__).resolve().parent

CONFIGS = [
    {"id": "A", "label": "vectorial / sin rerank", "mode": "vector", "rerank": False},
    {"id": "B", "label": "híbrida (RRF) / sin rerank", "mode": "hybrid", "rerank": False},
    {"id": "C", "label": "vectorial / rerank", "mode": "vector", "rerank": True},
    {"id": "D", "label": "híbrida (RRF) / rerank", "mode": "hybrid", "rerank": True},
]


async def _retrieve(session, cfg, query_text, query_vector, reranker, fulltext_config):
    """Ejecuta la recuperación de UNA config y devuelve el top-K de chunks."""
    recall_k = POOL if cfg["rerank"] else K
    if cfg["mode"] == "hybrid":
        rows = await hybrid_search(
            session,
            query_vector,
            query_text,
            k=recall_k,
            candidate_pool=POOL,
            fulltext_config=fulltext_config,
        )
    else:
        rows = await search_chunks(session, query_vector, recall_k)
    if cfg["rerank"]:
        rows = reranker.rerank(query_text, rows, K)
    return rows[:K]


def _budget_ids(rows) -> list[str]:
    return [(r.get("metadata") or {}).get("budget_id") for r in rows]


async def _measure(session, cfg, gq: GoldenQuery, query_vector, reranker, cfg_lang):
    """Mide una config sobre una consulta: precisión@5 (determinista) + latencia mediana."""
    # Precisión: el resultado es determinista, se calcula una vez.
    rows = await _retrieve(session, cfg, gq.query, query_vector, reranker, cfg_lang)
    retrieved = _budget_ids(rows)
    precision = precision_at_k(retrieved, gq.relevant_budget_ids, K)

    # Latencia: repetimos y nos quedamos con la mediana (amortigua ruido del sistema).
    latencies_ms: list[float] = []
    for _ in range(REPS):
        started = time.perf_counter()
        await _retrieve(session, cfg, gq.query, query_vector, reranker, cfg_lang)
        latencies_ms.append((time.perf_counter() - started) * 1000)

    return {
        "config": cfg["id"],
        "label": cfg["label"],
        "query_id": gq.id,
        "precision_at_5": precision,
        "latency_ms": statistics.median(latencies_ms),
        "top5_budgets": ";".join(b or "?" for b in retrieved),
    }


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    embedder = OpenAIEmbedder()
    reranker = CrossEncoderReranker(model_name=settings.rerank_model)

    # Embebemos cada consulta UNA vez (coste compartido por todas las configs) y de paso
    # calentamos el reranker, para que la carga del modelo no contamine la latencia.
    print("Embebiendo consultas del golden set (OpenAI)...")
    query_vectors: dict[str, list[float]] = {}
    for gq in GOLDEN_SET:
        query_vectors[gq.id] = embedder.embed_one(gq.query)
    print("Calentando el cross-encoder...")
    reranker.rerank("warm up", [{"content": "warm up document"}], 1)

    rows_out = []
    async with session_maker() as session:
        for cfg in CONFIGS:
            for gq in GOLDEN_SET:
                res = await _measure(
                    session, cfg, gq, query_vectors[gq.id], reranker, settings.fulltext_language
                )
                rows_out.append(res)
                print(
                    f"[{res['config']}] {res['query_id']}  P@5={res['precision_at_5']:.2f}  "
                    f"lat={res['latency_ms']:.1f}ms  -> {res['top5_budgets']}"
                )
    await engine.dispose()

    _write_csv(rows_out)
    _write_report(rows_out)
    print(f"\nEscrito: {(_HERE / 'results.csv')}")
    print(f"Escrito: {(_HERE / 'REPORT.md')}")


def _write_csv(rows_out) -> None:
    path = _HERE / "results.csv"
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "config",
                "label",
                "query_id",
                "precision_at_5",
                "latency_ms",
                "top5_budgets",
            ],
        )
        writer.writeheader()
        for r in rows_out:
            writer.writerow({**r, "latency_ms": round(r["latency_ms"], 1)})


def _agg(rows_out):
    """Agrega por config: precisión@5 media y latencia mediana media."""
    summary = []
    for cfg in CONFIGS:
        subset = [r for r in rows_out if r["config"] == cfg["id"]]
        summary.append(
            {
                "id": cfg["id"],
                "label": cfg["label"],
                "precision": mean([r["precision_at_5"] for r in subset]),
                "latency": mean([r["latency_ms"] for r in subset]),
            }
        )
    return summary


def _write_report(rows_out) -> None:
    summary = _agg(rows_out)
    query_ids = [gq.id for gq in GOLDEN_SET]

    lines = []
    lines.append("# Sesión 10 — Resultados de recuperación (precisión@5 + latencia)\n")
    lines.append(
        "> Generado por `evals/retrieval/run.py` contra Postgres real (37 chunks), "
        "embeddings reales de OpenAI y cross-encoder real. "
        f"Golden set: {len(GOLDEN_SET)} consultas. k={K}, pool de recall={POOL}, "
        f"repeticiones de latencia={REPS} (mediana).\n"
    )

    lines.append("## Tabla comparativa (media sobre el golden set)\n")
    lines.append("| Config | Descripción | Precisión@5 (media) | Latencia media (ms) |")
    lines.append("|--------|-------------|--------------------:|--------------------:|")
    for s in summary:
        lines.append(
            f"| {s['id']} | {s['label']} | {s['precision']:.3f} | {s['latency']:.1f} |"
        )
    lines.append("")

    lines.append("## Precisión@5 por consulta\n")
    header = "| Config | " + " | ".join(query_ids) + " |"
    sep = "|--------|" + "|".join(["------:"] * len(query_ids)) + "|"
    lines.append(header)
    lines.append(sep)
    for cfg in CONFIGS:
        cells = []
        for qid in query_ids:
            r = next(r for r in rows_out if r["config"] == cfg["id"] and r["query_id"] == qid)
            cells.append(f"{r['precision_at_5']:.2f}")
        lines.append(f"| {cfg['id']} | " + " | ".join(cells) + " |")
    lines.append("")

    lines.append("## Latencia por consulta (ms, mediana de %d)\n" % REPS)
    lines.append(header)
    lines.append(sep)
    for cfg in CONFIGS:
        cells = []
        for qid in query_ids:
            r = next(r for r in rows_out if r["config"] == cfg["id"] and r["query_id"] == qid)
            cells.append(f"{r['latency_ms']:.0f}")
        lines.append(f"| {cfg['id']} | " + " | ".join(cells) + " |")
    lines.append("")

    (_HERE / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
