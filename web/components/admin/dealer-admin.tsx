"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";

import { approveSource, pauseDealer, rejectSource } from "@/app/admin/agencias/actions";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";

function useAction() {
  const [pending, run] = useTransition();
  const call = (fn: () => Promise<{ error?: string }>, ok: string) => run(async () => {
    const result = await fn().catch(() => ({ error: "No pudimos guardar." }));
    if (result.error) toast.error(result.error);
    else toast.success(ok);
  });
  return [pending, call] as const;
}

/** Pause or resume an agency. There is no «approve»: an agency is on while its plan is (20270104120000). */
export function DealerActions({ id, paused }: { id: number; paused: boolean }) {
  const [pending, call] = useAction();
  return (
    <div className="flex flex-wrap gap-1.5">
      <Button size="sm" variant="outline" disabled={pending} onClick={() => call(() => pauseDealer(id, !paused), paused ? "Activa otra vez" : "Pausada")}>
        {paused ? "Reactivar" : "Pausar"}
      </Button>
    </div>
  );
}

/** A pending source: pick the seller account (admin_dealer_seller_candidates) and approve, or reject. */
export function SourceDecision({ id, candidates, suggested }: { id: number; candidates: { seller_key: string; seller_name: string | null; active: number }[]; suggested: string | null }) {
  const [pending, call] = useAction();
  const [key, setKey] = useState(suggested ?? candidates[0]?.seller_key ?? "");
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {candidates.length || suggested ? (
        <NativeSelect size="sm" aria-label="Cuenta del vendedor" value={key} onChange={(e) => setKey(e.target.value)}>
          {suggested && !candidates.some((c) => c.seller_key === suggested) ? <option value={suggested}>{suggested} (del aviso duplicado)</option> : null}
          {candidates.map((c) => <option key={c.seller_key} value={c.seller_key}>{c.seller_name ?? c.seller_key} · {c.active} activos</option>)}
        </NativeSelect>
      ) : <span className="text-xs text-muted-foreground">Sin cuentas parecidas</span>}
      <Button size="sm" disabled={pending || !key} onClick={() => call(() => approveSource(id, key), "Fuente aprobada")}>Aprobar</Button>
      <Button size="sm" variant="outline" disabled={pending} onClick={() => call(() => rejectSource(id), "Fuente rechazada")}>Rechazar</Button>
    </div>
  );
}
