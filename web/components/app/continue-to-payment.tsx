"use client";

import { ArrowRight } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";

import { continueToPayment, type PaymentStep } from "@/app/app/cuenta/actions";
import { PasswordForm } from "@/components/app/account-steps";
import { Button } from "@/components/ui/button";
import { analyticsEvent } from "@/lib/google-analytics";
import { pixel } from "@/lib/meta-pixel";
import { PLAN_COPY, planPrice, type WaitlistPlan } from "@/lib/pro";

/** The offer on its way to Mercado Pago, with the version and amount this page showed. */
export type PaymentOffer = { plan: WaitlistPlan; version: string; amount: number; currency: string };

const AUTOSTART_KEY = "pay-autostart";

/** Once per tab and destination: «Atrás» from Mercado Pago lands on the button, not on another checkout. */
function firstAutostart(next: string): boolean {
  try {
    const key = `${AUTOSTART_KEY}:${next}`;
    if (window.sessionStorage.getItem(key)) return false;
    window.sessionStorage.setItem(key, "1");
  } catch { /* no storage: start anyway, the button stays for the way back */ }
  return true;
}

/**
 * Camino al pago (docs/PAGO_CON_CODIGO.md): the session that proved its inbox
 * (or a full account) goes on to Mercado Pago. `autostart`: the code was just
 * typed in this tab (`?pagar=1`), so it goes without another tap; from the
 * email's link it waits for the button.
 */
export function ContinueToPayment({ next, offer, autostart }: { next: string; offer: PaymentOffer | null; autostart: boolean }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [step, setStep] = useState<PaymentStep>({});
  const [leaving, setLeaving] = useState(false);
  const started = useRef(false);

  function go() {
    start(async () => {
      try {
        const result = await continueToPayment(next, offer?.version ?? "", offer?.amount ?? 0);
        if (result.url && offer) {
          setLeaving(true);
          pixel("InitiateCheckout", { content_ids: [offer.plan], value: offer.amount, currency: offer.currency });
          analyticsEvent("begin_checkout", { currency: offer.currency, value: offer.amount, items: [{ item_id: offer.plan, item_name: PLAN_COPY[offer.plan].name }] });
          window.location.assign(result.url);
          return;
        }
        if (result.href) { setLeaving(true); router.replace(result.href); return; }
        // The proof is gone: the page goes back to the code step.
        if (result.expired) router.refresh();
        setStep(result);
      } catch {
        setStep({ error: "No pudimos continuar. Probá de nuevo en unos segundos." });
      }
    });
  }

  useEffect(() => {
    if (!autostart || started.current) return;
    started.current = true;
    if (firstAutostart(next)) go();
    // go() only reads props that keep their value for this page.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autostart, next]);

  // A database without the 'code' method yet: the password step, as before.
  if (step.password) return <div className="space-y-4">
    <p className="text-sm text-muted-foreground">Antes de pagar, elegí una contraseña: así entrás desde cualquier dispositivo y ves tus pagos.</p>
    <PasswordForm next={next} paying />
  </div>;

  const busy = pending || leaving;
  return <div className="space-y-3">
    {step.error ? <p role="alert" className="text-sm text-destructive">{step.error}</p> : null}
    <Button className="h-11 w-full text-[15px]" disabled={busy || step.expired} onClick={go}>
      {busy ? "Abriendo Mercado Pago…" : offer ? `Continuar en Mercado Pago · ${planPrice(offer.amount)}` : "Continuar"}
      {busy ? null : <ArrowRight aria-hidden />}
    </Button>
    {offer ? <p className="text-xs text-muted-foreground">
      Al continuar aceptás los <a href="/terminos" target="_blank" rel="noreferrer" className="underline underline-offset-2">Términos y condiciones</a>.
    </p> : null}
  </div>;
}
