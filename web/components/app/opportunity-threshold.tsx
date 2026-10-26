"use client";

import { cn } from "@/lib/utils";

export const THRESHOLD_MIN = 5;
export const THRESHOLD_MAX = 50;
export const THRESHOLD_STEP = 5;
export const THRESHOLD_DEFAULT = "10";
const TICKS = [5, 15, 25, 35, 50];

/**
 * Pro's opportunity threshold (3.2) as a switch and a slider: «avisame al
 * instante cuando esté 15 % por debajo del mercado». `value` is the
 * percentage as text, "" = off (the same string the form keeps).
 */
export function OpportunityThreshold({
  id,
  value,
  onChange,
  error,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  error?: React.ReactNode;
}) {
  const on = value.trim() !== "";
  const pct = Number(value);
  const shown = Number.isFinite(pct) && pct > 0 ? pct : Number(THRESHOLD_DEFAULT);
  const slider = Math.min(Math.max(shown, THRESHOLD_MIN), THRESHOLD_MAX);
  const fill = ((slider - THRESHOLD_MIN) / (THRESHOLD_MAX - THRESHOLD_MIN)) * 100;

  return (
    <fieldset className="space-y-3 rounded-lg border p-4 sm:col-span-2">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <legend className="float-left w-full text-sm font-medium">Avisos al instante por buen precio</legend>
          <p id={`${id}-hint`} className="clear-both text-xs text-muted-foreground">
            {on
              ? `Te avisamos al instante cuando un auto está ${shown} % o más por debajo del precio de mercado. El resto va al resumen diario.`
              : "Apagado: te avisamos de todo lo que coincide, hasta el tope diario de tu plan."}
          </p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={on}
          aria-label="Avisos al instante por buen precio"
          aria-describedby={`${id}-hint`}
          onClick={() => onChange(on ? "" : THRESHOLD_DEFAULT)}
          className={cn(
            "relative mt-0.5 inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
            on ? "bg-primary" : "bg-muted-foreground/30",
          )}
        >
          <span className={cn("inline-block size-5 rounded-full bg-background shadow transition-transform", on ? "translate-x-5" : "translate-x-0.5")} />
        </button>
      </div>
      {on ? (
        <div className="space-y-2">
          <div className="flex items-baseline justify-between">
            <label htmlFor={id} className="text-sm text-muted-foreground">Descuento mínimo</label>
            <span className="rounded-full bg-primary/10 px-3 py-0.5 text-sm font-semibold tabular-nums text-primary">{shown} %</span>
          </div>
          <input
            id={id}
            type="range"
            min={THRESHOLD_MIN}
            max={THRESHOLD_MAX}
            step={THRESHOLD_STEP}
            value={slider}
            onChange={(e) => onChange(e.target.value)}
            aria-valuetext={`${shown} % o más por debajo del mercado`}
            aria-describedby={`${id}-hint`}
            style={{ background: `linear-gradient(to right, var(--primary) ${fill}%, var(--muted) ${fill}%)` }}
            className={cn(
              "h-2 w-full cursor-pointer appearance-none rounded-full accent-primary focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
              "[&::-webkit-slider-thumb]:size-5 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-background [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:shadow",
              "[&::-moz-range-thumb]:size-5 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-background [&::-moz-range-thumb]:bg-primary [&::-moz-range-thumb]:shadow",
            )}
          />
          <div className="flex justify-between text-[11px] text-muted-foreground" aria-hidden>
            {TICKS.map((t) => <span key={t}>{t} %</span>)}
          </div>
          <p className="text-xs text-muted-foreground">Lo que no tiene autos comparables para medir el precio va al resumen diario.</p>
        </div>
      ) : null}
      {error}
    </fieldset>
  );
}
