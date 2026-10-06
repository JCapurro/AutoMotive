"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { SearchPromptInput } from "@/components/search-prompt-input";
import { Button } from "@/components/ui/button";
import { searchStartHref } from "@/lib/search-intent";

export function LandingSearch({ signedIn }: { signedIn: boolean }) {
  const [text, setText] = useState("");
  const [pending, start] = useTransition();
  const router = useRouter();

  return (
    <form id="landing-search" className="mt-6 space-y-4" onSubmit={(event) => {
      event.preventDefault();
      if (pending) return;
      start(() => router.push(searchStartHref(signedIn, text)));
    }}>
      <SearchPromptInput value={text} onChange={setText} disabled={pending} showExamples={false} />
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <Button type="submit" disabled={pending} className="h-11 px-4.5 text-[15px]">
          {pending ? "Continuando…" : "Crear mi búsqueda"}
        </Button>
        <Link href="/pricing" className="py-2 text-[15px] font-medium underline underline-offset-4">Ver planes</Link>
      </div>
      <p className="text-sm text-muted-foreground">Prueba gratis por 3 días. Sin tarjeta.</p>
    </form>
  );
}
