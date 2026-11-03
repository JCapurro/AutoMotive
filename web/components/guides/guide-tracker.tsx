"use client";

import { useEffect, useRef } from "react";

import { guideViewItem, logGuideEvent } from "@/components/guides/guide-events";

/** guide_viewed and GA4 view_item (item_category = guide), once per page load. */
export function GuideTracker({ slugMake, slugModel, name }: { slugMake: string; slugModel: string; name: string }) {
  // Strict Mode remounts effects in development; the ref survives it, so it counts once.
  const done = useRef<string | null>(null);
  useEffect(() => {
    const key = `${slugMake}/${slugModel}`;
    if (done.current === key) return;
    done.current = key;
    logGuideEvent("guide_viewed", slugMake, slugModel);
    guideViewItem(slugMake, slugModel, name);
  }, [slugMake, slugModel, name]);
  return null;
}
