import { useState, useEffect, useRef, useMemo } from 'react';
import {
  Search,
  Settings,
  Info,
  Book,
  Plus,
  FileText,
  Users,
  BarChart,
  FileSearch,
  Scale,
  BookOpen,
  Briefcase,
  FileSignature,
  Cpu,
  Sparkles,
  Tags,
  MessageSquare,
  GitGraph,
  Globe,
} from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { isOnnxRuntimeAvailable } from '@/lib/ml/model-manager';
import { emitOpenConfigDialog, type ConfigDialogTab } from '@/lib/events';
import type { CommandCategory, CommandType } from '@/lib/commands/definitions';
import { getAvailableCommands } from '@/lib/commands/search';

export interface CommandItem {
  id: string;
  label: string;
  description: string;
  icon: React.ReactNode;
  category: 'system' | CommandCategory;
  isLocal?: boolean;
  action?: () => void;
}

const COMMAND_ICONS: Record<CommandType, React.ReactNode> = {
  'search-case-law': <Search className="h-4 w-4" />,
  'research-statute': <BookOpen className="h-4 w-4" />,
  'extract-entities': <Users className="h-4 w-4" />,
  'analyze-document': <BarChart className="h-4 w-4" />,
  'summarize-local': <Cpu className="h-4 w-4" />,
  'ner-advanced': <Tags className="h-4 w-4" />,
  'classify-text': <Sparkles className="h-4 w-4" />,
  'analyze-contract': <FileSearch className="h-4 w-4" />,
  'summarize-document': <FileText className="h-4 w-4" />,
  'due-diligence-review': <Briefcase className="h-4 w-4" />,
  'draft-clause': <FileSignature className="h-4 w-4" />,
  'check-compliance': <Scale className="h-4 w-4" />,
  'generate-document': <FileText className="h-4 w-4" />,
  'use-template': <Book className="h-4 w-4" />,
  redline: <FileSearch className="h-4 w-4" />,
  'fetch-url': <Globe className="h-4 w-4" />,
  'web-search': <Search className="h-4 w-4" />,
};

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  onOpenConfig: () => void;
  onOpenShare: () => void;
  onOpenAbout: () => void;
  onOpenHistory?: () => void;
  onNewChat?: () => void;
  onSwitchToChat?: () => void;
  onSwitchToArtifacts?: () => void;
  onSwitchToTree?: () => void;
  hasMessages: boolean;
}

export function CommandPalette({
  isOpen,
  onClose,
  onOpenConfig,
  onOpenShare,
  onOpenAbout,
  onOpenHistory,
  onNewChat,
  onSwitchToChat,
  onSwitchToArtifacts,
  onSwitchToTree,
  hasMessages,
}: CommandPaletteProps) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');
  const [showManual, setShowManual] = useState(false);
  const [onnxAvailable, setOnnxAvailable] = useState(true);
  const inputRef = useRef<HTMLInputElement>(null);

  // Focus input when opened
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 100);
      setSearchQuery('');
      setSelectedIndex(0);
      setShowManual(false);
    }
  }, [isOpen]);

  useEffect(() => {
    let isMounted = true;
    isOnnxRuntimeAvailable().then((available) => {
      if (isMounted) setOnnxAvailable(available);
    });
    return () => {
      isMounted = false;
    };
  }, []);

  const openConfigTab = (tab: ConfigDialogTab) => {
    onOpenConfig();
    window.setTimeout(() => emitOpenConfigDialog(tab), 100);
  };

  const systemCommands: CommandItem[] = [
    ...(onNewChat
      ? [
          {
            id: 'new-chat',
            label: 'New Chat',
            description: 'Start a fresh conversation',
            icon: <Plus className="h-4 w-4" />,
            category: 'system' as const,
            action: onNewChat,
          },
        ]
      : []),
    ...(onOpenHistory
      ? [
          {
            id: 'history',
            label: 'Chat History',
            description: 'View and resume past conversations',
            icon: <Book className="h-4 w-4" />,
            category: 'system' as const,
            action: onOpenHistory,
          },
        ]
      : []),
    ...(onSwitchToChat
      ? [
          {
            id: 'switch-to-chat',
            label: 'Chat',
            description: 'Switch to the chat interface',
            icon: <MessageSquare className="h-4 w-4" />,
            category: 'system' as const,
            action: onSwitchToChat,
          },
        ]
      : []),
    ...(onSwitchToArtifacts
      ? [
          {
            id: 'switch-to-artifacts',
            label: 'Artifacts',
            description: 'Switch to the artifacts view',
            icon: <FileText className="h-4 w-4" />,
            category: 'system' as const,
            action: onSwitchToArtifacts,
          },
        ]
      : []),
    ...(onSwitchToTree
      ? [
          {
            id: 'switch-to-tree',
            label: 'Conversation Tree',
            description: 'View the branching history of this conversation',
            icon: <GitGraph className="h-4 w-4" />,
            category: 'system' as const,
            action: onSwitchToTree,
          },
        ]
      : []),
    {
      id: 'config',
      label: 'Configuration',
      description: 'Manage API keys and user profile settings',
      icon: <Settings className="h-4 w-4" />,
      category: 'system',
      action: onOpenConfig,
    },
    {
      id: 'config-profile',
      label: 'Configuration > Profile',
      description: 'Manage user persona and roles',
      icon: <Settings className="h-4 w-4" />,
      category: 'system',
      action: () => openConfigTab('profile'),
    },
    {
      id: 'config-generation',
      label: 'Configuration > Generation',
      description: 'Adjust temperature, tokens, and model parameters',
      icon: <Settings className="h-4 w-4" />,
      category: 'system',
      action: () => openConfigTab('generation'),
    },
    {
      id: 'config-local-models',
      label: 'Configuration > Local Models',
      description: 'Manage downloaded AI models',
      icon: <Settings className="h-4 w-4" />,
      category: 'system',
      action: () => openConfigTab('localModels'),
    },
    {
      id: 'config-providers',
      label: 'Configuration > Providers',
      description: 'Configure API keys for external providers',
      icon: <Settings className="h-4 w-4" />,
      category: 'system',
      action: () => openConfigTab('providers'),
    },
    {
      id: 'config-tools',
      label: 'Configuration > Tools',
      description: 'Enable or disable analysis tools',
      icon: <Settings className="h-4 w-4" />,
      category: 'system',
      action: () => openConfigTab('tools'),
    },
    {
      id: 'config-snippets',
      label: 'Configuration > Snippets',
      description: 'Manage reusable prompt snippets',
      icon: <Settings className="h-4 w-4" />,
      category: 'system',
      action: () => openConfigTab('snippets'),
    },
    {
      id: 'config-interface',
      label: 'Configuration > Interface',
      description: 'Customize theme and appearance',
      icon: <Settings className="h-4 w-4" />,
      category: 'system',
      action: () => openConfigTab('interface'),
    },
    {
      id: 'config-developer',
      label: 'Configuration > Developer',
      description: 'Advanced settings and TOML configuration',
      icon: <Settings className="h-4 w-4" />,
      category: 'system',
      action: () => openConfigTab('developer'),
    },
    ...(hasMessages
      ? [
          {
            id: 'share',
            label: 'Share Chat',
            description: 'Generate a shareable link for this conversation',
            icon: <Users className="h-4 w-4" />,
            category: 'system' as const,
            action: onOpenShare,
          },
        ]
      : []),
    {
      id: 'about',
      label: 'About Junas',
      description: 'Learn more about this application',
      icon: <Info className="h-4 w-4" />,
      category: 'system',
      action: onOpenAbout,
    },
    {
      id: 'manual',
      label: 'User Manual',
      description: 'View all available AI commands and tools',
      icon: <Book className="h-4 w-4" />,
      category: 'system',
      action: () => setShowManual(true),
    },
  ];

  const manualCommands = useMemo<CommandItem[]>(
    () =>
      getAvailableCommands(onnxAvailable).map((command) => ({
        id: command.id,
        label: command.label,
        description: command.description,
        icon: COMMAND_ICONS[command.id],
        category: command.category,
        isLocal: command.isLocal,
      })),
    [onnxAvailable]
  );

  // If showing manual, display tool commands. Otherwise display system commands.
  const activeCommands = showManual ? manualCommands : systemCommands;
  const normalizedSearchQuery = searchQuery.trim().toLowerCase();

  // Filter commands based on search query
  const filteredCommands = activeCommands.filter(
    (cmd) =>
      cmd.label.toLowerCase().includes(normalizedSearchQuery) ||
      cmd.description.toLowerCase().includes(normalizedSearchQuery) ||
      cmd.category.toLowerCase().includes(normalizedSearchQuery)
  );

  // Group commands by category (only relevant for manual view)
  const groupedCommands = filteredCommands.reduce(
    (acc, cmd) => {
      if (!acc[cmd.category]) {
        acc[cmd.category] = [];
      }
      acc[cmd.category].push(cmd);
      return acc;
    },
    {} as Record<string, CommandItem[]>
  );

  // Create a flat array in display order
  const categoryOrder = showManual ? ['research', 'analysis', 'drafting', 'tools'] : ['system'];

  const displayOrderCommands = categoryOrder.flatMap((category) => groupedCommands[category] || []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex((prev) => (prev < displayOrderCommands.length - 1 ? prev + 1 : prev));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex((prev) => (prev > 0 ? prev - 1 : prev));
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (displayOrderCommands[selectedIndex]) {
          handleCommandSelect(displayOrderCommands[selectedIndex]);
        }
      } else if (e.key === 'Backspace' && showManual && searchQuery === '') {
        // Go back from manual to system menu
        setShowManual(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, selectedIndex, displayOrderCommands, showManual, searchQuery]);

  const handleCommandSelect = (command: CommandItem) => {
    if (command.action) {
      command.action();
      if (command.id !== 'manual') {
        onClose();
      }
    }
  };

  const categoryLabels = {
    system: 'System',
    research: 'Research',
    analysis: 'Analysis',
    drafting: 'Drafting',
    tools: 'Tools',
  };

  let commandIndex = 0;

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="p-0 gap-0 max-w-2xl font-mono overflow-hidden bg-background">
        <DialogHeader className="hidden">
          <DialogTitle>Command Palette</DialogTitle>
        </DialogHeader>

        <div className="flex items-center border-b px-3 py-2">
          <Search className="h-4 w-4 mr-2 text-muted-foreground" />
          <Input
            ref={inputRef}
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setSelectedIndex(0);
            }}
            placeholder={showManual ? 'Search manual...' : 'Type a command...'}
            className="border-0 focus-visible:ring-0 px-0 h-9 text-sm"
          />
        </div>

        <div className="max-h-[300px] overflow-y-auto py-2">
          {filteredCommands.length === 0 ? (
            <div className="px-3 py-8 text-center text-sm text-muted-foreground">
              No results found
            </div>
          ) : (
            <>
              {categoryOrder.map((category) => {
                const cmds = groupedCommands[category];
                if (!cmds || cmds.length === 0) return null;

                return (
                  <div key={category}>
                    {showManual && (
                      <div className="px-3 py-1.5 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                        {categoryLabels[category as keyof typeof categoryLabels]}
                      </div>
                    )}

                    {cmds.map((command) => {
                      const currentIndex = commandIndex++;
                      const isSelected = currentIndex === selectedIndex;

                      return (
                        <button
                          key={command.id}
                          onClick={() => handleCommandSelect(command)}
                          className={`
                            w-full px-3 py-2 flex items-center gap-3 text-left transition-colors text-sm
                            ${isSelected ? 'bg-primary/10 text-primary' : 'hover:bg-muted/50'}
                          `}
                        >
                          <div
                            className={`
                            flex items-center justify-center h-8 w-8 rounded-md 
                            ${isSelected ? 'bg-primary/20 text-primary' : 'bg-muted text-muted-foreground'}
                          `}
                          >
                            {command.icon}
                          </div>

                          <div className="flex-1 min-w-0">
                            <div className="font-medium flex items-center gap-2">
                              {command.label}
                              {command.isLocal && (
                                <span className="text-[10px] px-1.5 py-0.5 bg-green-500/20 text-green-600 dark:text-green-400 rounded">
                                  LOCAL
                                </span>
                              )}
                            </div>
                            <div className="text-xs text-muted-foreground line-clamp-1">
                              {command.description}
                            </div>
                          </div>

                          {isSelected && <span className="text-xs text-muted-foreground">↵</span>}
                        </button>
                      );
                    })}
                  </div>
                );
              })}
            </>
          )}
        </div>

        <div className="bg-muted/50 px-3 py-2 border-t text-[10px] text-muted-foreground flex justify-between">
          <div>
            <span className="font-semibold">↑↓</span> to navigate
            <span className="mx-2">·</span>
            <span className="font-semibold">↵</span> to select
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
