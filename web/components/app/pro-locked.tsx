import Link from "next/link";

import { PRO_LOCKED } from "@/lib/copy";
import { cn } from "@/lib/utils";

/** The «Pro» tag on what only Pro includes (Juan, 02/11: in view on the other plans). */
export function ProBadge({ className }: { className?: string }) {
  return (
    <span className={cn("rounded bg-foreground px-1.5 py-px text-[11px] leading-4 font-semibold text-background", className)}>
      {PRO_LOCKED.badge}
    </span>
  );
}

/** «Ver planes», next to a Pro setting the plan doesn't include. */
export function ProPlansLink() {
  return (
    <Link href="/app/pro" className="font-semibold whitespace-nowrap text-foreground underline underline-offset-2">
      {PRO_LOCKED.cta}
    </Link>
  );
}

/**
 * Juan, 02/11: a Pro alert setting the plan doesn't include, where Pro has it:
 * the same box as OpportunityThreshold's, its switch off and disabled, what it
 * does and the plans. It sets nothing.
 */
export function ProLockedSwitch({ id, title, text, testId }: { id: string; title: string; text: string; testId?: string }) {
  const cut = title.lastIndexOf(" ") + 1;
  return (
    <fieldset disabled data-testid={testId} className="space-y-3 rounded-lg border p-4 sm:col-span-2">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          {/* The tag goes with the title's last word, never alone on a line. */}
          <legend className="float-left w-full text-sm font-medium">
            {title.slice(0, cut)}
            <span className="whitespace-nowrap">
              {title.slice(cut)} <ProBadge className="ml-1 inline-block align-middle" />
            </span>
          </legend>
          <p id={`${id}-hint`} className="clear-both text-xs text-muted-foreground">
            {text} <ProPlansLink />
          </p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={false}
          aria-label={title}
          aria-describedby={`${id}-hint`}
          className="relative mt-0.5 inline-flex h-6 w-11 shrink-0 cursor-not-allowed items-center rounded-full bg-muted-foreground/30 opacity-50"
        >
          <span className="inline-block size-5 translate-x-0.5 rounded-full bg-background shadow" />
        </button>
      </div>
    </fieldset>
  );
}
