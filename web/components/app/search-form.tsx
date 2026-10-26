"use client";

import { ChevronDown, Info, Loader2, LocateFixed, Plus, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState, useTransition } from "react";

import { type SaveOrigin, saveSearch } from "@/app/app/searches/actions";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import type { Catalog } from "@/lib/catalog";
import { BODY_TYPE, BODY_TYPE_CODES, type BodyType, FREQUENCY, FUEL, MIN_LEVEL_OPTIONS, SELLER, TRANSMISSION, isBodyType } from "@/lib/copy";
import { number } from "@/lib/format";
import { PROVINCES, citiesInProvince, cityById, cityByLocation } from "@/lib/argentina-locations";
import {
  MODEL_LESS_UNAVAILABLE,
  MODEL_LESS_UPSELL,
  type SearchInput,
  type SearchValues,
  defaultName,
  isModelLess,
  modelBodyTypes,
  selectedTrims,
} from "@/lib/search-form";
import { locationCapText } from "@/lib/pro";
import { cn } from "@/lib/utils";
import { analyticsEvent } from "@/lib/google-analytics";
import { detectDeviceLocation, type DetectedLocation } from "@/lib/search-location";

type Source = { id: string; name: string };

/** The localities of a province as select options; the department tells apart the ones that share a name. */
function cityOptions(provinceId: string) {
  const cities = citiesInProvince(provinceId);
  const counts = new Map<string, number>();
  for (const c of cities) counts.set(c.city, (counts.get(c.city) ?? 0) + 1);
  return cities.map((c) => (
    <NativeSelectOption key={c.id} value={c.id}>{c.city}{(counts.get(c.city) ?? 0) > 1 ? ` (${c.department})` : ""}</NativeSelectOption>
  ));
}

/** One city of a manual place with its own radius; `fixed` is a saved place that isn't in the city list. */
type Zone = { key: number; province: string; city: string; radius: string; fixed: { label: string; lat: number; lon: number } | null };
let zoneKeys = 0;
const newZone = (init: Partial<Zone> = {}): Zone => ({ key: ++zoneKeys, province: "", city: "", radius: "30", fixed: null, ...init });
const zoneReady = (z: Zone) => z.fixed != null || z.city !== "";

type Draft = {
  name: string;
  nameTouched: boolean;
  /** "model": make and model; "body": body types only, no model (model_less_search). */
  mode: "model" | "body";
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
  /** In "model" mode only the ones the model offers count (toInput); the rest wait for another model. */
  body_types: BodyType[];
  sources: string[];
  /** "" = todo el país; "current" = the device's location; "manual" = cities picked by hand (zones). */
  place: "" | "current" | "manual";
  /** The radius around the current location. */
  radius: string;
  current: DetectedLocation | null;
  /** The cities of a manual place: the first is the search's own place, the others are added to it. */
  zones: Zone[];
  km_target: string;
  price_target: string;
  seller_type: "" | "private" | "dealer";
  notification_frequency: "immediate" | "daily";
  notify_min_level: SearchValues["notify_min_level"];
  opportunity_threshold_pct: string;
};

/** "11.500" or "11500" → 11500; "" → null; anything else (signs, decimals, "1e9", letters) → NaN, rejected by checkNumbers. */
function amount(text: string): number | null {
  const clean = text.trim().replace(/\s/g, "");
  if (!clean) return null;
  return /^(\d{1,3}(\.\d{3})+|\d+)$/.test(clean) ? Number(clean.replace(/\./g, "")) : NaN;
}

const WHOLE_NUMBER = "Escribí solo números enteros, sin comas ni decimales (por ejemplo: 11500).";

/** The form's own checks, in Spanish and all at once, before the server sees the input. */
function checkNumbers(input: SearchInput, d: Draft): Record<string, string> {
  const fields: Record<string, string> = {};
  const bad = (n: number | null | undefined) => n != null && !Number.isFinite(n);
  for (const key of ["km_max", "km_target", "price_max", "price_target"] as const) {
    if (bad(input[key])) fields[key] = WHOLE_NUMBER;
  }
  if (!fields.km_max && input.km_max != null && input.km_max > 2_000_000) fields.km_max = "Poné hasta 2.000.000 km.";
  if (!fields.km_target && input.km_target != null && input.km_target > 2_000_000) fields.km_target = "Poné hasta 2.000.000 km.";
  if (!fields.price_target && !fields.price_max && input.price_target != null && input.price_max != null && input.price_target > input.price_max) {
    fields.price_target = "El precio ideal no puede ser mayor que el máximo.";
  }
  if (!fields.km_target && !fields.km_max && input.km_target != null && input.km_max != null && input.km_target > input.km_max) {
    fields.km_target = "El kilometraje ideal no puede ser mayor que el máximo.";
  }
  if (input.year_min != null && input.year_max != null && input.year_min > input.year_max) {
    fields.year_max = "El año «desde» no puede ser mayor que el «hasta».";
  }
  const radii = d.place === "current" ? [d.radius] : d.place === "manual" ? d.zones.map((z) => z.radius) : [];
  for (const text of radii) {
    const radius = amount(text);
    if (radius == null || !Number.isFinite(radius)) fields.location = "Escribí el radio en kilómetros, sin decimales (por ejemplo: 30).";
    else if (radius <= 0) fields.location = "El radio tiene que ser mayor a 0.";
    else if (radius > 3000) fields.location = "Poné un radio de hasta 3.000 km.";
    if (fields.location) break;
  }
  return fields;
}

/** "10" → 10; "7,5" → 7.5 (the schema refuses it: whole percents only); "" → null. */
function percentInput(text: string): number | null {
  const clean = text.trim().replace("%", "").replace(",", ".");
  return clean ? Number(clean) : null;
}

/** A new search starts with an approximate zone, refined silently if permission exists. */
function draftFrom(
  v: SearchValues,
  isNew: boolean,
  approximateLocation: DetectedLocation | null = null,
  mode: Draft["mode"] = "model",
): Draft {
  // A saved place is shown as cities: the ones of the list pick their province and city; any other stays as it is.
  const zones = v.location
    ? [v.location, ...v.extra_locations].map((p) => {
        const locality = cityByLocation(p);
        return newZone({ radius: String(p.radius_km), ...(locality ? { province: locality.provinceId, city: locality.id } : { fixed: { label: p.label, lat: p.lat, lon: p.lon } }) });
      })
    : [];
  const place: Draft["place"] = v.location ? "manual" : isNew ? "current" : "";
  return {
    name: v.name,
    nameTouched: Boolean(v.name) && v.name !== defaultName(v),
    mode,
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
    body_types: v.body_types,
    sources: v.sources,
    place,
    radius: isNew ? "30" : "",
    current: isNew ? approximateLocation : null,
    zones,
    km_target: v.km_target != null ? number(v.km_target) : "",
    price_target: v.price_target != null ? number(v.price_target) : "",
    seller_type: v.seller_type,
    notification_frequency: v.notification_frequency,
    notify_min_level: v.notify_min_level,
    opportunity_threshold_pct: v.opportunity_threshold_pct?.toString() ?? "",
  };
}

/** The place the draft describes: its own and the ones added to it ("Chaco o Corrientes"). */
function places(d: Draft): { location: SearchInput["location"]; extra_locations: NonNullable<SearchInput["extra_locations"]> } {
  if (d.place === "current" && d.current) {
    const { label, lat, lon } = d.current;
    // Whole km, dots as thousands like every other number here ("3.000" is 3000 km, not 3).
    return { location: { label, lat, lon, radius_km: amount(d.radius) ?? NaN }, extra_locations: [] };
  }
  if (d.place !== "manual") return { location: null, extra_locations: [] };
  const found: NonNullable<SearchInput["extra_locations"]> = [];
  for (const z of d.zones) {
    const city = z.fixed ? null : cityById(z.city);
    const at = z.fixed ?? (city ? { label: city.label, lat: city.lat, lon: city.lon } : null);
    if (at && !found.some((f) => f.lat === at.lat && f.lon === at.lon)) found.push({ ...at, radius_km: amount(z.radius) ?? NaN });
  }
  return { location: found[0] ?? null, extra_locations: found.slice(1) };
}

/** `offered`: the body types the chosen model offers (modelBodyTypes). */
function toInput(d: Draft, offered: readonly string[]): SearchInput {
  const byBody = d.mode === "body";
  return {
    name: d.nameTouched ? d.name : "",
    make: byBody ? "" : d.make,
    model: byBody ? "" : d.model,
    trim: byBody ? "" : d.trim,
    trims: byBody ? [] : d.trims,
    trim_strict: byBody ? false : d.trim_strict,
    year_min: amount(d.year_min),
    year_max: amount(d.year_max),
    price_max: amount(d.price_max),
    currency: d.currency,
    km_max: amount(d.km_max),
    transmission: d.transmission,
    fuel: d.fuel,
    body_types: byBody ? d.body_types : d.body_types.filter((code) => offered.includes(code)),
    sources: d.sources,
    ...places(d),
    km_target: amount(d.km_target),
    price_target: amount(d.price_target),
    seller_type: d.seller_type,
    notification_frequency: d.notification_frequency,
    notify_min_level: d.notify_min_level,
    opportunity_threshold_pct: percentInput(d.opportunity_threshold_pct),
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
  approximateLocation = null,
  modelLessSearch = false,
  maxLocations = null,
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
  approximateLocation?: DetectedLocation | null;
  /** The plan can search by body type without a model (Particular, Pro; docs/CARROCERIA.md). */
  modelLessSearch?: boolean;
  /** Places one search may look in, its own included (the plan's cap); null = no cap. */
  maxLocations?: number | null;
}) {
  const fid = (key: string) => (idPrefix ? `${idPrefix}-${key}` : key);
  const isNew = profileId == null && !initial.location;
  const offeredBy = (make: string, model: string) =>
    modelBodyTypes(catalog.find((m) => m.make === make)?.models.find((m) => m.model === model)?.bodyTypes);
  // A model-less proposal opens by body type when the plan has it; without
  // it, by model with its body types kept to preselect. A saved model-less
  // search always opens by body type, locked if the account lost the feature.
  const savedModelLess = isModelLess(initial) && initial.body_types.length > 0;
  const showModes = modelLessSearch || (profileId != null && savedModelLess);
  const initialMode: Draft["mode"] = savedModelLess && showModes ? "body" : "model";
  const [d, setDraft] = useState<Draft>(() => draftFrom(initial, isNew, approximateLocation, initialMode));
  const [versionText, setVersionText] = useState("");
  // With catalog versions, the free-text field hides until asked for from the menu.
  const [otherVersion, setOtherVersion] = useState(false);
  // The proposal as it arrived, to record whether the user corrected it.
  const [pristine] = useState(() =>
    JSON.stringify(toInput(draftFrom(initial, isNew, null, initialMode), offeredBy(initial.make, initial.model))));
  // Until the user picks a zone, the location filled in on mount isn't a correction.
  const placeTouched = useRef(false);
  const formRef = useRef<HTMLFormElement>(null);
  const locationRequest = useRef(0);
  const [errors, setErrors] = useState<{ error?: string; fields?: Record<string, string> }>({});
  const [saving, startSaving] = useTransition();
  const [locating, setLocating] = useState(false);
  const [locationNotice, setLocationNotice] = useState("");

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((prev) => ({ ...prev, [key]: value }));

  const byBody = d.mode === "body";
  // By body type without the plan feature: shown, but it can't be saved.
  const locked = byBody && !modelLessSearch;
  const models = useMemo(() => catalog.find((m) => m.make === d.make)?.models ?? [], [catalog, d.make]);
  const entry = byBody ? undefined : models.find((m) => m.model === d.model);
  const offered = useMemo(() => modelBodyTypes(entry?.bodyTypes), [entry]);
  const years = useMemo(() => {
    const from = Math.max(entry?.yearFrom ?? 1990, 1990);
    const to = Math.min(entry?.yearTo ?? THIS_YEAR, THIS_YEAR);
    return Array.from({ length: Math.max(to - from + 1, 0) }, (_, i) => to - i);
  }, [entry]);
  const fuels = entry?.fuels.length ? entry.fuels : Object.keys(FUEL);
  const pendingVersion = versionText.trim();
  const zonesCapText = locationCapText(maxLocations);
  const zonesFull = maxLocations != null && d.zones.length >= maxLocations;
  const updateZone = (key: number, patch: Partial<Zone>) => {
    placeTouched.current = true;
    setErrors({});
    setDraft((prev) => ({ ...prev, zones: prev.zones.map((z) => (z.key === key ? { ...z, ...patch } : z)) }));
  };
  const removeZone = (key: number) => {
    placeTouched.current = true;
    setDraft((prev) => ({ ...prev, zones: prev.zones.length > 1 ? prev.zones.filter((z) => z.key !== key) : prev.zones }));
  };
  const addZone = () => {
    placeTouched.current = true;
    setDraft((prev) => ({ ...prev, zones: [...prev.zones, newZone({ radius: prev.zones.at(-1)?.radius || "30" })] }));
  };

  const input = useMemo(
    () => toInput({ ...d, trims: [...new Set([...d.trims, versionText.trim()].filter(Boolean))] }, offered),
    [d, versionText, offered],
  );
  const autoName = defaultName(input);
  const locationReady = d.place === "current" ? Boolean(d.current) : d.place === "manual" ? d.zones.length > 0 && d.zones.every(zoneReady) : true;

  function chooseMake(make: string) {
    setVersionText("");
    setOtherVersion(false);
    setDraft((prev) => ({ ...prev, make, model: "", trim: "", trims: [], trim_strict: false, fuel: "" }));
  }

  function chooseModel(model: string) {
    setVersionText("");
    setOtherVersion(false);
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
    setOtherVersion(false);
  }

  function choosePlace(choice: Draft["place"]) {
    placeTouched.current = true;
    locationRequest.current += 1;
    setLocating(false);
    setLocationNotice("");
    setErrors({});
    setDraft((prev) => ({
      ...prev,
      place: choice,
      radius: prev.radius || "30",
      zones: choice === "manual" && !prev.zones.length ? [newZone()] : prev.zones,
    }));
    if (choice === "current" && !d.current) void locate(true);
  }

  async function locate(requestPermission = false) {
    const request = ++locationRequest.current;
    setLocationNotice("");
    setErrors((prev) => ({ ...prev, fields: { ...prev.fields, location: "" } }));
    setLocating(true);
    const result = await detectDeviceLocation(requestPermission);
    if (request !== locationRequest.current) return;
    setLocating(false);
    if (result.location) {
      setDraft((prev) => prev.place === "current" ? { ...prev, current: result.location, radius: prev.radius || "30" } : prev);
      return;
    }
    // Keep an available zone after a failed refresh; never widen the search silently.
    if (!requestPermission && d.current && (result.reason === "permission" || result.reason === "denied")) return;
    const notices = {
      permission: "Podés usar la zona aproximada o permitir la ubicación del dispositivo para ajustarla.",
      denied: "El navegador bloqueó la ubicación del dispositivo. Podés continuar con la zona aproximada o elegir otra ciudad.",
      timeout: "La ubicación del dispositivo está tardando. Conservamos la zona disponible; también podés elegir otra ciudad.",
      unavailable: "No pudimos leer la ubicación del dispositivo. Conservamos la zona disponible; también podés elegir otra ciudad.",
    };
    if (!d.current && !requestPermission && !placeTouched.current) {
      // Nothing detected on open: ask for the place instead of starting in an error.
      setDraft((prev) => prev.place === "current" ? { ...prev, place: "manual", zones: prev.zones.length ? prev.zones : [newZone()] } : prev);
      setLocationNotice("Elegí dónde buscar: tu ubicación actual, una o más ciudades, o todo el país.");
      return;
    }
    setLocationNotice(d.current ? notices[result.reason] : "No pudimos detectar tu zona. Elegí una ubicación manual o usá la ubicación del dispositivo.");
  }

  useEffect(() => {
    if (isNew && d.place === "current") void locate();
    return () => { locationRequest.current += 1; };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once, when a new search opens
  }, []);

  function chooseMode(mode: string) {
    setErrors({});
    set("mode", mode === "body" ? "body" : "model");
  }

  function toggleBodyType(code: string, on: boolean) {
    if (!isBodyType(code)) return;
    setDraft((prev) => ({
      ...prev,
      body_types: on ? [...new Set([...prev.body_types, code])] : prev.body_types.filter((c) => c !== code),
    }));
  }

  function toggleSource(id: string, on: boolean) {
    setDraft((prev) => ({
      ...prev,
      sources: on ? [...new Set([...prev.sources, id])] : prev.sources.filter((s) => s !== id),
    }));
  }

  /** Shows the errors and takes the user to the first one: a submit that seems to do nothing is the worst outcome. */
  function showErrors(next: { error?: string; fields?: Record<string, string> }) {
    setErrors(next);
    window.requestAnimationFrame(() => {
      const alert = formRef.current?.querySelector<HTMLElement>("[role=alert]");
      if (!alert) return;
      alert.scrollIntoView({ behavior: "smooth", block: "center" });
      alert.parentElement?.querySelector<HTMLElement>("input, select, button")?.focus({ preventScroll: true });
    });
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setErrors({});
    if (locked) {
      showErrors({ error: MODEL_LESS_UNAVAILABLE });
      return;
    }
    const fields = checkNumbers(input, d);
    if (!byBody && !input.make) fields.make = "Elegí una marca.";
    if (!byBody && input.make && !input.model) fields.model = "Elegí un modelo.";
    if (byBody && !input.body_types?.length) fields.body_types = "Elegí al menos una carrocería.";
    if (byBody && input.price_max == null && !fields.price_max) fields.price_max = "Poné un precio máximo para buscar por carrocería.";
    if (!locationReady) fields.location = d.place === "manual" ? "Elegí la provincia y la localidad de cada zona, o quitá la que sobre." : "Elegí dónde buscar: tu ubicación actual, una o más ciudades, o todo el país.";
    if (Object.keys(fields).length) {
      showErrors({ fields });
      return;
    }
    locationRequest.current += 1;
    setLocating(false);
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
      if (result?.error) showErrors(result);
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
    <form ref={formRef} onSubmit={submit} noValidate className="grid gap-5">
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
        {showModes ? (
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Buscar por</legend>
            <Segmented
              name={fid("mode")}
              value={d.mode}
              onChange={chooseMode}
              options={[
                { value: "model", label: "Modelo" },
                { value: "body", label: "Carrocería" },
              ]}
            />
          </fieldset>
        ) : null}
        <Card>
          <CardHeader>
            <CardTitle>Vehículo</CardTitle>
            <CardDescription>
              {byBody
                ? "Buscamos autos de cualquier marca y modelo con estas carrocerías, hasta el precio máximo que pongas."
                : "Podés incluir varias versiones del mismo modelo. Cada modelo distinto tiene su propia búsqueda."}
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            {byBody ? (
              <fieldset className="space-y-2 sm:col-span-2" disabled={locked}>
                <legend className="text-sm font-medium">Carrocería</legend>
                <ChipToggles
                  name={fid("body_types")}
                  value={d.body_types}
                  onToggle={toggleBodyType}
                  options={BODY_TYPE_CODES.map((code) => ({ value: code, label: BODY_TYPE[code] }))}
                />
                {locked ? (
                  <p className="text-sm">
                    {MODEL_LESS_UNAVAILABLE}{" "}
                    <Link href="/app/pro" className="font-medium underline underline-offset-3">Ver planes</Link>
                  </p>
                ) : (
                  <p className="text-xs text-muted-foreground">Elegí una o más. Necesita un precio máximo.</p>
                )}
                {fieldError("body_types")}
              </fieldset>
            ) : (
            <>
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
                // An assisted draft with the make but no model ("No encontramos «Chery Arrizo 8»"): the model is what's left.
                autoFocus={origin?.mode === "assisted" && Boolean(initial.make) && !initial.model}
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
                <DropdownMenu modal={false}>
                  <DropdownMenuTrigger asChild>
                    <Button id={fid("trim")} type="button" variant="outline" className="w-full justify-between font-normal">
                      <span className="truncate">{d.trims.length === 0 ? "Todas las versiones" : d.trims.length === 1 ? "1 versión elegida" : `${d.trims.length} versiones elegidas`}</span>
                      <ChevronDown className="size-4 opacity-50" aria-hidden />
                    </Button>
                  </DropdownMenuTrigger>
                  {/* Focus goes to the free-text field when it was asked for, not back to the trigger. */}
                  <DropdownMenuContent className="max-h-72" onCloseAutoFocus={(e) => { if (otherVersion) e.preventDefault(); }}>
                    {[...new Set([...entry.trims, ...d.trims])].map((t) => (
                      <DropdownMenuCheckboxItem
                        key={t}
                        checked={d.trims.includes(t)}
                        onCheckedChange={(on) => chooseTrim(t, on === true)}
                        // Stay open: several versions are picked in one go.
                        onSelect={(e) => e.preventDefault()}
                      >
                        {t}
                      </DropdownMenuCheckboxItem>
                    ))}
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onSelect={() => setOtherVersion(true)}>Escribir otra versión…</DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : null}
              {/* Listings carry versions the catalog doesn't (and some models have none). */}
              {!entry?.trims.length || otherVersion ? (
              <div className="flex gap-2">
                <Input
                  id={entry?.trims.length ? fid("trim_other") : fid("trim")}
                  autoFocus={otherVersion}
                  aria-label={entry?.trims.length ? "Otra versión" : undefined}
                  value={versionText}
                  onChange={(e) => setVersionText(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addFreeVersion(); } }}
                  placeholder="Ej.: Highline"
                  maxLength={60}
                  disabled={!d.model}
                />
                <Button type="button" variant="outline" onClick={addFreeVersion} disabled={!d.model || !pendingVersion}>Agregar versión</Button>
              </div>
              ) : null}
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
            {offered.length ? (
              <fieldset className="space-y-2 sm:col-span-2">
                <legend className="text-sm font-medium">
                  Carrocería <span className="font-normal text-muted-foreground">· Opcional</span>
                </legend>
                <ChipToggles
                  name={fid("body_types")}
                  value={d.body_types}
                  onToggle={toggleBodyType}
                  options={offered.map((code) => ({ value: code, label: BODY_TYPE[code] }))}
                />
                <p className="text-xs text-muted-foreground">Sin carrocería elegida, buscamos todas las del modelo.</p>
                {fieldError("body_types")}
              </fieldset>
            ) : null}
            </>
            )}
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
                onBlur={() => Number.isFinite(amount(d.km_max)) && set("km_max", number(amount(d.km_max)!))}
                placeholder="Sin límite (ej.: 150.000)"
              />
            </Field>
            <details className="space-y-2 text-sm" open={d.km_target ? true : undefined}>
              <summary className="cursor-pointer text-muted-foreground">Kilometraje ideal (opcional)</summary>
              <Field id={fid("km_target")} label="Kilometraje ideal" error={fieldError("km_target")}>
                <Input id={fid("km_target")} inputMode="numeric" value={d.km_target} onChange={(e) => set("km_target", e.target.value)} placeholder="Ej.: 120.000" />
              </Field>
              <p className="text-xs text-muted-foreground">Prioriza publicaciones; no las descarta.</p>
            </details>
          </CardContent>
        </Card>
        {!modelLessSearch && !locked ? (
          <p data-testid="model-less-upsell" className="text-sm text-muted-foreground">
            {MODEL_LESS_UPSELL}{" "}
            <Link href="/app/pro" className="font-medium underline underline-offset-3">Ver planes</Link>
          </p>
        ) : null}

        <Card>
          <CardHeader>
            <CardTitle>Precio</CardTitle>
            <CardDescription>
              Comparamos en la misma moneda: una publicación en pesos se convierte a dólares si tu tope está en dólares.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <Field id={fid("price_max")} label="Precio máximo" hint={byBody ? "Obligatorio" : undefined} error={fieldError("price_max")}>
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
                  onBlur={() => Number.isFinite(amount(d.price_max)) && set("price_max", number(amount(d.price_max)!))}
                  placeholder={byBody ? (d.currency === "USD" ? "Ej.: 11.500" : "Ej.: 15.000.000") : d.currency === "USD" ? "Sin límite (ej.: 11.500)" : "Sin límite (ej.: 15.000.000)"}
                  required={byBody}
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
                  placeholder={d.currency === "USD" ? "Ej.: 10.500" : "Ej.: 14.000.000"}
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
            <fieldset className="space-y-2 sm:col-span-2">
              <legend className="text-sm font-medium">Buscar cerca de</legend>
              <Segmented
                name={fid("place")}
                value={d.place}
                onChange={(v) => choosePlace(v === "current" || v === "manual" ? v : "")}
                variant="chips"
                options={[
                  { value: "current", label: "Mi ubicación actual" },
                  { value: "manual", label: "Ubicación manual" },
                  { value: "", label: "Todo el país" },
                ]}
              />
              {fieldError("location")}
            </fieldset>
            {d.place === "manual" ? (
              <div className="space-y-3 sm:col-span-2">
                {d.zones.map((z, i) => (
                  <div key={z.key} className="grid gap-3 sm:grid-cols-[1fr_1fr_6.5rem_auto] sm:items-end">
                    {z.fixed ? (
                      <div className="sm:col-span-2">
                        <p className="text-sm font-medium">{z.fixed.label}</p>
                        <p className="text-xs text-muted-foreground">Ubicación guardada en esta búsqueda.</p>
                      </div>
                    ) : (
                      <>
                        <Field id={fid(`province-${z.key}`)} label={i === 0 ? "Provincia" : `Provincia ${i + 1}`}>
                          <NativeSelect id={fid(`province-${z.key}`)} value={z.province} onChange={(e) => updateZone(z.key, { province: e.target.value, city: "" })} className="w-full">
                            <NativeSelectOption value="">Elegí una provincia</NativeSelectOption>
                            {PROVINCES.map((p) => <NativeSelectOption key={p.id} value={p.id}>{p.label}</NativeSelectOption>)}
                          </NativeSelect>
                        </Field>
                        <Field id={fid(`city-${z.key}`)} label={i === 0 ? "Localidad" : `Localidad ${i + 1}`}>
                          <NativeSelect id={fid(`city-${z.key}`)} value={z.city} onChange={(e) => updateZone(z.key, { city: e.target.value })} className="w-full" disabled={!z.province}>
                            <NativeSelectOption value="">{z.province ? "Elegí una localidad" : "Primero elegí la provincia"}</NativeSelectOption>
                            {cityOptions(z.province)}
                          </NativeSelect>
                        </Field>
                      </>
                    )}
                    <Field id={fid(`radius-${z.key}`)} label="Radio (km)">
                      <Input id={fid(`radius-${z.key}`)} inputMode="numeric" value={z.radius} onChange={(e) => updateZone(z.key, { radius: e.target.value })} />
                    </Field>
                    {d.zones.length > 1 ? (
                      <Button type="button" variant="ghost" size="icon" aria-label={`Quitar la zona ${i + 1}`} onClick={() => removeZone(z.key)}>
                        <X aria-hidden />
                      </Button>
                    ) : null}
                  </div>
                ))}
                <div className="flex flex-wrap items-center gap-3">
                  <Button type="button" variant="outline" size="sm" disabled={zonesFull} onClick={addZone}>
                    <Plus aria-hidden /> Agregar otra ciudad
                  </Button>
                  <p className="text-xs text-muted-foreground">
                    Buscamos publicaciones en cualquiera de las ciudades, cada una con su radio.{zonesCapText ? ` ${zonesCapText}` : ""}
                  </p>
                </div>
              </div>
            ) : null}
            {d.place === "current" ? (
              <>
                <Field id={fid("radius")} label="Radio (km)">
                  <Input id={fid("radius")} inputMode="numeric" value={d.radius} onChange={(e) => set("radius", e.target.value)} />
                </Field>
                <p role="status" className="flex items-center gap-1.5 text-xs text-muted-foreground sm:col-span-2">
                  <LocateFixed className="size-3.5" aria-hidden />
                  {locating
                    ? d.current ? "Podés continuar con esta zona mientras ajustamos la ubicación…" : "Buscando tu ubicación… Si hay un fallo temporal, reintentamos automáticamente."
                    : d.current
                      ? d.current.approximate ? `Zona aproximada por tu conexión: ${d.current.label}. Podés cambiarla si no coincide.` : "Ubicación detectada. Usamos este punto como centro del radio."
                      : "Usá la ubicación del dispositivo o elegí una ciudad."}
                </p>
              </>
            ) : null}
            {locationNotice ? <p role="status" className="text-xs text-muted-foreground sm:col-span-2">{locationNotice}</p> : null}
            {d.place === "current" ? (
              <Button type="button" variant="outline" size="sm" disabled={locating} onClick={() => {
                placeTouched.current = true;
                set("place", "current");
                void locate(true);
              }}>
                <LocateFixed aria-hidden /> {d.current && !d.current.approximate ? "Actualizar mi ubicación" : "Usar ubicación del dispositivo"}
              </Button>
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
                placeholder={byBody ? "Ej.: SUV para la familia" : "Ej.: Fiesta Titanium"}
                maxLength={80}
              />
            </Field>
          </CardContent>
        </Card>
      </div>

      <div className="mx-auto w-full max-w-md space-y-3 pb-4 text-center">
        {locked && !errors.error ? <p className="text-sm text-destructive">{MODEL_LESS_UNAVAILABLE}</p> : null}
        {errors.error ? (
          <p role="alert" className="text-sm text-destructive">
            {errors.error}
          </p>
        ) : null}
        <Button type="submit" className="h-11 w-full text-base" disabled={saving || locked || (locating && !locationReady)}>
          {saving ? <Loader2 className="animate-spin" aria-hidden /> : null}
          {profileId ? "Guardar cambios" : "Crear búsqueda"}
        </Button>
        <p className="text-xs text-muted-foreground">
          Al guardar buscamos coincidencias entre las publicaciones de los últimos 30 días. Esas no se notifican: las
          ves acá. Desde entonces te avisamos de las nuevas.
        </p>
      </div>
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
  variant = "segmented",
}: {
  name: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  variant?: "segmented" | "chips";
}) {
  return (
    <div className={variant === "chips" ? "flex flex-wrap gap-2" : "inline-flex rounded-lg bg-muted p-0.5"}>
      {options.map((o) => (
        <label
          key={o.value || "any"}
          className={cn(
            "inline-flex min-h-11 cursor-pointer items-center px-3 py-1.5 text-sm md:min-h-0 has-focus-visible:ring-2 has-focus-visible:ring-ring",
            variant === "chips"
              ? "rounded-full border border-border text-muted-foreground hover:bg-muted"
              : "rounded-md text-muted-foreground",
            value === o.value && (variant === "chips"
              ? "border-primary bg-primary font-medium text-primary-foreground hover:bg-primary"
              : "bg-background font-medium text-foreground shadow-sm"),
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

/** Checkboxes that look like chips (native inputs: keyboard and screen readers work). Wraps on narrow screens. */
function ChipToggles({
  name,
  value,
  onToggle,
  options,
}: {
  name: string;
  value: readonly string[];
  onToggle: (value: string, on: boolean) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((o) => {
        const on = value.includes(o.value);
        return (
          <label
            key={o.value}
            className={cn(
              "inline-flex min-h-11 cursor-pointer items-center rounded-full border border-border px-3 py-1.5 text-sm md:min-h-0 text-muted-foreground hover:bg-muted has-focus-visible:ring-2 has-focus-visible:ring-ring has-disabled:cursor-not-allowed has-disabled:opacity-60",
              on && "border-primary bg-primary font-medium text-primary-foreground hover:bg-primary",
            )}
          >
            <input
              type="checkbox"
              name={name}
              value={o.value}
              checked={on}
              onChange={(e) => onToggle(o.value, e.target.checked)}
              className="sr-only"
            />
            {o.label}
          </label>
        );
      })}
    </div>
  );
}

