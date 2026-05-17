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
    expect(html).toContain("ACRA identity lookup");
    expect(html).toContain("Search company name or UEN");
    expect(html).not.toContain("No counterparty selected");
  });
});
