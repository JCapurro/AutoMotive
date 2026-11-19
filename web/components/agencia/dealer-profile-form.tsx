"use client";

import { Plus, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";

import { createDealer, updateDealer } from "@/app/agencia/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { citiesInProvince, cityByLocation, PROVINCES } from "@/lib/argentina-locations";

export type DealerFormValues = {
  name: string;
  locality: { label: string; lat: number; lon: number } | null;
  phone: string;
  whatsapp: string;
  contactEmail: string;
  addressText: string;
  links: { kind: LinkKind; url: string }[];
};
type LinkKind = "mercadolibre" | "facebook" | "instagram" | "web";

const LINK_LABEL: Record<LinkKind, string> = { mercadolibre: "Mercado Libre", facebook: "Facebook", instagram: "Instagram", web: "Sitio web" };

/** Alta (mode create) and «Datos» (mode update) of the agency: the same fields. */
export function DealerProfileForm({ mode, initial }: { mode: "create" | "update"; initial?: DealerFormValues }) {
  const router = useRouter();
  const start = initial?.locality ? cityByLocation(initial.locality) : undefined;
  const [name, setName] = useState(initial?.name ?? "");
  const [province, setProvince] = useState(start?.provinceId ?? "");
  const [cityId, setCityId] = useState(start?.id ?? "");
  const [phone, setPhone] = useState(initial?.phone ?? "");
  const [whatsapp, setWhatsapp] = useState(initial?.whatsapp ?? "");
  const [contactEmail, setContactEmail] = useState(initial?.contactEmail ?? "");
  const [addressText, setAddressText] = useState(initial?.addressText ?? "");
  const [links, setLinks] = useState(initial?.links ?? []);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [pending, run] = useTransition();
  const cities = useMemo(() => (province ? citiesInProvince(province) : []), [province]);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSaved(false);
    run(async () => {
      const input = { name, cityId, phone, whatsapp, contactEmail, addressText, links };
      try {
        const result = mode === "create" ? await createDealer(input) : await updateDealer(input);
        if (result.error) setError(result.error);
        else {
          setSaved(true);
          router.refresh();
        }
      } catch {
        setError("No pudimos guardar. Probá de nuevo.");
      }
    });
  }

  return (
    <form onSubmit={submit} className="max-w-xl space-y-4" data-testid={`dealer-form-${mode}`}>
      <div className="space-y-1.5">
        <Label htmlFor="dealer-name">Nombre de la agencia</Label>
        <Input id="dealer-name" required minLength={2} maxLength={80} value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <fieldset className="space-y-1.5">
        <legend className="text-sm font-medium">Dónde está</legend>
        <p className="text-xs text-muted-foreground">La usamos para medir la demanda de tu zona y la mostramos como la ubicación de tus autos. Si cambiás el nombre o la ubicación, volvemos a revisar tu agencia.</p>
        <div className="flex flex-wrap gap-2">
          <NativeSelect aria-label="Provincia" value={province} onChange={(e) => { setProvince(e.target.value); setCityId(""); }} className="min-w-48">
            <option value="">Provincia</option>
            {PROVINCES.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
          </NativeSelect>
          <NativeSelect aria-label="Localidad" value={cityId} onChange={(e) => setCityId(e.target.value)} disabled={!province} className="min-w-56">
            <option value="">Localidad</option>
            {cities.map((c) => <option key={c.id} value={c.id}>{c.city}{c.department ? ` (${c.department})` : ""}</option>)}
          </NativeSelect>
        </div>
      </fieldset>
      <div className="space-y-1.5">
        <Label htmlFor="dealer-address">Dirección (opcional)</Label>
        <Input id="dealer-address" maxLength={160} value={addressText} onChange={(e) => setAddressText(e.target.value)} />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="dealer-whatsapp">WhatsApp (opcional)</Label>
          <Input id="dealer-whatsapp" type="tel" inputMode="tel" placeholder="11 2345-6789" maxLength={40} value={whatsapp} onChange={(e) => setWhatsapp(e.target.value)} />
          <p className="text-xs text-muted-foreground">Con él, quien te pida contacto te puede escribir directo.</p>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="dealer-phone">Teléfono (opcional)</Label>
          <Input id="dealer-phone" type="tel" inputMode="tel" maxLength={40} value={phone} onChange={(e) => setPhone(e.target.value)} />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="dealer-email">Email para las consultas (opcional)</Label>
        <Input id="dealer-email" type="email" maxLength={200} value={contactEmail} onChange={(e) => setContactEmail(e.target.value)} />
        <p className="text-xs text-muted-foreground">Si lo dejás vacío, te avisamos al email de tu cuenta.</p>
      </div>
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Dónde publicás (opcional)</legend>
        {links.map((link, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2">
            <NativeSelect aria-label="Dónde" value={link.kind} onChange={(e) => setLinks(links.map((l, k) => (k === i ? { ...l, kind: e.target.value as LinkKind } : l)))}>
              {(Object.keys(LINK_LABEL) as LinkKind[]).map((k) => <option key={k} value={k}>{LINK_LABEL[k]}</option>)}
            </NativeSelect>
            <Input aria-label="Link" placeholder="https://" maxLength={300} value={link.url} className="min-w-0 flex-1"
              onChange={(e) => setLinks(links.map((l, k) => (k === i ? { ...l, url: e.target.value } : l)))} />
            <Button type="button" variant="ghost" size="icon" aria-label="Sacar link" onClick={() => setLinks(links.filter((_, k) => k !== i))}>
              <X aria-hidden />
            </Button>
          </div>
        ))}
        {links.length < 6 ? (
          <Button type="button" variant="outline" size="sm" onClick={() => setLinks([...links, { kind: "mercadolibre", url: "" }])}>
            <Plus aria-hidden /> Agregar link
          </Button>
        ) : null}
      </fieldset>
      {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
      {saved && mode === "update" ? <p role="status" className="text-sm">Listo, guardamos los datos.</p> : null}
      <Button type="submit" className="h-10" disabled={pending || !cityId || name.trim().length < 2}>
        {pending ? "Guardando…" : mode === "create" ? "Dar de alta mi agencia" : "Guardar"}
      </Button>
    </form>
  );
}
