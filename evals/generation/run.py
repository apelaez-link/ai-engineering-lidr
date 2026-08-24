"""Runner de evaluación de la generación (sesión 11).

Para cada consulta del golden set enriquecido:
  1. recupera contexto (retrieval de la S10),
  2. genera la estimación citada (generador de la S11),
  3. verifica las citaciones (dangling detection),
  4. prepara la muestra RAGAS (question, answer, contexts, ground_truth).

Luego corre RAGAS con las 4 métricas (faithfulness, answer_relevancy, context_precision,
context_recall) y escribe:
    evals/generation/REPORT.md          (tabla RAGAS + verificación de citas + nota)
    evals/generation/results.csv        (una fila por consulta)
    evals/generation/sample_estimate.json (una estimación real + su informe de citación)

Uso:
    docker compose up -d postgres
    DATABASE_URL=postgresql+asyncpg://estimator:estimator@localhost:5433/estimator \\
      uv run python -m evals.generation.run

Hace llamadas REALES a OpenAI (generación + juez de RAGAS + embeddings). k de contexto=8.
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.embedding_pipeline.embedder import OpenAIEmbedder  # noqa: E402
from app.embedding_pipeline.repository import search_chunks  # noqa: E402
from app.generation.generator import generate_estimate, retrieved_chunk_ids  # noqa: E402
from app.generation.verify import verify_citations  # noqa: E402

from .golden_set import GENERATION_GOLDEN_SET  # noqa: E402

K = 8  # nº de chunks de contexto que ve el generador
_HERE = Path(__file__).resolve().parent
_METRICS = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]


async def _generate_all(session, embedder):
    """Genera estimación + verificación + muestra RAGAS para cada consulta."""
    from ragas import SingleTurnSample

    samples = []
    records = []
    for gq in GENERATION_GOLDEN_SET:
        query_vector = embedder.embed_one(gq.query)
        retrieved = await search_chunks(session, query_vector, K)
        estimate = generate_estimate(gq.query, retrieved)
        report = verify_citations(
            estimate, retrieved_chunk_ids(retrieved), request_id=gq.id
        )
        samples.append(
            SingleTurnSample(
                user_input=gq.query,
                response=estimate.as_text(),
                retrieved_contexts=[r["content"] for r in retrieved],
                reference=gq.ground_truth,
            )
        )
        records.append({"id": gq.id, "estimate": estimate, "report": report})
        print(
            f"[{gq.id}] líneas={report.total_lines} grounded={report.grounded} "
            f"dangling={report.dangling} insufficient={report.insufficient} "
            f"total={estimate.total_hours:g}h"
        )
    return samples, records


def _run_ragas(samples):
    from ragas import EvaluationDataset, RunConfig, evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import (
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings

    settings = get_settings()
    key = settings.openai_api_key
    judge = LangchainLLMWrapper(ChatOpenAI(model="gpt-4o-mini", api_key=key, temperature=0))
    emb = LangchainEmbeddingsWrapper(
        OpenAIEmbeddings(model="text-embedding-3-small", api_key=key)
    )
    result = evaluate(
        dataset=EvaluationDataset(samples=samples),
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=judge,
        embeddings=emb,
        run_config=RunConfig(max_workers=4),
    )
    return result.to_pandas()


async def _generate_phase():
    """Parte ASYNC (retrieval + generación). Se ejecuta con asyncio.run y cierra el
    bucle antes de llamar a RAGAS, que gestiona su propio event loop internamente."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    embedder = OpenAIEmbedder()
    try:
        async with session_maker() as session:
            return await _generate_all(session, embedder)
    finally:
        await engine.dispose()


def main() -> None:
    print("Generando estimaciones citadas del golden set...")
    samples, records = asyncio.run(_generate_phase())  # bucle async cerrado al volver

    print("Ejecutando RAGAS (juez LLM + embeddings)...")
    df = _run_ragas(samples)  # síncrono, sin bucle async activo

    _write_outputs(df, records)
    print(f"\nEscrito: {_HERE / 'REPORT.md'}")
    print(f"Escrito: {_HERE / 'results.csv'}")
    print(f"Escrito: {_HERE / 'sample_estimate.json'}")


def _fmt(x) -> str:
    try:
        return f"{float(x):.3f}"
    except (TypeError, ValueError):
        return "n/a"


def _write_outputs(df, records) -> None:
    ids = [r["id"] for r in records]
    by_id = {r["id"]: r for r in records}

    # results.csv
    with (_HERE / "results.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["query_id", *_METRICS, "grounded", "dangling", "insufficient"])
        for i, qid in enumerate(ids):
            rep = by_id[qid]["report"]
            w.writerow(
                [qid, *[_fmt(df.iloc[i][m]) for m in _METRICS],
                 rep.grounded, rep.dangling, rep.insufficient]
            )

    # sample_estimate.json (primera consulta: estimación real + informe de citación)
    first = records[0]
    (_HERE / "sample_estimate.json").write_text(
        json.dumps(
            {
                "query_id": first["id"],
                "estimate": first["estimate"].model_dump(),
                "citation_report": first["report"].model_dump(),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # REPORT.md
    means = {m: df[m].astype(float).mean() for m in _METRICS}
    lines = ["# Sesión 11 — Evaluación de la generación (RAGAS + citación)\n"]
    lines.append(
        "> Generado por `evals/generation/run.py`. Pipeline real (retrieval S10 + "
        f"generador citado S11), juez RAGAS gpt-4o-mini. {len(ids)} consultas, k de "
        f"contexto={K}.\n"
    )
    lines.append("## Métricas RAGAS por consulta\n")
    lines.append("| Consulta | faithfulness | answer_relevancy | context_precision | context_recall |")
    lines.append("|----------|-------------:|-----------------:|------------------:|---------------:|")
    for i, qid in enumerate(ids):
        lines.append(
            f"| {qid} | " + " | ".join(_fmt(df.iloc[i][m]) for m in _METRICS) + " |"
        )
    lines.append(
        "| **media** | " + " | ".join(f"**{means[m]:.3f}**" for m in _METRICS) + " |"
    )
    lines.append("")
    lines.append("## Verificación de citaciones por consulta\n")
    lines.append("| Consulta | líneas | grounded | dangling | insufficient |")
    lines.append("|----------|-------:|---------:|---------:|-------------:|")
    for qid in ids:
        rep = by_id[qid]["report"]
        lines.append(
            f"| {qid} | {rep.total_lines} | {rep.grounded} | {rep.dangling} | {rep.insufficient} |"
        )
    total_dangling = sum(by_id[q]["report"].dangling for q in ids)
    lines.append("")
    lines.append(
        f"**Citaciones colgantes en todo el golden set: {total_dangling}.** "
        "(La detección se valida además con un caso a propósito en "
        "`tests/generation/test_verify.py`.)\n"
    )
    (_HERE / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
