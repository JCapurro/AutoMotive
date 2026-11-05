import { Check } from "lucide-react";

/**
 * A plan card on Planes and the landing: one column on wide screens (eight
 * subgrid rows, so prices and buttons line up across cards), one slide of the
 * carousel below lg. Shared by the server cards and the client Particular card.
 */
export const PLAN_CARD = "flex w-[85%] max-w-[22rem] shrink-0 snap-center flex-col rounded-lg border bg-card p-5 transition-opacity motion-reduce:transition-none max-lg:data-[active=false]:opacity-50 lg:row-span-8 lg:grid lg:w-auto lg:max-w-none lg:grid-rows-subgrid lg:gap-y-0";

export function PlanFeatures({ items }: { items: string[] }) {
  return (
    <ul className="mt-5 space-y-3 border-t pt-5 text-sm">
      {items.map((item) => (
        <li key={item} className="flex items-start gap-2.5">
          <Check aria-hidden className="mt-0.5 size-4 shrink-0" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}
