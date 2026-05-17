import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import AgentPlan, { type AgentPlanTask } from "@/components/ui/agent-plan";

describe("AgentPlan", () => {
  it("renders active tool-call steps with tool labels", () => {
    const tasks: AgentPlanTask[] = [
      {
        id: "dossier",
        title: "Resolve the counterparty identity",
        description: "Call the dossier workflow.",
        status: "in-progress",
        subtasks: [
          {
            id: "tool",
            title: "Call Singapore business dossier",
            description: "Requesting the bounded MCP workflow.",
            status: "in-progress",
            tools: ["sg_business_dossier"],
          },
        ],
      },
    ];

    const html = renderToStaticMarkup(
      <AgentPlan description="Dude is calling official Singapore data tools." tasks={tasks} />,
    );

    expect(html).toContain("Dude is working");
    expect(html).toContain("Resolve the counterparty identity");
    expect(html).toContain("Call Singapore business dossier");
    expect(html).toContain("sg_business_dossier");
  });

  it("keeps status treatment neutral across working states", () => {
    const tasks: AgentPlanTask[] = [
      {
        id: "completed",
        title: "Prepare dossier input",
        description: "Done.",
        status: "completed",
      },
      {
        id: "running",
        title: "Call Singapore business dossier",
        description: "Running.",
        status: "in-progress",
      },
      {
        id: "help",
        title: "Clarify identifiers",
        description: "Needs input.",
        status: "need-help",
      },
      {
        id: "failed",
        title: "Read upstream record",
        description: "Failed.",
        status: "failed",
      },
    ];

    const html = renderToStaticMarkup(<AgentPlan tasks={tasks} />);

    expect(html).toContain("Complete");
    expect(html).toContain("Running");
    expect(html).toContain("Needs input");
    expect(html).toContain("Failed");
    expect(html).not.toMatch(/(?:blue|emerald|amber|red)-/);
  });
});
