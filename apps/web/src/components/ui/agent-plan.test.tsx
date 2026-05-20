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
            title: "Run CDD orchestrator",
            description: "Requesting the ACRA-gated CDD workflow.",
            status: "in-progress",
            tools: ["cdd-orchestrator"],
          },
        ],
      },
    ];

    const html = renderToStaticMarkup(
      <AgentPlan description="Dude is calling official Singapore data tools." tasks={tasks} />,
    );

    expect(html).toContain("Dude is working");
    expect(html).toContain("Resolve the counterparty identity");
    expect(html).toContain("Run CDD orchestrator");
    expect(html).toContain("cdd-orchestrator");
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
        title: "Run CDD orchestrator",
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
