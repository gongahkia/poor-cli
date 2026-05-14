import { useState, useMemo } from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import {
  DEFAULT_SG_RULES, checkCompliance, loadCustomRules,
  type ComplianceCheckResult, type ComplianceStatus,
} from '@/lib/compliance/rules';

const STATUS_STYLES: Record<ComplianceStatus, { dot: string; bg: string; label: string }> = {
  pass: { dot: 'bg-green-500', bg: 'bg-green-500/10', label: 'Pass' },
  warning: { dot: 'bg-yellow-500', bg: 'bg-yellow-500/10', label: 'Warning' },
  fail: { dot: 'bg-red-500', bg: 'bg-red-500/10', label: 'Fail' },
  unchecked: { dot: 'bg-gray-400', bg: 'bg-muted', label: 'Unchecked' },
};
const SEVERITY_BADGE: Record<string, string> = {
  high: 'text-red-600 bg-red-500/10',
  medium: 'text-yellow-600 bg-yellow-500/10',
  low: 'text-muted-foreground bg-muted',
};

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

export function ComplianceDashboard({ isOpen, onClose }: Props) {
  const [text, setText] = useState('');
  const [results, setResults] = useState<ComplianceCheckResult[] | null>(null);
  const allRules = useMemo(() => [...DEFAULT_SG_RULES, ...loadCustomRules()], []);
  const handleCheck = () => {
    if (!text.trim()) return;
    setResults(checkCompliance(text, allRules));
  };
  const summary = useMemo(() => {
    if (!results) return null;
    const pass = results.filter((r) => r.status === 'pass').length;
    const warn = results.filter((r) => r.status === 'warning').length;
    const fail = results.filter((r) => r.status === 'fail').length;
    return { pass, warn, fail, total: results.length };
  }, [results]);
  const categories = useMemo(() => {
    if (!results) return [];
    return [...new Set(allRules.map((r) => r.category))];
  }, [results, allRules]);
  return (
    <Dialog open={isOpen} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className="sm:max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Compliance Dashboard</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          {!results ? (
            <>
              <Textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Paste contract or document text to check compliance..."
                className="min-h-[200px] text-sm font-mono"
              />
              <Button size="sm" onClick={handleCheck} disabled={!text.trim()}>
                Run Compliance Check
              </Button>
            </>
          ) : (
            <>
              {/* summary bar */}
              {summary && (
                <div className="flex items-center gap-4 text-xs px-3 py-2 border rounded-md bg-muted/20">
                  <span className="font-semibold">Results:</span>
                  <span className="text-green-600">{summary.pass} pass</span>
                  <span className="text-yellow-600">{summary.warn} warnings</span>
                  <span className="text-red-600">{summary.fail} fail</span>
                  <span className="text-muted-foreground">/ {summary.total} rules</span>
                  <Button variant="ghost" size="sm" className="ml-auto text-xs h-6" onClick={() => setResults(null)}>
                    New Check
                  </Button>
                </div>
              )}
              {/* results by category */}
              {categories.map((cat) => {
                const catResults = results.filter((r) => {
                  const rule = allRules.find((ar) => ar.id === r.ruleId);
                  return rule?.category === cat;
                });
                if (catResults.length === 0) return null;
                return (
                  <div key={cat}>
                    <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">{cat}</h3>
                    <div className="space-y-1">
                      {catResults.map((r) => {
                        const style = STATUS_STYLES[r.status];
                        const sevStyle = SEVERITY_BADGE[r.severity] || '';
                        return (
                          <div key={r.ruleId} className={`flex items-start gap-2 px-3 py-2 rounded-md ${style.bg}`}>
                            <span className={`mt-1.5 h-2 w-2 rounded-full shrink-0 ${style.dot}`} />
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="text-xs font-medium">{r.ruleName}</span>
                                <span className={`text-[10px] px-1.5 py-0.5 rounded ${sevStyle}`}>{r.severity}</span>
                                <span className="text-[10px] text-muted-foreground ml-auto">{style.label}</span>
                              </div>
                              <p className="text-[11px] text-muted-foreground mt-0.5">{r.details}</p>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
