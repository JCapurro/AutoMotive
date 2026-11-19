import { DealerProfileForm } from "@/components/agencia/dealer-profile-form";

/** /agencia without an agency yet: what the panel gives, and the form. */
export function DealerSignupForm() {
  return (
    <section className="space-y-5" data-testid="dealer-signup">
      <div className="max-w-2xl space-y-2">
        <h1 className="type-heading text-[1.9rem] leading-tight">Tu stock, contra el mercado</h1>
        <p className="text-[15px] text-muted-foreground">
          Cargá tus autos y te mostramos, por cada uno, cómo está de precio contra autos parecidos y cuánta gente lo busca.
          Es gratis mientras dure el piloto.
        </p>
      </div>
      <DealerProfileForm mode="create" />
    </section>
  );
}
