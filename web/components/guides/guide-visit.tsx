"use client";

import { Check } from "lucide-react";
import { useEffect, useId, useState } from "react";

import { GUIDE_COPY } from "@/lib/guides";

export type VisitGroup = {
  key: string;
  /** The generation («E170 · 2014 a 2019») when the page has several; null otherwise. */
  label: string | null;
  anchor?: string;
  items: { text: string; applies: string | null }[];
};

/** What this browser ticked, per page. Without storage the ticks just don't survive a reload. */
function load(key: string | null): string[] {
  if (!key) return [];
  try {
    const value: unknown = JSON.parse(localStorage.getItem(key) ?? "[]");
    return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
  } catch {
    return [];
  }
}

/**
 * «Qué revisar en la visita» as something to use standing next to the car: one
 * card per step, a 56 px circle to tick it, a counter and a bar of dots. The
 * text is server-rendered like the rest of the page; only the ticks are the
 * browser's (localStorage, per model).
 */
export function GuideVisit({ groups, storageKey }: { groups: VisitGroup[]; storageKey: string | null }) {
  const [done, setDone] = useState<Set<string>>(() => new Set());
  const id = useId();
  useEffect(() => {
    const saved = load(storageKey);
    // eslint-disable-next-line react-hooks/set-state-in-effect -- read once after hydration: storage is the browser's
    if (saved.length) setDone(new Set(saved));
  }, [storageKey]);

  function toggle(key: string) {
    setDone((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      if (storageKey) {
        try {
          localStorage.setItem(storageKey, JSON.stringify([...next]));
        } catch {}
      }
      return next;
    });
  }

  return (
    <div className="space-y-8">
      {groups.map((group) => {
        const keys = group.items.map((_, n) => `${group.key}:${n}`);
        const count = keys.filter((k) => done.has(k)).length;
        return (
          <div key={group.key} className="space-y-3">
            {group.label ? <h3 id={group.anchor} className="type-heading scroll-mt-6 text-lg">{group.label}</h3> : null}
            <div className="flex items-baseline justify-between gap-3">
              <span className="type-figure text-[34px] leading-none" aria-live="polite">
                {count}/{keys.length}
              </span>
              <span className="text-right text-sm text-muted-foreground">{GUIDE_COPY.visitHint}</span>
            </div>
            <div aria-hidden="true" className="flex gap-1">
              {keys.map((k) => <i key={k} className={`h-1.5 flex-1 rounded-full ${done.has(k) ? "bg-foreground" : "bg-muted"}`} />)}
            </div>
            <ol className="space-y-2.5">
              {group.items.map((item, n) => {
                const key = keys[n];
                const on = done.has(key);
                return (
                  <li
                    key={key}
                    className={`grid grid-cols-[minmax(0,1fr)_56px] items-center gap-3 rounded-md border p-3.5 text-[16px] leading-snug transition-colors ${on ? "border-muted bg-muted text-muted-foreground" : ""}`}
                  >
                    <span id={`${id}-${key}`}>
                      {item.text}
                      {item.applies ? <span className="mt-1 block text-sm text-muted-foreground">{GUIDE_COPY.appliesTo.replace("{text}", item.applies)}</span> : null}
                    </span>
                    <button
                      type="button"
                      aria-pressed={on}
                      aria-label={GUIDE_COPY.visitTick}
                      aria-describedby={`${id}-${key}`}
                      onClick={() => toggle(key)}
                      className={`grid size-14 place-items-center rounded-full border-2 border-foreground transition-colors ${on ? "bg-foreground text-background" : "bg-background text-foreground"}`}
                    >
                      <Check aria-hidden="true" className={`size-6 ${on ? "" : "opacity-20"}`} />
                    </button>
                  </li>
                );
              })}
            </ol>
          </div>
        );
      })}
    </div>
  );
}
