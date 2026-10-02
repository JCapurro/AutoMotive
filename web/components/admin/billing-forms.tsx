"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";
import { confirmPayment, launchCommercialPilot, recordRefund } from "@/app/admin/billing/actions";
import { Button } from "@/components/ui/button";
import { PLAN_COPY, planPrice, type ProOffer, type WaitlistPlan, WAITLIST_PLANS } from "@/lib/pro";

const field = "mt-1 block h-10 w-full rounded-lg border bg-background px-3 text-sm";
export function PaymentForm({ users, offer }: { users: { id: string; email: string | null }[]; offer: ProOffer }) {
  const [plan, setPlan] = useState<WaitlistPlan>("pass_30");
  const [pending, start] = useTransition();
  return <form className="grid gap-4 rounded-xl border p-5 sm:grid-cols-2" onSubmit={(e) => {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    start(async () => {
      const paidAt = new Date(String(data.get("paidAt")));
      if (!Number.isFinite(paidAt.getTime())) { toast.error("Revisá la fecha del pago."); return; }
      const result = await confirmPayment({ userId: String(data.get("userId")), offer: plan,
        provider: String(data.get("provider")), reference: String(data.get("reference")),
        paidAt: paidAt.toISOString(), note: String(data.get("note")), verified: data.get("verified") === "on" });
      if (result.error) { toast.error(result.error); return; }
      toast.success(`Pago ${result.id} registrado y acceso actualizado.`);
      form.reset();
    });
  }}>
    <h2 className="font-semibold sm:col-span-2">Confirmar un pago externo</h2>
    <label className="text-sm">Cuenta<select required name="userId" className={field} defaultValue="">
      <option value="" disabled>Elegí una cuenta</option>
      {users.map((u) => <option key={u.id} value={u.id}>{u.email ?? `Telegram · ${u.id.slice(0, 8)}`}</option>)}
    </select></label>
    <label className="text-sm">Plan<select name="offer" className={field} value={plan} onChange={(e) => setPlan(e.target.value as WaitlistPlan)}>
      {WAITLIST_PLANS.map((p) => <option key={p} value={p}>{PLAN_COPY[p].name} · {planPrice(offer[p].amount)} ARS</option>)}
    </select></label>
    <label className="text-sm">Proveedor<input required name="provider" defaultValue="Mercado Pago" minLength={2} maxLength={80} className={field} /></label>
    <label className="text-sm">Referencia única del pago<input required name="reference" minLength={3} maxLength={160} className={field} /></label>
    <label className="text-sm">Fecha y hora del pago (hora de este dispositivo)<input required type="datetime-local" name="paidAt" className={field} /></label>
    <label className="text-sm">Nota para auditoría<input name="note" maxLength={1000} className={field} /></label>
    <label className="flex items-start gap-2 text-sm sm:col-span-2"><input required type="checkbox" name="verified" className="mt-1" />
      Verifiqué en el proveedor el estado aprobado, la cuenta destinataria y el importe completo en ARS.
      Guardar activa 30 días; una renovación Agencia extiende desde el vencimiento vigente.</label>
    <Button type="submit" disabled={pending} className="sm:col-span-2">Registrar pago y activar período</Button>
  </form>;
}
export function PilotLaunch({ enabled, freeUsers, excessSearches }: { enabled: boolean; freeUsers: number; excessSearches: number }) {
  const [confirm, setConfirm] = useState(false);
  const [pending, start] = useTransition();
  return <section className="space-y-3 rounded-xl border p-5 text-sm">
    <h2 className="font-semibold">{enabled ? "Piloto comercial habilitado" : "Habilitar el piloto comercial"}</h2>
    {enabled ? <p>Free dura 72 horas; Particular permite 3 búsquedas activas y Agencia, 10. Los pagos y las renovaciones se verifican manualmente.</p> : <>
      <p>Hay {freeUsers} cuentas gratuitas con búsquedas activas. Las que todavía no iniciaron una prueba recibirán 72 horas desde la habilitación.
        Hay {excessSearches} búsquedas por encima de la capacidad nominal. Se pausarán los excedentes y las búsquedas con acceso vencido;
        se mantienen las más antiguas dentro del límite y todo el historial.</p>
      <label className="flex gap-2"><input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />
        Revisé las cuentas y comuniqué el inicio de la prueba y los límites.</label>
      <Button disabled={!confirm || pending} onClick={() => start(async () => {
        const res = await launchCommercialPilot();
        if (res.error) toast.error(res.error); else toast.success("Piloto comercial habilitado.");
      })}>Habilitar prueba de 3 días y límites</Button>
    </>}
  </section>;
}
export function RefundForm({ id }: { id: number }) {
  const [pending, start] = useTransition();
  return <form className="flex flex-wrap gap-2" onSubmit={(e) => {
    e.preventDefault();
    const reference = String(new FormData(e.currentTarget).get("refundReference"));
    start(async () => {
      const res = await recordRefund(id, reference);
      if (res.error) toast.error(res.error); else toast.success("Devolución registrada; acceso recalculado.");
    });
  }}>
    <input required name="refundReference" aria-label="Referencia de la devolución ya realizada" minLength={3} maxLength={160} placeholder="Referencia de devolución" className="h-8 min-w-40 rounded border px-2 text-xs" />
    <label className="flex items-center gap-1 text-xs"><input required type="checkbox" />Devolución total ya verificada</label>
    <Button type="submit" variant="outline" size="sm" disabled={pending}>Registrar devolución</Button>
  </form>;
}
