import { useState, useMemo } from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { TEMPLATES, renderTemplate, type LegalTemplate } from '@/lib/templates';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onGenerate: (content: string, title: string) => void;
}

export function TemplateLibrary({ isOpen, onClose, onGenerate }: Props) {
  const [selected, setSelected] = useState<LegalTemplate | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [search, setSearch] = useState('');
  const filtered = useMemo(() => {
    if (!search) return TEMPLATES;
    const q = search.toLowerCase();
    return TEMPLATES.filter(
      (t) => t.title.toLowerCase().includes(q) ||
        t.category.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q)
    );
  }, [search]);
  const categories = useMemo(() => [...new Set(TEMPLATES.map((t) => t.category))], []);
  const handleSelect = (t: LegalTemplate) => {
    setSelected(t);
    setValues({});
  };
  const handleGenerate = () => {
    if (!selected) return;
    const rendered = renderTemplate(selected, values);
    onGenerate(rendered, selected.title);
    setSelected(null);
    setValues({});
    onClose();
  };
  const handleBack = () => {
    setSelected(null);
    setValues({});
  };
  return (
    <Dialog open={isOpen} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className="sm:max-w-xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{selected ? selected.title : 'Legal Templates'}</DialogTitle>
        </DialogHeader>
        {!selected ? (
          <div className="space-y-4">
            <Input
              placeholder="Search templates..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="text-sm"
            />
            {categories.map((cat) => {
              const items = filtered.filter((t) => t.category === cat);
              if (items.length === 0) return null;
              return (
                <div key={cat}>
                  <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">{cat}</h3>
                  <div className="space-y-1">
                    {items.map((t) => (
                      <button
                        key={t.id}
                        onClick={() => handleSelect(t)}
                        className="w-full text-left px-3 py-2 rounded-md hover:bg-muted transition-colors"
                      >
                        <div className="text-sm font-medium">{t.title}</div>
                        <div className="text-xs text-muted-foreground">{t.description}</div>
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
            <div className="space-y-3">
              {selected.variables.map((v) => (
                <div key={v.name} className="space-y-1">
                  <Label className="text-xs">{v.label}</Label>
                  <Input
                    type={v.type === 'date' ? 'date' : v.type === 'number' ? 'number' : 'text'}
                    placeholder={v.placeholder}
                    value={values[v.name] || ''}
                    onChange={(e) => setValues((prev) => ({ ...prev, [v.name]: e.target.value }))}
                    className="text-sm"
                  />
                </div>
              ))}
            </div>
            <DialogFooter className="flex justify-between">
              <Button variant="ghost" size="sm" onClick={handleBack}>Back</Button>
              <Button size="sm" onClick={handleGenerate}>Generate Document</Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
