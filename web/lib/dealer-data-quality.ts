/**
 * Agencias: how complete the agency's data is. The km and the trim decide which
 * cars a price is compared against (dealer_market_ref's basis); a car without
 * them is compared loosely, and the panel says so loudly. Pure.
 */

const nf = new Intl.NumberFormat("es-AR");

export function missingData(cars: { km: number | null; trim: string | null }[]): { total: number; km: number; trim: number } {
  return {
    total: cars.length,
    km: cars.filter((c) => c.km == null || c.km <= 0).length,
    trim: cars.filter((c) => !c.trim || !c.trim.trim()).length,
  };
}

/** «8 de 35 autos no tienen kilómetros y 3 no tienen versión.»; null when every car has both. */
export function missingDataText(cars: { km: number | null; trim: string | null }[]): string | null {
  const m = missingData(cars);
  if (m.km === 0 && m.trim === 0) return null;
  const of = (n: number) => `${nf.format(n)} de ${nf.format(m.total)} ${m.total === 1 ? "auto" : "autos"}`;
  const have = (n: number) => (n === 1 ? "no tiene" : "no tienen");
  if (m.km > 0 && m.trim > 0) return `${of(m.km)} ${have(m.km)} kilómetros y ${nf.format(m.trim)} ${have(m.trim)} versión.`;
  return m.km > 0 ? `${of(m.km)} ${have(m.km)} kilómetros.` : `${of(m.trim)} ${have(m.trim)} versión.`;
}
