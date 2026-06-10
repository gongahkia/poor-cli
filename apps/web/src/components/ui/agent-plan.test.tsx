import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import AgentPlan, { type AgentPlanTask } from "@/components/ui/agent-plan";

describe("AgentPlan", () => {
  it("renders active tool-call steps with tool labels", () => {
    const tasks: AgentPlanTask[] = [
      {
        id: "pulse",
        title: "Build the Pulse snapshot",
        description: "Call the city-signal workflow.",
        status: "in-progress",
        subtasks: [
          {
            id: "tool",
            title: "Run Pulse aggregator",
            description: "Requesting source-backed mobility and weather signals.",
            status: "in-progress",
            tools: ["swee_pulse_snapshot"],
          },
        ],
      },
    ];

    const html = renderToStaticMarkup(
      <AgentPlan description="Swee SG is calling official Singapore data tools." tasks={tasks} />,
    );

    expect(html).toContain("Swee SG is working");
    expect(html).toContain("Build the Pulse snapshot");
    expect(html).toContain("Run Pulse aggregator");
    expect(html).toContain("swee_pulse_snapshot");
  });

  it("keeps status treatment neutral across working states", () => {
    const tasks: AgentPlanTask[] = [
      {
        id: "completed",
        title: "Prepare Pulse input",
        description: "Done.",
        status: "completed",
      },
      {
        id: "running",
        title: "Run Pulse aggregator",
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
