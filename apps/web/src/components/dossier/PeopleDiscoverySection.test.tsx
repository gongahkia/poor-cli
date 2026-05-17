import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { PeopleDiscoverySection } from "@/components/dossier/PeopleDiscoverySection";

describe("PeopleDiscoverySection", () => {
  it("renders candidate people results with explicit verification limits", () => {
    const html = renderToStaticMarkup(<PeopleDiscoverySection state={{
      discovery: {
        configured: true,
        entityName: "DBS PTE. LTD.",
        limits: ["Candidate people references are not verified employees."],
        query: "\"DBS PTE. LTD.\" Singapore employees directors leadership LinkedIn",
        results: [{
          position: 1,
          siteName: "LinkedIn",
          snippet: "Example Person - DBS - Singapore",
          title: "Example Person - DBS",
          url: "https://www.linkedin.com/in/example",
        }],
        suggestedActions: ["Verify each person's current role through official or company-controlled sources before relying on it."],
        uen: "197700546G",
      },
      status: "success",
    }} />);

    expect(html).toContain("People Follow-up");
    expect(html).toContain("Example Person - DBS");
    expect(html).toContain("Review result");
    expect(html).toContain("Candidate people references are not verified employees.");
    expect(html).toContain("Verify each person");
  });
});
