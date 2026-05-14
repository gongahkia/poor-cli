import { useEffect, useState, useMemo } from 'react';
import { CommandInfo } from '@/lib/commands/definitions';
import {
  createCommandSearch,
  getAvailableCommands,
  getCommandMatches,
} from '@/lib/commands/search';
import { cn } from '@/lib/utils';
import { isOnnxRuntimeAvailable } from '@/lib/ml/model-manager';

interface CommandSuggestionsProps {
  query: string;
  onSelect: (command: string) => void;
  isOpen: boolean;
  selectedIndex: number;
}

export function CommandSuggestions({
  query,
  onSelect,
  isOpen,
  selectedIndex,
}: CommandSuggestionsProps) {
  const [onnxAvailable, setOnnxAvailable] = useState(true);
  const [matches, setMatches] = useState<CommandInfo[]>([]);
  const availableCommands = useMemo(() => getAvailableCommands(onnxAvailable), [onnxAvailable]);

  const commandSearchIndex = useMemo(
    () => createCommandSearch(availableCommands),
    [availableCommands]
  );

  useEffect(() => {
    let isMounted = true;
    isOnnxRuntimeAvailable().then((available) => {
      if (isMounted) setOnnxAvailable(available);
    });
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    setMatches(getCommandMatches(query, availableCommands, commandSearchIndex));
  }, [query, availableCommands, commandSearchIndex]);

  if (!isOpen) return null;

  return (
    <div className="absolute bottom-full left-0 w-full mb-2 bg-popover border border-border rounded-md shadow-lg overflow-hidden z-50 max-h-[300px] overflow-y-auto">
      <div className="p-1">
        <div className="text-[10px] text-muted-foreground px-2 py-1 uppercase tracking-wider font-semibold border-b border-border/50 mb-1">
          Commands
        </div>
        {matches.length === 0 ? (
          <div className="px-2 py-2 text-xs text-muted-foreground">No matching commands.</div>
        ) : (
          matches.map((cmd, index) => (
            <button
              key={cmd.id}
              onClick={() => onSelect(cmd.id)}
              className={cn(
                'w-full text-left px-2 py-2 text-sm rounded flex flex-col gap-0.5 transition-colors font-mono',
                index === selectedIndex
                  ? 'bg-accent text-accent-foreground'
                  : 'hover:bg-muted/50 text-foreground'
              )}
            >
              <div className="flex items-center justify-between w-full">
                <span className="font-semibold">/{cmd.id}</span>
                {cmd.isLocal && (
                  <span className="text-[10px] bg-green-500/10 text-green-600 px-1.5 py-0.5 rounded">
                    LOCAL
                  </span>
                )}
              </div>
              <span className="text-xs text-muted-foreground line-clamp-1">{cmd.description}</span>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
