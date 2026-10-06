"use client";

import { Bookmark, Check, ExternalLink, X } from "lucide-react";
import { useState, useTransition } from "react";
import { toast } from "sonner";
import { setStatus } from "@/app/app/listings/actions";
import { Button } from "@/components/ui/button";
import { pixel } from "@/lib/meta-pixel";
import { analyticsEvent } from "@/lib/google-analytics";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { REJECTION, type RejectionReason, type InteractionStatus } from "@/lib/copy";

type Props = {
  listingId: number;
  status: InteractionStatus;
  saved: boolean;
  outboundHref: string;
};

export function ListingActions({ listingId, status, saved, outboundHref }: Props) {
  const [pending, start] = useTransition();
  const [discarding, setDiscarding] = useState(false);
  const interested = status === "interested" && saved;
  const run = (fn: () => Promise<void>, ok: string) => start(async () => {
    try {
      await fn();
      toast.success(ok);
    } catch {
      toast.error("No pudimos guardar el cambio. Probá de nuevo.");
    }
  });
  return (
    <div className="flex flex-wrap gap-2">
      <Button
        variant={interested ? "default" : "outline"}
        aria-pressed={interested}
        disabled={pending || interested || status === "purchased"}
        onClick={() => {
          if (!saved) {
            pixel("AddToWishlist", { content_ids: [String(listingId)], content_type: "product" });
            analyticsEvent("add_to_wishlist", { item_id: String(listingId) });
          }
          run(() => setStatus(listingId, "interested"), "Guardada: te avisamos si cambia");
        }}
      >
        {interested ? <Check aria-hidden /> : <Bookmark aria-hidden />} {interested ? "Guardada" : "Guardar"}
      </Button>
      <Button variant="outline" disabled={pending || status === "discarded" || status === "purchased"} onClick={() => setDiscarding(true)}>
        <X aria-hidden /> Descartar
      </Button>
      <Button asChild variant="secondary">
        <a href={outboundHref} target="_blank" rel="noopener noreferrer">Ver publicación <ExternalLink aria-hidden /></a>
      </Button>
      <DiscardDialog open={discarding} onOpenChange={setDiscarding} onConfirm={(reason) => {
        setDiscarding(false);
        run(() => setStatus(listingId, "discarded", reason), "Publicación descartada");
      }} />
    </div>
  );
}

function DiscardDialog({
  open,
  onOpenChange,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (reason: RejectionReason | null) => void;
}) {
  const [reason, setReason] = useState<RejectionReason | "">("");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>¿Por qué la descartás?</DialogTitle>
          <DialogDescription>Opcional. Nos sirve para ajustar lo que te mostramos.</DialogDescription>
        </DialogHeader>
        <div role="radiogroup" aria-label="Motivo de descarte" className="grid grid-cols-2 gap-2">
          {(Object.keys(REJECTION) as RejectionReason[]).map((r) => (
            <label
              key={r}
              className="flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm ring-1 ring-foreground/10 has-checked:bg-muted has-checked:ring-foreground/40"
            >
              <input type="radio" name="reason" value={r} checked={reason === r} onChange={() => setReason(r)} />
              {REJECTION[r]}
            </label>
          ))}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onConfirm(null)}>
            Descartar sin motivo
          </Button>
          <Button onClick={() => onConfirm(reason || null)} disabled={!reason}>
            Descartar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
