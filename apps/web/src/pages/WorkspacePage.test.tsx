import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ToastProvider } from "@/components/notifications/ToastProvider";
import { WorkspacePanel } from "@/pages/WorkspacePage";

describe("WorkspacePanel", () => {
  it("keeps the audit log in an internal scroll region", () => {
    const html = renderToStaticMarkup(
      <ToastProvider>
        <WorkspacePanel />
      </ToastProvider>,
    );

    expect(html).toContain("Audit log");
    expect(html).toContain("max-h-[60vh] overflow-auto");
    expect(html).toContain("sticky top-0");
  });
});
