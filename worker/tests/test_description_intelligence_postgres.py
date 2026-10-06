from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import db
from collectors.base import Listing, ListingDetail
from db.repos import listings as repo
from intelligence.config import IntelligenceConfig
from intelligence.red_flags import red_flags
from intelligence.seller_questions import seller_questions
from pgcase import PostgresTestCase, requires_db
from pipeline.enrich import DescriptionLLM, ingest_detail
from pipeline.ingest import ingest
from test_description_intelligence import answer

pytestmark = [pytest.mark.db, requires_db]


class DescriptionIntelligencePostgresTests(PostgresTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.item = Listing(source="v6", listing_id="desc-1", titulo="Ford Fiesta 2017",
                            url="https://example.test/v6/desc-1", precio=12_000, moneda="USD", anio=2017,
                            descripcion="Versión Titanium. Tiene granizo. Services al día.")
        result = await ingest([self.item], geocode=None)
        self.lid = result.ids[("v6", "desc-1")]

    async def row(self):
        async with db.connection() as cx:
            return await (await cx.execute("SELECT * FROM listings WHERE id = %s", (self.lid,))).fetchone()

    async def test_parallel_reservations_share_daily_cap(self):
        slots = await asyncio.gather(*(repo.reserve_description_run(self.lid, f"v2:input-{i}", 2) for i in range(6)))
        assert sum(s is not None for s in slots) == 2

    async def test_failures_and_deleted_listings_still_count(self):
        slot = await repo.reserve_description_run(self.lid, "v2:one", 1)
        await repo.finish_description_run(slot, error="LLMTimeout")
        assert await repo.reserve_description_run(self.lid, "v2:one", 2) is None
        assert await repo.reserve_description_run(self.lid, "v2:two", 1) is None
        async with db.connection() as cx:
            await cx.execute("DELETE FROM listings WHERE id = %s", (self.lid,))
            ledger = await (await cx.execute("SELECT listing_id, error FROM description_llm_runs")).fetchone()
        assert ledger["listing_id"] is None and ledger["error"] == "LLMTimeout"

    async def test_analysis_survives_ingest_and_drives_questions_and_events(self):
        provider = AsyncMock()
        provider.extract_listing_facts.return_value = answer(trim="Titanium", damage_mentioned=True,
            damage_details="Tiene granizo", service_history=True, evidence=[
                {"field": "trim", "quote": "Versión Titanium"},
                {"field": "damage_mentioned", "quote": "Tiene granizo"},
                {"field": "damage_details", "quote": "Tiene granizo"},
                {"field": "service_history", "quote": "Services al día"}])
        helper = DescriptionLLM(provider, daily_cap=2)
        with patch("normalization.geo.geocode_location", AsyncMock(return_value=None)):
            result = await ingest_detail(dict(await self.row()), ListingDetail(self.item.url, listing=self.item),
                                         stage="enrich", llm=helper)
        row = dict(await self.row())
        assert row["trim"] == "Titanium"
        assert row["description_facts"]["claims"]["damage_details"] == "Tiene granizo"
        assert any(e.kind == "listing_updated" and "description" in e.changes for e in result.events)
        now = datetime.now(timezone.utc)
        flags = red_flags(row, diff_pct=12, guard=None, timing_belt=True, cfg=IntelligenceConfig(), now=now)
        assert "damage_mentioned" in [f.id for f in flags]
        questions = seller_questions(row, flags, timing_belt=True, now=now)
        assert "daños que mencionás" in questions and "comprobantes" in questions
        await helper.refine(self.lid, self.item)
        provider.extract_listing_facts.assert_awaited_once()
        # A card without a description must retain the complete analyzed facts.
        await ingest([Listing(source="v6", listing_id="desc-1", titulo="Ford Fiesta 2017",
                              url=self.item.url, precio=12_000, moneda="USD", anio=2017)], geocode=None)
        assert (await self.row())["description_facts"]["claims"]["damage_mentioned"] is True

    async def test_ledger_is_not_accessible_to_users(self):
        async with db.connection() as cx:
            grants = await (await cx.execute(
                "SELECT has_table_privilege('authenticated', 'description_llm_runs', 'SELECT') AS user_read, "
                "has_table_privilege('anon', 'description_llm_runs', 'SELECT') AS anon_read, "
                "has_table_privilege('service_role', 'description_llm_runs', 'INSERT') AS worker_write")).fetchone()
        assert grants == {"user_read": False, "anon_read": False, "worker_write": True}
