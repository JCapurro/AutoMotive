"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";

import { setNote } from "@/app/app/listings/actions";
import { ListingStatusSelect } from "@/components/app/listing-status-select";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { type InteractionStatus, TRACKING } from "@/lib/copy";

/**
 * X-01 "Seguimiento": the follow-up status and a private note, under the
 * detail's actions. Shown for gone listings too: a contacted car that went
 * offline is still part of the user's search.
 */
export function ListingTracking({
  listingId,
  status,
  note,
  noteMaxChars,
  profileId,
}: {
  listingId: number;
  status: InteractionStatus;
  note: string | null;
  noteMaxChars: number;
  profileId: number | null;
}) {
  const [editing, setEditing] = useState(!note);
  const [draft, setDraft] = useState(note ?? "");
  const [pending, start] = useTransition();
  const length = [...draft.trim()].length;

  const save = () =>
    start(async () => {
      try {
        await setNote(listingId, draft);
        setEditing(!draft.trim());
        toast.success("Nota guardada");
      } catch {
        toast.error("No pudimos guardar la nota. Probá de nuevo.");
      }
    });

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

      <div className="mt-4 grid gap-1.5">
        {editing ? (
          <>
            <Label htmlFor="tracking-note">{TRACKING.note}</Label>
            <Textarea
              id="tracking-note"
              value={draft}
              maxLength={noteMaxChars}
              placeholder={TRACKING.notePlaceholder}
              onChange={(e) => setDraft(e.target.value)}
              className="bg-background"
            />
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs text-muted-foreground" aria-live="polite">
                {length}/{noteMaxChars}
              </span>
              <div className="flex gap-2">
                {note ? (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={pending}
                    onClick={() => {
                      setDraft(note);
                      setEditing(false);
                    }}
                  >
                    {TRACKING.cancel}
                  </Button>
                ) : null}
                <Button size="sm" disabled={pending || length > noteMaxChars} onClick={save}>
                  {TRACKING.saveNote}
                </Button>
              </div>
            </div>
          </>
        ) : (
          <>
            <p className="text-sm font-medium">{TRACKING.note}</p>
            <p data-testid="listing-note" className="text-[15px] break-words whitespace-pre-line">
              {note}
            </p>
            <div>
              <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
                {TRACKING.editNote}
              </Button>
            </div>
          </>
        )}
        <p className="text-xs text-muted-foreground">{TRACKING.notePrivacy}</p>
      </div>
    </section>
  );
}
