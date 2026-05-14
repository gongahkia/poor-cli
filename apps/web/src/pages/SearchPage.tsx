import { DiligenceSearch } from "@/components/search/DiligenceSearch";

export function SearchPage() {
  return (
    <main className="min-h-screen bg-background px-6 py-16">
      <section className="mx-auto flex w-full max-w-3xl flex-col gap-8">
        <div className="space-y-3">
          <p className="text-sm font-medium text-muted-foreground">Dude</p>
          <h1 className="text-4xl font-semibold tracking-normal text-foreground sm:text-5xl">
            Singapore due diligence in 30 seconds
          </h1>
        </div>

        <DiligenceSearch />
      </section>
    </main>
  );
}
