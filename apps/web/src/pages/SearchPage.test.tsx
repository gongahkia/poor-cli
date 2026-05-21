import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { SearchPage } from "@/pages/SearchPage";

describe("SearchPage", () => {
  it("renders the first screen as a plain CDD search form", () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <SearchPage />
      </MemoryRouter>,
    );

    expect(html).toContain("Dude CDD");
    expect(html).toContain("CDD search");
    expect(html).toContain("Company name or UEN");
    expect(html).toContain("Start CDD case");
    expect(html).toContain("Import case JSON");
    expect(html).toContain("Absence of public evidence is not a positive clearance finding");
    expect(html).not.toContain("CSV");
    expect(html).not.toContain("Workspace");
    expect(html).not.toContain("System status");
  });
});
