"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { requestSeller } from "@/app/agencia/vendedores/actions";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

/** «Quiero contactarlo»: an optional short message, then the request. The seller decides; no contact comes back. */
export function SellerRequest({ sellerRef }: { sellerRef: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [pending, run] = useTransition();

  if (!open) {
    return (
      <Button type="button" size="sm" onClick={() => setOpen(true)} data-testid="seller-request-open">
        Quiero contactarlo
      </Button>
    );
  }
  return (
    <form
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        run(async () => {
          const r = await requestSeller(sellerRef, message.trim() || undefined);
          if (r.error) {
            toast.error(r.error);
            return;
          }
          toast.success("Listo. Le avisamos al vendedor. Si acepta, vas a ver su contacto acá.");
          setOpen(false);
          router.refresh();
        });
      }}
    >
      <label className="block text-sm font-medium" htmlFor={`msg-${sellerRef}`}>
        Mensaje para el vendedor (opcional)
      </label>
      <Textarea
        id={`msg-${sellerRef}`}
        value={message}
        maxLength={300}
        rows={2}
        placeholder="Hola, compramos tu auto. Te hacemos una oferta sin compromiso."
        onChange={(e) => setMessage(e.target.value)}
      />
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={pending}>
          {pending ? "Enviando…" : "Pedir contacto"}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={() => setOpen(false)} disabled={pending}>
          Cancelar
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">No te pasamos ningún dato hasta que el vendedor acepte.</p>
    </form>
  );
}
