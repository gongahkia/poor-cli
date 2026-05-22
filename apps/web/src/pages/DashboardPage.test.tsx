import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { App } from "@/App";
import { DashboardPage } from "@/pages/DashboardPage";

describe("DashboardPage", () => {
  it("renders the Swee SG dashboard shell without CDD copy", () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    );

    expect(html).toContain("Swee SG");
    expect(html).toContain("Overview");
    expect(html).toContain("Mobility");
    expect(html).toContain("Weather");
    expect(html).toContain("Sources");
    expect(html).toContain("Shield Audit");
    expect(html).not.toContain("Dude CDD");
    expect(html).not.toContain("CDD case");
    expect(html).not.toContain("counterparty");
  });

  it("keeps the active app surface on the dashboard route", () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );

    expect(html).toContain("Swee SG");
    expect(html).not.toContain("Running CDD orchestrator");
  });
});
