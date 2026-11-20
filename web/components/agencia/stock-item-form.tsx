"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";

import { saveItem } from "@/app/agencia/actions";
import { PhotoUploader } from "@/components/agencia/photo-uploader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import type { Catalog } from "@/lib/catalog";
import { FUEL, TRANSMISSION } from "@/lib/copy";

export type ItemFormValues = {
  make: string;
  model: string;
  trim: string;
  year: string;
  mileageKm: string;
  price: string;
  currency: "ARS" | "USD";
  transmission: "" | "manual" | "automatic";
  fuel: string;
  color: string;
  inStockSince: string;
  title: string;
  description: string;
  images: string[];
};

export const EMPTY_ITEM: ItemFormValues = {
  make: "", model: "", trim: "", year: "", mileageKm: "", price: "", currency: "ARS", transmission: "", fuel: "", color: "",
  inStockSince: "", title: "", description: "", images: [],
};

/** Alta manual and edit of a car (spec §6.1): make, model and trim from the catalog; photos uploaded or by link. */
export function StockItemForm({ catalog, dealerId, itemId = null, initial = EMPTY_ITEM }: { catalog: Catalog; dealerId: number; itemId?: number | null; initial?: ItemFormValues }) {
  const router = useRouter();
  const [v, setV] = useState<ItemFormValues>(initial);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [pending, run] = useTransition();
  const make = useMemo(() => catalog.find((m) => m.make === v.make), [catalog, v.make]);
  const model = useMemo(() => make?.models.find((m) => m.model === v.model), [make, v.model]);
  const set = (patch: Partial<ItemFormValues>) => {
    setSaved(false);
    setV((prev) => ({ ...prev, ...patch }));
  };

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    run(async () => {
      try {
        const result = await saveItem(itemId, v);
        if (result.error) {
          setError(result.error);
          return;
        }
        setSaved(true);
        if (itemId === null && result.id) router.push(`/agencia/stock/${result.id}`);
        else router.refresh();
      } catch {
        setError("No pudimos guardar. Probá de nuevo.");
      }
    });
  }

  const current = new Date().getFullYear() + 1;
  return (
    <form onSubmit={submit} className="max-w-2xl space-y-4" data-testid="stock-item-form">
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Marca" id="item-make">
          <NativeSelect id="item-make" required value={v.make} onChange={(e) => set({ make: e.target.value, model: "", trim: "" })} className="w-full">
            <option value="">Elegí</option>
            {catalog.map((m) => <option key={m.make} value={m.make}>{m.make}</option>)}
          </NativeSelect>
        </Field>
        <Field label="Modelo" id="item-model">
          <NativeSelect id="item-model" required value={v.model} disabled={!make} onChange={(e) => set({ model: e.target.value, trim: "" })} className="w-full">
            <option value="">Elegí</option>
            {make?.models.map((m) => <option key={m.model} value={m.model}>{m.model}</option>)}
          </NativeSelect>
        </Field>
        <Field label="Versión" id="item-trim">
          <Input id="item-trim" list="item-trims" maxLength={80} value={v.trim} onChange={(e) => set({ trim: e.target.value })} />
          <datalist id="item-trims">{model?.trims.map((t) => <option key={t} value={t} />)}</datalist>
        </Field>
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Año" id="item-year">
          <Input id="item-year" required type="number" inputMode="numeric" min={1950} max={current} value={v.year} onChange={(e) => set({ year: e.target.value })} />
        </Field>
        <Field label="Km" id="item-km">
          <Input id="item-km" type="number" inputMode="numeric" min={0} max={2000000} value={v.mileageKm} onChange={(e) => set({ mileageKm: e.target.value })} />
        </Field>
        <Field label="Fecha de ingreso" id="item-since">
          <Input id="item-since" type="date" value={v.inStockSince} onChange={(e) => set({ inStockSince: e.target.value })} />
        </Field>
      </div>
      <div className="grid gap-4 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Field label="Precio de venta" id="item-price">
          <Input id="item-price" required type="number" inputMode="decimal" min={1} step="any" value={v.price} onChange={(e) => set({ price: e.target.value })} />
        </Field>
        <Field label="Moneda" id="item-currency">
          <NativeSelect id="item-currency" value={v.currency} onChange={(e) => set({ currency: e.target.value as "ARS" | "USD" })} className="w-full">
            <option value="ARS">Pesos</option>
            <option value="USD">Dólares</option>
          </NativeSelect>
        </Field>
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Caja" id="item-transmission">
          <NativeSelect id="item-transmission" value={v.transmission} onChange={(e) => set({ transmission: e.target.value as ItemFormValues["transmission"] })} className="w-full">
            <option value="">Sin dato</option>
            {Object.entries(TRANSMISSION).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
          </NativeSelect>
        </Field>
        <Field label="Combustible" id="item-fuel">
          <NativeSelect id="item-fuel" value={v.fuel} onChange={(e) => set({ fuel: e.target.value })} className="w-full">
            <option value="">Sin dato</option>
            {Object.entries(FUEL).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
          </NativeSelect>
        </Field>
        <Field label="Color" id="item-color">
          <Input id="item-color" maxLength={80} value={v.color} onChange={(e) => set({ color: e.target.value })} />
        </Field>
      </div>
      <Field label="Descripción (opcional)" id="item-description">
        <Textarea id="item-description" maxLength={4000} value={v.description} onChange={(e) => set({ description: e.target.value })} />
      </Field>
      <fieldset className="space-y-1.5">
        <legend className="text-sm font-medium">Fotos (hasta 10)</legend>
        <PhotoUploader dealerId={dealerId} value={v.images} onChange={(images) => set({ images })} />
      </fieldset>
      {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
      {saved && itemId !== null ? <p role="status" className="text-sm">Listo, guardamos el auto. Queda confirmado desde hoy.</p> : null}
      <Button type="submit" className="h-10" disabled={pending}>{pending ? "Guardando…" : itemId === null ? "Cargar auto" : "Guardar cambios"}</Button>
    </form>
  );
}

function Field({ label, id, children }: { label: string; id: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0 space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  );
}
