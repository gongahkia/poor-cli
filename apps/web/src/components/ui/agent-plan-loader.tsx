import { lazy, Suspense } from "react";

import { cn } from "@/lib/utils";
import type { AgentPlanProps } from "@/components/ui/agent-plan";

const LazyAgentPlan = lazy(() => import("@/components/ui/agent-plan"));

export function AgentPlan({
  className,
  description,
  title = "Swee SG is working",
  ...props
}: AgentPlanProps) {
  return (
    <Suspense
      fallback={(
        <section className={cn("min-w-0 rounded-lg border border-border bg-card shadow-sm", className)}>
          <div className="border-b border-border px-4 py-3 sm:px-5">
            <h2 className="text-base font-semibold tracking-normal text-foreground">{title}</h2>
            {description === undefined ? null : (
              <p className="mt-1 break-words text-sm leading-6 text-muted-foreground">{description}</p>
            )}
          </div>
          <div className="p-5 text-sm text-muted-foreground">Loading plan...</div>
        </section>
      )}
    >
      <LazyAgentPlan
        className={className}
        description={description}
        title={title}
        {...props}
      />
    </Suspense>
  );
}
