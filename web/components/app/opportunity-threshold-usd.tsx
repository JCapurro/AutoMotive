"use client";

import { Input } from "@/components/ui/input";
import { MARGIN } from "@/lib/copy";
import { number } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * PRO-02: Pro's threshold by estimated margin, as a switch and an amount in
 * USD: «avisame al instante cuando el margen estimado sea de USD 800 o más».
 * `value` is the amount as text, "" = off; turning it on starts at the
 * plan's minimum (`min`, plan_limits.pro.min_threshold_usd).
 */
export function OpportunityThresholdUsd({
  id,
  value,
  min,
  onChange,
  error,
}: {
  id: string;
  value: string;
  min: number;
  onChange: (value: string) => void;
  error?: React.ReactNode;
}) {
  const on = value.trim() !== "";
  const usd = `USD ${value.trim() || number(min)}`;
  return (
    <fieldset className="space-y-3 rounded-lg border p-4 sm:col-span-2">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <legend className="float-left w-full text-sm font-medium">{MARGIN.thresholdTitle}</legend>
          <p id={`${id}-hint`} className="clear-both text-xs text-muted-foreground">
            {on ? MARGIN.thresholdOn.replace("{usd}", usd) : MARGIN.thresholdOff}
          </p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={on}
          aria-label={MARGIN.thresholdTitle}
          aria-describedby={`${id}-hint`}
          onClick={() => onChange(on ? "" : number(min))}
          className={cn(
            "relative mt-0.5 inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
            on ? "bg-primary" : "bg-muted-foreground/30",
          )}
        >
          <span className={cn("inline-block size-5 rounded-full bg-background shadow transition-transform", on ? "translate-x-5" : "translate-x-0.5")} />
        </button>
      </div>
      {on ? (
        <div className="space-y-1.5">
          <label htmlFor={id} className="text-sm text-muted-foreground">{MARGIN.thresholdLabel}</label>
          <Input
            id={id}
            inputMode="numeric"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            aria-describedby={`${id}-hint ${id}-min`}
            className="max-w-40 tabular-nums"
          />
          <p id={`${id}-min`} className="text-xs text-muted-foreground">
            {MARGIN.thresholdMin.replace("{min}", number(min))} {MARGIN.thresholdNoMargin}
          </p>
        </div>
      ) : null}
      {error}
    </fieldset>
  );
}
