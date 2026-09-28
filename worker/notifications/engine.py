"""The notification decision (sección 7.1). Pure: no database, no channels.

    decide(event, rules, sent_today=…) → zero or more Decisions (one per channel)

| Event                             | Condition                                         | kind          |
|-----------------------------------|---------------------------------------------------|---------------|
| new match (not backfill)          | level = high and high ≥ notify_min_level          | opportunity   |
| new match (not backfill)          | level ≥ notify_min_level                          | new_match     |
| new match                         | level < notify_min_level                          | — (web, digest)|
| new match with probable_repost_of | by level                                          | new_match, "re-publicado" |
| price_drop                        | saved, or a match of level ≥ match; drop ≥ min %  | price_drop    |
| listing_gone                      | saved or followed                                 | listing_gone (digest) |

Rules:
  * frequency: `immediate` → status 'queued' (sent right away); `daily` →
    'digest'. price_drop of a saved listing is always immediate.
  * daily cap (alerts_max_per_user_day) over immediate alerts: the ones past
    it become 'digest' with payload.degraded = 'daily_cap'. One alert on three
    channels counts once. A saved listing's price_drop is not capped (it is
    "always immediate") but it counts.
  * dedupe_key: match:<listing_id> for new_match and opportunity (a listing is
    announced once, whatever its level), price_drop:<listing_id>:<snapshot_id>,
    listing_gone:<listing_id>. The table enforces it per (user, channel).
  * a listing the user discarded is not notified again.
  * several profiles of a user, one listing: `decide_all` keeps one alert, the
    one with the highest level.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from intelligence.levels import at_least, rank


MATCH, PRICE_DROP, LISTING_GONE = "match", "price_drop", "listing_gone"
FOLLOWED_STATUSES = frozenset({"interested", "contacted", "visit_scheduled"})

QUEUED, DIGEST = "queued", "digest"
DEGRADED_CAP = "daily_cap"


@dataclass(frozen=True)
class Audience:
    """Who an event is for: the user, through the profile that carries it."""
    user_id: str
    channels: tuple[str, ...] = ("web",)      # deliverable ones (linked, configured)
    frequency: str = "immediate"              # search_profiles.notification_frequency
    min_level: str = "good"                   # search_profiles.notify_min_level
    profile_id: int | None = None


@dataclass(frozen=True)
class Event:
    kind: str                                 # match | price_drop | listing_gone
    listing_id: int
    audience: Audience
    level: str | None = None                  # the user's best match on the listing
    score: int | None = None
    match_id: int | None = None
    backfill: bool = False
    repost: bool = False
    saved: bool = False
    status: str | None = None                 # user_listing_interactions.status
    snapshot_id: int | None = None
    drop_pct: float | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)

    @property
    def followed(self) -> bool:
        return self.status in FOLLOWED_STATUSES


@dataclass(frozen=True)
class Rules:
    alerts_max_per_user_day: int = 10
    price_drop_min_pct: float = 3.0


@dataclass(frozen=True)
class Decision:
    user_id: str
    kind: str
    channel: str
    status: str
    dedupe_key: str
    listing_id: int
    match_id: int | None
    profile_id: int | None
    payload: dict[str, Any]

    @property
    def immediate(self) -> bool:
        return self.status == QUEUED


@dataclass(frozen=True)
class _Plan:
    kind: str
    dedupe_key: str
    status: str
    capped: bool          # subject to the daily cap


def classify(event: Event, rules: Rules) -> _Plan | None:
    """The decision table: which kind, key and delivery an event gets, if any."""
    a = event.audience
    if event.status == "discarded" and not event.saved:
        return None
    by_frequency = QUEUED if a.frequency == "immediate" else DIGEST

    if event.kind == MATCH:
        if event.backfill or event.level is None or not at_least(event.level, a.min_level):
            return None
        kind = "opportunity" if event.level == "high" and not event.repost else "new_match"
        return _Plan(kind, f"match:{event.listing_id}", by_frequency, True)

    if event.kind == PRICE_DROP:
        if event.drop_pct is None or event.drop_pct < rules.price_drop_min_pct:
            return None
        matched = event.level is not None and at_least(event.level, "match")
        if not (event.saved or matched):
            return None
        key = f"price_drop:{event.listing_id}:{event.snapshot_id or 0}"
        if event.saved:
            return _Plan("price_drop", key, QUEUED, False)
        return _Plan("price_drop", key, by_frequency, True)

    if event.kind == LISTING_GONE:
        if not (event.saved or event.followed):
            return None
        return _Plan("listing_gone", f"listing_gone:{event.listing_id}", DIGEST, False)

    return None


def decide(event: Event, rules: Rules, *, sent_today: int = 0) -> list[Decision]:
    """Notifications for one event, one per deliverable channel. `sent_today`
    is how many immediate alerts the user already got today (ART)."""
    plan = classify(event, rules)
    if plan is None or not event.audience.channels:
        return []
    payload = dict(event.payload)
    status = plan.status
    if status == QUEUED and plan.capped and sent_today >= rules.alerts_max_per_user_day:
        status = DIGEST
        payload["degraded"] = DEGRADED_CAP
    if event.kind == MATCH and event.repost:
        payload["repost"] = True
    a = event.audience
    return [Decision(a.user_id, plan.kind, ch, status, plan.dedupe_key, event.listing_id,
                     event.match_id, a.profile_id, payload)
            for ch in dict.fromkeys(a.channels)]


def _priority(event: Event) -> tuple:
    # Highest level first, then score: the first decision for a key wins.
    return (-rank(event.level) if event.level else 1, -(event.score or 0))


def decide_all(events: Iterable[Event], rules: Rules, *, sent_today: Mapping[str, int] | None = None,
               existing: set[tuple[str, str]] | None = None) -> list[Decision]:
    """Decide a batch. One alert per (user, dedupe_key), from the event with
    the highest level; keys in `existing` (user_id, dedupe_key) were already
    notified and are skipped without counting towards the cap."""
    counts = dict(sent_today or {})
    done = set(existing or ())
    out: list[Decision] = []
    for event in sorted(events, key=_priority):
        plan = classify(event, rules)
        if plan is None:
            continue
        key = (event.audience.user_id, plan.dedupe_key)
        if key in done:
            continue
        decisions = decide(event, rules, sent_today=counts.get(event.audience.user_id, 0))
        if not decisions:
            continue
        done.add(key)
        if decisions[0].immediate:
            counts[event.audience.user_id] = counts.get(event.audience.user_id, 0) + 1
        out += decisions
    return out
