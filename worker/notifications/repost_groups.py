"""One alert per car (docs/FB_DUPLICADOS_PLACEHOLDER_TERMINADOS.md). Pure: no I/O.

The same car shows up as several listings: a Facebook seller reposts it (another external id, another
locality), or a fingerprint twin appears on another source. `listings.fingerprint` cannot tie them when
the km is missing (77 % of Facebook's active listings, 24/11/2026), so the twin relation lives in SQL
(db/repos/notifications.repost_twins) and this module only uses its pairs:

  * a new match whose user was already alerted about a twin of it gets no alert («repost_alerted»):
    the rule engine.py calls «re-publicado» still alerts the first time the user hears of the car, when
    only the original was never sent to them (below their level, or from before the search);
  * of the twins in one batch, only the best one (highest level, then score) is alerted, the others
    stay as matches of the same group («repost_group»).

Applied only to MATCH events, only with app_config.listing_noise.repost_groups on.
"""
from __future__ import annotations

from typing import Iterable

from intelligence.levels import rank
from notifications.engine import MATCH, NONE, Event, Outcome

R_REPOST_ALERTED = "repost_alerted"       # the user was already alerted about a twin of this listing
R_REPOST_GROUP = "repost_group"           # a better twin of this batch takes the alert


def _priority(event: Event) -> tuple:
    return (-rank(event.level) if event.level else 1, -(event.score or 0), event.listing_id)


def groups(listing_ids: Iterable[int], twins: Iterable[tuple[int, int]]) -> dict[int, int]:
    """listing id → the group's smallest id, over the twin pairs (connected components)."""
    parent: dict[int, int] = {i: i for i in listing_ids}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in twins:
        if a in parent and b in parent:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)
    return {i: find(i) for i in parent}


def collapse(events: list[Event], twins: Iterable[tuple[int, int]],
             alerted: set[tuple[str, int]]) -> tuple[list[Event], dict[int, Outcome]]:
    """(the events that stay, Outcome by id(event) of the ones dropped). `twins`: pairs of listing ids
    that are the same car; `alerted`: (user, listing) whose twin the user already got an alert about."""
    group = groups({e.listing_id for e in events if e.kind == MATCH}, twins)
    best: dict[tuple[str, int], Event] = {}
    for e in events:
        if e.kind != MATCH or (e.audience.user_id, e.listing_id) in alerted:
            continue
        key = (e.audience.user_id, group[e.listing_id])
        if key not in best or _priority(e) < _priority(best[key]):
            best[key] = e
    kept: list[Event] = []
    dropped: dict[int, Outcome] = {}
    for e in events:
        if e.kind != MATCH:
            kept.append(e)
        elif (e.audience.user_id, e.listing_id) in alerted:
            dropped[id(e)] = Outcome(NONE, R_REPOST_ALERTED)
        elif best[(e.audience.user_id, group[e.listing_id])].listing_id != e.listing_id:
            dropped[id(e)] = Outcome(NONE, R_REPOST_GROUP)
        else:
            kept.append(e)
    return kept, dropped
