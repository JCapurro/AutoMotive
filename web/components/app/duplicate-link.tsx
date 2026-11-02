"use client";

import { ExternalLink } from "lucide-react";
import Link from "next/link";

import { trackDuplicateLink } from "@/app/app/listings/actions";
import { DUPLICATE_LINK_LABEL, type DuplicateTarget } from "@/lib/red-flags";

/**
 * PAR-02 resto: «Ver la otra publicación» at the end of a duplicate flag. The
 * other listing's page when it is still in the base, else its public URL in a
 * new tab. duplicate_link_clicked is fired without waiting: the navigation goes on.
 */
export function DuplicateLink({ listingId, target }: { listingId: number; target: DuplicateTarget }) {
  const onClick = () => {
    void trackDuplicateLink(listingId, target.otherListingId, target.kind, target.external ? "external" : "internal");
  };
  const className = "ml-1 inline-flex items-center gap-1 font-normal text-foreground underline underline-offset-2 hover:text-primary";
  if (target.external) {
    return (
      <a href={target.href} target="_blank" rel="noopener noreferrer" onClick={onClick} className={className} data-testid="duplicate-link">
        {DUPLICATE_LINK_LABEL}
        <ExternalLink className="size-3.5" aria-hidden />
      </a>
    );
  }
  return (
    <Link href={target.href} onClick={onClick} className={className} data-testid="duplicate-link">
      {DUPLICATE_LINK_LABEL}
    </Link>
  );
}
