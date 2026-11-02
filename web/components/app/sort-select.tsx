"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { trackMarginSort } from "@/app/app/searches/margin-actions";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { type Sort, SORTS, sortsFor } from "@/lib/sorts";

/**
 * §29 "Orden": keeps the filter, drops the page. `options`: the orders the
 * user can pick (PRO-02: «Mayor margen estimado» only for Pro); choosing it
 * records results_sorted_margin for `profileId`.
 */
export function SortSelect({ value, options = sortsFor(false), profileId }: { value: Sort; options?: Sort[]; profileId?: number }) {
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
    </NativeSelect>
  );
}
