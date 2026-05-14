import { FileText, X } from 'lucide-react';
import type { ParsedDocument } from '@/lib/tauri-bridge';

interface Props {
  doc: ParsedDocument;
  onRemove: () => void;
}

export function DocumentPreview({ doc, onRemove }: Props) {
  const sizeLabel = doc.char_count > 1000
    ? `${(doc.char_count / 1000).toFixed(1)}k chars`
    : `${doc.char_count} chars`;
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-muted text-xs border">
      <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      <span className="truncate max-w-[180px] font-medium">{doc.filename}</span>
      <span className="text-muted-foreground">
        {doc.page_count}p &middot; {sizeLabel}
      </span>
      <button onClick={onRemove} className="ml-auto hover:text-destructive">
        <X className="h-3 w-3" />
      </button>
    </div>
  );
}
