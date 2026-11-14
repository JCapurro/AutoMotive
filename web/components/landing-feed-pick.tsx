"use client";

import { LANDING_PICK_EVENT } from "@/components/landing-builder";

/** «Avisame de un Polo así»: hands the row's model to the form above (LandingBuilder listens). */
export function LandingFeedPick({ model, label }: { model: string; label: string }) {
  return (
    <button
      type="button"
      className="inline-flex min-h-10 items-center rounded-lg bg-background px-3 text-[14.5px] font-semibold shadow-[inset_0_0_0_1.5px_var(--foreground)] outline-none focus-visible:ring-3 focus-visible:ring-ring/50 active:translate-y-px"
      onClick={() => window.dispatchEvent(new CustomEvent(LANDING_PICK_EVENT, { detail: model }))}
    >
      {label}
    </button>
  );
}
