"use client";

import { Loader2, LocateFixed } from "lucide-react";
import { useEffect, useMemo, useState, useTransition } from "react";

import { type Preview, previewSearch, saveSearch } from "@/app/app/searches/actions";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import type { Catalog } from "@/lib/catalog";
import { FREQUENCY, FUEL, MIN_LEVEL_OPTIONS, SELLER, TRANSMISSION } from "@/lib/copy";
import { km, money, number, vehicle } from "@/lib/format";
import { AMBA, PLACES, placeById, placeByLabel } from "@/lib/locations";
import { type SearchInput, type SearchValues, defaultName } from "@/lib/search-form";
import { cn } from "@/lib/utils";

type Source = { id: string; name: string };
type Origin = { label: string; lat: number; lon: number } | null;

type Draft = {
  name: string;
  nameTouched: boolean;
  make: string;
  model: string;
  trim: string;
  trim_strict: boolean;
  year_min: string;
  year_max: string;
  price_max: string;
  currency: "USD" | "ARS";
  km_max: string;
  transmission: "" | "manual" | "automatic";
  fuel: string;
  sources: string[];
  place: string; // "" (todo el país) | "amba" | a PLACES id | "default" | "current" | "saved"
  radius: string;
  current: { lat: number; lon: number } | null;
  saved: { label: string; lat: number; lon: number } | null;
  km_target: string;
  price_target: string;
  seller_type: "" | "private" | "dealer";
  notification_frequency: "immediate" | "daily";
  notify_min_level: SearchValues["notify_min_level"];
};

/** "11.500" → 11500; "" → null. */
function amount(text: string): number | null {
  const digits = text.replace(/\D/g, "");
  return digits ? Number(digits) : null;
}

function draftFrom(v: SearchValues, defaultOrigin: Origin): Draft {
  let place = "";
  let saved: Draft["saved"] = null;
  if (v.location) {
    const preset = placeByLabel(v.location.label);
    if (preset && preset.lat === v.location.lat && preset.lon === v.location.lon) place = preset.id;
    else if (defaultOrigin && defaultOrigin.lat === v.location.lat && defaultOrigin.lon === v.location.lon) place = "default";
    else {
      place = "saved";
      saved = { label: v.location.label, lat: v.location.lat, lon: v.location.lon };
    }
  }
  return {
    name: v.name,
    nameTouched: Boolean(v.name) && v.name !== defaultName(v),
    make: v.make,
    model: v.model,
    trim: v.trim,
    trim_strict: v.trim_strict,
    year_min: v.year_min?.toString() ?? "",
    year_max: v.year_max?.toString() ?? "",
    price_max: v.price_max != null ? number(v.price_max) : "",
    currency: v.currency,
    km_max: v.km_max != null ? number(v.km_max) : "",
    transmission: v.transmission,
    fuel: v.fuel,
    sources: v.sources,
    place,
    radius: v.location ? String(v.location.radius_km) : "",
    current: null,
    saved,
    km_target: v.km_target != null ? number(v.km_target) : "",
    price_target: v.price_target != null ? number(v.price_target) : "",
    seller_type: v.seller_type,
    notification_frequency: v.notification_frequency,
    notify_min_level: v.notify_min_level,
  };
}

function location(d: Draft, defaultOrigin: Origin): SearchInput["location"] {
  const radius = Number(d.radius.replace(",", "."));
  const radius_km = Number.isFinite(radius) && radius > 0 ? radius : 30;
  if (d.place === "default" && defaultOrigin) return { ...defaultOrigin, radius_km };
  if (d.place === "current" && d.current) return { label: "Mi ubicación", ...d.current, radius_km };
  if (d.place === "saved" && d.saved) return { ...d.saved, radius_km };
  const preset = placeById(d.place);
  return preset ? { label: preset.label, lat: preset.lat, lon: preset.lon, radius_km } : null;
}

function toInput(d: Draft, defaultOrigin: Origin): SearchInput {
  return {
    name: d.nameTouched ? d.name : "",
    make: d.make,
    model: d.model,
    trim: d.trim,
    trim_strict: d.trim_strict,
    year_min: amount(d.year_min),
    year_max: amount(d.year_max),
    price_max: amount(d.price_max),
    currency: d.currency,
    km_max: amount(d.km_max),
    transmission: d.transmission,
    fuel: d.fuel,
    sources: d.sources,
    location: location(d, defaultOrigin),
    km_target: amount(d.km_target),
    price_target: amount(d.price_target),
    seller_type: d.seller_type,
    notification_frequency: d.notification_frequency,
    notify_min_level: d.notify_min_level,
  };
}

const THIS_YEAR = new Date().getFullYear();

export function SearchForm({
  catalog,
  sources,
  initial,
  profileId,
  defaultOrigin,
}: {
  catalog: Catalog;
  sources: Source[];
  initial: SearchValues;
  profileId: number | null;
  defaultOrigin: Origin;
}) {
  const [d, setDraft] = useState<Draft>(() => draftFrom(initial, defaultOrigin));
  const [errors, setErrors] = useState<{ error?: string; fields?: Record<string, string> }>({});
  const [saving, startSaving] = useTransition();
  // Tagged with the input it answers, so a stale count never shows for other filters.
  const [preview, setPreview] = useState<{ key: string; data: Preview | null } | null>(null);
  const [previewing, startPreview] = useTransition();
  const [locating, setLocating] = useState(false);

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((prev) => ({ ...prev, [key]: value }));

  const models = useMemo(() => catalog.find((m) => m.make === d.make)?.models ?? [], [catalog, d.make]);
  const entry = models.find((m) => m.model === d.model);
  const years = useMemo(() => {
    const from = Math.max(entry?.yearFrom ?? 1990, 1990);
    const to = Math.min(entry?.yearTo ?? THIS_YEAR, THIS_YEAR);
    return Array.from({ length: Math.max(to - from + 1, 0) }, (_, i) => to - i);
  }, [entry]);
  const fuels = entry?.fuels.length ? entry.fuels : Object.keys(FUEL);
  const autoName = defaultName({ make: d.make, model: d.model, trim: d.trim });

  const input = useMemo(() => toInput(d, defaultOrigin), [d, defaultOrigin]);
  const previewKey = JSON.stringify({ ...input, name: "", notification_frequency: "", notify_min_level: "" });

  useEffect(() => {
    if (!input.make || !input.model) return;
    const timer = setTimeout(() => {
      startPreview(async () => {
        const data = await previewSearch(input);
        setPreview({ key: previewKey, data });
      });
    }, 400);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- previewKey is the input minus the alert settings
  }, [previewKey]);
  const shownPreview = preview?.key === previewKey ? preview.data : null;
  const previewFailed = preview?.key === previewKey && preview.data === null;

  function chooseMake(make: string) {
    setDraft((prev) => ({ ...prev, make, model: "", trim: "", trim_strict: false, fuel: "" }));
  }

  function chooseModel(model: string) {
    setDraft((prev) => ({ ...prev, model, trim: "", trim_strict: false }));
  }

  function choosePlace(place: string) {
    const preset = placeById(place);
    setDraft((prev) => ({
      ...prev,
      place,
      radius: preset ? String(preset.radius) : prev.radius || "30",
    }));
    if (place === "current" && !d.current) locate();
  }

  function locate() {
    if (!("geolocation" in navigator)) return;
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setDraft((prev) => ({
          ...prev,
          place: "current",
          current: { lat: pos.coords.latitude, lon: pos.coords.longitude },
          radius: prev.radius || "30",
        }));
        setLocating(false);
      },
      () => {
        setLocating(false);
        setDraft((prev) => ({ ...prev, place: prev.current ? "current" : "" }));
        setErrors({ fields: { location: "No pudimos leer tu ubicación. Elegí una zona de la lista." } });
      },
      { enableHighAccuracy: false, timeout: 10_000 },
    );
  }

  function toggleSource(id: string, on: boolean) {
    setDraft((prev) => ({
      ...prev,
      sources: on ? [...new Set([...prev.sources, id])] : prev.sources.filter((s) => s !== id),
    }));
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setErrors({});
    startSaving(async () => {
      const result = await saveSearch(profileId, input);
      if (result?.error) setErrors(result);
    });
  }

  const fieldError = (key: string) =>
    errors.fields?.[key] ? (
      <p role="alert" className="text-xs text-destructive">
        {errors.fields[key]}
      </p>
    ) : null;

  return (
    <form onSubmit={submit} className="grid gap-5 lg:grid-cols-[1fr_300px] lg:items-start">
      <div className="space-y-5">
        <Card>
          <CardHeader>
            <CardTitle>Vehículo</CardTitle>
            <CardDescription>Un modelo por búsqueda. Si buscás varios, creá una búsqueda para cada uno.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <Field id="make" label="Marca" error={fieldError("make")}>
              <NativeSelect id="make" value={d.make} onChange={(e) => chooseMake(e.target.value)} className="w-full" required>
                <NativeSelectOption value="">Elegí una marca</NativeSelectOption>
                {catalog.map((m) => (
                  <NativeSelectOption key={m.make} value={m.make}>
                    {m.make}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </Field>
            <Field id="model" label="Modelo" error={fieldError("model")}>
              <NativeSelect
                id="model"
                value={d.model}
                onChange={(e) => chooseModel(e.target.value)}
                disabled={!d.make}
                className="w-full"
                required
              >
                <NativeSelectOption value="">{d.make ? "Elegí un modelo" : "Primero elegí la marca"}</NativeSelectOption>
                {models.map((m) => (
                  <NativeSelectOption key={m.model} value={m.model}>
                    {m.model}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </Field>
            <Field id="trim" label="Versión" hint="Opcional">
              {entry?.trims.length ? (
                <NativeSelect id="trim" value={d.trim} onChange={(e) => set("trim", e.target.value)} className="w-full">
                  <NativeSelectOption value="">Cualquiera</NativeSelectOption>
                  {entry.trims.map((t) => (
                    <NativeSelectOption key={t} value={t}>
                      {t}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
              ) : (
                <Input
                  id="trim"
                  value={d.trim}
                  onChange={(e) => set("trim", e.target.value)}
                  placeholder="Ej.: Highline"
                  disabled={!d.model}
                />
              )}
            </Field>
            <div className="flex items-end pb-1.5">
              {d.trim ? (
                <label className="flex items-center gap-2 text-sm">
                  <Checkbox checked={d.trim_strict} onCheckedChange={(v) => set("trim_strict", v === true)} />
                  Solo esta versión
                  <span className="text-xs text-muted-foreground">(si no, es preferida)</span>
                </label>
              ) : null}
            </div>
            <Field id="year_min" label="Año desde">
              <NativeSelect id="year_min" value={d.year_min} onChange={(e) => set("year_min", e.target.value)} className="w-full">
                <NativeSelectOption value="">Cualquiera</NativeSelectOption>
                {years.map((y) => (
                  <NativeSelectOption key={y} value={String(y)}>
                    {y}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </Field>
            <Field id="year_max" label="Año hasta" error={fieldError("year_max")}>
              <NativeSelect id="year_max" value={d.year_max} onChange={(e) => set("year_max", e.target.value)} className="w-full">
                <NativeSelectOption value="">Cualquiera</NativeSelectOption>
                {years.map((y) => (
                  <NativeSelectOption key={y} value={String(y)}>
                    {y}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </Field>
            <fieldset className="space-y-2 sm:col-span-2">
              <legend className="text-sm font-medium">Transmisión</legend>
              <Segmented
                name="transmission"
                value={d.transmission}
                onChange={(v) => set("transmission", v as Draft["transmission"])}
                options={[
                  { value: "", label: "Cualquiera" },
                  { value: "manual", label: TRANSMISSION.manual },
                  { value: "automatic", label: TRANSMISSION.automatic },
                ]}
              />
            </fieldset>
            <Field id="fuel" label="Combustible">
              <NativeSelect id="fuel" value={d.fuel} onChange={(e) => set("fuel", e.target.value)} className="w-full">
                <NativeSelectOption value="">Cualquiera</NativeSelectOption>
                {fuels.map((f) => (
                  <NativeSelectOption key={f} value={f}>
                    {FUEL[f] ?? f}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </Field>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Precio y kilometraje</CardTitle>
            <CardDescription>
              El precio se compara convirtiendo de moneda: un aviso en pesos cuenta contra un tope en dólares.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <Field id="price_max" label="Precio máximo" error={fieldError("price_max")}>
              <div className="flex gap-2">
                <NativeSelect
                  className="w-24 shrink-0"
                  aria-label="Moneda"
                  value={d.currency}
                  onChange={(e) => set("currency", e.target.value as Draft["currency"])}
                >
                  <NativeSelectOption value="USD">USD</NativeSelectOption>
                  <NativeSelectOption value="ARS">ARS</NativeSelectOption>
                </NativeSelect>
                <Input
                  id="price_max"
                  inputMode="numeric"
                  value={d.price_max}
                  onChange={(e) => set("price_max", e.target.value)}
                  onBlur={() => amount(d.price_max) != null && set("price_max", number(amount(d.price_max)))}
                  placeholder={d.currency === "USD" ? "11.500" : "15.000.000"}
                />
              </div>
            </Field>
            <Field id="km_max" label="Kilometraje máximo" error={fieldError("km_max")}>
              <Input
                id="km_max"
                inputMode="numeric"
                value={d.km_max}
                onChange={(e) => set("km_max", e.target.value)}
                onBlur={() => amount(d.km_max) != null && set("km_max", number(amount(d.km_max)))}
                placeholder="150.000"
              />
            </Field>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Ubicación</CardTitle>
            <CardDescription>Las publicaciones sin ubicación no se descartan: se muestran como «no informado».</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-[1fr_140px]">
            <Field id="place" label="Zona" error={fieldError("location")}>
              <NativeSelect id="place" value={d.place} onChange={(e) => choosePlace(e.target.value)} className="w-full">
                <NativeSelectOption value="">Todo el país</NativeSelectOption>
                <NativeSelectOption value={AMBA.id}>AMBA (CABA y 60 km)</NativeSelectOption>
                {defaultOrigin ? (
                  <NativeSelectOption value="default">Mi ubicación guardada: {defaultOrigin.label}</NativeSelectOption>
                ) : null}
                {d.saved ? <NativeSelectOption value="saved">{d.saved.label}</NativeSelectOption> : null}
                <NativeSelectOption value="current">Mi ubicación actual</NativeSelectOption>
                {PLACES.map((p) => (
                  <NativeSelectOption key={p.id} value={p.id}>
                    {p.label}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </Field>
            {d.place ? (
              <Field id="radius" label="Radio (km)">
                <Input id="radius" inputMode="numeric" value={d.radius} onChange={(e) => set("radius", e.target.value)} />
              </Field>
            ) : null}
            {d.place === "current" ? (
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground sm:col-span-2">
                <LocateFixed className="size-3.5" aria-hidden />
                {locating
                  ? "Leyendo tu ubicación…"
                  : d.current
                    ? `Ubicación leída (${d.current.lat.toFixed(3)}, ${d.current.lon.toFixed(3)}).`
                    : "Permití el acceso a tu ubicación."}
              </p>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Fuentes</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="grid gap-2 sm:grid-cols-3">
              {sources.map((s) => (
                <label key={s.id} className="flex items-center gap-2 text-sm">
                  <Checkbox checked={d.sources.includes(s.id)} onCheckedChange={(v) => toggleSource(s.id, v === true)} />
                  {s.name}
                </label>
              ))}
            </div>
            {fieldError("sources")}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Preferencias</CardTitle>
            <CardDescription>Opcionales: no descartan publicaciones, suben o bajan el Opportunity Score.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-3">
            <Field id="km_target" label="Kilometraje ideal">
              <Input id="km_target" inputMode="numeric" value={d.km_target} onChange={(e) => set("km_target", e.target.value)} placeholder="120.000" />
            </Field>
            <Field id="price_target" label={`Precio ideal (${d.currency})`}>
              <Input
                id="price_target"
                inputMode="numeric"
                value={d.price_target}
                onChange={(e) => set("price_target", e.target.value)}
                placeholder={d.currency === "USD" ? "10.500" : "14.000.000"}
              />
            </Field>
            <Field id="seller_type" label="Vendedor">
              <NativeSelect
                id="seller_type"
                value={d.seller_type}
                onChange={(e) => set("seller_type", e.target.value as Draft["seller_type"])}
                className="w-full"
              >
                <NativeSelectOption value="">Cualquiera</NativeSelectOption>
                <NativeSelectOption value="private">{SELLER.private}</NativeSelectOption>
                <NativeSelectOption value="dealer">{SELLER.dealer}</NativeSelectOption>
              </NativeSelect>
            </Field>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Alertas</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">Frecuencia</legend>
              <Segmented
                name="notification_frequency"
                value={d.notification_frequency}
                onChange={(v) => set("notification_frequency", v as Draft["notification_frequency"])}
                options={[
                  { value: "immediate", label: FREQUENCY.immediate.label },
                  { value: "daily", label: FREQUENCY.daily.label },
                ]}
              />
              <p className="text-xs text-muted-foreground">{FREQUENCY[d.notification_frequency].hint}</p>
            </fieldset>
            <Field id="notify_min_level" label="Avisarme de">
              <NativeSelect
                id="notify_min_level"
                value={d.notify_min_level}
                onChange={(e) => set("notify_min_level", e.target.value as Draft["notify_min_level"])}
                className="w-full"
              >
                {MIN_LEVEL_OPTIONS.map((o) => (
                  <NativeSelectOption key={o.value} value={o.value}>
                    {o.label}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </Field>
            <Field id="name" label="Nombre de la búsqueda" className="sm:col-span-2">
              <Input
                id="name"
                value={d.nameTouched ? d.name : autoName}
                onChange={(e) => setDraft((prev) => ({ ...prev, name: e.target.value, nameTouched: true }))}
                placeholder="Ej.: Fiesta Titanium"
                maxLength={80}
              />
            </Field>
          </CardContent>
        </Card>
      </div>

      <aside className="space-y-3 lg:sticky lg:top-20">
        <PreviewCard
          preview={shownPreview}
          loading={previewing}
          failed={previewFailed}
          ready={Boolean(d.make && d.model)}
        />
        {errors.error ? (
          <p role="alert" className="text-sm text-destructive">
            {errors.error}
          </p>
        ) : null}
        <Button type="submit" className="h-11 w-full text-base" disabled={saving}>
          {saving ? <Loader2 className="animate-spin" aria-hidden /> : null}
          {profileId ? "Guardar cambios" : "Crear búsqueda"}
        </Button>
        <p className="text-xs text-muted-foreground">
          Al guardar buscamos coincidencias entre las publicaciones de los últimos 30 días. Esas no se notifican: las
          ves acá. Desde entonces te avisamos de las nuevas.
        </p>
      </aside>
    </form>
  );
}

function Field({
  id,
  label,
  hint,
  error,
  className,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  error?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <Label htmlFor={id}>
        {label}
        {hint ? <span className="font-normal text-muted-foreground">· {hint}</span> : null}
      </Label>
      {children}
      {error}
    </div>
  );
}

/** Radio buttons that look like a segmented control (native inputs: keyboard and screen readers work). */
function Segmented({
  name,
  value,
  onChange,
  options,
}: {
  name: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <div className="inline-flex rounded-lg bg-muted p-0.5">
      {options.map((o) => (
        <label
          key={o.value || "any"}
          className={cn(
            "cursor-pointer rounded-md px-3 py-1.5 text-sm text-muted-foreground has-focus-visible:ring-2 has-focus-visible:ring-ring",
            value === o.value && "bg-background font-medium text-foreground shadow-sm",
          )}
        >
          <input
            type="radio"
            name={name}
            value={o.value}
            checked={value === o.value}
            onChange={() => onChange(o.value)}
            className="sr-only"
          />
          {o.label}
        </label>
      ))}
    </div>
  );
}

function PreviewCard({
  preview,
  loading,
  failed,
  ready,
}: {
  preview: Preview | null;
  loading: boolean;
  failed: boolean;
  ready: boolean;
}) {
  return (
    <Card size="sm" aria-live="polite">
      <CardContent className="space-y-3">
        {!ready ? (
          <p className="text-sm text-muted-foreground">Elegí marca y modelo para ver cuántas publicaciones coinciden hoy.</p>
        ) : failed ? (
          <p className="text-sm text-muted-foreground">No pudimos contar las publicaciones ahora. Igual podés guardar.</p>
        ) : preview == null ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" aria-hidden /> Contando publicaciones…
          </p>
        ) : (
          <>
            <p data-testid="preview-count" className={cn("text-sm", loading && "opacity-60")}>
              <span className="text-2xl font-semibold tabular-nums">{preview.count}</span>{" "}
              {preview.count === 1 ? "publicación actual coincide" : "publicaciones actuales coinciden"}
            </p>
            {preview.sample.length ? (
              <ul className="space-y-1.5 border-t pt-3 text-xs">
                {preview.sample.map((l) => (
                  <li key={l.id} className="flex justify-between gap-2">
                    <span className="truncate">{vehicle(l)}</span>
                    <span className="shrink-0 text-muted-foreground">
                      {[money(l.price, l.currency), km(l.mileage_km)].filter(Boolean).join(" · ")}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-muted-foreground">
                Hoy no hay publicaciones con estos filtros. Igual la monitoreamos y te avisamos cuando aparezca una.
              </p>
            )}
            <p className="text-[11px] text-muted-foreground">
              Estimación con los filtros duros; al guardar calculamos el Opportunity Score de cada una.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
