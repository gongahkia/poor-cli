import type { RiskAssessment, RiskLevel } from '@/lib/risk/risk-parser';

const LEVEL_COLORS: Record<RiskLevel, { bg: string; text: string; dot: string }> = {
  HIGH: { bg: 'bg-red-500/10', text: 'text-red-600 dark:text-red-400', dot: 'bg-red-500' },
  MEDIUM: { bg: 'bg-yellow-500/10', text: 'text-yellow-600 dark:text-yellow-400', dot: 'bg-yellow-500' },
  LOW: { bg: 'bg-green-500/10', text: 'text-green-600 dark:text-green-400', dot: 'bg-green-500' },
};

interface Props {
  assessment: RiskAssessment;
}

export function RiskMatrix({ assessment }: Props) {
  if (assessment.flags.length === 0) return null;
  const overall = LEVEL_COLORS[assessment.overall];
  return (
    <div className="my-3 border rounded-md overflow-hidden text-xs">
      <div className={`px-3 py-2 flex items-center justify-between ${overall.bg}`}>
        <span className="font-semibold">Risk Assessment</span>
        <span className={`font-bold ${overall.text}`}>
          Overall: {assessment.overall}
        </span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-px bg-border">
        {assessment.flags.map((flag, i) => {
          const colors = LEVEL_COLORS[flag.level];
          return (
            <div key={i} className={`px-3 py-2 ${colors.bg} bg-background flex items-start gap-2`}>
              <span className={`mt-1 h-2 w-2 rounded-full shrink-0 ${colors.dot}`} />
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="font-medium truncate">{flag.category}</span>
                  <span className={`font-bold ${colors.text}`}>{flag.level}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
      <div className="px-3 py-1.5 text-muted-foreground border-t">
        {assessment.summary}
      </div>
    </div>
  );
}
