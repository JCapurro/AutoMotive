"use client";
import { useEffect, useState, useTransition } from "react";
import { toast } from "sonner";
import { checkPayment, stopSubscription } from "@/app/app/pro/billing-actions";
import { Button } from "@/components/ui/button";
import { pixel } from "@/lib/meta-pixel";
import { accessDate, PLAN_COPY, planPrice } from "@/lib/pro";

const STATUS: Record<string, string> = { creating: "Preparando contratación", pending: "Esperando confirmación", authorized: "Suscripción autorizada", paused: "Suscripción pausada", cancelled: "Suscripción cancelada", paid: "Pago aprobado", failed: "Contratación rechazada" };
export function BillingStatus({ checkout }: { checkout: { id: string; offer: string; amount: number; status: string; init_point: string | null; next_payment_at: string | null; sync_error: string | null; created_at: string } }) {
  const [pending, start] = useTransition();
  const [confirm, setConfirm] = useState(false);
  const monthly = checkout.offer === "pro_monthly";
  const cancellable = monthly && ["creating", "pending", "authorized", "paused"].includes(checkout.status);
  usePurchasePixel(checkout);
  return <section className="space-y-3 rounded-xl border bg-card p-5 text-sm" aria-label="Estado de contratación">
    <h2 className="font-semibold">{monthly ? PLAN_COPY.pro_monthly.name : PLAN_COPY.pass_30.name} · {STATUS[checkout.status] ?? "Verificación pendiente"}</h2>
    <p>{planPrice(checkout.amount)} ARS {monthly ? "por mes" : "por 30 días, pago único"}.</p>
    <p>El acceso se habilita con cada pago aprobado. Al volver de Mercado Pago puede demorar unos minutos. Después, reactivá tus búsquedas pausadas.</p>
    {checkout.next_payment_at && checkout.status === "authorized" ? <p>Próximo cobro previsto: {accessDate(checkout.next_payment_at)}.</p> : null}
    {checkout.status === "cancelled" ? <p>Se detuvieron las renovaciones. El período ya pagado sigue vigente hasta su vencimiento.</p> : null}
    {checkout.sync_error ? <p role="status">La verificación requiere revisión. Contactanos si ya pagaste; evitá pagar otra vez.</p> : null}
    <div className="flex flex-wrap gap-2">
      <Button variant="outline" disabled={pending} onClick={() => start(async () => { const result = await checkPayment(checkout.id); if (result.error) toast.error(result.error); else toast.success("Estado consultado."); })}>Consultar estado</Button>
      {checkout.init_point && checkout.status === "pending" ? <Button asChild><a href={checkout.init_point}>Continuar en Mercado Pago</a></Button> : null}
      {cancellable && !confirm ? <Button variant="outline" disabled={pending} onClick={() => setConfirm(true)}>Cancelar suscripción</Button> : null}
    </div>
    {cancellable && confirm ? <div className="space-y-2" role="group" aria-label="Confirmar baja">
      <p>¿Confirmás la baja de los próximos cobros de Agencia? Conservás el acceso ya pagado.</p>
      <Button variant="destructive" disabled={pending} onClick={() => start(async () => { const result = await stopSubscription(checkout.id); if (result.error) toast.error(result.error); else { setConfirm(false); toast.success("Baja confirmada en Mercado Pago."); } })}>Confirmar baja</Button>{" "}
      <Button variant="outline" disabled={pending} onClick={() => setConfirm(false)}>Volver</Button>
    </div> : null}
  </section>;
}

/**
 * Purchase for the ads pixel, once per approved checkout on this browser: the
 * webhook confirms the payment server-side, so the browser fires it when the
 * user sees it approved. Old checkouts (e.g. a new device) don't count.
 */
function usePurchasePixel(checkout: { id: string; offer: string; amount: number; status: string; created_at: string }) {
  const approved = checkout.status === "paid" || checkout.status === "authorized";
  useEffect(() => {
    if (!approved || Date.now() - new Date(checkout.created_at).getTime() > 7 * 86_400_000) return;
    const key = `px_purchase:${checkout.id}`;
    try {
      if (localStorage.getItem(key)) return;
      localStorage.setItem(key, "1");
    } catch {}
    pixel("Purchase", { content_ids: [checkout.offer], value: checkout.amount, currency: "ARS" }, `purchase:${checkout.id}`);
  }, [approved, checkout.id, checkout.offer, checkout.amount, checkout.created_at]);
}
