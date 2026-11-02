"use client";

import { ListingStatusSelect } from "@/components/app/listing-status-select";
import { Label } from "@/components/ui/label";
import { type InteractionStatus, TRACKING } from "@/lib/copy";

/**
 * X-01 "Seguimiento": the follow-up status, at the foot of the listing page's
 * decision panel. Shown for gone listings too: a contacted car that went
 * offline is still part of the user's search. No private note since Juan's
 * 02/11 request.
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
    <section aria-labelledby="tracking-title" data-testid="listing-tracking">
      <div className="flex items-center justify-between gap-3 lg:block">
        <h2 id="tracking-title" className="text-[13px] font-bold">
          {TRACKING.title}
        </h2>
        {/* The heading names the block; «Estado» stays the select's name for screen readers. */}
        <Label htmlFor="tracking-status" className="sr-only">
          {TRACKING.status}
        </Label>
        <ListingStatusSelect key={status} id="tracking-status" listingId={listingId} status={status} profileId={profileId} className="w-full max-w-52 lg:mt-1.5 lg:max-w-none" />
      </div>
      {status === "purchased" ? <p className="mt-1.5 text-[13px] text-muted-foreground">{TRACKING.purchasedLocked}</p> : null}
    </section>
  );
}
