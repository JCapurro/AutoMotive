"use client";

import { ChevronDown, Info, Loader2, LocateFixed, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState, useTransition } from "react";

import { type Preview, type SaveOrigin, previewSearch, saveSearch } from "@/app/app/searches/actions";
import { RelaxSuggestions } from "@/components/app/relax-suggestions";
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
import { km, money, number, vehicle } from "@/lib/format";
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
import type { RelaxChange } from "@/lib/search-relax";
import type { SearchPlace } from "@/lib/types";
import { cn } from "@/lib/utils";
import { analyticsEvent } from "@/lib/google-analytics";
import { AMBA_RADIUS_KM } from "@/lib/assisted-fallback";
import { detectDeviceLocation, type DetectedLocation } from "@/lib/search-location";

type Source = { id: string; name: string };

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
  place: string; // "" (todo el país) | "city" | "current" | "saved"
  province: string;
  city: string;
  radius: string;
  /** Places added to the one above ("Chaco o Corrientes"); each keeps the radius it was added with. */
  extras: SearchPlace[];
  current: DetectedLocation | null;
  saved: { label: string; lat: number; lon: number } | null;
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
  if (d.place) {
    const radius = amount(d.radius);
    if (radius == null || !Number.isFinite(radius)) fields.location = "Escribí el radio en kilómetros, sin decimales (por ejemplo: 30).";
    else if (radius <= 0) fields.location = "El radio tiene que ser mayor a 0.";
    else if (radius > 3000) fields.location = "Poné un radio de hasta 3.000 km.";
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
    province,
    city,
    radius: v.location ? String(v.location.radius_km) : isNew ? "30" : "",
    extras: v.location ? v.extra_locations : [],
    current: isNew ? approximateLocation : null,
    saved,
    km_target: v.km_target != null ? number(v.km_target) : "",
    price_target: v.price_target != null ? number(v.price_target) : "",
    seller_type: v.seller_type,
    notification_frequency: v.notification_frequency,
    notify_min_level: v.notify_min_level,
    opportunity_threshold_pct: v.opportunity_threshold_pct?.toString() ?? "",
  };
}

function location(d: Draft): SearchInput["location"] {
  // Whole km, dots as thousands like every other number here ("3.000" is 3000 km, not 3).
  const radius_km = amount(d.radius) ?? NaN;
  if (d.place === "current" && d.current) {
    const { label, lat, lon } = d.current;
    return { label, lat, lon, radius_km };
  }
  if (d.place === "saved" && d.saved) return { ...d.saved, radius_km };
  if (d.place === "city") {
    const city = cityById(d.city);
    return city ? { label: city.label, lat: city.lat, lon: city.lon, radius_km } : null;
  }
  return null;
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
    location: location(d),
    extra_locations: d.place ? d.extras : [],
    km_target: amount(d.km_target),
    price_target: amount(d.price_target),
    seller_type: d.seller_type,
    notification_frequency: d.notification_frequency,
    notify_min_level: d.notify_min_level,
    opportunity_threshold_pct: percentInput(d.opportunity_threshold_pct),
  };
}

/** A zero-results hint (lib/search-relax.ts) applied to the fields; the place goes through choosePlace. */
function relaxDraft(d: Draft, c: RelaxChange): Draft {
  return {
    ...d,
    ...(c.trim_strict !== undefined ? { trim_strict: c.trim_strict } : {}),
    ...(c.year_min !== undefined ? { year_min: c.year_min?.toString() ?? "" } : {}),
    ...(c.year_max !== undefined ? { year_max: c.year_max?.toString() ?? "" } : {}),
    ...(c.price_max !== undefined ? { price_max: c.price_max != null ? number(c.price_max) : "" } : {}),
    ...(c.km_max !== undefined ? { km_max: c.km_max != null ? number(c.km_max) : "" } : {}),
    ...(c.transmission !== undefined ? { transmission: c.transmission } : {}),
    ...(c.fuel !== undefined ? { fuel: c.fuel } : {}),
    ...(c.body_types !== undefined ? { body_types: c.body_types } : {}),
  };
}

const THIS_YEAR = new Date().getFullYear();
const AMBA = "amba";
const isAmba = (d: Draft) => d.place === "city" && d.city === "caba" && d.radius === String(AMBA_RADIUS_KM);

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
  thresholdAlerts = false,
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
  /** The plan includes the opportunity threshold (Pro, 3.2). */
  thresholdAlerts?: boolean;
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
  // Tagged with the input it answers, so a stale count never shows for other filters.
  const [preview, setPreview] = useState<{ key: string; data: Preview | null } | null>(null);
  const [previewing, startPreview] = useTransition();
  const [locating, setLocating] = useState(false);
  const [locationNotice, setLocationNotice] = useState("");
  // The "Otras zonas" picker: a province and a locality, added with their own radius.
  const [addProvince, setAddProvince] = useState("");
  const [addCity, setAddCity] = useState("");

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((prev) => ({ ...prev, [key]: value }));

  const byBody = d.mode === "body";
  // By body type without the plan feature: shown, but it can't be saved.
  const locked = byBody && !modelLessSearch;
  const models = useMemo(() => catalog.find((m) => m.make === d.make)?.models ?? [], [catalog, d.make]);
  const entry = byBody ? undefined : models.find((m) => m.model === d.model);
  const offered = useMemo(() => modelBodyTypes(entry?.bodyTypes), [entry]);
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
  const addCities = useMemo(() => citiesInProvince(addProvince), [addProvince]);
  const addCityNames = useMemo(() => {
    const counts = new Map<string, number>();
    for (const city of addCities) counts.set(city.city, (counts.get(city.city) ?? 0) + 1);
    return counts;
  }, [addCities]);
  const zonesCapText = locationCapText(maxLocations);
  const zonesFull = maxLocations != null && 1 + d.extras.length >= maxLocations;
  function addZone() {
    const city = cityById(addCity);
    if (!city || zonesFull) return;
    const radius = amount(d.radius);
    const radius_km = radius != null && Number.isFinite(radius) && radius > 0 ? radius : city.radius;
    const same = (p: { lat: number; lon: number }) => p.lat === city.lat && p.lon === city.lon;
    const primary = location(d);
    if (d.extras.some(same) || (primary && same(primary))) {
      setLocationNotice(`${city.label} ya está entre las zonas.`);
      return;
    }
    setLocationNotice("");
    setDraft((prev) => ({ ...prev, extras: [...prev.extras, { label: city.label, lat: city.lat, lon: city.lon, radius_km }] }));
    setAddCity("");
  }

  const input = useMemo(
    () => toInput({ ...d, trims: [...new Set([...d.trims, versionText.trim()].filter(Boolean))] }, offered),
    [d, versionText, offered],
  );
  const autoName = defaultName(input);
  // By body type the search needs a max price (lib/search-form.ts): without
  // one previewSearch rejects the input, which isn't a failed count.
  const bodyNeedsPrice = byBody && input.price_max == null;
  const vehicleReady = byBody
    ? Boolean(input.body_types?.length) && !bodyNeedsPrice && !locked
    : Boolean(input.make && input.model);
  // Junk in a number field (checkNumbers) isn't a failed count: the preview waits for it to be fixed.
  const numbersOk = Object.keys(checkNumbers(input, d)).length === 0;
  const locationReady = !((d.place === "current" && !d.current) || (d.place === "city" && !d.city));
  const previewKey = JSON.stringify({ ...input, locationReady, name: "", notification_frequency: "", notify_min_level: "",
    opportunity_threshold_pct: null });

  useEffect(() => {
    if (!vehicleReady || !locationReady || !numbersOk) return;
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

  function choosePlace(choice: string) {
    placeTouched.current = true;
    locationRequest.current += 1;
    setLocating(false);
    setLocationNotice("");
    setErrors({});
    // AMBA: the city and its suburbs, as a manual place (CABA's center and a wide radius).
    const amba = choice === AMBA;
    const place = amba ? "city" : choice;
    setDraft((prev) => ({
      ...prev,
      place,
      ...(amba ? { province: "02", city: "caba" } : {}),
      radius: amba ? String(AMBA_RADIUS_KM) : prev.radius || "30",
    }));
    if (place === "current" && !d.current) void locate(true);
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
      setDraft((prev) => prev.place === "current" ? { ...prev, place: "city" } : prev);
      setLocationNotice("Elegí dónde buscar: AMBA, una provincia y localidad, o todo el país.");
      return;
    }
    setLocationNotice(d.current ? notices[result.reason] : "No pudimos detectar tu zona. Elegí AMBA, Ubicación manual o usá la ubicación del dispositivo.");
  }

  useEffect(() => {
    if (isNew && d.place === "current") void locate();
    return () => { locationRequest.current += 1; };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once, when a new search opens
  }, []);

  function applyRelax(change: RelaxChange) {
    setDraft((prev) => relaxDraft(prev, change));
    if (change.location === null) choosePlace("");
  }

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
    if (!locationReady) fields.location = "Elegí dónde buscar: AMBA, una provincia y localidad, o todo el país.";
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
    <form ref={formRef} onSubmit={submit} noValidate className="grid gap-5 lg:grid-cols-[1fr_300px] lg:items-start">
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
                value={isAmba(d) ? AMBA : d.place}
                onChange={choosePlace}
                variant="chips"
                options={[
                  { value: AMBA, label: "AMBA (CABA y alrededores)" },
                  { value: "current", label: "Mi ubicación actual" },
                  { value: "city", label: "Ubicación manual" },
                  { value: "", label: "Todo el país" },
                  ...(d.saved ? [{ value: "saved", label: "Ubicación guardada" }] : []),
                ]}
              />
              {fieldError("location")}
            </fieldset>
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
                <Field id={fid("city")} label="Localidad">
                  <NativeSelect id={fid("city")} value={d.city} onChange={(e) => {
                    placeTouched.current = true;
                    setErrors({});
                    set("city", e.target.value);
                  }} className="w-full" disabled={!d.province} required>
                    <NativeSelectOption value="">{d.province ? "Elegí una localidad" : "Primero elegí la provincia"}</NativeSelectOption>
                    {cities.map((city) => <NativeSelectOption key={city.id} value={city.id}>
                      {city.city}{(cityNames.get(city.city) ?? 0) > 1 ? ` (${city.department})` : ""}
                    </NativeSelectOption>)}
                  </NativeSelect>
                </Field>
              </>
            ) : null}
            {d.place ? (
              <Field id={fid("radius")} label="Radio (km)">
                <Input id={fid("radius")} inputMode="numeric" value={d.radius} onChange={(e) => set("radius", e.target.value)} />
              </Field>
            ) : null}
            {d.place === "current" ? (
              <p role="status" className="flex items-center gap-1.5 text-xs text-muted-foreground sm:col-span-2">
                <LocateFixed className="size-3.5" aria-hidden />
                {locating
                  ? d.current ? "Podés continuar con esta zona mientras ajustamos la ubicación…" : "Buscando tu ubicación… Si hay un fallo temporal, reintentamos automáticamente."
                  : d.current
                    ? d.current.approximate ? `Zona aproximada por tu conexión: ${d.current.label}. Podés cambiarla si no coincide.` : "Ubicación detectada. Usamos este punto como centro del radio."
                    : "Usá la ubicación del dispositivo o elegí una ciudad."}
              </p>
            ) : null}
            {d.place === "saved" && d.saved ? (
              <p className="text-xs text-muted-foreground sm:col-span-2">{d.saved.label}. Usamos la ubicación guardada en esta búsqueda.</p>
            ) : null}
            {d.place ? (
              <fieldset className="space-y-2 sm:col-span-2">
                <legend className="text-sm font-medium">Otras zonas (opcional)</legend>
                {d.extras.length ? (
                  <ul className="flex flex-wrap gap-2">
                    {d.extras.map((z, i) => (
                      <li key={`${z.lat},${z.lon}`} className="flex items-center gap-1 rounded-full border px-3 py-1 text-sm">
                        {z.label} · {number(z.radius_km)} km
                        <button
                          type="button"
                          aria-label={`Quitar ${z.label}`}
                          className="text-muted-foreground hover:text-foreground"
                          onClick={() => setDraft((prev) => ({ ...prev, extras: prev.extras.filter((_, j) => j !== i) }))}
                        >
                          <X className="size-3.5" aria-hidden />
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
                {zonesFull ? null : (
                  <div className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
                    <NativeSelect aria-label="Provincia de la otra zona" value={addProvince} onChange={(e) => { setAddProvince(e.target.value); setAddCity(""); }} className="w-full">
                      <NativeSelectOption value="">Provincia</NativeSelectOption>
                      {PROVINCES.map((p) => <NativeSelectOption key={p.id} value={p.id}>{p.label}</NativeSelectOption>)}
                    </NativeSelect>
                    <NativeSelect aria-label="Localidad de la otra zona" value={addCity} onChange={(e) => setAddCity(e.target.value)} className="w-full" disabled={!addProvince}>
                      <NativeSelectOption value="">{addProvince ? "Localidad" : "Primero la provincia"}</NativeSelectOption>
                      {addCities.map((city) => <NativeSelectOption key={city.id} value={city.id}>
                        {city.city}{(addCityNames.get(city.city) ?? 0) > 1 ? ` (${city.department})` : ""}
                      </NativeSelectOption>)}
                    </NativeSelect>
                    <Button type="button" variant="outline" disabled={!addCity} onClick={addZone}>Agregar zona</Button>
                  </div>
                )}
                <p className="text-xs text-muted-foreground">
                  Buscamos publicaciones en cualquiera de las zonas, cada una con su radio.{zonesCapText ? ` ${zonesCapText}` : ""}
                </p>
              </fieldset>
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
            {thresholdAlerts ? (
              <Field
                id={fid("opportunity_threshold_pct")}
                label="Umbral de oportunidad (opcional)"
                hint="Lo que llega a ese porcentaje te lo avisamos al instante, sin tope diario. El resto, y lo que no tiene comparables, va al resumen diario. Vacío: avisos inmediatos hasta el tope diario de tu plan."
                error={fieldError("opportunity_threshold_pct")}
                className="sm:col-span-2"
              >
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <span>Avisame al instante si está</span>
                  <Input
                    id={fid("opportunity_threshold_pct")}
                    value={d.opportunity_threshold_pct}
                    onChange={(e) => set("opportunity_threshold_pct", e.target.value)}
                    inputMode="numeric"
                    placeholder="10"
                    className="w-20"
                    aria-describedby={fid("opportunity_threshold_pct-unit")}
                  />
                  <span id={fid("opportunity_threshold_pct-unit")}>% o más por debajo de comparables</span>
                </div>
              </Field>
            ) : null}
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

      <aside className="space-y-3 lg:sticky lg:top-20">
        <PreviewCard
          preview={shownPreview}
          loading={previewing}
          failed={previewFailed}
          ready={vehicleReady && numbersOk}
          notReady={
            !numbersOk ? "Corregí los números marcados para contar las publicaciones."
            : locked
              ? "Para contar las publicaciones, elegí un modelo."
              : byBody
                ? input.body_types?.length
                  ? "Poné un precio máximo para ver cuántas publicaciones coinciden hoy."
                  : "Elegí al menos una carrocería para ver cuántas publicaciones coinciden hoy."
                : "Elegí marca y modelo para ver cuántas publicaciones coinciden hoy."
          }
          locationRequired={!locationReady}
          relax={byBody ? null : <RelaxSuggestions input={input} inputKey={previewKey} onApply={(s) => applyRelax(s.change)} />}
        />
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

function PreviewCard({
  preview,
  loading,
  failed,
  ready,
  notReady,
  locationRequired,
  relax,
}: {
  preview: Preview | null;
  loading: boolean;
  failed: boolean;
  ready: boolean;
  /** What to pick before there's something to count. */
  notReady: string;
  locationRequired: boolean;
  /** With a model, what to loosen when nothing matches (RelaxSuggestions). */
  relax?: React.ReactNode;
}) {
  return (
    <Card size="sm" aria-live="polite">
      <CardContent className="space-y-3">
        {!ready ? (
          <p className="text-sm text-muted-foreground">{notReady}</p>
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
                    <span className="truncate">
                      {vehicle(l)}
                      {isBodyType(l.body_type) ? <span className="text-muted-foreground"> · {BODY_TYPE[l.body_type]}</span> : null}
                    </span>
                    <span className="shrink-0 text-muted-foreground">
                      {[money(l.price, l.currency), km(l.mileage_km)].filter(Boolean).join(" · ")}
                    </span>
                  </li>
                ))}
              </ul>
            ) : preview.count === 0 && relax ? (
              relax
            ) : (
              <p className="text-xs text-muted-foreground">
                Hoy no hay ninguna publicada. Es normal con autos buscados: duran poco. Nosotros seguimos mirando y te
                escribimos cuando aparezca una.
              </p>
            )}
            {preview.count > 0 ? (
              <p className="text-xs text-muted-foreground">
                Lo importante es lo que se publique a partir de ahora: eso te lo avisamos apenas aparece.
              </p>
            ) : null}
            <p className="text-[11px] text-muted-foreground">
              Estimación con tus filtros; al guardar calculamos qué tan buena oportunidad es cada una.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
