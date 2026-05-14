import type { WorkflowPlan, StepStatus } from '@/lib/agents/workflow';
import { Loader2, CheckCircle2, XCircle, Clock } from 'lucide-react';

const STATUS_ICON: Record<StepStatus, React.ReactNode> = {
  pending: <Clock className="h-3.5 w-3.5 text-muted-foreground" />,
  running: <Loader2 className="h-3.5 w-3.5 text-primary animate-spin" />,
  done: <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />,
  error: <XCircle className="h-3.5 w-3.5 text-red-500" />,
};

interface Props {
  plan: WorkflowPlan;
}

export function AgentProgress({ plan }: Props) {
  const completed = plan.steps.filter((s) => s.status === 'done').length;
  const total = plan.steps.length;
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
  return (
    <div className="border rounded-md overflow-hidden text-xs">
      {/* header */}
      <div className="px-3 py-2 bg-muted/30 flex items-center justify-between">
        <span className="font-semibold">{plan.title}</span>
        <span className="text-muted-foreground">{pct}% ({completed}/{total})</span>
      </div>
      {/* progress bar */}
      <div className="h-1 bg-muted">
        <div className="h-full bg-primary transition-all duration-300" style={{ width: `${pct}%` }} />
      </div>
      {/* steps */}
      <div className="px-3 py-2 space-y-1.5">
        {plan.steps.map((step) => (
          <div key={step.id} className="flex items-start gap-2">
            <span className="mt-0.5 shrink-0">{STATUS_ICON[step.status]}</span>
            <div className="min-w-0 flex-1">
              <span className={step.status === 'done' ? 'text-muted-foreground' : ''}>{step.label}</span>
              {step.error && <p className="text-red-500 mt-0.5">{step.error}</p>}
            </div>
          </div>
        ))}
      </div>
      {/* final output */}
      {plan.finalOutput && (
        <div className="px-3 py-2 border-t text-xs">
          <div className="font-semibold mb-1">Result:</div>
          <div className="whitespace-pre-wrap text-muted-foreground">{plan.finalOutput.slice(0, 500)}...</div>
        </div>
      )}
    </div>
  );
}
