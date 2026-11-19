"use client";

import { MessageCircle, PhoneCall } from "lucide-react";
import { useState, useTransition } from "react";

import { requestDealerContact } from "@/app/app/listings/dealer-actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { consentText, defaultMessage, leadDate, type LeadResult, whatsappText, whatsappUrl } from "@/lib/dealer-contact";
import { analyticsEvent } from "@/lib/google-analytics";

type Props = {
  listingId: number;
  dealerId: number | null;
  dealerName: string;
  vehicle: string;
  /** profiles.phone, to prefill (the buyer can change it). */
  phone: string | null;
  canRequest: boolean;
  /** A lead the buyer already made for this car. */
  existing: { createdAt: string } | null;
  whatsapp: string | null;
  /** ?n=<id> from an alert link: the lead's origin. */
  notificationId: number | null;
};

/**
 * «Quiero que me contacten» (spec §6.4): a form of ours, with an unticked
 * consent box; only after the lead exists, the agency's WhatsApp with a
 * message ready. Analytics get ids only, never the name, phone or message.
 */
export function DealerContact({ listingId, dealerId, dealerName, vehicle, phone, canRequest, existing, whatsapp, notificationId }: Props) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [tel, setTel] = useState(phone ?? "");
  const [message, setMessage] = useState(defaultMessage(vehicle));
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lead, setLead] = useState<LeadResult | null>(null);
  const [pending, start] = useTransition();

  const already = lead ? { createdAt: lead.createdAt, whatsapp: lead.whatsapp, created: lead.created } : existing ? { createdAt: existing.createdAt, whatsapp, created: false } : null;
  const wa = already ? whatsappUrl(already.whatsapp, whatsappText(vehicle, lead ? name : "")) : null;

  if (already) {
    return (
      <div data-testid="dealer-contact-done" className="space-y-2" role="status">
        <p className="text-[15px] font-semibold">
          {already.created ? `Listo. ${dealerName} ya tiene tu pedido.` : `Ya le pediste a ${dealerName} que te contacte el ${leadDate(already.createdAt)}.`}
        </p>
        {wa ? (
          <Button asChild variant="outline" className="h-10">
            <a href={wa} target="_blank" rel="noreferrer">
              <MessageCircle aria-hidden /> Escribile por WhatsApp
            </a>
          </Button>
        ) : null}
      </div>
    );
  }
  if (!canRequest) return null;

  if (!open) {
    return (
      <Button data-testid="dealer-contact-open" className="h-11 w-full text-[15px]" onClick={() => setOpen(true)}>
        <PhoneCall aria-hidden /> Quiero que me contacten
      </Button>
    );
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    start(async () => {
      try {
        const result = await requestDealerContact(listingId, { name, phone: tel, message, consent, notificationId });
        if (result.error || !result.lead) {
          setError(result.error ?? "No pudimos guardar. Probá de nuevo.");
          return;
        }
        setLead(result.lead);
        if (result.lead.created) {
          analyticsEvent("dealer_contact_requested", { listing_id: listingId, dealer_id: dealerId ?? undefined, origin: notificationId ? "alert" : "ficha" });
        }
      } catch {
        setError("No pudimos guardar. Probá de nuevo.");
      }
    });
  }

  return (
    <form onSubmit={submit} data-testid="dealer-contact-form" className="space-y-3">
      <p className="text-sm text-muted-foreground">{dealerName} te va a escribir o llamar por este auto.</p>
      <div className="space-y-1.5">
        <Label htmlFor="dealer-contact-name">Nombre</Label>
        <Input id="dealer-contact-name" autoComplete="given-name" required minLength={2} maxLength={80} value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="dealer-contact-phone">Teléfono</Label>
        <Input id="dealer-contact-phone" type="tel" inputMode="tel" autoComplete="tel-national" required maxLength={40} placeholder="11 2345-6789" value={tel} onChange={(e) => setTel(e.target.value)} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="dealer-contact-message">Mensaje (opcional)</Label>
        <Textarea id="dealer-contact-message" maxLength={500} value={message} onChange={(e) => setMessage(e.target.value)} />
      </div>
      <label className="flex items-start gap-2.5 text-sm">
        <input type="checkbox" data-testid="dealer-contact-consent" className="mt-0.5 size-4 shrink-0 accent-foreground" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
        <span>{consentText(dealerName)}</span>
      </label>
      {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" className="h-10" disabled={!consent || pending}>{pending ? "Enviando…" : "Pedir contacto"}</Button>
        <Button type="button" variant="ghost" className="h-10" onClick={() => setOpen(false)} disabled={pending}>Cancelar</Button>
      </div>
    </form>
  );
}
