import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { ToastProvider } from "@/components/notifications/ToastProvider";
import { DiligenceSearch } from "@/components/search/DiligenceSearch";

describe("DiligenceSearch", () => {
  it("does not render a false no-counterparty empty state before search", () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <ToastProvider>
          <DiligenceSearch />
        </ToastProvider>
      </MemoryRouter>,
    );

    expect(html).toContain("Client or counterparty company name or UEN");
    expect(html).toContain("Company name, UEN, or multiple rows");
    expect(html).toContain("CSV");
    expect(html).not.toContain("ACRA identity lookup");
    expect(html).not.toContain("Search company name or UEN");
    expect(html).not.toContain("rounded-full border border-border bg-background px-3 py-1.5");
    expect(html).not.toContain("No counterparty selected");
  });

  it("renders the tools action on the search bar row", () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <ToastProvider>
          <DiligenceSearch secondaryAction={<button type="button">Tools</button>} />
        </ToastProvider>
      </MemoryRouter>,
    );

    expect(html).toContain("Tools");
    expect(html).toContain("shrink-0 self-center");
  });
});
