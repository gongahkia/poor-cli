import { Menu } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

interface MobileMenuProps {
  onNewChat?: () => void;
  onCommandPalette?: () => void;
  onHistory?: () => void;
  onConfig?: () => void;
  onImport?: () => void;
  onExport?: () => void;
  onShare?: () => void;
  onAbout?: () => void;
}

export function MobileMenu({
  onNewChat,
  onCommandPalette,
  onHistory,
  onConfig,
  onImport,
  onExport,
  onShare,
  onAbout,
}: MobileMenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="p-2 -mr-2 text-foreground/80 hover:text-foreground">
          <Menu className="h-6 w-6" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-[200px] font-mono">
        {onNewChat && (
          <DropdownMenuItem onClick={onNewChat} className="cursor-pointer">
            [ New Chat ]
          </DropdownMenuItem>
        )}
        {onCommandPalette && (
          <DropdownMenuItem onClick={onCommandPalette} className="cursor-pointer">
            [ Command Palette ]
          </DropdownMenuItem>
        )}
        {onHistory && (
          <DropdownMenuItem onClick={onHistory} className="cursor-pointer">
            [ History ]
          </DropdownMenuItem>
        )}

        <DropdownMenuSeparator />

        {onConfig && (
          <DropdownMenuItem onClick={onConfig} className="cursor-pointer">
            [ Config ]
          </DropdownMenuItem>
        )}

        <DropdownMenuSeparator />

        {onImport && (
          <DropdownMenuItem onClick={onImport} className="cursor-pointer">
            [ ↑ Import ]
          </DropdownMenuItem>
        )}
        {onExport && (
          <DropdownMenuItem onClick={onExport} className="cursor-pointer">
            [ ↓ Export ]
          </DropdownMenuItem>
        )}

        <DropdownMenuSeparator />

        {onShare && (
          <DropdownMenuItem onClick={onShare} className="cursor-pointer">
            [ Share ]
          </DropdownMenuItem>
        )}
        {onAbout && (
          <DropdownMenuItem onClick={onAbout} className="cursor-pointer">
            [ About ]
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
