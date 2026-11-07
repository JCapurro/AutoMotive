"use client";

import { useEffect } from "react";

/** A link to a folded chapter (#mantenimiento) opens it: the index at the top never leads to a closed box. */
export function GuideChapterOpener() {
  useEffect(() => {
    function open() {
      const id = decodeURIComponent(location.hash.slice(1));
      const target = id ? document.getElementById(id) : null;
      const details = target?.closest("details");
      if (details && !details.open) {
        details.open = true;
        target?.scrollIntoView();
      }
    }
    open();
    window.addEventListener("hashchange", open);
    return () => window.removeEventListener("hashchange", open);
  }, []);
  return null;
}
