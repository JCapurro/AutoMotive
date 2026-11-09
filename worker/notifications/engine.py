"""The notification decision (sección 7.1). Pure: no database, no channels.

    decide(event, rules, sent_today=…, cap=…) → zero or more Decisions (one per channel)

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
  * daily cap over immediate alerts: the user's plan sets it
    (plan_limits.immediate_alerts_per_day, public.immediate_alert_cap), with
    alerts_max_per_user_day as the default. The ones past it become 'digest'
    with payload.degraded = 'daily_cap'. One alert on three channels counts
    once. A saved listing's price_drop is not capped (it is "always
    immediate") but it counts.
  * opportunity threshold (Pro, 3.2): a search with one alerts a new match,
    or a price drop of a match, that is at least that % below comparables
    at once, outside the daily cap and without counting towards it
    (payload.threshold_pct); whatever doesn't reach it, or has no
    comparables, goes to the digest. Reaching it alerts even below
    notify_min_level. A saved listing's price_drop stays always immediate.
  * threshold by margin (PRO-02, Pro): the same rule with
    opportunity_threshold_usd against the estimated margin's low end
    (payload.margin.usd_low, unrounded); with both thresholds set, reaching either one
    is enough (payload.threshold_usd and/or threshold_pct). Without a margin
    (not enough dealer comparables) it is not reached.
  * dedupe_key: match:<listing_id> for new_match and opportunity (a listing is
    announced once, whatever its level), price_drop:<listing_id>:<snapshot_id>,
    listing_gone:<listing_id>. The table enforces it per (user, channel).
  * a listing the user discarded is not notified again.
  * several profiles of a user, one listing: `decide_all` keeps one alert, the
    one with the highest level.

f3 shadow (docs/superpowers/specs/2026-11-08-recalibracion-score-design.md
§4.4): `decide_all(..., outcomes={})` also records, per event, which exit it
took (Outcome: queued / digest / none, and why). It is a side channel only:
the decisions are the same with or without it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from intelligence.levels import at_least, rank


MATCH, PRICE_DROP, LISTING_GONE = "match", "price_drop", "listing_gone"
FOLLOWED_STATUSES = frozenset({"interested", "contacted", "visit_scheduled"})

QUEUED, DIGEST = "queued", "digest"
DEGRADED_CAP = "daily_cap"
# Outcome.result of an event that got no notification.
NONE = "none"

# Outcome.reason: why an event got no notification, or went to the digest, or skipped the cap.
R_DISCARDED = "discarded"                 # the user discarded the listing
R_BACKFILL = "backfill"
R_NO_LEVEL = "no_level"
R_BELOW_MIN_LEVEL = "below_min_level"
R_DROP_BELOW_MIN = "drop_below_min"       # price_drop under rules.price_drop_min_pct
R_NOT_MATCHED = "not_matched"             # price_drop of a listing neither saved nor matched at «match» or more
R_NOT_FOLLOWED = "not_followed"           # listing_gone of a listing neither saved nor followed
R_UNKNOWN_KIND = "unknown_kind"
R_DEDUPE_EXISTING = "dedupe_existing"     # the key was notified before this batch
R_DEDUPE_BATCH = "dedupe_batch"           # another event of this batch (another profile) took the key
R_NO_CHANNELS = "no_channels"
R_THRESHOLD = "threshold"                 # reached the Pro threshold: outside the cap
R_THRESHOLD_NOT_REACHED = "threshold_not_reached"   # a search with a Pro threshold sends the rest to the digest
R_DAILY_CAP = DEGRADED_CAP
R_FREQUENCY = "frequency"                 # notification_frequency daily
R_HIDDEN_TRIAL = "hidden_trial"           # set by notifications.service (the trial hides it)
R_NO_AUDIENCE = "no_audience"             # set by notifications.service (no access or no profile)


@dataclass(frozen=True)
class Audience:
    """Who an event is for: the user, through the profile that carries it."""
    user_id: str
    channels: tuple[str, ...] = ("web",)      # deliverable ones (linked, configured)
    frequency: str = "immediate"              # search_profiles.notification_frequency
    min_level: str = "good"                   # search_profiles.notify_min_level
    profile_id: int | None = None
    threshold_pct: int | None = None          # search_profiles.opportunity_threshold_pct, if the plan has it
    threshold_usd: int | None = None          # PRO-02: opportunity_threshold_usd, if the plan has dealer_margin


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
class Outcome:
    """What decide_all did with one event (the f3 shadow's decision log)."""
    result: str                    # QUEUED | DIGEST | NONE
    reason: str | None = None      # R_* above; None for a plain immediate alert
    kind: str | None = None        # opportunity | new_match | price_drop | listing_gone, when a plan existed
    threshold: bool = False        # reached the search's Pro threshold


@dataclass(frozen=True)
class _Plan:
    kind: str
    dedupe_key: str
    status: str
    capped: bool              # subject to the daily cap
    threshold: bool = False   # reached the search's threshold: outside the cap


def below_comparables(event: Event) -> float | None:
    """How far below comparables the listing is, in % (None without enough of them)."""
    diff = (event.payload.get("match") or {}).get("diff_pct")
    return float(diff) if isinstance(diff, (int, float)) and not isinstance(diff, bool) else None


def margin_low(event: Event) -> float | None:
    """PRO-02: the estimated margin's low end in USD, unrounded
    (payload.margin.usd_low, margin.threshold_low), or None. Never usd_min:
    that one is rounded for the copy (a single value to the nearest 10)."""
    low = (event.payload.get("margin") or {}).get("usd_low")
    return float(low) if isinstance(low, (int, float)) and not isinstance(low, bool) else None


def _has_threshold(a: Audience) -> bool:
    return a.threshold_pct is not None or a.threshold_usd is not None


def _reached(event: Event) -> tuple[bool, bool]:
    """Whether the event reaches the search's threshold in %, and in USD."""
    a = event.audience
    diff, low = below_comparables(event), margin_low(event)
    return (a.threshold_pct is not None and diff is not None and diff >= a.threshold_pct,
            a.threshold_usd is not None and low is not None and low >= a.threshold_usd)


def _reaches(event: Event) -> bool:
    return any(_reached(event))


def classify(event: Event, rules: Rules) -> _Plan | None:
    """The decision table: which kind, key and delivery an event gets, if any."""
    a = event.audience
    if event.status == "discarded" and not event.saved:
        return None
    by_frequency = QUEUED if a.frequency == "immediate" else DIGEST

    if event.kind == MATCH:
        if event.backfill or event.level is None:
            return None
        kind = "opportunity" if event.level == "high" and not event.repost else "new_match"
        key = f"match:{event.listing_id}"
        if _has_threshold(a) and _reaches(event):
            return _Plan(kind, key, by_frequency, False, threshold=True)
        if not at_least(event.level, a.min_level):
            return None
        return _Plan(kind, key, DIGEST if _has_threshold(a) else by_frequency, True)

    if event.kind == PRICE_DROP:
        if event.drop_pct is None or event.drop_pct < rules.price_drop_min_pct:
            return None
        matched = event.level is not None and at_least(event.level, "match")
        if not (event.saved or matched):
            return None
        key = f"price_drop:{event.listing_id}:{event.snapshot_id or 0}"
        if event.saved:
            return _Plan("price_drop", key, QUEUED, False)
        if _has_threshold(a):
            if _reaches(event):
                return _Plan("price_drop", key, by_frequency, False, threshold=True)
            return _Plan("price_drop", key, DIGEST, True)
        return _Plan("price_drop", key, by_frequency, True)

    if event.kind == LISTING_GONE:
        if not (event.saved or event.followed):
            return None
        return _Plan("listing_gone", f"listing_gone:{event.listing_id}", DIGEST, False)

    return None


def why_not(event: Event, rules: Rules | None = None) -> str | None:
    """Why classify() gives no plan for this event (R_*), or None when it gives one. Mirrors classify's
    branches for the decision log; MATCH reads no rule."""
    rules = rules or Rules()
    if classify(event, rules) is not None:
        return None
    a = event.audience
    if event.status == "discarded" and not event.saved:
        return R_DISCARDED
    if event.kind == MATCH:
        if event.backfill:
            return R_BACKFILL
        if event.level is None:
            return R_NO_LEVEL
        return R_BELOW_MIN_LEVEL if not at_least(event.level, a.min_level) else R_UNKNOWN_KIND
    if event.kind == PRICE_DROP:
        if event.drop_pct is None or event.drop_pct < rules.price_drop_min_pct:
            return R_DROP_BELOW_MIN
        return R_NOT_MATCHED
    if event.kind == LISTING_GONE:
        return R_NOT_FOLLOWED
    return R_UNKNOWN_KIND


def _decided(event: Event, plan: _Plan, decision: Decision) -> Outcome:
    """The Outcome of an event that got notifications (its first decision speaks for all channels)."""
    if plan.threshold:
        reason = R_THRESHOLD
    elif decision.status == DIGEST and decision.payload.get("degraded") == DEGRADED_CAP:
        reason = R_DAILY_CAP
    elif decision.status == DIGEST and _has_threshold(event.audience) and event.kind in (MATCH, PRICE_DROP):
        reason = R_THRESHOLD_NOT_REACHED
    elif decision.status == DIGEST and event.audience.frequency != "immediate":
        reason = R_FREQUENCY
    else:
        reason = None
    return Outcome(decision.status, reason, plan.kind, plan.threshold)


def decide(event: Event, rules: Rules, *, sent_today: int = 0, cap: int | None = None) -> list[Decision]:
    """Notifications for one event, one per deliverable channel. `sent_today`
    is how many immediate alerts the user already got today (ART); `cap` is
    the user's daily limit (default: rules.alerts_max_per_user_day)."""
    plan = classify(event, rules)
    if plan is None or not event.audience.channels:
        return []
    payload = dict(event.payload)
    status = plan.status
    cap = rules.alerts_max_per_user_day if cap is None else cap
    if status == QUEUED and plan.capped and sent_today >= cap:
        status = DIGEST
        payload["degraded"] = DEGRADED_CAP
    if event.kind == MATCH and event.repost:
        payload["repost"] = True
    if plan.threshold:
        by_pct, by_usd = _reached(event)
        if by_pct:
            payload["threshold_pct"] = event.audience.threshold_pct
        if by_usd:
            payload["threshold_usd"] = event.audience.threshold_usd
    a = event.audience
    return [Decision(a.user_id, plan.kind, ch, status, plan.dedupe_key, event.listing_id,
                     event.match_id, a.profile_id, payload)
            for ch in dict.fromkeys(a.channels)]


def _priority(event: Event) -> tuple:
    # Highest level first, then score: the first decision for a key wins.
    return (-rank(event.level) if event.level else 1, -(event.score or 0))


def decide_all(events: Iterable[Event], rules: Rules, *, sent_today: Mapping[str, int] | None = None,
               existing: set[tuple[str, str]] | None = None,
               caps: Mapping[str, int] | None = None,
               outcomes: dict[int, Outcome] | None = None) -> list[Decision]:
    """Decide a batch. One alert per (user, dedupe_key), from the event with
    the highest level; keys in `existing` (user_id, dedupe_key) were already
    notified and are skipped without counting towards the cap. `caps` is each
    user's daily limit; a user without one gets rules.alerts_max_per_user_day.
    `outcomes`, when given, gets outcomes[id(event)] = Outcome(...) for every
    event (the f3 shadow's log); it changes nothing of the decisions."""
    counts = dict(sent_today or {})
    caps = caps or {}
    before = set(existing or ())
    done = set(before)
    out: list[Decision] = []
    for event in sorted(events, key=_priority):
        plan = classify(event, rules)
        if plan is None:
            if outcomes is not None:
                outcomes[id(event)] = Outcome(NONE, why_not(event, rules))
            continue
        key = (event.audience.user_id, plan.dedupe_key)
        if key in done:
            if outcomes is not None:
                reason = R_DEDUPE_EXISTING if key in before else R_DEDUPE_BATCH
                outcomes[id(event)] = Outcome(NONE, reason, plan.kind, plan.threshold)
            continue
        decisions = decide(event, rules, sent_today=counts.get(event.audience.user_id, 0),
                           cap=caps.get(event.audience.user_id))
        if not decisions:
            if outcomes is not None:
                outcomes[id(event)] = Outcome(NONE, R_NO_CHANNELS, plan.kind, plan.threshold)
            continue
        if outcomes is not None:
            outcomes[id(event)] = _decided(event, plan, decisions[0])
        done.add(key)
        if decisions[0].immediate and not plan.threshold:
            counts[event.audience.user_id] = counts.get(event.audience.user_id, 0) + 1
        out += decisions
    return out
