import { answerSellIntent, requestSellNotice } from "@/app/vender-mi-auto/actions";
import { Button } from "@/components/ui/button";
import { CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { SELL_INTENT, type SellIntentAnswer } from "@/lib/sell-intent";
import type { SellIntentRow, SellIntentViewer } from "@/lib/sell-intent-server";

/** The email link's id and signature, carried through every form of the page. */
function LinkInputs({ viewer }: { viewer: SellIntentViewer }) {
  if (!viewer.link) return null;
  return (
    <>
      <input type="hidden" name="e" value={viewer.link.id} />
      {viewer.link.signature ? <input type="hidden" name="s" value={viewer.link.signature} /> : null}
    </>
  );
}

/** The question with both answers; the email's choice comes marked. Opening the link records nothing. */
export function SellIntentConfirm({ viewer, chosen }: { viewer: SellIntentViewer; chosen: SellIntentAnswer | null }) {
  return (
    <>
      <CardHeader>
        <CardTitle className="text-lg">{SELL_INTENT.question}</CardTitle>
        <CardDescription>{SELL_INTENT.confirm}</CardDescription>
      </CardHeader>
      <CardContent>
        <form action={answerSellIntent} className="space-y-4">
          <LinkInputs viewer={viewer} />
          <fieldset className="flex gap-6">
            <legend className="sr-only">{SELL_INTENT.question}</legend>
            {(["yes", "no"] as const).map((answer) => (
              <label key={answer} className="flex items-center gap-2 text-sm">
                <input type="radio" name="r" value={answer} defaultChecked={answer === chosen} required />
                {answer === "yes" ? SELL_INTENT.yes : SELL_INTENT.no}
              </label>
            ))}
          </fieldset>
          <Button type="submit" className="h-10 w-full">
            {SELL_INTENT.send}
          </Button>
        </form>
      </CardContent>
    </>
  );
}

/** After «Sí»: the honest offer. No price, no amount, nothing that says the reference exists. */
export function SellIntentNotice({ viewer, row, agenciesContact }: { viewer: SellIntentViewer; row: SellIntentRow; agenciesContact: boolean }) {
  return (
    <>
      <CardHeader>
        <CardTitle className="text-lg">{row.wants_notice ? SELL_INTENT.notified : SELL_INTENT.question}</CardTitle>
        <CardDescription>{SELL_INTENT.pitch}</CardDescription>
      </CardHeader>
      <CardContent>
        <form action={requestSellNotice} className="space-y-4">
          <LinkInputs viewer={viewer} />
          {viewer.email ? (
            <p className="text-sm">
              {SELL_INTENT.emailLabel} <b data-testid="sell-intent-email">{viewer.email}</b>
            </p>
          ) : null}
          {agenciesContact ? (
            <label className="flex items-start gap-2 text-sm">
              <input type="checkbox" name="agencias" defaultChecked={row.agencies_contact_ok} className="mt-0.5" />
              {SELL_INTENT.agencies}
            </label>
          ) : null}
          {!row.wants_notice || agenciesContact ? (
            <Button type="submit" className="h-10 w-full">
              {row.wants_notice ? SELL_INTENT.save : SELL_INTENT.notify}
            </Button>
          ) : null}
        </form>
      </CardContent>
    </>
  );
}
