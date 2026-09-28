import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-3 px-4 text-center">
      <p className="text-4xl">🚗💨</p>
      <h1 className="text-xl font-semibold">No encontramos esta página</h1>
      <p className="text-sm text-muted-foreground">Puede que la publicación o la búsqueda ya no exista.</p>
      <Link href="/app" className="text-sm underline">
        Volver al inicio
      </Link>
    </main>
  );
}
