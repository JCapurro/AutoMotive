import type { Metadata } from "next";
import Link from "next/link";

import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { feedbackEmail } from "@/lib/email-feedback";
import {
  FEEDBACK_COMMENT_MAX,
  FEEDBACK_REASONS,
  feedbackEmailId,
  feedbackReason,
  offeredReasons,
} from "@/lib/email-feedback-reasons";

import { sendFeedback } from "./actions";

export const metadata: Metadata = { title: "Contanos qué pasó", robots: { index: false } };
export const dynamic = "force-dynamic";

/**
 * The feedback link of a remarketing email (docs/MAILS_DE_PLAN.md,
 * «Remarketing»). Opening it records nothing — mail scanners open links
 * too —; the button does. A link with ?r= comes with that reason marked.
 */
export default async function FeedbackPage({ params, searchParams }: PageProps<"/f/[emailId]">) {
  const [{ emailId }, query] = await Promise.all([params, searchParams]);
  const id = feedbackEmailId(emailId);
  const signature = typeof query.s === "string" ? query.s : null;
  const email = id == null ? null : await feedbackEmail(id, signature);
  const done = query.listo === "1";
  const chosen = feedbackReason(query.r);

  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-6 px-4 py-10">
      <Logo />
      <Card className="w-full max-w-sm">
        {done ? (
          <CardHeader>
            <CardTitle className="text-lg">Gracias por contarnos</CardTitle>
            <CardDescription>
              Lo leemos todo. Si en algún momento querés probar, <Link href="/app/searches/new" className="underline">
              armá tu búsqueda acá</Link>.
            </CardDescription>
          </CardHeader>
        ) : email && id != null ? (
          <>
            <CardHeader>
              <CardTitle className="text-lg">¿Qué te frenó?</CardTitle>
              <CardDescription>Elegí lo que más se acerque. Si querés, sumá unas palabras.</CardDescription>
            </CardHeader>
            <CardContent>
              <form action={sendFeedback} className="space-y-4">
                <input type="hidden" name="id" value={id} />
                {signature ? <input type="hidden" name="s" value={signature} /> : null}
                <fieldset className="space-y-2">
                  <legend className="sr-only">Motivo</legend>
                  {offeredReasons(email.kind, email.after).map((reason) => (
                    <label key={reason} className="flex items-center gap-2 text-sm">
                      <input type="radio" name="r" value={reason} defaultChecked={reason === chosen} required />
                      {FEEDBACK_REASONS[reason]}
                    </label>
                  ))}
                </fieldset>
                <textarea
                  name="comment"
                  maxLength={FEEDBACK_COMMENT_MAX}
                  rows={3}
                  placeholder="¿Algo más que quieras contarnos? (opcional)"
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                />
                <Button type="submit" className="h-10 w-full">
                  Enviar
                </Button>
              </form>
            </CardContent>
          </>
        ) : (
          <CardHeader>
            <CardTitle className="text-lg">Este link no es válido</CardTitle>
            <CardDescription>
              Si querés contarnos algo, respondé el email que te llegó.
            </CardDescription>
          </CardHeader>
        )}
      </Card>
    </main>
  );
}
