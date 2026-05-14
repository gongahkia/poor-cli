import { useState, useMemo } from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { CLAUSE_LIBRARY, searchClauses, type LegalClause } from '@/lib/clauses';

type Variant = 'standardWording' | 'aggressive' | 'balanced' | 'protective';
const VARIANTS: { key: Variant; label: string; color: string }[] = [
  { key: 'standardWording', label: 'Standard', color: 'text-foreground' },
  { key: 'aggressive', label: 'Aggressive', color: 'text-red-600' },
  { key: 'balanced', label: 'Balanced', color: 'text-yellow-600' },
  { key: 'protective', label: 'Protective', color: 'text-green-600' },
];

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onInsert?: (text: string) => void;
}

export function ClauseLibrary({ isOpen, onClose, onInsert }: Props) {
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<LegalClause | null>(null);
  const [variant, setVariant] = useState<Variant>('standardWording');
  const results = useMemo(() => searchClauses(search), [search]);
  const categories = useMemo(() => [...new Set(CLAUSE_LIBRARY.map((c) => c.category))], []);
  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
  };
  return (
    <Dialog open={isOpen} onOpenChange={(open) => { if (!open) { onClose(); setSelected(null); } }}>
      <DialogContent className="sm:max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{selected ? selected.name : 'Clause Library'}</DialogTitle>
        </DialogHeader>
        {!selected ? (
          <div className="space-y-4">
            <Input placeholder="Search clauses..." value={search} onChange={(e) => setSearch(e.target.value)} className="text-sm" />
            {categories.map((cat) => {
              const items = results.filter((c) => c.category === cat);
              if (items.length === 0) return null;
              return (
                <div key={cat}>
                  <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">{cat}</h3>
                  <div className="space-y-1">
                    {items.map((c) => (
                      <button key={c.id} onClick={() => { setSelected(c); setVariant('standardWording'); }}
                        className="w-full text-left px-3 py-2 rounded-md hover:bg-muted transition-colors">
                        <div className="text-sm font-medium">{c.name}</div>
                        <div className="text-xs text-muted-foreground">{c.description}</div>
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="space-y-4">
            <p className="text-xs text-muted-foreground">{selected.description}</p>
            {/* variant tabs */}
            <div className="flex gap-1 border-b">
              {VARIANTS.map((v) => (
                <button key={v.key} onClick={() => setVariant(v.key)}
                  className={`px-3 py-1.5 text-xs font-medium border-b-2 transition-colors ${variant === v.key ? `${v.color} border-current` : 'text-muted-foreground border-transparent hover:text-foreground'}`}>
                  {v.label}
                </button>
              ))}
            </div>
            {/* clause text */}
            <div className="text-sm leading-relaxed p-3 bg-muted/20 rounded-md font-mono whitespace-pre-wrap">
              {selected[variant]}
            </div>
            {/* notes */}
            {selected.notes && (
              <div className="text-xs text-muted-foreground p-2 bg-muted/10 rounded border-l-2 border-primary/30">
                <span className="font-semibold">Practice Note:</span> {selected.notes}
              </div>
            )}
            {/* actions */}
            <div className="flex gap-2">
              <Button variant="ghost" size="sm" onClick={() => setSelected(null)}>Back</Button>
              <Button variant="outline" size="sm" onClick={() => handleCopy(selected[variant])}>Copy</Button>
              {onInsert && (
                <Button size="sm" onClick={() => { onInsert(selected[variant]); onClose(); setSelected(null); }}>
                  Insert into Chat
                </Button>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
