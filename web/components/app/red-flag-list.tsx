import { AlertTriangle, Info } from "lucide-react";

import { DuplicateLink } from "@/components/app/duplicate-link";
import { duplicateTarget } from "@/lib/red-flags";
import type { RedFlag } from "@/lib/types";

/**
 * «Conviene verificar» of the listing page: one row per flag, warnings in bold
 * with the warning icon. PAR-02 resto: a duplicate flag ends with «Ver la otra
 * publicación» (components/app/duplicate-link.tsx); `present` holds the linked
 * listings still in the base. Flags are already sorted (lib/red-flags.ts sortFlags).
 */
export function RedFlagList({ listingId, flags, present }: { listingId: number; flags: readonly RedFlag[]; present: ReadonlySet<number> }) {
  return (
    <ul className="mt-2" data-testid="red-flags">
      {flags.map((f) => {
        const target = duplicateTarget(f, present);
        return (
          <li key={f.id} data-flag={f.id} className="grid grid-cols-[20px_1fr] gap-2.5 border-b py-2.5 text-[15px] last:border-b-0">
            {f.severity === "warning" ? (
              <AlertTriangle className="mt-0.5 size-4 text-warn" aria-label="Importante" />
            ) : (
              <Info className="mt-0.5 size-4 text-faint" aria-hidden />
            )}
            <span className={f.severity === "warning" ? "min-w-0 break-words font-semibold text-warn" : "min-w-0 break-words"}>
              {f.text}
              {target ? <DuplicateLink listingId={listingId} target={target} /> : null}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
