"use client";

import { Copy, MessageCircleQuestion } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { trackSellerQuestions } from "@/app/app/listings/actions";
import { Button } from "@/components/ui/button";

/** §25 "¿Qué le pregunto al vendedor?": Automotive only drafts the message; the user copies it. */
export function SellerQuestions({ listingId, text }: { listingId: number; text: string }) {
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

  if (!open) {
    return (
      <Button
        variant="outline"
        onClick={() => {
          setOpen(true);
          void trackSellerQuestions(listingId, "generated");
        }}
      >
        <MessageCircleQuestion aria-hidden /> ¿Qué le pregunto al vendedor?
      </Button>
    );
  }
  return (
    <div className="space-y-3">
      <p data-testid="seller-questions" className="rounded-lg bg-muted p-4 text-sm leading-relaxed select-all">
        {text}
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={copy}>
          <Copy aria-hidden /> Copiar mensaje
        </Button>
        <span className="text-xs text-muted-foreground">Automotive no contacta al vendedor: vos decidís si mandarlo.</span>
      </div>
    </div>
  );
}
