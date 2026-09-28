import { Logo } from "@/components/logo";
import { SiteFooter } from "@/components/site-footer";

/** The frame of /privacidad and /terminos: plain, readable text. */
export function LegalPage({ title, updated, children }: { title: string; updated: string; children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="mx-auto flex w-full max-w-3xl items-center px-4 py-4">
        <Logo />
      </header>
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 pt-4 pb-16">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">Última actualización: {updated}</p>
        <div className="mt-8 space-y-4 text-[15px] leading-relaxed [&_h2]:mt-8 [&_h2]:text-lg [&_h2]:font-semibold [&_li]:ml-5 [&_li]:list-disc [&_a]:underline">
          {children}
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}

/** How to reach us (NEXT_PUBLIC_CONTACT_EMAIL; set it before opening the pilot). */
export function Contact({ email }: { email: string }) {
  return email ? <a href={`mailto:${email}`}>{email}</a> : <>el email de contacto del piloto</>;
}
