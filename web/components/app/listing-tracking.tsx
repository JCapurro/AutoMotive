"use client";

import { ListingStatusSelect } from "@/components/app/listing-status-select";
import { Label } from "@/components/ui/label";
import { type InteractionStatus, TRACKING } from "@/lib/copy";

/**
 * X-01 "Seguimiento": the follow-up status, under the detail's actions.
 * Shown for gone listings too: a contacted car that went offline is still
 * part of the user's search. No private note since Juan's 02/11 request.
 */
export function ListingTracking({
  listingId,
  status,
  profileId,
}: {
  listingId: number;
  status: InteractionStatus;
  profileId: number | null;
}) {
  return (
    <section aria-labelledby="tracking-title" className="rounded-lg bg-muted p-4" data-testid="listing-tracking">
      <h2 id="tracking-title" className="text-[15px] font-bold">
        {TRACKING.title}
      </h2>
      <div className="mt-3 grid gap-1.5">
        <Label htmlFor="tracking-status">{TRACKING.status}</Label>
        <ListingStatusSelect key={status} id="tracking-status" listingId={listingId} status={status} profileId={profileId} className="w-full sm:w-64" />
        {status === "purchased" ? <p className="text-[13px] text-muted-foreground">{TRACKING.purchasedLocked}</p> : null}
      </div>
    </section>
  );
}
