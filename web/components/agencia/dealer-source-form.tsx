"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { addDealerSource } from "@/app/agencia/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";

/** «Ya publico en…»: the profile link and how the name shows there; we approve which seller account is the agency's. */
export function DealerSourceForm({ sources }: { sources: { id: string; name: string }[] }) {
  const router = useRouter();
  const [source, setSource] = useState(sources[0]?.id ?? "");
  const [url, setUrl] = useState("");
  const [hint, setHint] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [pending, run] = useTransition();

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSaved(false);
    run(async () => {
      const result = await addDealerSource({ source, profileUrl: url, sellerNameHint: hint }).catch(() => ({ error: "No pudimos guardar. Probá de nuevo." }));
      if (result.error) setError(result.error);
      else {
        setSaved(true);
        setUrl("");
        setHint("");
        router.refresh();
      }
    });
  }

  return (
    <form onSubmit={submit} className="max-w-xl space-y-3" data-testid="dealer-source-form">
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <div className="space-y-1.5">
          <Label htmlFor="source-id">Dónde</Label>
          <NativeSelect id="source-id" value={source} onChange={(e) => setSource(e.target.value)} className="w-full">
            {sources.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </NativeSelect>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="source-url">Link de tu perfil</Label>
          <Input id="source-url" placeholder="https://" maxLength={300} value={url} onChange={(e) => setUrl(e.target.value)} />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="source-hint">Cómo figura tu nombre ahí</Label>
        <Input id="source-hint" maxLength={80} value={hint} onChange={(e) => setHint(e.target.value)} />
      </div>
      {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
      {saved ? <p role="status" className="text-sm">Listo. Lo revisamos. Cuando lo aprobemos, tus avisos aparecen solos en tu stock.</p> : null}
      <Button type="submit" variant="outline" className="h-10" disabled={pending || !source}>{pending ? "Guardando…" : "Sumar"}</Button>
    </form>
  );
}
