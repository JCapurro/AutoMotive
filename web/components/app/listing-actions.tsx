"use client";

import { Bookmark, Check, ExternalLink, X } from "lucide-react";
import { useState, useTransition } from "react";
import { toast } from "sonner";
import { setSaved, setStatus } from "@/app/app/listings/actions";
import { useHideOnScrollDown } from "@/components/app/app-nav";
import { Button } from "@/components/ui/button";
import { pixel } from "@/lib/meta-pixel";
import { analyticsEvent } from "@/lib/google-analytics";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { REJECTION, type RejectionReason, type InteractionStatus } from "@/lib/copy";
import { statusOnSave } from "@/lib/listing-tracking";
import { cn } from "@/lib/utils";

type Props = {
  listingId: number;
  status: InteractionStatus;
  saved: boolean;
  outboundHref: string;
};

/**
 * The listing page's actions: in its decision panel from lg; below it, a bar
 * fixed at the bottom of the screen, above the phone's bottom nav and in its
 * place while the nav hides, with Guardar and Descartar as icons on a phone.
 */
export function ListingActions({ listingId, status, saved, outboundHref }: Props) {
  const [pending, start] = useTransition();
  const [discarding, setDiscarding] = useState(false);
  const navHidden = useHideOnScrollDown();
  // X-01: "Guardada" follows saved, so a contacted listing can be saved too.
  const interested = saved;
  const run = (fn: () => Promise<void>, ok: string) => start(async () => {
    try {
      await fn();
      toast.success(ok);
    } catch {
      toast.error("No pudimos guardar el cambio. Probá de nuevo.");
    }
  });
  return (
    <div
      className={cn(
        "fixed inset-x-0 bottom-0 z-30 flex items-center gap-2 border-t bg-background/95 px-4 pt-2.5 pb-[calc(0.625rem+env(safe-area-inset-bottom))] backdrop-blur-sm transition-transform duration-200 motion-reduce:transition-none sm:px-6",
        !navHidden && "max-md:translate-y-[calc(-3.5rem-env(safe-area-inset-bottom))] max-md:pb-2.5",
        "lg:static lg:grid lg:translate-y-0 lg:grid-cols-2 lg:border-0 lg:bg-transparent lg:p-0 lg:backdrop-blur-none",
      )}
    >
      <Button asChild size="lg" className="h-11 flex-1 text-[15px] max-lg:order-last lg:col-span-2">
        <a href={outboundHref} target="_blank" rel="noopener noreferrer">Ver publicación <ExternalLink aria-hidden /></a>
      </Button>
      <Button
        variant={interested ? "secondary" : "outline"}
        size="lg"
        className="h-11 max-md:w-11 max-md:px-0"
        aria-pressed={interested}
        disabled={pending || interested || status === "purchased"}
        onClick={() => {
          if (!saved) {
            pixel("AddToWishlist", { content_ids: [String(listingId)], content_type: "product" });
            analyticsEvent("add_to_wishlist", { item_id: String(listingId) });
          }
          // Saving never lowers Contactado or Visita agendada: it only sets saved.
          const save = statusOnSave(status);
          run(() => (save.kind === "setSaved" ? setSaved(listingId, true) : setStatus(listingId, save.status)), "Guardada: te avisamos si cambia");
        }}
      >
        {interested ? <Check aria-hidden /> : <Bookmark aria-hidden />} <span className="max-md:sr-only">{interested ? "Guardada" : "Guardar"}</span>
      </Button>
      <Button
        variant="outline"
        size="lg"
        className="h-11 max-md:w-11 max-md:px-0"
        disabled={pending || status === "discarded" || status === "purchased"}
        onClick={() => setDiscarding(true)}
      >
        <X aria-hidden /> <span className="max-md:sr-only">Descartar</span>
      </Button>
      <DiscardDialog open={discarding} onOpenChange={setDiscarding} onConfirm={(reason) => {
        setDiscarding(false);
        run(() => setStatus(listingId, "discarded", reason), "Publicación descartada");
      }} />
    </div>
  );
}

/** The §27 reason dialog; the "Seguimiento" select (X-01) opens it too. */
export function DiscardDialog({
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
