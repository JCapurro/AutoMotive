"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { resolveDuplicate, saveItemPrivate } from "@/app/agencia/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";

/** «Lo que pagaste (solo lo ves vos)» and notes: dealer_item_private, read only by the agency's members. */
export function ItemPrivateForm({ itemId, initial }: { itemId: number; initial: { purchasePrice: string; purchaseCurrency: "" | "ARS" | "USD"; notes: string } }) {
  const router = useRouter();
  const [v, setV] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [pending, run] = useTransition();

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    run(async () => {
      const result = await saveItemPrivate(itemId, v).catch(() => ({ error: "No pudimos guardar. Probá de nuevo." }));
      if (result.error) setError(result.error);
      else {
        setSaved(true);
        router.refresh();
      }
    });
  }

  return (
    <form onSubmit={submit} className="max-w-xl space-y-3" data-testid="item-private-form">
      <div className="grid gap-3 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="space-y-1.5">
          <Label htmlFor="private-price">Lo que pagaste (solo lo ves vos)</Label>
          <Input id="private-price" type="number" inputMode="decimal" min={1} step="any" value={v.purchasePrice}
            onChange={(e) => { setSaved(false); setV({ ...v, purchasePrice: e.target.value }); }} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="private-currency">Moneda</Label>
          <NativeSelect id="private-currency" value={v.purchaseCurrency} className="w-full"
            onChange={(e) => { setSaved(false); setV({ ...v, purchaseCurrency: e.target.value as "" | "ARS" | "USD" }); }}>
            <option value="">—</option>
            <option value="ARS">Pesos</option>
            <option value="USD">Dólares</option>
          </NativeSelect>
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="private-notes">Notas</Label>
        <Textarea id="private-notes" maxLength={1000} value={v.notes} onChange={(e) => { setSaved(false); setV({ ...v, notes: e.target.value }); }} />
      </div>
      {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
      {saved ? <p role="status" className="text-sm">Listo, guardado.</p> : null}
      <Button type="submit" variant="outline" className="h-10" disabled={pending}>{pending ? "Guardando…" : "Guardar"}</Button>
    </form>
  );
}

/** «¿Es este aviso tuyo?»: the item looks like a listing we already read, from another seller account. */
export function ItemReview({ itemId, duplicate }: { itemId: number; duplicate: { title: string; source: string; url: string | null } | null }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [pending, run] = useTransition();

  function answer(mine: boolean) {
    setError(null);
    run(async () => {
      const result = await resolveDuplicate(itemId, mine).catch(() => ({ error: "No pudimos guardar. Probá de nuevo." }));
      if (result.error) setError(result.error);
      else {
        setDone(mine ? "Listo. Revisamos esa cuenta. Cuando la aprobemos, este auto queda unido a ese aviso." : "Listo. Lo cargamos como un auto aparte.");
        router.refresh();
      }
    });
  }

  return (
    <section className="space-y-3 rounded-lg border-2 border-foreground p-4" data-testid="item-review">
      <h2 className="text-[17px] font-bold">¿Es este aviso tuyo?</h2>
      <p className="text-[15px]">
        Encontramos un auto igual publicado cerca{duplicate ? <> en <b>{duplicate.source}</b>: {duplicate.title}</> : null}.
        {duplicate?.url ? <> <a href={duplicate.url} target="_blank" rel="noreferrer" className="underline underline-offset-2">Ver aviso</a></> : null}
      </p>
      <p className="text-sm text-muted-foreground">Si es tuyo, lo sincronizamos y no se carga dos veces.</p>
      {done ? <p role="status" className="text-sm font-semibold">{done}</p> : (
        <div className="flex flex-wrap gap-2">
          <Button className="h-10" disabled={pending} onClick={() => answer(true)}>Sí, es mío</Button>
          <Button variant="outline" className="h-10" disabled={pending} onClick={() => answer(false)}>No, es otro auto</Button>
        </div>
      )}
      {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
    </section>
  );
}
