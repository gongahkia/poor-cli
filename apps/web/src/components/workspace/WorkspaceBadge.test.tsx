import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { WorkspaceBadge } from "@/components/workspace/WorkspaceBadge";

describe("WorkspaceBadge", () => {
  it("opens workspace as a dialog trigger instead of navigating to a page", () => {
    const html = renderToStaticMarkup(<WorkspaceBadge />);

    expect(html).toContain("Open workspace");
    expect(html).not.toContain(">admin<");
    expect(html).not.toContain("href=\"/workspace\"");
  });
});
