"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";
import { toast } from "sonner";

import { declareSale } from "@/app/agencia/sale-actions";
import { Button } from "@/components/ui/button";
import type { PendingSale } from "@/lib/dealer-funnel";

export const SALE_QUESTION = "¿La venta vino por Ese Auto?";
const THANKS = "Gracias. Lo sumamos a tus números.";

type SaleTarget = { itemId?: number | null; leadId?: number | null; vehicle?: string };

async function answer(target: SaleTarget, viaEseAuto: boolean, after?: () => void): Promise<void> {
  const result = await declareSale({ itemId: target.itemId ?? null, leadId: target.leadId ?? null, viaEseAuto })
    .catch(() => ({ error: "No pudimos guardar tu respuesta. Probá de nuevo." }));
  if (result.error) toast.error(result.error);
  else toast.success(THANKS);
  after?.();
}

/**
 * Right after a car is marked sold or a lead «Compró»: the question, answered
 * with one click in the toast. If it is closed without an answer, the home of
 * the panel asks again (my_dealer_reach().pending_sales).
 */
export function askSaleSource(target: SaleTarget, after?: () => void): void {
  toast(SALE_QUESTION, {
    description: target.vehicle ? `Vendiste el ${target.vehicle}.` : "Nos sirve para saber si el canal te sirve.",
    duration: 30_000,
    action: { label: "Sí", onClick: () => void answer(target, true, after) },
    cancel: { label: "No", onClick: () => void answer(target, false, after) },
  });
}

/** The sold cars still without an answer, on the home of the panel. */
export function PendingSales({ sales }: { sales: PendingSale[] }) {
  const router = useRouter();
  const [pending, run] = useTransition();
  if (!sales.length) return null;
  return (
    <section className="space-y-2 rounded-lg bg-muted p-4" data-testid="pending-sales">
      <h2 className="text-[15px] font-semibold">{SALE_QUESTION}</h2>
      <ul className="divide-y">
        {sales.map((s) => (
          <li key={`${s.item_id ?? ""}-${s.lead_id ?? ""}`} className="flex flex-wrap items-center justify-between gap-2 py-2 text-[15px]">
            <span>{s.vehicle}</span>
            <span className="flex gap-2">
              <Button size="sm" disabled={pending} onClick={() => run(() => answer({ itemId: s.item_id, leadId: s.lead_id }, true, () => router.refresh()))}>
                Sí
              </Button>
              <Button size="sm" variant="outline" disabled={pending} onClick={() => run(() => answer({ itemId: s.item_id, leadId: s.lead_id }, false, () => router.refresh()))}>
                No, por otro lado
              </Button>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
