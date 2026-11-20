import { AlertTriangle, ClipboardList } from "lucide-react";
import Link from "next/link";

import { missingDataText } from "@/lib/dealer-data-quality";

/**
 * Juan, 20/11: «necesitamos que la información esté clarísima». What every car
 * needs for the panel's numbers to mean something, said before anything is
 * loaded (the spreadsheet page and the one-car form).
 */
export function DataNeeded() {
  return (
    <div className="max-w-2xl rounded-lg border-2 border-foreground p-4" data-testid="data-needed">
      <p className="flex items-center gap-2 text-[15px] font-bold">
        <ClipboardList className="size-4 shrink-0" aria-hidden /> Para que los números sirvan, cada auto necesita estos datos
      </p>
      <ul className="mt-2 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
        <li><b className="font-semibold">Marca y modelo</b>: Ford Focus, no solo «Focus»</li>
        <li><b className="font-semibold">Versión</b>: S 1.6, Titanium 2.0 AT…</li>
        <li><b className="font-semibold">Año</b>: el del auto, con cuatro cifras</li>
        <li><b className="font-semibold">Kilómetros</b>: los reales, es lo que más mueve el precio</li>
        <li><b className="font-semibold">Precio de venta</b>: el que pedís, no lo que pagaste</li>
        <li><b className="font-semibold">Moneda</b>: pesos o dólares, escrito</li>
      </ul>
      <p className="mt-2 text-sm">
        Sin kilómetros o sin versión el auto se carga igual, pero lo comparamos contra autos de cualquier uso y el precio de mercado
        que ves <b className="font-semibold">no es confiable</b>.
      </p>
    </div>
  );
}

/**
 * How many cars lack the km or the trim, loud: in the spreadsheet's preview
 * (before loading) and on top of the stock (after). Nothing when all have both.
 */
export function MissingDataNotice({ cars, where, firstHref }: {
  cars: { km: number | null; trim: string | null }[];
  where: "sheet" | "stock";
  /** Stock only: the first car to complete. */
  firstHref?: string | null;
}) {
  const text = missingDataText(cars);
  if (!text) return null;
  return (
    <div role="status" className="flex max-w-3xl items-start gap-2.5 rounded-lg bg-warn-soft p-4 text-[15px]" data-testid="missing-data">
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warn" aria-hidden />
      <p>
        <b className="font-semibold">{text}</b>{" "}
        {where === "sheet"
          ? "Los podés cargar igual, pero su precio de mercado no va a ser confiable. Lo mejor: completá esos datos en la planilla y subila de nuevo."
          : "Mientras falten, su precio contra el mercado no es confiable: los comparamos con autos de cualquier uso."}
        {where === "stock" && firstHref ? <> <Link href={firstHref} className="font-semibold underline underline-offset-2">Completar el primero</Link></> : null}
      </p>
    </div>
  );
}
