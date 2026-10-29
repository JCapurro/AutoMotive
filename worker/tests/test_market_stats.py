"""F-03 fase 0: the weekly market aggregation (pipeline/market_stats.py), on
flat rows made up by hand. No database."""
from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone

from normalization.zone import DEFAULT_ZONE_MAP
from pipeline.market_stats import (aggregate, last_closed_week, percentile, report, week_bounds)

_AR = timezone(timedelta(hours=-3))
WEEK = "2026-W44"                                   # Monday 26/10 to Sunday 1/11/2026
START = datetime(2026, 10, 26, tzinfo=_AR)
END = datetime(2026, 11, 2, tzinfo=_AR)
CFG = {"min_n": {"price": 8, "days": 5}, "year_band": 2, "max_age_days": 30,
       "confirm_since": {"mercadolibre": "2026-10-24"}}


def at(days: float) -> datetime:
    """`days` after the week starts (negative: before)."""
    return START + timedelta(days=days)


def row(**kw) -> dict:
    """An active Ford Fiesta 2018 of San Isidro, seen at the end of the week,
    first seen well before it, from a source that is not in confirm_sources."""
    r = dict(id=kw.pop("id", 1), source="facebook", make="Ford", model="Fiesta", body_type="hatchback",
             year=2018, status="active", price_usd=10_000.0, price_partial=False, probable_repost_of=None,
             first_seen_at=at(-20), seen_at=at(6.5), published_at=None, not_news=False,
             province_id="06", department="San Isidro", precision="locality",
             confirm_source=False, unconfirmed=False)
    r.update(kw)
    return r


def stats(rows, **cfg):
    return aggregate(rows, week=WEEK, zone_map=DEFAULT_ZONE_MAP, cfg={**CFG, **cfg})


def find(out, *, kind="model", zone="todas", year_from=2018, **key):
    hits = [s for s in out if s.group_kind == kind and s.zone == zone and s.year_from == year_from
            and all(getattr(s, k) == v for k, v in key.items())]
    assert len(hits) <= 1, hits
    return hits[0] if hits else None


class WeekTests(unittest.TestCase):
    def test_week_bounds_are_monday_to_monday_in_argentina(self):
        self.assertEqual(week_bounds(WEEK), (START, END))
        self.assertEqual(week_bounds(date(2026, 10, 28)), (START, END))     # any day of it

    def test_last_closed_week(self):
        self.assertEqual(last_closed_week(datetime(2026, 11, 2, 6, 0, tzinfo=_AR)), "2026-W44")
        # Monday 01:00 UTC is still Sunday in Argentina.
        self.assertEqual(last_closed_week(datetime(2026, 11, 2, 1, 0, tzinfo=timezone.utc)), "2026-W43")
        self.assertEqual(last_closed_week(datetime(2026, 10, 29, 12, 0, tzinfo=_AR)), "2026-W43")


class PercentileTests(unittest.TestCase):
    def test_linear_interpolation_like_percentile_cont(self):
        values = [10, 20, 30, 40]
        self.assertEqual(percentile(values, 0.5), 25.0)
        self.assertEqual(percentile(values, 0.25), 17.5)
        self.assertEqual(percentile(values, 0.75), 32.5)
        self.assertEqual(percentile([7], 0.5), 7.0)
        self.assertIsNone(percentile([], 0.5))
        self.assertEqual(percentile([40, 10, 30, 20], 0.5), 25.0)           # unsorted input


class AggregateTests(unittest.TestCase):
    def test_price_percentiles_need_min_n(self):
        rows = [row(id=i, price_usd=10_000.0 + 1_000 * i) for i in range(7)]
        s = find(stats(rows), make="ford", model="fiesta")
        self.assertEqual((s.active_count, s.price_n), (7, 7))
        self.assertIsNone(s.median_price_usd)
        rows.append(row(id=7, price_usd=17_000.0))
        s = find(stats(rows), make="ford", model="fiesta")
        self.assertEqual(s.price_n, 8)
        self.assertEqual((s.p25_price_usd, s.median_price_usd, s.p75_price_usd), (11_750.0, 13_500.0, 15_250.0))

    def test_prices_skip_partial_and_unknown(self):
        rows = [row(id=1), row(id=2, price_partial=True), row(id=3, price_usd=None), row(id=4, price_usd=0)]
        s = find(stats(rows), make="ford", model="fiesta")
        self.assertEqual((s.active_count, s.price_n), (4, 1))

    def test_days_need_min_n(self):
        gone = [row(id=i, source="autocity", confirm_source=True, unconfirmed=True, status="active",
                    first_seen_at=at(-10 - i), seen_at=at(2)) for i in range(4)]
        s = find(stats(gone), make="ford", model="fiesta")
        self.assertEqual((s.gone_count, s.days_n), (4, 4))
        self.assertIsNone(s.median_days_to_gone)
        gone.append(row(id=4, source="autocity", confirm_source=True, unconfirmed=True,
                        first_seen_at=at(-14), seen_at=at(2)))
        s = find(stats(gone), make="ford", model="fiesta")
        self.assertEqual(s.days_n, 5)
        self.assertEqual((s.p25_days_to_gone, s.median_days_to_gone, s.p75_days_to_gone), (13.0, 14.0, 15.0))
        self.assertEqual(s.days_source, "confirm_sources")

    def test_year_bands(self):
        out = stats([row(id=1, year=2018), row(id=2, year=2019), row(id=3, year=2020), row(id=4, year=None)])
        self.assertEqual(find(out, make="ford", model="fiesta").active_count, 2)
        self.assertEqual(find(out, make="ford", model="fiesta", year_from=2020).active_count, 1)
        self.assertEqual(sum(s.active_count for s in out if s.group_kind == "model" and s.zone == "todas"), 3)

    def test_reposts_and_unknown_body_types_are_left_out(self):
        out = stats([row(id=1), row(id=2, probable_repost_of=1), row(id=3, body_type=None)])
        self.assertEqual(find(out, make="ford", model="fiesta").active_count, 2)
        self.assertEqual(find(out, kind="body_type", body_type="hatchback").active_count, 1)
        self.assertEqual({s.body_type for s in out if s.group_kind == "body_type"}, {"hatchback"})

    def test_todas_counts_the_listings_without_a_region(self):
        out = stats([row(id=1), row(id=2, province_id="82", department="Rosario"),
                     row(id=3, province_id="06", department=None, precision="province"),
                     row(id=4, province_id=None, department=None, precision=None)])
        regions = [s for s in out if s.group_kind == "model" and s.zone != "todas"]
        self.assertEqual({s.zone: s.active_count for s in regions}, {"amba": 1, "litoral": 1})
        self.assertEqual(find(out, make="ford", model="fiesta").active_count, 4)
        self.assertGreaterEqual(4, sum(s.active_count for s in regions))

    def test_new_count_ignores_not_news(self):
        out = stats([row(id=1, first_seen_at=at(1)), row(id=2, first_seen_at=at(2), not_news=True),
                     row(id=3, first_seen_at=at(-1)), row(id=4, first_seen_at=at(7.5))])
        s = find(out, make="ford", model="fiesta")
        self.assertEqual(s.new_count, 1)
        self.assertEqual(s.active_count, 3)                                  # first seen after the week: not yet

    def test_gone_only_from_confirm_sources_with_evidence(self):
        out = stats([
            row(id=1, source="autocity", confirm_source=True, unconfirmed=True, seen_at=at(3)),
            row(id=2, source="autocity", confirm_source=True, unconfirmed=False, seen_at=at(3)),
            row(id=3, source="facebook", status="gone", seen_at=at(3)),       # mark_gone, not a full read
            row(id=4, source="autocity", confirm_source=True, unconfirmed=True, seen_at=at(-2)),  # last week
        ])
        s = find(out, make="ford", model="fiesta")
        self.assertEqual((s.gone_count, s.days_n), (1, 1))
        self.assertEqual((s.active_count, s.active_confirmed_count), (1, 1))  # 2 still counts; 1, 3, 4 do not

    def test_mercadolibre_before_confirm_since_is_left_out(self):
        early = datetime(2026, 10, 23, 12, tzinfo=_AR)
        out = aggregate([
            row(id=1, source="mercadolibre", confirm_source=True, unconfirmed=True, seen_at=early),
            row(id=2, source="mercadolibre", confirm_source=True, unconfirmed=True,
                seen_at=datetime(2026, 10, 24, 12, tzinfo=_AR)),
        ], week="2026-W43", zone_map=DEFAULT_ZONE_MAP, cfg=CFG)
        s = find(out, make="ford", model="fiesta")
        self.assertEqual((s.gone_count, s.days_n), (1, 1))

    def test_days_skip_unknown_publication_of_old_stock_and_negatives(self):
        gone = dict(source="autocity", confirm_source=True, unconfirmed=True, seen_at=at(3))
        out = stats([
            row(id=1, **gone, first_seen_at=at(-7)),                               # 10 days
            row(id=2, **gone, first_seen_at=at(-7), not_news=True),                # first crawl, not a publication
            row(id=3, **gone, first_seen_at=at(-7), not_news=True, published_at=at(-27)),  # 30 days
            row(id=4, **gone, first_seen_at=at(-7), published_at=at(5)),           # negative
        ])
        s = find(out, make="ford", model="fiesta")
        self.assertEqual((s.gone_count, s.days_n), (4, 2))
        self.assertEqual(percentile([10.0, 30.0], 0.5), 20.0)

    def test_active_confirmed_never_exceeds_active(self):
        out = stats([row(id=1), row(id=2, source="autocity", confirm_source=True),
                     row(id=3, source="autocity", confirm_source=True, unconfirmed=True, seen_at=at(1))])
        for s in out:
            self.assertLessEqual(s.active_confirmed_count, s.active_count)
        self.assertEqual(find(out, make="ford", model="fiesta").active_confirmed_count, 1)

    def test_seen_too_long_ago_is_not_active(self):
        out = stats([row(id=1), row(id=2, seen_at=at(-25))])                    # 32 days before the end
        self.assertEqual(find(out, make="ford", model="fiesta").active_count, 1)

    def test_make_and_model_group_case_insensitively(self):
        out = stats([row(id=1), row(id=2, make="FORD", model="fiesta "), row(id=3, make=None)])
        self.assertEqual(find(out, make="ford", model="fiesta").active_count, 2)

    def test_same_input_same_rows(self):
        rows = [row(id=i, year=2016 + i % 4, province_id=("06", "82", "14")[i % 3],
                    department=("San Isidro", "Rosario", "Capital")[i % 3]) for i in range(30)]
        self.assertEqual(stats(rows), stats(list(reversed(rows))))

    def test_every_row_carries_the_week_and_the_map_version(self):
        for s in stats([row()]):
            self.assertEqual((s.week_start, s.zone_map_version), (date(2026, 10, 26), 1))


class ReportTests(unittest.TestCase):
    def test_report(self):
        rows = [row(id=i) for i in range(8)] + [row(id=8, source="gruporandazzo", province_id=None,
                                                    department=None, precision=None)]
        out = stats(rows)
        rep = report(out, rows, week=WEEK, cfg=CFG)
        self.assertEqual(rep["rows"], len(out))
        self.assertEqual(rep["no_zone_by_source"]["gruporandazzo"], {"total": 1, "no_zone": 1})
        self.assertEqual(rep["no_zone_by_source"]["facebook"], {"total": 8, "no_zone": 0})
        self.assertEqual(rep["rows_with_price_sample"], 4)                    # model and body type, amba and todas
        self.assertEqual(sum(rep["price_n"].values()), len(out))
        self.assertGreater(rep["projected_mb_26_weeks"], 0)


if __name__ == "__main__":
    unittest.main()
