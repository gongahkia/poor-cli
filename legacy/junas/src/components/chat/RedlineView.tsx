import { useState, useMemo } from 'react';
import { diffWords, type DiffSegment } from '@/lib/diff/text-diff';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';

interface Props {
  originalText?: string;
  revisedText?: string;
  onAccept?: (finalText: string) => void;
}

export function RedlineView({ originalText = '', revisedText = '', onAccept }: Props) {
  const [original, setOriginal] = useState(originalText);
  const [revised, setRevised] = useState(revisedText);
  const [showInput, setShowInput] = useState(!originalText || !revisedText);
  const [acceptedOps, setAcceptedOps] = useState<Record<number, boolean>>({});

  const segments = useMemo(() => {
    if (!original || !revised) return [];
    return diffWords(original, revised);
  }, [original, revised]);

  const handleAcceptChange = (index: number) => {
    setAcceptedOps((prev) => ({ ...prev, [index]: true }));
  };
  const handleRejectChange = (index: number) => {
    setAcceptedOps((prev) => ({ ...prev, [index]: false }));
  };
  const handleAcceptAll = () => {
    if (onAccept) onAccept(revised);
  };

  const buildFinalText = (): string => {
    return segments.map((seg, i) => {
      if (seg.op === 'equal') return seg.text;
      const accepted = acceptedOps[i];
      if (accepted === undefined) return seg.op === 'delete' ? seg.text : ''; // keep original by default
      if (seg.op === 'insert') return accepted ? seg.text : '';
      if (seg.op === 'delete') return accepted ? '' : seg.text;
      return seg.text;
    }).join('');
  };

  if (showInput) {
    return (
      <div className="space-y-3 p-4 border rounded-md">
        <h3 className="text-sm font-semibold">Contract Redlining</h3>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-muted-foreground">Original</label>
            <Textarea
              value={original}
              onChange={(e) => setOriginal(e.target.value)}
              className="text-xs font-mono min-h-[150px]"
              placeholder="Paste original contract text..."
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground">Revised</label>
            <Textarea
              value={revised}
              onChange={(e) => setRevised(e.target.value)}
              className="text-xs font-mono min-h-[150px]"
              placeholder="Paste revised contract text..."
            />
          </div>
        </div>
        <Button size="sm" onClick={() => setShowInput(false)} disabled={!original || !revised}>
          Compare
        </Button>
      </div>
    );
  }

  const stats = {
    insertions: segments.filter((s) => s.op === 'insert').length,
    deletions: segments.filter((s) => s.op === 'delete').length,
    unchanged: segments.filter((s) => s.op === 'equal').length,
  };

  return (
    <div className="space-y-3 border rounded-md overflow-hidden">
      {/* header */}
      <div className="px-3 py-2 bg-muted/30 flex items-center justify-between text-xs">
        <div className="flex gap-3">
          <span className="text-green-600">+{stats.insertions} additions</span>
          <span className="text-red-600">-{stats.deletions} deletions</span>
          <span className="text-muted-foreground">{stats.unchanged} unchanged</span>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" className="text-xs h-6" onClick={() => setShowInput(true)}>
            Edit
          </Button>
          <Button size="sm" className="text-xs h-6" onClick={handleAcceptAll}>
            Accept All
          </Button>
        </div>
      </div>
      {/* diff view */}
      <div className="px-3 pb-3 text-sm font-mono leading-relaxed whitespace-pre-wrap">
        {segments.map((seg, i) => {
          const decided = acceptedOps[i] !== undefined;
          if (seg.op === 'equal') {
            return <span key={i}>{seg.text}</span>;
          }
          if (seg.op === 'insert') {
            return (
              <span
                key={i}
                className={`${decided ? (acceptedOps[i] ? 'bg-green-500/20' : 'bg-muted line-through opacity-40') : 'bg-green-500/15 underline decoration-green-500'} cursor-pointer`}
                onClick={() => decided ? undefined : handleAcceptChange(i)}
                onContextMenu={(e) => { e.preventDefault(); handleRejectChange(i); }}
                title="Click to accept, right-click to reject"
              >
                {seg.text}
              </span>
            );
          }
          // delete
          return (
            <span
              key={i}
              className={`${decided ? (acceptedOps[i] ? 'hidden' : 'bg-muted') : 'bg-red-500/15 line-through decoration-red-500'} cursor-pointer`}
              onClick={() => decided ? undefined : handleAcceptChange(i)}
              onContextMenu={(e) => { e.preventDefault(); handleRejectChange(i); }}
              title="Click to accept deletion, right-click to keep"
            >
              {seg.text}
            </span>
          );
        })}
      </div>
    </div>
  );
}
