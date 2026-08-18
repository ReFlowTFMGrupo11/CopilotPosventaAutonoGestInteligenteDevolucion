"""
Ingesta de embeddings de políticas (RAG).

Trocea (chunking) los documentos markdown de `dataset/policies/*.md` y
genera sus embeddings con `text-embedding-3-small` (el mismo modelo que usa
`search_return_policy` en `backend/services/supabase_service.py`) para
poblar la tabla `policy_embeddings`. Es el paso de ingesta que
`dataset/README.md` (sección "Cómo cargar el dataset en Supabase", punto 3)
deja documentado como pendiente por requerir credenciales y llamadas de red.

Requiere:
    - OPENAI_API_KEY y las credenciales de Supabase en `.env` (ver
      `backend/db/supabase_client.py`).
    - Las migraciones aplicadas y `return_policies` ya cargada (p. ej.
      `supabase/seed_synthetic.sql`, que inserta una fila por cada una de
      las 16 categorías de `dataset/generate_dataset.py::CATEGORIES`) —
      si una categoría VÁLIDA no tiene (todavía) fila activa en
      `return_policies`, su documento se salta con un aviso en vez de
      fallar. Un `--category` que no exista en absoluto sí es un error
      (ValueError con la lista de categorías válidas): un typo no debe
      pasar desapercibido como "solo se ingestó el marco general".

Uso:
    python -m dataset.ingest_policy_embeddings
    python -m dataset.ingest_policy_embeddings --category electronica_informatica
    python -m dataset.ingest_policy_embeddings --dry-run   # solo trocea y cuenta, sin red

Es "reemplaza, no acumula": antes de insertar los chunks de una política,
borra los que ya hubiera para ese `policy_id` (o para `policy_id IS NULL`,
el caso del marco general), así que ejecutar el script varias veces no va
duplicando filas en `policy_embeddings`.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from typing import Any, Optional

import tiktoken
from dotenv import load_dotenv
from openai import OpenAI

from backend.db.supabase_client import get_supabase_client
from dataset.generate_dataset import CATEGORIES, POLICIES_DIR  # POLICIES_DIR → dataset/rag/policies/

load_dotenv(override=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# El marco general (sección 5, umbral HITL, plazos legales...) no está
# atado a ninguna categoría: se ingesta con policy_id = NULL, y el RAG lo
# encuentra igual porque match_policy_embeddings busca por similitud del
# embedding, no por policy_id.
GENERAL_POLICY_DOC = "00_marco_general_devoluciones.md"

# Mismo modelo que ya usa search_return_policy para la consulta del cliente
# (backend/services/supabase_service.py): si no coincidiera, las distancias
# vectoriales entre pregunta y política dejarían de tener sentido.
EMBEDDING_MODEL = "text-embedding-3-small"

# dataset/README.md documenta chunks de "~300-500 tokens" — se respeta ese
# rango salvo que un único párrafo (p. ej. la tabla de la sección 6) ya lo
# supere él solo, en cuyo caso se deja como chunk propio sin partirlo.
MIN_CHUNK_TOKENS = 200
MAX_CHUNK_TOKENS = 500

# cl100k_base: el encoding de text-embedding-3-small (y de los modelos
# gpt-4o/gpt-5), usado aquí solo para MEDIR tamaño de chunk, no para
# tokenizar de verdad la llamada (eso lo hace la API de OpenAI).
_encoding = tiktoken.get_encoding("cl100k_base")


def _count_tokens(text: str) -> int:
    return len(_encoding.encode(text))


def _split_into_sections(markdown_text: str) -> list[tuple[str, str]]:
    """Divide el markdown por encabezados de nivel 2 (``## ...``), devolviendo
    pares ``(encabezado, texto_de_la_sección)``. El texto antes del primer
    ``##`` (título del documento, "Última revisión", etc.) queda como una
    sección con encabezado vacío.

    Encabezados de nivel 1 (``# ...``) no se usan como separador: cada
    documento de dataset/policies/ solo tiene uno, el título.
    """
    sections: list[tuple[str, list[str]]] = [("", [])]
    for line in markdown_text.splitlines():
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        else:
            sections[-1][1].append(line)
    return [
        (header, "\n".join(body).strip())
        for header, body in sections
        if "\n".join(body).strip()
    ]


def _chunk_section(header: str, body: str) -> list[str]:
    """Agrupa los párrafos (separados por línea en blanco) de una sección en
    chunks de entre ``MIN_CHUNK_TOKENS`` y ``MAX_CHUNK_TOKENS`` tokens, sin
    partir nunca un párrafo por la mitad. Cada chunk se antepone con el
    encabezado de su sección para que tenga sentido leído de forma aislada
    (así es como lo recupera el RAG, un chunk a la vez).
    """
    prefix = f"## {header}\n\n" if header else ""
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    def flush() -> None:
        if current:
            chunks.append(prefix + "\n\n".join(current))

    for paragraph in paragraphs:
        paragraph_tokens = _count_tokens(paragraph)

        if paragraph_tokens > MAX_CHUNK_TOKENS:
            # Un párrafo que ya por sí solo supera el máximo (la tabla de
            # la sección 6, por ejemplo): en vez de partirlo a ciegas por
            # caracteres (rompería filas de tabla o frases a la mitad), se
            # fusiona con lo que hubiera acumulado hasta ahora (si lo hay)
            # en un único chunk, para no dejar justo delante un chunk
            # huérfano demasiado pequeño.
            current.append(paragraph)
            chunks.append(prefix + "\n\n".join(current))
            current, current_tokens = [], 0
            continue

        if current_tokens + paragraph_tokens > MAX_CHUNK_TOKENS and current_tokens >= MIN_CHUNK_TOKENS:
            flush()
            current, current_tokens = [], 0

        current.append(paragraph)
        current_tokens += paragraph_tokens

    flush()
    return chunks


def chunk_markdown(markdown_text: str) -> list[str]:
    """Trocea un documento markdown completo en chunks de ~300-500 tokens,
    respetando su estructura de secciones (``## ...``) y sin partir
    párrafos por la mitad.
    """
    chunks: list[str] = []
    for header, body in _split_into_sections(markdown_text):
        chunks.extend(_chunk_section(header, body))
    return chunks


def _embed_texts(openai_client: OpenAI, texts: list[str]) -> list[list[float]]:
    """Pide los embeddings de varios textos en una sola llamada a la API
    (acepta ``input`` como lista), preservando el orden de entrada."""
    response = openai_client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [item.embedding for item in response.data]


async def _get_active_policy_id(supabase_client: Any, category: str) -> Optional[str]:
    """Busca el id de la fila activa de ``return_policies`` para una
    categoría. Devuelve ``None`` si no existe (el caller decide si eso es
    motivo para saltarse el documento, no para fallar todo el script)."""
    resp = (
        await supabase_client.table("return_policies")
        .select("id")
        .eq("category", category)
        .eq("active", True)
        .execute()
    )
    if not resp.data:
        return None
    return resp.data[0]["id"]


async def _replace_embeddings(
    supabase_client: Any,
    policy_id: Optional[str],
    chunks: list[str],
    embeddings: list[list[float]],
    source_doc: str,
    category: Optional[str] = None,
) -> int:
    """Borra los chunks existentes de este ``policy_id`` (o los de
    ``policy_id IS NULL`` para el marco general) y los reemplaza por los
    nuevos, para que ejecutar el script más de una vez no acumule
    duplicados en ``policy_embeddings``.
    """
    delete_query = supabase_client.table("policy_embeddings").delete()
    delete_query = (
        delete_query.is_("policy_id", None)
        if policy_id is None
        else delete_query.eq("policy_id", policy_id)
    )
    await delete_query.execute()

    rows = [
        {
            "policy_id": policy_id,
            "chunk_text": chunk,
            "embedding": embedding,
            "metadata": {
                "source_doc": source_doc,
                "chunk_index": index,
                # Stored explicitly so match_policy_embeddings can filter by
                # category without a JOIN — keeps the RPC query self-contained.
                "category": category or "general",
                # Version tag: allows invalidating stale chunks if policies change.
                "policy_version": "2026-08",
            },
        }
        for index, (chunk, embedding) in enumerate(zip(chunks, embeddings))
    ]
    if rows:
        await supabase_client.table("policy_embeddings").insert(rows).execute()
    return len(rows)


async def ingest(*, only_category: Optional[str] = None, dry_run: bool = False) -> int:
    """Trocea y (salvo ``dry_run``) vectoriza + inserta en ``policy_embeddings``
    el marco general y cada política de categoría. Devuelve el nº total de
    chunks generados (o insertados, si no es ``dry_run``).
    """
    if only_category is not None and only_category not in CATEGORIES:
        raise ValueError(
            f"Categoría desconocida: '{only_category}'. Categorías válidas: "
            f"{', '.join(sorted(CATEGORIES))}."
        )

    openai_client: Optional[OpenAI] = None if dry_run else OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    supabase_client = None if dry_run else await get_supabase_client()

    # (nombre_de_fichero, categoría) — categoría=None para el marco general,
    # que no está atado a ninguna (ver GENERAL_POLICY_DOC arriba).
    targets: list[tuple[str, Optional[str]]] = [(GENERAL_POLICY_DOC, None)]
    for category, cfg in CATEGORIES.items():
        if only_category and category != only_category:
            continue
        targets.append((cfg["policy_doc"], category))

    total_chunks = 0
    for policy_doc, category in targets:
        markdown_text = (POLICIES_DIR / policy_doc).read_text(encoding="utf-8")
        chunks = chunk_markdown(markdown_text)
        logger.info("%s -> %d chunks", policy_doc, len(chunks))

        if dry_run:
            total_chunks += len(chunks)
            continue

        policy_id = None
        if category is not None:
            policy_id = await _get_active_policy_id(supabase_client, category)
            if policy_id is None:
                logger.warning(
                    "return_policies no tiene fila activa para la categoría '%s' "
                    "(¿falta cargar supabase/seed_synthetic.sql?) — se omite %s.",
                    category, policy_doc,
                )
                continue

        embeddings = _embed_texts(openai_client, chunks)
        inserted = await _replace_embeddings(
            supabase_client, policy_id, chunks, embeddings, policy_doc, category
        )
        total_chunks += inserted

    logger.info(
        "Total de chunks %s: %d",
        "a generar (dry-run)" if dry_run else "insertados", total_chunks,
    )
    return total_chunks


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Solo trocea y cuenta chunks/tokens; no llama a OpenAI ni a Supabase.",
    )
    parser.add_argument(
        "--category", default=None,
        help="Ingesta solo la política de esta categoría, además del marco general. Por defecto, las 16.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(ingest(only_category=args.category, dry_run=args.dry_run))
