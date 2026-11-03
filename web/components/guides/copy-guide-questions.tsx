"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";

import { logGuideEvent } from "@/components/guides/guide-events";
import { Button } from "@/components/ui/button";
import { GUIDE_COPY } from "@/lib/guides";

/** «Copiar preguntas»: every question of the page, one per line (guide_questions_copied). */
export function CopyGuideQuestions({ text, slugMake, slugModel }: { text: string; slugMake?: string; slugModel?: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  return (
    <div className="space-y-2">
      <Button type="button" variant="outline" className="h-11" onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setState("copied");
          if (slugMake && slugModel) logGuideEvent("guide_questions_copied", slugMake, slugModel);
        } catch {
          setState("failed");
        }
      }}>
        {state === "copied" ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
        {GUIDE_COPY.copy}
      </Button>
      <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
        {state === "copied" ? GUIDE_COPY.copied : state === "failed" ? GUIDE_COPY.copyFailed : null}
      </p>
    </div>
  );
}
