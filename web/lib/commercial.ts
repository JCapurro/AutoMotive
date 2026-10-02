import { z } from "zod";
import { WAITLIST_PLANS } from "@/lib/pro";

const PriceInput = z.object({ amount: z.number().int().positive().safe(), currency: z.literal("ARS"), days: z.literal(30) }).strict();
export const CommercialOfferInput = z.object({ version: z.string().trim().min(1).max(80), pass_30: PriceInput, pro_monthly: PriceInput }).strict();

export const PaymentInput = z.object({
  userId: z.uuid(), offer: z.enum(WAITLIST_PLANS),
  provider: z.string().trim().min(2).max(80),
  reference: z.string().trim().min(3).max(160),
  paidAt: z.iso.datetime({ offset: true }),
  note: z.string().trim().max(1000).optional(),
  verified: z.literal(true, { error: "Confirmá que verificaste el pago en el proveedor." }),
});
export const COMMERCIAL_ERRORS: Record<string, string> = {
  payment_reference_conflict: "Esa referencia ya pertenece a otra cuenta o plan.",
  paid_plan_already_active: "La cuenta ya tiene un período pago vigente. Solo Agencia permite renovar por adelantado.",
  invalid_payment: "Revisá la referencia y la fecha: debe ser un pago de los últimos 30 días, sin fecha futura.",
  invalid_offer: "La oferta de cobro no está configurada correctamente.",
  admin_required: "Solo un administrador puede confirmar pagos.",
  refund_newer_period_first: "Registrá primero la devolución de los períodos más nuevos de esta cuenta.",
};
export function commercialError(message: string): string {
  const known = Object.keys(COMMERCIAL_ERRORS).find((key) => message.includes(key));
  return known ? COMMERCIAL_ERRORS[known] : "No pudimos guardar la operación. Revisá los datos y probá nuevamente.";
}
