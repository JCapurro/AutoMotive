"use client";

import { MapPin } from "lucide-react";
import { useEffect, useState, useTransition } from "react";
import { toast } from "sonner";

import { type SaveResult, dismissZoneNotice, trackZoneNoticeShown, widenSearchZone, zoneNoticeFor } from "@/app/app/searches/actions";
import { Button } from "@/components/ui/button";
import {
  IP_ZONE_LINE,
  KEEP_FAILED,
  KEPT_TEXT,
  SEARCH_TITLE_ID,
  WIDEN_FAILED,
  type WidenTo,
  ZONE_NOTICE_POLL_MAX_MS,
  ZONE_NOTICE_POLL_MS,
  type ZoneNoticeAnswer,
  type ZoneNoticeData,
  type ZonePlacement,
  noticeHeadline,
  optionLabel,
  widenedText,
  zoneLine,
} from "@/lib/zone-notice";

/**
 * Aviso de zona (docs/AVISO_ZONA.md): «Ampliá tu rango» with the options the
 * server counted, and «Dejar así». On the results page a tap refreshes the
 * page; on the modo asistido's card, `onWidened` and `onKept` update the card
 * and the form below, `disabled` waits while that form has unsaved changes,
 * and `onPendingChange` tells it while a tap is being saved.
 */
export function ZoneNoticeOptions({
  notice,
  placement,
  disabled = false,
  onWidened,
  onKept,
  onPendingChange,
}: {
  notice: ZoneNoticeData;
  placement: ZonePlacement;
  disabled?: boolean;
  onWidened?: (to: WidenTo) => void;
  onKept?: () => void;
  onPendingChange?: (pending: boolean) => void;
}) {
  const [pending, start] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const zoneKey = notice.zone.join(",");

  useEffect(() => {
    void trackZoneNoticeShown(placement, notice);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per search and zone; the server skips repeats
  }, [notice.profileId, zoneKey, placement]);

  // A tap that went through takes the options away while still pending: false again then.
  useEffect(() => {
    onPendingChange?.(pending);
    return () => onPendingChange?.(false);
  }, [pending, onPendingChange]);

  // On the results page the panel goes with the refresh: a toast says what
  // changed, and focus waits on the page's title.
  function done(text: string) {
    if (placement !== "page") return;
    toast(text);
    document.getElementById(SEARCH_TITLE_ID)?.focus();
  }

  function widen(to: WidenTo) {
    setError(null);
    start(async () => {
      let result: SaveResult;
      try {
        result = await widenSearchZone(notice.profileId, to, placement, {
          zone: notice.zone, count: notice.count, options: notice.options.length,
        });
      } catch {
        setError(WIDEN_FAILED);
        return;
      }
      if (result.error) {
        setError(result.error);
        return;
      }
      done(widenedText(to, notice.place));
      onWidened?.(to);
    });
  }

  function keep() {
    setError(null);
    start(async () => {
      let result: SaveResult;
      try {
        result = await dismissZoneNotice(notice.profileId, placement, notice.zone);
      } catch {
        setError(KEEP_FAILED);
        return;
      }
      if (result.error) {
        setError(result.error);
        return;
      }
      done(KEPT_TEXT);
      onKept?.();
    });
  }

  return (
    <div className="space-y-2">
      {notice.kind === "ip" ? <p className="text-sm text-muted-foreground">{IP_ZONE_LINE}</p> : null}
      <p id={`zone-options-${notice.profileId}`} className="text-sm font-medium">Ampliá tu rango:</p>
      <div role="group" aria-labelledby={`zone-options-${notice.profileId}`} className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
        {notice.options.map((option, i) => (
          <Button
            key={option.to}
            type="button"
            variant={i === 0 ? "default" : "outline"}
            className="w-full sm:w-auto"
            disabled={pending || disabled}
            onClick={() => widen(option.to)}
          >
            {optionLabel(option)}
          </Button>
        ))}
        <Button type="button" variant="link" className="self-start px-0 sm:self-center" disabled={pending} onClick={keep}>
          Dejar así
        </Button>
      </div>
      {disabled ? <p className="text-xs text-muted-foreground">Tenés cambios sin guardar abajo: guardalos primero.</p> : null}
      {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
    </div>
  );
}

/** The results page's notice, where the bot's «¿Por qué hay pocos resultados?» card would be. */
export function ZoneNoticePanel({ notice }: { notice: ZoneNoticeData }) {
  return (
    <section data-testid="zone-notice" aria-labelledby="zone-notice-title" className="space-y-3 rounded-lg border bg-muted/50 p-4 text-sm">
      <div className="space-y-1">
        <h2 id="zone-notice-title" className="flex items-center gap-2 font-semibold">
          <MapPin aria-hidden className="size-4" /> {noticeHeadline(notice.count)}
        </h2>
        <p>{zoneLine(notice)}</p>
      </div>
      <ZoneNoticeOptions notice={notice} placement="page" />
    </section>
  );
}

/**
 * The card's notice for a search just saved (`profileId`): asked once now,
 * then every ZONE_NOTICE_POLL_MS while the search is being prepared and the
 * tab is visible, for at most ZONE_NOTICE_POLL_MAX_MS. Null until it shows,
 * or if it never does.
 */
export function useZoneNoticePoll(profileId: number | null): ZoneNoticeData | null {
  const [shown, setShown] = useState<{ id: number; notice: ZoneNoticeData } | null>(null);
  useEffect(() => {
    if (profileId == null) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const started = Date.now();
    const next = () => {
      if (Date.now() - started < ZONE_NOTICE_POLL_MAX_MS) timer = setTimeout(tick, ZONE_NOTICE_POLL_MS);
    };
    // A failed call is asked again, like a search still pending.
    const settle = (answer: ZoneNoticeAnswer | null) => {
      if (stopped) return;
      if (answer?.state === "show") setShown({ id: profileId, notice: answer.notice });
      else if (answer?.state !== "none") next();
    };
    const tick = () => {
      if (document.visibilityState !== "visible") {
        next();
        return;
      }
      zoneNoticeFor(profileId).then(settle, () => settle(null));
    };
    tick();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [profileId]);
  return shown?.id === profileId ? shown.notice : null;
}
