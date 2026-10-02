"use client";

import { Bookmark, BookmarkCheck, Check, ExternalLink, KeyRound, ThumbsUp, X } from "lucide-react";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import {
  answerInfluence,
  recordPurchase,
  setDiscardReason,
  setSaved,
  setStatus,
} from "@/app/app/listings/actions";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import {
  INFLUENCE,
  type Influence,
  type InteractionStatus,
  REJECTION,
  type RejectionReason,
  STATUS,
  STATUSES,
} from "@/lib/copy";
import { number } from "@/lib/format";

type Props = {
  listingId: number;
  status: InteractionStatus;
  saved: boolean;
  rejectionReason: RejectionReason | null;
  outboundHref: string;
  price: number | null;
  currency: string | null;
  profiles: { id: number; name: string }[];
  owned: { id: number; influence: Influence | null } | null;
};

const TODAY = () =>
  new Intl.DateTimeFormat("en-CA", { timeZone: "America/Argentina/Buenos_Aires" }).format(new Date());

/** §26 states, §27 reasons, §30 watchlist and §38 "Compré este vehículo". */
export function ListingActions(props: Props) {
  const { listingId, status, saved, rejectionReason, outboundHref } = props;
  const [pending, start] = useTransition();
  const [discarding, setDiscarding] = useState(false);
  const [buying, setBuying] = useState(false);

  const run = (fn: () => Promise<void>, ok?: string) =>
    start(async () => {
      try {
        await fn();
        if (ok) toast.success(ok);
      } catch {
        toast.error("No pudimos guardar el cambio. Probá de nuevo.");
      }
    });

  const selectable = STATUSES.filter((s) => s !== "purchased" || status === "purchased");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <Button
          variant={status === "interested" ? "default" : "outline"}
          disabled={pending || status === "interested" || status === "purchased"}
          onClick={() => run(() => setStatus(listingId, "interested"), "Marcada como «Me interesa»")}
        >
          {status === "interested" ? <Check aria-hidden /> : <ThumbsUp aria-hidden />}
          {status === "interested" ? "Te interesa" : "Me interesa"}
        </Button>
        <Button
          variant="outline"
          disabled={pending || status === "discarded" || status === "purchased"}
          onClick={() => setDiscarding(true)}
        >
          <X aria-hidden /> {status === "discarded" ? "Descartada" : "Descartar"}
        </Button>
        <Button
          variant="outline"
          aria-pressed={saved}
          disabled={pending}
          onClick={() => run(() => setSaved(listingId, !saved), saved ? "Quitada de guardados" : "Guardada: te avisamos si cambia")}
        >
          {saved ? <BookmarkCheck aria-hidden className="text-amber-600" /> : <Bookmark aria-hidden />}
          {saved ? "Guardada" : "Guardar"}
        </Button>
        <Button asChild variant="secondary">
          <a href={outboundHref} target="_blank" rel="noopener noreferrer">
            Ver publicación <ExternalLink aria-hidden />
          </a>
        </Button>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="status">Estado</Label>
          <NativeSelect
            id="status"
            value={status}
            disabled={pending || status === "purchased"}
            onChange={(e) => {
              const next = e.target.value as InteractionStatus;
              if (next === "discarded") setDiscarding(true);
              else run(() => setStatus(listingId, next));
            }}
          >
            {selectable.map((s) => (
              <NativeSelectOption key={s} value={s}>
                {STATUS[s]}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </div>
        {status === "discarded" ? (
          <div className="space-y-1.5">
            <Label htmlFor="rejection_reason">Motivo</Label>
            <NativeSelect
              id="rejection_reason"
              value={rejectionReason ?? ""}
              disabled={pending}
              onChange={(e) => run(() => setDiscardReason(listingId, (e.target.value || null) as RejectionReason | null))}
            >
              <NativeSelectOption value="">Sin motivo</NativeSelectOption>
              {(Object.keys(REJECTION) as RejectionReason[]).map((r) => (
                <NativeSelectOption key={r} value={r}>
                  {REJECTION[r]}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </div>
        ) : null}
        {!props.owned ? (
          <Button variant="outline" className="ml-auto" onClick={() => setBuying(true)}>
            <KeyRound aria-hidden /> Compré este vehículo
          </Button>
        ) : null}
      </div>

      {props.owned ? <PurchasedBanner owned={props.owned} /> : null}

      <DiscardDialog
        open={discarding}
        onOpenChange={setDiscarding}
        onConfirm={(reason) => {
          setDiscarding(false);
          run(() => setStatus(listingId, "discarded", reason), "Publicación descartada");
        }}
      />
      <PurchaseDialog open={buying} onOpenChange={setBuying} {...props} />
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

function PurchaseDialog({
  open,
  onOpenChange,
  listingId,
  price,
  currency,
  profiles,
}: Props & { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [pending, start] = useTransition();
  const [amount, setAmount] = useState(price != null ? number(price) : "");
  const [cur, setCur] = useState<"USD" | "ARS">(currency === "ARS" ? "ARS" : "USD");
  const [date, setDate] = useState(TODAY);
  const [profileId, setProfileId] = useState<number | null>(profiles[0]?.id ?? null);
  const [error, setError] = useState<string>();

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const digits = amount.replace(/\D/g, "");
    start(async () => {
      const result = await recordPurchase({
        listingId,
        profileId,
        price: digits ? Number(digits) : null,
        currency: digits ? cur : null,
        date: date || null,
      });
      if (result.error) setError(result.error);
      else onOpenChange(false);
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>¡Felicitaciones! 🎉</DialogTitle>
            <DialogDescription>Contanos cómo fue la compra. Queda guardado en tu cuenta.</DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="purchase_price">Precio de compra</Label>
            <div className="flex gap-2">
              <NativeSelect className="w-24 shrink-0" aria-label="Moneda de compra" value={cur} onChange={(e) => setCur(e.target.value as "USD" | "ARS")}>
                <NativeSelectOption value="USD">USD</NativeSelectOption>
                <NativeSelectOption value="ARS">ARS</NativeSelectOption>
              </NativeSelect>
              <Input id="purchase_price" inputMode="numeric" value={amount} onChange={(e) => setAmount(e.target.value)} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="purchase_date">Fecha</Label>
            <Input id="purchase_date" type="date" value={date} max={TODAY()} onChange={(e) => setDate(e.target.value)} />
          </div>
          {profiles.length > 1 ? (
            <div className="space-y-1.5">
              <Label htmlFor="purchase_profile">¿De qué búsqueda?</Label>
              <NativeSelect
                id="purchase_profile"
                className="w-full"
                value={profileId ?? ""}
                onChange={(e) => setProfileId(e.target.value ? Number(e.target.value) : null)}
              >
                {profiles.map((p) => (
                  <NativeSelectOption key={p.id} value={p.id}>
                    {p.name}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </div>
          ) : null}
          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="submit" disabled={pending}>
              Confirmar compra
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** After the purchase, the §38 question — once. */
function PurchasedBanner({ owned }: { owned: { id: number; influence: Influence | null } }) {
  const [pending, start] = useTransition();
  return (
    <div className="space-y-3 rounded-xl bg-emerald-50 p-4 text-sm text-emerald-950 ring-1 ring-emerald-200" data-testid="purchased">
      <p className="font-medium">🔑 Compraste este vehículo.</p>
      {owned.influence ? (
        <p>¡Gracias por contarnos! Nos dijiste que Ese Auto influyó: {INFLUENCE[owned.influence].toLowerCase()}.</p>
      ) : (
        <div className="space-y-2">
          <p id="influence-question">¿Ese Auto influyó en que encontraras este vehículo?</p>
          <div role="group" aria-labelledby="influence-question" className="flex flex-wrap gap-2">
            {(Object.keys(INFLUENCE) as Influence[]).map((i) => (
              <Button
                key={i}
                size="sm"
                variant="outline"
                className="bg-background"
                disabled={pending}
                onClick={() => start(() => answerInfluence(owned.id, i))}
              >
                {INFLUENCE[i]}
              </Button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
