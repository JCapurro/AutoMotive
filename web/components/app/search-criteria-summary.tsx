import { Banknote, CalendarDays, CarFront, Check, ChevronDown, CircleHelp, Gauge, Loader2, MapPin, Pause, Settings2, TriangleAlert, type LucideIcon } from "lucide-react";

import { FUEL, SELLER, TRANSMISSION } from "@/lib/copy";
import { number } from "@/lib/format";
import type { CollectionState, SearchSource } from "@/lib/search-collection";
import type { Filters, Preferences } from "@/lib/types";
import { cn } from "@/lib/utils";

type Fact = { label: string; value: string; icon?: LucideIcon };
type Props = {
  name: string;
  filters: Filters;
  preferences: Preferences;
  radiusKm: number | null;
  hasLocation: boolean;
  sources: SearchSource[] | null;
};

const STATUS: Record<CollectionState, { label: string; icon: LucideIcon }> = {
  waiting: { label: "Recolección pendiente", icon: Loader2 },
  loading: { label: "Recolectando datos", icon: Loader2 },
  done: { label: "Recolección completada", icon: Check },
  failed: { label: "No se pudo completar la recolección", icon: TriangleAlert },
  paused: { label: "Recolección pausada", icon: Pause },
  unknown: { label: "Estado de recolección sin confirmar", icon: CircleHelp },
};

function range(min: number | undefined, max: number | undefined, format: (value: number) => string) {
  if (min != null && max != null) return min === max ? format(min) : `${format(min)}–${format(max)}`;
  if (min != null) return `Desde ${format(min)}`;
  if (max != null) return `Hasta ${format(max)}`;
  return null;
}

// Legacy profiles without a currency use the same threshold as the matcher.
function currency(amount: number, explicit?: string) {
  return explicit || (amount >= 1_000_000 ? "ARS" : "USD");
}

export function SearchCriteriaSummary({ name, filters: f, preferences: p, radiusKm, hasLocation, sources }: Props) {
  const main: Fact[] = [];
  const extra: Fact[] = [];
  const vehicle = [f.make, f.model].filter(Boolean).join(" ");
  if (vehicle && !name.toLocaleLowerCase().includes(vehicle.toLocaleLowerCase())) {
    main.push({ label: "Vehículo", value: vehicle, icon: CarFront });
  }
  const years = range(f.year_min, f.year_max, String);
  if (years) main.push({ label: "Año", value: years, icon: CalendarDays });
  const priceAmount = f.price_max ?? f.price_min;
  if (priceAmount != null) {
    const unit = currency(priceAmount, f.currency);
    const price = range(f.price_min, f.price_max, number)!;
    const value = price.replace(/^(Desde |Hasta )?/, (_, prefix = "") => `${prefix}${unit} `);
    main.push({ label: "Presupuesto", value, icon: Banknote });
  }
  const mileage = range(f.km_min, f.km_max, number);
  if (mileage) main.push({ label: "Kilometraje", value: `${mileage} km`, icon: Gauge });
  if (f.transmission) main.push({ label: "Caja", value: TRANSMISSION[f.transmission] ?? f.transmission, icon: Settings2 });
  if (hasLocation && radiusKm != null && radiusKm > 0) {
    main.push({ label: "Zona", value: `${f.location_label || "Tu ubicación"} · ${number(radiusKm)} km`, icon: MapPin });
  }

  if (f.fuel) extra.push({ label: "Combustible", value: FUEL[f.fuel] ?? f.fuel });
  const strictTrims = f.trim_strict && f.trims?.length ? f.trims : [];
  if (strictTrims.length) extra.push({ label: "Versión", value: strictTrims.join(", ") });
  const preferredTrims = [...new Set([...(strictTrims.length ? [] : f.trims ?? []), ...(p.preferred_trims ?? [])])];
  if (preferredTrims.length) extra.push({ label: "Versión preferida", value: preferredTrims.join(", ") });
  if (p.seller_type) extra.push({ label: "Vendedor preferido", value: SELLER[p.seller_type] ?? p.seller_type });
  if (p.colors?.length) extra.push({ label: "Colores preferidos", value: p.colors.join(", ") });
  if (p.km_target != null) extra.push({ label: "Kilometraje preferido", value: `${number(p.km_target)} km` });
  if (p.price_target != null) {
    extra.push({ label: "Precio preferido", value: `${currency(p.price_target, p.price_target_currency ?? f.currency)} ${number(p.price_target)}` });
  }
  if (hasLocation && p.max_distance_km != null) extra.push({ label: "Distancia preferida", value: `${number(p.max_distance_km)} km` });

  const selectedIds = f.sources?.length ? [...new Set(f.sources)] : null;
  const platforms = sources == null ? [] : selectedIds
    ? selectedIds.map((id) => sources.find((source) => source.id === id) ?? { id, name: `${id} · sin información`, enabled: true, collectionState: "unknown" as const })
    : sources.filter((source) => source.enabled);
  if (!main.length && !extra.length && !platforms.length && sources != null) return null;

  return (
    <section aria-label="Criterios de búsqueda" data-testid="search-criteria" className="space-y-2.5">
      {main.length ? (
        <dl className={cn(
          "grid grid-cols-2 gap-x-4 gap-y-2.5 rounded-lg border bg-muted/40 px-3 py-2.5",
          main.length === 1 && "grid-cols-1",
          ["md:grid-cols-1", "md:grid-cols-2", "md:grid-cols-3", "md:grid-cols-4", "md:grid-cols-5", "md:grid-cols-3 lg:grid-cols-6"][main.length - 1],
        )}>
          {main.map(({ label, value, icon: Icon }, index) => (
            <div key={label} className={cn(
              "min-w-0",
              main.length > 1 && main.length % 2 === 1 && index === main.length - 1
                && "col-span-2 flex items-baseline gap-2 border-t pt-2 md:col-span-1 md:block md:border-t-0 md:pt-0",
            )}>
              <dt className="flex shrink-0 items-center gap-1.5 text-[11px] leading-4 text-muted-foreground">
                {Icon ? <Icon className="size-3.5 shrink-0 self-center" aria-hidden /> : null}
                {label}
              </dt>
              <dd className={cn(
                "min-w-0 break-words text-xs font-medium leading-4",
                main.length > 1 && main.length % 2 === 1 && index === main.length - 1
                  ? "md:mt-0.5 md:pl-5" : "mt-0.5 pl-5",
              )}>{value}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      <div className="flex flex-wrap items-start justify-between gap-x-5 gap-y-3">
        {platforms.length ? (
          <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1.5 text-xs">
            <span className="text-muted-foreground">Plataformas</span>
            <ul aria-label="Plataformas de la búsqueda" className="flex flex-wrap gap-1.5">
              {platforms.map((source) => {
                const state = source.enabled ? source.collectionState ?? "unknown" : "paused";
                const { label, icon: Icon } = STATUS[state];
                const loading = state === "waiting" || state === "loading";
                return (
                  <li key={source.id} title={label} aria-label={`${source.name}: ${label}`} data-collection-state={state}
                    className="flex max-w-full items-center gap-1.5 rounded border px-2 py-1 font-medium">
                    <span className="min-w-0 break-words">{source.name}{state === "paused" ? <span className="font-normal text-muted-foreground"> · pausada</span> : null}</span>
                    <Icon aria-hidden className={`size-3.5 shrink-0 ${loading ? "animate-spin text-muted-foreground motion-reduce:animate-none" : state === "done" ? "text-ok" : state === "failed" ? "text-warn" : "text-muted-foreground"}`} />
                  </li>
                );
              })}
            </ul>
          </div>
        ) : sources == null ? <p className="text-xs text-muted-foreground">No se pudieron cargar las plataformas.</p> : null}
        {extra.length ? (
          <details className="group w-full">
            <summary className="flex w-fit cursor-pointer list-none items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground focus-visible:rounded focus-visible:outline-2 focus-visible:outline-offset-4 [&::-webkit-details-marker]:hidden">
              Ver más criterios
              <ChevronDown className="size-3.5 transition-transform group-open:rotate-180 motion-reduce:transition-none" aria-hidden />
            </summary>
            <dl className="mt-3 grid gap-x-6 gap-y-3 border-t pt-3 text-[13px] sm:grid-cols-2 lg:grid-cols-3">
              {extra.map(({ label, value }) => (
                <div key={label} className="min-w-0">
                  <dt className="text-xs text-muted-foreground">{label}</dt>
                  <dd className="break-words font-medium">{value}</dd>
                </div>
              ))}
            </dl>
          </details>
        ) : null}
      </div>
    </section>
  );
}
