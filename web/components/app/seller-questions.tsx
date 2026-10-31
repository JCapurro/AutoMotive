"use client";

import { Copy, Mail, MessageCircleQuestion } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { trackContactMessage, trackSellerQuestions } from "@/app/app/listings/actions";
import { Button } from "@/components/ui/button";
import { mailtoHref } from "@/lib/contact-message";
import { CONTACT_MESSAGE } from "@/lib/copy";

/**
 * PRO-01: the ready-to-send message (lib/contact-message.ts, already rendered
 * by the page): copy it, or open it in the user's email without a recipient.
 * Ese Auto never sends it and has no seller address.
 */
function ContactMessage({ listingId, message, subject, custom, outboundHref }: {
  listingId: number; message: string; subject: string; custom: boolean; outboundHref: string;
}) {
  async function copy() {
    try {
      await navigator.clipboard.writeText(message);
      toast.success(CONTACT_MESSAGE.copied);
    } catch {
      toast.error(CONTACT_MESSAGE.copyFailed);
    }
    void trackContactMessage(listingId, "clipboard", custom);
  }
  return (
    <div data-testid="contact-message-block" className="space-y-3">
      <p className="text-sm font-medium">{CONTACT_MESSAGE.title}</p>
      <p data-testid="contact-message" className="whitespace-pre-line rounded-lg bg-muted p-4 text-sm leading-relaxed select-all [overflow-wrap:anywhere]">
        {message}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={copy}>
          <Copy aria-hidden /> {CONTACT_MESSAGE.copy}
        </Button>
        <Button asChild variant="outline">
          <a data-testid="contact-message-mailto" href={mailtoHref(subject, message)} onClick={() => void trackContactMessage(listingId, "mailto", custom)}>
            <Mail aria-hidden /> {CONTACT_MESSAGE.mail}
          </a>
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        {CONTACT_MESSAGE.note}{" "}
        <a href={outboundHref} target="_blank" rel="noopener noreferrer" className="underline underline-offset-2">
          {CONTACT_MESSAGE.send}
        </a>
      </p>
    </div>
  );
}

/** §25 "¿Qué le pregunto al vendedor?": Ese Auto only drafts the message; the user copies it. */
export function SellerQuestions({ listingId, text, contact }: {
  listingId: number;
  text: string;
  /** PRO-01: the ready-to-send message above the full list. */
  contact?: { message: string; subject: string; custom: boolean; outboundHref: string };
}) {
  const [open, setOpen] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      toast.success("Copiado. Pegalo en el chat con el vendedor.");
    } catch {
      toast.error("No pudimos copiar. Seleccioná el texto y copialo a mano.");
    }
    void trackSellerQuestions(listingId, "copied");
  }

  const block = contact ? <ContactMessage listingId={listingId} {...contact} /> : null;
  if (!open) {
    return (
      <div className="space-y-4">
        {block}
        <Button
          variant="outline"
          onClick={() => {
            setOpen(true);
            void trackSellerQuestions(listingId, "generated");
          }}
        >
          <MessageCircleQuestion aria-hidden /> ¿Qué le pregunto al vendedor?
        </Button>
      </div>
    );
  }
  return (
    <div className="space-y-4">
      {block}
      <div className="space-y-3">
        <p data-testid="seller-questions" className="rounded-lg bg-muted p-4 text-sm leading-relaxed select-all">
          {text}
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={copy}>
            <Copy aria-hidden /> Copiar mensaje
          </Button>
          <span className="text-xs text-muted-foreground">Ese Auto no contacta al vendedor: vos decidís si mandarlo.</span>
        </div>
      </div>
    </div>
  );
}
