"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";

import { recordPurchase, setStatus } from "@/app/app/listings/actions";
import { DiscardDialog } from "@/components/app/listing-actions";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { type InteractionStatus, STATUS, TRACKING } from "@/lib/copy";
import { canChangeStatus, parsePurchasePrice, selectableStatuses } from "@/lib/listing-tracking";

/**
 * X-01: the listing's follow-up status, in the detail's "Seguimiento" block
 * and, compact, on each saved card. Descartado asks the §27 reason, Comprado
 * goes through recordPurchase and then locks the select (terminal in v1).
 * Parents key it by status so a refresh resets the local value.
 */
export function ListingStatusSelect({
  listingId,
  status,
  profileId,
  id,
  size = "default",
  className,
}: {
  listingId: number;
  status: InteractionStatus;
  /** The best match's search, for owned_vehicles.search_profile_id. */
  profileId: number | null;
  id?: string;
  size?: "sm" | "default";
  className?: string;
}) {
  const [value, setValue] = useState<InteractionStatus>(status);
  const [dialog, setDialog] = useState<"discarded" | "purchased" | null>(null);
  const [pending, start] = useTransition();
  const locked = status === "purchased";

  const change = (to: InteractionStatus, reason?: Parameters<typeof setStatus>[2]) =>
    start(async () => {
      setValue(to);
      try {
        await setStatus(listingId, to, reason);
        toast.success(`Estado: ${STATUS[to]}`);
      } catch {
        setValue(status);
        toast.error("No pudimos guardar el cambio. Probá de nuevo.");
      }
    });

  return (
    <>
      <NativeSelect
        id={id}
        size={size}
        aria-label={id ? undefined : TRACKING.status}
        className={className}
        value={value}
        disabled={locked || pending}
        onChange={(e) => {
          const to = e.target.value as InteractionStatus;
          if (to === "purchased") setDialog("purchased");
          else if (!canChangeStatus(status, to)) return;
          else if (to === "discarded") setDialog("discarded");
          else change(to);
        }}
      >
        {value === "new" ? (
          <NativeSelectOption value="new" disabled hidden>
            {STATUS.new}
          </NativeSelectOption>
        ) : null}
        {selectableStatuses().map((s) => (
          <NativeSelectOption key={s.value} value={s.value}>
            {s.label}
          </NativeSelectOption>
        ))}
      </NativeSelect>
      <DiscardDialog
        open={dialog === "discarded"}
        onOpenChange={(open) => setDialog(open ? "discarded" : null)}
        onConfirm={(reason) => {
          setDialog(null);
          change("discarded", reason);
        }}
      />
      <PurchaseDialog
        open={dialog === "purchased"}
        onOpenChange={(open) => setDialog(open ? "purchased" : null)}
        onConfirm={(purchase) =>
          start(async () => {
            // Like change(): a failure keeps the dialog open and the status as it was.
            try {
              const result = await recordPurchase({ listingId, profileId, ...purchase });
              if (result.error) {
                toast.error(result.error);
                return;
              }
            } catch {
              toast.error("No pudimos registrar la compra. Probá de nuevo.");
              return;
            }
            setDialog(null);
            setValue("purchased");
            toast.success("Registramos la compra");
          })
        }
        pending={pending}
      />
    </>
  );
}

type Purchase = { price: number | null; currency: "USD" | "ARS" | null; date: string | null };

/** "Comprado" (§38–39): price, currency and date, all optional; confirming is final in v1. */
export function PurchaseDialog({
  open,
  onOpenChange,
  onConfirm,
  pending,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (purchase: Purchase) => void;
  pending: boolean;
}) {
  const [price, setPrice] = useState("");
  const [currency, setCurrency] = useState<"USD" | "ARS">("USD");
  const [date, setDate] = useState("");
  const parsed = parsePurchasePrice(price);
  const amount = "price" in parsed ? parsed.price : null;
  const invalid = "error" in parsed;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{TRACKING.purchaseTitle}</DialogTitle>
          <DialogDescription>{TRACKING.purchaseDescription}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
          <div className="grid gap-1.5">
            <Label htmlFor="purchase-price">{TRACKING.purchasePrice}</Label>
            <Input
              id="purchase-price"
              inputMode="numeric"
              value={price}
              aria-invalid={invalid || undefined}
              aria-describedby={invalid ? "purchase-price-error" : undefined}
              onChange={(e) => setPrice(e.target.value)}
            />
            {"error" in parsed ? (
              <p id="purchase-price-error" className="text-[13px] text-destructive">
                {parsed.error}
              </p>
            ) : null}
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="purchase-currency">{TRACKING.purchaseCurrency}</Label>
            <NativeSelect id="purchase-currency" value={currency} onChange={(e) => setCurrency(e.target.value as "USD" | "ARS")}>
              <NativeSelectOption value="USD">USD</NativeSelectOption>
              <NativeSelectOption value="ARS">ARS</NativeSelectOption>
            </NativeSelect>
          </div>
          <div className="grid gap-1.5 sm:col-span-2">
            <Label htmlFor="purchase-date">{TRACKING.purchaseDate}</Label>
            <Input id="purchase-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {TRACKING.cancel}
          </Button>
          <Button
            disabled={pending || invalid}
            onClick={() => onConfirm({ price: amount, currency: amount != null ? currency : null, date: date || null })}
          >
            {TRACKING.purchaseConfirm}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
