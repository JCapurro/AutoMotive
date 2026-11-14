"use client";

import { MapPin } from "lucide-react";
import { useEffect, useId, useState } from "react";

import type { LandingHow } from "@/components/landing-events";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ASSISTED_MAX_CHARS } from "@/lib/assisted";
import {
  type Builder, blurred, builderPicking, builderText, EMPTY_BUILDER, HERE, HERO_BUDGETS, HERO_ZONES,
  modelLabel, pickBudget, pickModel, pickOther, pickZone, typed,
} from "@/lib/landing-hero";
import { clearHere, storeHere } from "@/lib/landing-here";
import { detectDeviceLocation } from "@/lib/search-location";

/** A row of the feed asks for «uno así»: the form takes that model (components/landing-feed.tsx). */
export const LANDING_PICK_EVENT = "landing-pick";

const CHIP =
  "inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-full bg-muted px-3.5 text-[15.5px] font-semibold whitespace-nowrap transition-colors outline-none select-none focus-visible:ring-3 focus-visible:ring-ring/50 active:bg-border disabled:text-muted-foreground aria-pressed:bg-(--mark) aria-pressed:text-[#14213d] aria-pressed:shadow-[inset_0_0_0_1.5px_#14213d]";
// A phone scrolls the row sideways, edge to edge; wider screens wrap it.
const ROW = "-mx-4 mt-2 flex gap-2 overflow-x-auto px-4 pb-0.5 [scrollbar-width:none] sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0 [&::-webkit-scrollbar]:hidden";
const usd = (n: number) => `USD ${new Intl.NumberFormat("es-AR").format(n)}`;

/**
 * The landing's search built by tapping (lib/landing-hero.ts): a model chip
 * (or «Otro» and typing it), then budget and zone, all of it written into the
 * same box the old hero had, which stays editable by hand.
 */
export function LandingBuilder({ state, onState, models, disabled = false, invalid = false, describedBy, onStarted }: {
  state: Builder;
  onState: (update: (current: Builder) => Builder) => void;
  models: string[];
  disabled?: boolean;
  invalid?: boolean;
  describedBy?: string;
  /** The first thing done to the search, once. */
  onStarted: (how: LandingHow) => void;
}) {
  const id = useId();
  const [locating, setLocating] = useState(false);
  const [geoError, setGeoError] = useState(false);
  const picking = builderPicking(state);

  // The coordinates wait for the search only while «Mi ubicación» is the zone.
  useEffect(() => {
    if (state.zone !== HERE) clearHere();
  }, [state.zone]);

  useEffect(() => {
    const onPick = (event: Event) => {
      const model = (event as CustomEvent<string>).detail;
      if (typeof model !== "string" || !model) return;
      onStarted("row");
      onState(() => pickModel(EMPTY_BUILDER, model));
      document.getElementById("crear-busqueda")?.scrollIntoView({ behavior: "smooth", block: "start" });
    };
    window.addEventListener(LANDING_PICK_EVENT, onPick);
    return () => window.removeEventListener(LANDING_PICK_EVENT, onPick);
  }, [onStarted, onState]);

  const here = async () => {
    if (locating) return;
    setGeoError(false);
    if (state.zone === HERE) {
      onState((s) => pickZone(s, HERE));
      return;
    }
    setLocating(true);
    const result = await detectDeviceLocation(true);
    setLocating(false);
    if (!result.location) {
      setGeoError(true);
      return;
    }
    storeHere(result.location);
    onState((s) => pickZone({ ...s, zone: "" }, HERE));
  };

  return (
    <div className="space-y-3.5">
      <div>
        <p className="text-[15px] font-bold">
          <Label htmlFor={id} className="inline text-[15px] font-bold">¿Qué auto buscás?</Label>{" "}
          <span id={`${id}-help`} className="text-[13.5px] font-medium text-muted-foreground">Tocá uno, o «Otro» y escribilo.</span>
        </p>
        <ul aria-label="Modelos más buscados" className={ROW}>
          {models.map((model) => (
            <li key={model} className="shrink-0">
              <button type="button" className={CHIP} aria-pressed={state.model === model} disabled={disabled}
                onClick={() => { onStarted("model"); onState((s) => pickModel(s, model)); }}>
                {modelLabel(model)}
              </button>
            </li>
          ))}
          {/* «Otro» stays in sight at the end of the row while the models scroll under it. */}
          <li className="sticky -right-4 -mr-4 shrink-0 bg-[linear-gradient(to_right,transparent,var(--background)_12px)] pr-4 pl-3.5 sm:static sm:m-0 sm:bg-none sm:p-0">
            <button type="button" className={CHIP} aria-pressed={state.other} disabled={disabled}
              onClick={() => {
                onStarted("other");
                onState(pickOther);
                if (!state.other) document.getElementById(id)?.focus();
              }}>
              Otro
            </button>
          </li>
        </ul>
      </div>

      {picking ? (
        <>
          <div>
            <p className="text-[15px] font-bold">¿Hasta cuánto? <span className="text-[13.5px] font-medium text-muted-foreground">Opcional.</span></p>
            <ul aria-label="Presupuesto" className={ROW}>
              {HERO_BUDGETS.map((budget) => (
                <li key={budget} className="shrink-0">
                  <button type="button" className={CHIP} aria-pressed={state.budget === budget} disabled={disabled} onClick={() => onState((s) => pickBudget(s, budget))}>
                    {usd(budget)}
                  </button>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="text-[15px] font-bold">¿Dónde? <span className="text-[13.5px] font-medium text-muted-foreground">Opcional.</span></p>
            <ul aria-label="Zona" className={ROW}>
              <li className="shrink-0">
                <button type="button" className={CHIP} aria-pressed={state.zone === HERE} disabled={disabled || locating} onClick={() => void here()}>
                  <MapPin aria-hidden className="size-[15px]" strokeWidth={2.4} />
                  {locating ? "Buscando…" : HERE}
                </button>
              </li>
              {HERO_ZONES.map((zone) => (
                <li key={zone} className="shrink-0">
                  <button type="button" className={CHIP} aria-pressed={state.zone === zone} disabled={disabled}
                    onClick={() => { setGeoError(false); onState((s) => pickZone(s, zone)); }}>
                    {zone}
                  </button>
                </li>
              ))}
            </ul>
            {geoError ? <p role="status" className="mt-2 text-sm text-destructive">No pudimos ver tu ubicación. Elegí una zona de la lista.</p> : null}
          </div>
        </>
      ) : null}

      <div>
        {/* Fixed size, like the old hero's: long text scrolls inside. */}
        <Textarea
          id={id}
          value={builderText(state)}
          onChange={(event) => { onStarted("typed"); const value = event.target.value; onState((s) => typed(s, value)); }}
          onBlur={() => onState(blurred)}
          placeholder={state.other ? "¿Cuál? Ej.: Peugeot 208 2019 en adelante" : "O escribilo: Fiesta Titanium 2016 a 2018 hasta USD 11.500"}
          maxLength={ASSISTED_MAX_CHARS}
          rows={2}
          disabled={disabled}
          aria-invalid={invalid || undefined}
          aria-describedby={[`${id}-help`, picking ? `${id}-more` : null, describedBy].filter(Boolean).join(" ")}
          className="h-[68px] resize-none bg-background text-base field-sizing-fixed"
        />
        {picking ? (
          <p id={`${id}-more`} className="mt-1.5 text-[13px] text-muted-foreground">
            Podés sumar años, kilómetros, versión, color, caja, combustible y si lo querés de particular o de agencia.
          </p>
        ) : null}
      </div>
    </div>
  );
}
