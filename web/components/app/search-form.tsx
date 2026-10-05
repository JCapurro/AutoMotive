"use client";

import { Info, Loader2, LocateFixed, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, useTransition } from "react";

import { type Preview, type SaveOrigin, previewSearch, saveSearch } from "@/app/app/searches/actions";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import type { Catalog } from "@/lib/catalog";
import { FREQUENCY, FUEL, MIN_LEVEL_OPTIONS, SELLER, TRANSMISSION } from "@/lib/copy";
import { km, money, number, vehicle } from "@/lib/format";
import { PROVINCES, citiesInProvince, cityById, cityByLocation } from "@/lib/argentina-locations";
import { type SearchInput, type SearchValues, defaultName, selectedTrims } from "@/lib/search-form";
import { cn } from "@/lib/utils";
import { analyticsEvent } from "@/lib/google-analytics";

type Source = { id: string; name: string };

type Draft = {
  name: string;
  nameTouched: boolean;
  make: string;
  model: string;
  trim: string;
  trims: string[];
  trim_strict: boolean;
  year_min: string;
  year_max: string;
  price_max: string;
  currency: "USD" | "ARS";
  km_max: string;
  transmission: "" | "manual" | "automatic";
  fuel: string;
  sources: string[];
  place: string; // "" (todo el país) | "city" | "current" | "saved"
  province: string;
  city: string;
  radius: string;
  current: { label: string; lat: number; lon: number } | null;
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

/** A new search without a zone starts at the device's location (asked on mount). */
function draftFrom(v: SearchValues, isNew: boolean): Draft {
  let place = isNew ? "current" : "";
  let saved: Draft["saved"] = null;
  let province = "";
  let city = "";
  if (v.location) {
    const locality = cityByLocation(v.location);
    if (locality) {
      place = "city";
      province = locality.provinceId;
      city = locality.id;
    } else {
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
    trims: selectedTrims(v),
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
    province,
    city,
    radius: v.location ? String(v.location.radius_km) : isNew ? "30" : "",
    current: null,
    saved,
    km_target: v.km_target != null ? number(v.km_target) : "",
    price_target: v.price_target != null ? number(v.price_target) : "",
    seller_type: v.seller_type,
    notification_frequency: v.notification_frequency,
    notify_min_level: v.notify_min_level,
  };
}

function location(d: Draft): SearchInput["location"] {
  const radius = Number(d.radius.replace(",", "."));
  const radius_km = radius;
  if (d.place === "current" && d.current) return { ...d.current, radius_km };
  if (d.place === "saved" && d.saved) return { ...d.saved, radius_km };
  if (d.place === "city") {
    const city = cityById(d.city);
    return city ? { label: city.label, lat: city.lat, lon: city.lon, radius_km } : null;
  }
  return null;
}

function toInput(d: Draft): SearchInput {
  return {
    name: d.nameTouched ? d.name : "",
    make: d.make,
    model: d.model,
    trim: d.trim,
    trims: d.trims,
    trim_strict: d.trim_strict,
    year_min: amount(d.year_min),
    year_max: amount(d.year_max),
    price_max: amount(d.price_max),
    currency: d.currency,
    km_max: amount(d.km_max),
    transmission: d.transmission,
    fuel: d.fuel,
    sources: d.sources,
    location: location(d),
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
  idPrefix,
  notes,
  origin,
  onSaved,
}: {
  catalog: Catalog;
  sources: Source[];
  initial: SearchValues;
  profileId: number | null;
  /** Several forms on one page (modo asistido) need distinct element ids. */
  idPrefix?: string;
  /** What the assisted parse couldn't settle, shown above the fields. */
  notes?: string[];
  origin?: Omit<SaveOrigin, "edited">;
  /** With origin.stay: the new search's id, instead of navigating to it. */
  onSaved?: (id: number) => void;
}) {
  const fid = (key: string) => (idPrefix ? `${idPrefix}-${key}` : key);
  const isNew = profileId == null && !initial.location;
  const [d, setDraft] = useState<Draft>(() => draftFrom(initial, isNew));
  const [versionText, setVersionText] = useState("");
  // The proposal as it arrived, to record whether the user corrected it.
  const [pristine] = useState(() => JSON.stringify(toInput(draftFrom(initial, isNew))));
  // Until the user picks a zone, the location filled in on mount isn't a correction.
  const placeTouched = useRef(false);
  const locationRequest = useRef(0);
  const [errors, setErrors] = useState<{ error?: string; fields?: Record<string, string> }>({});
  const [saving, startSaving] = useTransition();
  // Tagged with the input it answers, so a stale count never shows for other filters.
  const [preview, setPreview] = useState<{ key: string; data: Preview | null } | null>(null);
  const [previewing, startPreview] = useTransition();
  const [locating, setLocating] = useState(false);

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((prev) => ({ ...prev, [key]: value }));

  const models = useMemo(() => catalog.find((m) => m.make === d.make)?.models ?? [], [catalog, d.make]);
  const entry = models.find((m) => m.model === d.model);
  const cities = useMemo(() => citiesInProvince(d.province), [d.province]);
  const cityNames = useMemo(() => {
    const counts = new Map<string, number>();
    for (const city of cities) counts.set(city.city, (counts.get(city.city) ?? 0) + 1);
    return counts;
  }, [cities]);
  const years = useMemo(() => {
    const from = Math.max(entry?.yearFrom ?? 1990, 1990);
    const to = Math.min(entry?.yearTo ?? THIS_YEAR, THIS_YEAR);
    return Array.from({ length: Math.max(to - from + 1, 0) }, (_, i) => to - i);
  }, [entry]);
  const fuels = entry?.fuels.length ? entry.fuels : Object.keys(FUEL);
  const pendingVersion = versionText.trim();
  const autoName = defaultName({ make: d.make, model: d.model, trim: d.trim, trims: [...d.trims, pendingVersion].filter(Boolean) });

  const input = useMemo(() => toInput({ ...d, trims: [...new Set([...d.trims, versionText.trim()].filter(Boolean))] }), [d, versionText]);
  const locationReady = !((d.place === "current" && !d.current) || (d.place === "city" && !d.city));
  const previewKey = JSON.stringify({ ...input, locationReady, name: "", notification_frequency: "", notify_min_level: "" });

  useEffect(() => {
    if (!input.make || !input.model || !locationReady) return;
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
    setVersionText("");
    setDraft((prev) => ({ ...prev, make, model: "", trim: "", trims: [], trim_strict: false, fuel: "" }));
  }

  function chooseModel(model: string) {
    setVersionText("");
    setDraft((prev) => ({ ...prev, model, trim: "", trims: [], trim_strict: false }));
  }

  function chooseTrim(trim: string, add: boolean) {
    setDraft((prev) => {
      const trims = add ? [...new Set([...prev.trims, trim])] : prev.trims.filter((t) => t !== trim);
      return { ...prev, trims, trim: trims[0] ?? "", trim_strict: trims.length > 0 && prev.trim_strict };
    });
  }

  function addFreeVersion() {
    if (!pendingVersion) return;
    chooseTrim(pendingVersion, true);
    setVersionText("");
  }

  function choosePlace(place: string) {
    placeTouched.current = true;
    locationRequest.current += 1;
    setLocating(false);
    setErrors({});
    setDraft((prev) => ({
      ...prev,
      place,
      radius: prev.radius || "30",
    }));
    if (place === "current" && !d.current) locate();
  }

  function locate() {
    const request = ++locationRequest.current;
    const failed = () => {
      if (request !== locationRequest.current) return;
      setLocating(false);
      // Only fall back if the user is still waiting on "current": they may have picked a zone meanwhile.
      setDraft((prev) => (prev.place === "current" ? { ...prev, place: prev.current ? "current" : "city" } : prev));
      setErrors({ fields: { location: "No pudimos leer tu ubicación. Elegí provincia y ciudad, o volvé a intentarlo." } });
    };
    if (!("geolocation" in navigator)) return failed();
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        if (request !== locationRequest.current) return;
        // ~1 km is plenty for a radius filter and avoids storing an exact address.
        const round = (n: number) => Math.round(n * 100) / 100;
        const lat = round(pos.coords.latitude);
        const lon = round(pos.coords.longitude);
        setDraft((prev) =>
          prev.place === "current"
            ? {
                ...prev,
                current: { label: "Mi ubicación actual", lat, lon },
                radius: prev.radius || "30",
              }
            : prev,
        );
        setLocating(false);
      },
      failed,
      { enableHighAccuracy: false, timeout: 10_000 },
    );
  }

  useEffect(() => {
    if (isNew && d.place === "current") locate();
    return () => { locationRequest.current += 1; };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once, when a new search opens
  }, []);

  function toggleSource(id: string, on: boolean) {
    setDraft((prev) => ({
      ...prev,
      sources: on ? [...new Set([...prev.sources, id])] : prev.sources.filter((s) => s !== id),
    }));
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setErrors({});
    if (!locationReady) {
      setErrors({ fields: { location: "Elegí provincia y ciudad o permití el acceso a tu ubicación." } });
      return;
    }
    startSaving(async () => {
      const result = await saveSearch(
        profileId,
        input,
        origin
          ? {
              ...origin,
              edited:
                JSON.stringify(
                  placeTouched.current || d.place !== "current" ? input : { ...input, location: initial.location },
                ) !== pristine,
            }
          : undefined,
      );
      if (result?.error) setErrors(result);
      else if (result?.savedId != null) {
        analyticsEvent("search", { search_type: "structured" });
        analyticsEvent("search_created", { search_type: "structured" });
        onSaved?.(result.savedId);
      }
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
        {notes?.length ? (
          <Alert data-testid="draft-notes">
            <Info aria-hidden />
            <AlertTitle>Revisá estos puntos</AlertTitle>
            <AlertDescription>
              <ul className="list-disc space-y-0.5 pl-4">
                {notes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        ) : null}
        <Card>
          <CardHeader>
            <CardTitle>Vehículo</CardTitle>
            <CardDescription>Podés incluir varias versiones del mismo modelo. Cada modelo distinto tiene su propia búsqueda.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <Field id={fid("make")} label="Marca" error={fieldError("make")}>
              <NativeSelect id={fid("make")} value={d.make} onChange={(e) => chooseMake(e.target.value)} className="w-full" required>
                <NativeSelectOption value="">Elegí una marca</NativeSelectOption>
                {catalog.map((m) => (
                  <NativeSelectOption key={m.make} value={m.make}>
                    {m.make}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </Field>
            <Field id={fid("model")} label="Modelo" error={fieldError("model")}>
              <NativeSelect
                id={fid("model")}
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
            <Field id={fid("trim")} label="Versiones" hint="Opcional" className="sm:col-span-2">
              {entry?.trims.length ? (
                <NativeSelect id={fid("trim")} value="" onChange={(e) => e.target.value && chooseTrim(e.target.value, true)} className="w-full">
                  <NativeSelectOption value="">{d.trims.length ? "Agregar otra versión" : "Cualquier versión"}</NativeSelectOption>
                  {entry.trims.filter((t) => !d.trims.includes(t)).map((t) => (
                    <NativeSelectOption key={t} value={t}>
                      {t}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
              ) : (
                <div className="flex gap-2">
                  <Input
                    id={fid("trim")}
                    value={versionText}
                    onChange={(e) => setVersionText(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addFreeVersion(); } }}
                    placeholder="Ej.: Highline"
                    maxLength={60}
                    disabled={!d.model}
                  />
                  <Button type="button" variant="outline" onClick={addFreeVersion} disabled={!d.model || !pendingVersion}>Agregar versión</Button>
                </div>
              )}
              {d.trims.length ? (
                <ul aria-label="Versiones seleccionadas" className="flex flex-wrap gap-2">
                  {d.trims.map((trim) => (
                    <li key={trim}>
                      <Button type="button" size="sm" variant="secondary" onClick={() => chooseTrim(trim, false)} aria-label={`Quitar versión ${trim}`}>
                        {trim}<X className="size-3.5" aria-hidden />
                      </Button>
                    </li>
                  ))}
                </ul>
              ) : null}
              <p className="text-xs text-muted-foreground">{d.trims.length ? "Todas las versiones seleccionadas forman parte de esta búsqueda." : "Sin versiones seleccionadas, buscamos todas las del modelo."}</p>
              {fieldError("trims")}
            </Field>
            <div className="flex items-end pb-1.5 sm:col-span-2">
              {d.trim ? (
                <label className="flex items-center gap-2 text-sm">
                  <Checkbox checked={d.trim_strict} onCheckedChange={(v) => set("trim_strict", v === true)} />
                  Solo las versiones seleccionadas
                  <span className="text-xs text-muted-foreground">(si no, son preferidas)</span>
                </label>
              ) : null}
            </div>
            <Field id={fid("year_min")} label="Año desde">
              <NativeSelect id={fid("year_min")} value={d.year_min} onChange={(e) => set("year_min", e.target.value)} className="w-full">
                <NativeSelectOption value="">Cualquiera</NativeSelectOption>
                {years.map((y) => (
                  <NativeSelectOption key={y} value={String(y)}>
                    {y}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </Field>
            <Field id={fid("year_max")} label="Año hasta" error={fieldError("year_max")}>
              <NativeSelect id={fid("year_max")} value={d.year_max} onChange={(e) => set("year_max", e.target.value)} className="w-full">
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
                name={fid("transmission")}
                value={d.transmission}
                onChange={(v) => set("transmission", v as Draft["transmission"])}
                options={[
                  { value: "", label: "Cualquiera" },
                  { value: "manual", label: TRANSMISSION.manual },
                  { value: "automatic", label: TRANSMISSION.automatic },
                ]}
              />
            </fieldset>
            <Field id={fid("fuel")} label="Combustible">
              <NativeSelect id={fid("fuel")} value={d.fuel} onChange={(e) => set("fuel", e.target.value)} className="w-full">
                <NativeSelectOption value="">Cualquiera</NativeSelectOption>
                {fuels.map((f) => (
                  <NativeSelectOption key={f} value={f}>
                    {FUEL[f] ?? f}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </Field>
            <Field id={fid("seller_type")} label="Vendedor" hint="Preferido">
              <NativeSelect
                id={fid("seller_type")}
                value={d.seller_type}
                onChange={(e) => set("seller_type", e.target.value as Draft["seller_type"])}
                className="w-full"
              >
                <NativeSelectOption value="">Cualquiera</NativeSelectOption>
                <NativeSelectOption value="private">{SELLER.private}</NativeSelectOption>
                <NativeSelectOption value="dealer">{SELLER.dealer}</NativeSelectOption>
              </NativeSelect>
            </Field>
            <Field id={fid("km_max")} label="Kilometraje máximo" error={fieldError("km_max")}>
              <Input
                id={fid("km_max")}
                inputMode="numeric"
                value={d.km_max}
                onChange={(e) => set("km_max", e.target.value)}
                onBlur={() => amount(d.km_max) != null && set("km_max", number(amount(d.km_max)))}
                placeholder="150.000"
              />
            </Field>
            <details className="space-y-2 text-sm" open={d.km_target ? true : undefined}>
              <summary className="cursor-pointer text-muted-foreground">Kilometraje ideal (opcional)</summary>
              <Field id={fid("km_target")} label="Kilometraje ideal" error={fieldError("km_target")}>
                <Input id={fid("km_target")} inputMode="numeric" value={d.km_target} onChange={(e) => set("km_target", e.target.value)} placeholder="120.000" />
              </Field>
              <p className="text-xs text-muted-foreground">Prioriza publicaciones; no las descarta.</p>
            </details>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Precio</CardTitle>
            <CardDescription>
              El precio se compara convirtiendo de moneda: un aviso en pesos cuenta contra un tope en dólares.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <Field id={fid("price_max")} label="Precio máximo" error={fieldError("price_max")}>
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
                  id={fid("price_max")}
                  inputMode="numeric"
                  value={d.price_max}
                  onChange={(e) => set("price_max", e.target.value)}
                  onBlur={() => amount(d.price_max) != null && set("price_max", number(amount(d.price_max)))}
                  placeholder={d.currency === "USD" ? "11.500" : "15.000.000"}
                />
              </div>
            </Field>
            <details className="space-y-2 text-sm" open={d.price_target ? true : undefined}>
              <summary className="cursor-pointer text-muted-foreground">Precio ideal (opcional)</summary>
              <Field id={fid("price_target")} label={`Precio ideal (${d.currency})`} error={fieldError("price_target")}>
                <Input
                  id={fid("price_target")}
                  inputMode="numeric"
                  value={d.price_target}
                  onChange={(e) => set("price_target", e.target.value)}
                  placeholder={d.currency === "USD" ? "10.500" : "14.000.000"}
                />
              </Field>
              <p className="text-xs text-muted-foreground">Prioriza publicaciones; no las descarta.</p>
            </details>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Ubicación</CardTitle>
            <CardDescription>Las publicaciones sin ubicación no se descartan: se muestran como «no informado».</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <Field id={fid("place")} label="Buscar cerca de" error={fieldError("location")} className="sm:col-span-2">
              <NativeSelect id={fid("place")} value={d.place} onChange={(e) => choosePlace(e.target.value)} className="w-full">
                <NativeSelectOption value="current">Mi ubicación actual</NativeSelectOption>
                <NativeSelectOption value="city">Otra ubicación</NativeSelectOption>
                <NativeSelectOption value="">Todo el país</NativeSelectOption>
                {d.saved ? <NativeSelectOption value="saved">{d.saved.label} (guardada)</NativeSelectOption> : null}
              </NativeSelect>
            </Field>
            {d.place === "city" ? (
              <>
                <Field id={fid("province")} label="Provincia">
                  <NativeSelect id={fid("province")} value={d.province} onChange={(e) => {
                    placeTouched.current = true;
                    setErrors({});
                    setDraft((prev) => ({ ...prev, province: e.target.value, city: "" }));
                  }} className="w-full" required>
                    <NativeSelectOption value="">Elegí una provincia</NativeSelectOption>
                    {PROVINCES.map((p) => <NativeSelectOption key={p.id} value={p.id}>{p.label}</NativeSelectOption>)}
                  </NativeSelect>
                </Field>
                <Field id={fid("city")} label="Ciudad">
                  <NativeSelect id={fid("city")} value={d.city} onChange={(e) => {
                    placeTouched.current = true;
                    setErrors({});
                    set("city", e.target.value);
                  }} className="w-full" disabled={!d.province} required>
                    <NativeSelectOption value="">{d.province ? "Elegí una ciudad" : "Primero elegí la provincia"}</NativeSelectOption>
                    {cities.map((city) => <NativeSelectOption key={city.id} value={city.id}>
                      {city.city}{(cityNames.get(city.city) ?? 0) > 1 ? ` (${city.department})` : ""}
                    </NativeSelectOption>)}
                  </NativeSelect>
                </Field>
              </>
            ) : null}
            {d.place ? (
              <Field id={fid("radius")} label="Radio (km)" error={fieldError("location")}>
                <Input id={fid("radius")} inputMode="numeric" value={d.radius} onChange={(e) => set("radius", e.target.value)} />
              </Field>
            ) : null}
            {d.place === "current" ? (
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground sm:col-span-2">
                <LocateFixed className="size-3.5" aria-hidden />
                {locating
                  ? "Leyendo tu ubicación…"
                  : d.current
                    ? "Ubicación detectada. Usamos este punto como centro del radio."
                    : "Permití el acceso a tu ubicación."}
              </p>
            ) : null}
            {d.place === "current" && !locating ? <Button type="button" variant="outline" size="sm" onClick={locate}>Actualizar mi ubicación</Button> : null}
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
            <CardTitle>Alertas</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">Frecuencia</legend>
              <Segmented
                name={fid("notification_frequency")}
                value={d.notification_frequency}
                onChange={(v) => set("notification_frequency", v as Draft["notification_frequency"])}
                options={[
                  { value: "immediate", label: FREQUENCY.immediate.label },
                  { value: "daily", label: FREQUENCY.daily.label },
                ]}
              />
              <p className="text-xs text-muted-foreground">{FREQUENCY[d.notification_frequency].hint}</p>
            </fieldset>
            <Field id={fid("notify_min_level")} label="Avisarme de">
              <NativeSelect
                id={fid("notify_min_level")}
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
            <Field id={fid("name")} label="Nombre de la búsqueda" className="sm:col-span-2">
              <Input
                id={fid("name")}
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
          locationRequired={!locationReady}
        />
        {errors.error ? (
          <p role="alert" className="text-sm text-destructive">
            {errors.error}
          </p>
        ) : null}
        <Button type="submit" className="h-11 w-full text-base" disabled={saving || locating}>
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
  locationRequired,
}: {
  preview: Preview | null;
  loading: boolean;
  failed: boolean;
  ready: boolean;
  locationRequired: boolean;
}) {
  return (
    <Card size="sm" aria-live="polite">
      <CardContent className="space-y-3">
        {!ready ? (
          <p className="text-sm text-muted-foreground">Elegí marca y modelo para ver cuántas publicaciones coinciden hoy.</p>
        ) : locationRequired ? (
          <p className="text-sm text-muted-foreground">Elegí una ubicación para contar las publicaciones cercanas.</p>
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
