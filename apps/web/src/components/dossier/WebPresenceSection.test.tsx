import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { WebPresenceSection } from "@/components/dossier/WebPresenceSection";

describe("WebPresenceSection", () => {
  it("renders configured results", () => {
    const html = renderToStaticMarkup(<WebPresenceSection state={{
      presence: {
        configured: true,
        limits: ["Web discovery is supplemental."],
        possibleOfficialWebsite: "https://www.dbs.com.sg/",
        query: "DBS BANK",
        results: [{
          position: 1,
          siteName: "DBS",
          snippet: "Official site fixture.",
          title: "DBS Bank Singapore",
          url: "https://www.dbs.com.sg/",
        }],
      },
      status: "success",
    }} />);

    expect(html).toContain("DBS Bank Singapore");
    expect(html).toContain("Web discovery is supplemental.");
    expect(html).toContain("Read more");
    expect(html).toContain("href=\"https://www.dbs.com.sg/\"");
  });

  it("moves trailing read-more snippet copy into the clickable result action", () => {
    const html = renderToStaticMarkup(<WebPresenceSection state={{
      presence: {
        configured: true,
        limits: [],
        possibleOfficialWebsite: null,
        query: "P M A SATHAR AND COMPANY",
        results: [{
          position: 1,
          siteName: "Singapore Business Directory",
          snippet: "Operating Status Live as on 13 ...Read more",
          title: "P M A SATHAR AND COMPANY (03591300B) - Singapore",
          url: "https://example.com/company",
        }],
      },
      status: "success",
    }} />);

    expect(html).toContain("Operating Status Live as on 13");
    expect(html).not.toContain("...Read more");
    expect(html).toContain("aria-label=\"Read more: P M A SATHAR AND COMPANY");
    expect(html).toContain("href=\"https://example.com/company\"");
  });

  it("renders unconfigured and error states", () => {
    expect(renderToStaticMarkup(<WebPresenceSection state={{
      presence: {
        configured: false,
        limits: [],
        possibleOfficialWebsite: null,
        query: "DBS BANK",
        results: [],
      },
      status: "success",
    }} />)).toContain("TinyFish Search is not configured");

    expect(renderToStaticMarkup(<WebPresenceSection state={{
      message: "Gateway failed",
      status: "error",
    }} />)).toContain("Gateway failed");
  });
});
