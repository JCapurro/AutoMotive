"""model_guides (PAR-04): the published guides' questions for the scorer, and
the guide job's reads and writes (pipeline/llm_jobs.py).

On a database without the PAR-04 migrations (to_regclass is null) the
scorer gets no guides and the worker behaves as before.
"""
from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from intelligence.guides import GuideIndex, build_index


async def table_exists(cx: AsyncConnection) -> bool:
    row = await (await cx.execute("SELECT to_regclass('public.model_guides') IS NOT NULL AS ok")).fetchone()
    return bool(row and row["ok"])


async def published_index(cx: AsyncConnection) -> GuideIndex:
    """{(make, model) lowercased: [GuideEntry]} of the published guides."""
    if not await table_exists(cx):
        return {}
    rows = await (await cx.execute(
        "SELECT id, make, model, generation_label, year_from, year_to, questions "
        "  FROM model_guides WHERE status = 'published' ORDER BY id")).fetchall()
    return build_index(rows)


async def get(cx: AsyncConnection, guide_id: int) -> dict[str, Any] | None:
    return await (await cx.execute(
        "SELECT id, make, model, generation_label, year_from, year_to, status, updated_at, generated_at "
        "  FROM model_guides WHERE id = %s", (guide_id,))).fetchone()


async def catalog_context(cx: AsyncConnection, make: str, model: str) -> dict[str, Any]:
    """The catalog's years and trims of the model: all the provider is told
    besides the names (never listings, prices, searches or timing_belt)."""
    rows = await (await cx.execute(
        "SELECT trim, year_from, year_to FROM vehicle_catalog "
        " WHERE lower(make) = lower(%s) AND lower(model) = lower(%s) "
        " ORDER BY trim NULLS FIRST, trim", (make, model))).fetchall()
    base = next((r for r in rows if r["trim"] is None), None)
    return {"years": (base["year_from"], base["year_to"]) if base else (None, None),
            "trims": [r["trim"] for r in rows if r["trim"]]}


async def cached_output(cx: AsyncConnection, key: str, *, exclude_job: int) -> dict[str, Any] | None:
    """The output of an earlier done guide job with this cache key, if any."""
    row = await (await cx.execute(
        "SELECT id, output FROM llm_jobs "
        " WHERE kind = 'model_guide' AND status = 'done' AND output ->> 'cache_key' = %s AND id <> %s "
        "   AND output ? 'guide' "
        " ORDER BY finished_at DESC NULLS LAST, id DESC LIMIT 1", (key, exclude_job))).fetchone()
    return {"job_id": row["id"], **row["output"]} if row else None


async def apply_draft(cx: AsyncConnection, guide_id: int, draft: dict[str, Any], *, job_id: int,
                      llm_version: str, requested_at: Any) -> bool:
    """Write the draft into the guide if it is still a draft and nobody edited
    its content after the job was requested (content_updated_at, moved by a
    trigger on content changes only: publishing and unpublishing are not
    edits; this write moves it to generated_at's now()). False: the guide was left as it was."""
    cur = await cx.execute(
        "UPDATE model_guides SET body = %s, questions = %s, sources = %s, origin = 'llm', "
        "       llm_job_id = %s, llm_version = %s, generated_at = now() "
        " WHERE id = %s AND status = 'draft' AND content_updated_at <= %s",
        (Jsonb(draft["body"]), Jsonb(draft["questions"]), Jsonb(draft["sources"]),
         job_id, llm_version, guide_id, requested_at))
    return cur.rowcount == 1
