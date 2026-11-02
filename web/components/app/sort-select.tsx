"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { trackMarginSort } from "@/app/app/searches/margin-actions";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { PRO_LOCKED } from "@/lib/copy";
import { type Sort, SORTS, sortsFor } from "@/lib/sorts";

/**
 * §29 "Orden": keeps the filter, drops the page. `options`: the orders the
 * user can pick (PRO-02: «Mayor margen estimado» only for Pro); choosing it
 * records results_sorted_margin for `profileId`. `locked`: Pro's orders the
 * plan doesn't include, in view and disabled (Juan, 02/11).
 */
export function SortSelect({ value, options = sortsFor(false), locked = [], profileId }: { value: Sort; options?: Sort[]; locked?: Sort[]; profileId?: number }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  return (
    <NativeSelect
      size="sm"
      aria-label="Ordenar"
      value={value}
      onChange={(e) => {
        const next = new URLSearchParams(params);
        next.set("s", e.target.value);
        next.delete("p");
        if (e.target.value === "margin" && profileId != null) void trackMarginSort(profileId).catch(() => undefined);
        router.push(`${pathname}?${next}`);
      }}
    >
      {options.map((s) => (
        <NativeSelectOption key={s} value={s}>
          {SORTS[s]}
        </NativeSelectOption>
      ))}
      {/* Greyed: the options' own text color would hide that it's disabled. */}
      {locked.filter((s) => !options.includes(s)).map((s) => (
        <NativeSelectOption key={s} value={s} disabled className="text-muted-foreground">
          {PRO_LOCKED.sort.replace("{sort}", SORTS[s])}
        </NativeSelectOption>
      ))}
    </NativeSelect>
  );
}
