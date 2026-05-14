import { useState, useEffect } from 'react';
import { ToastProvider } from '@/components/ui/toast';
import { migrateApiKeysToSession } from '@/lib/migrate-keys';
import { isTauriRuntime } from '@/lib/runtime';
import { MobileMenu } from './MobileMenu';

interface LayoutProps {
  children: React.ReactNode;
  focusMode?: boolean;
  onImport?: () => void;
  onExport?: () => void;
  onShare?: () => void;
  onNewChat?: () => void;
  onCommandPalette?: () => void;
  onConfig?: () => void;
  onAbout?: () => void;
  onHistory?: () => void;
}

export function Layout({
  children,
  focusMode = false,
  onImport,
  onExport,
  onShare,
  onNewChat,
  onCommandPalette,
  onConfig,
  onAbout,
  onHistory,
}: LayoutProps) {
  const [mounted, setMounted] = useState(false);
  const isWebMode = !isTauriRuntime();

  useEffect(() => {
    setMounted(true);

    // Migrate old localStorage API keys to secure session storage
    migrateApiKeysToSession().catch((error) => {
      console.error('Failed to migrate API keys:', error);
    });
  }, []);

  if (!mounted) {
    return null;
  }

  return (
    <ToastProvider>
      <div className="h-screen bg-background flex flex-col overflow-hidden">
        {/* Header */}
        {!focusMode && (
          <header className="shrink-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
            <div className="max-w-7xl mx-auto flex h-14 md:h-16 items-center justify-between px-4 md:px-8 font-mono">
              {/* Logo / Brand (Optional: added for structure) */}
              <div className="font-bold text-sm md:hidden">JUNAS</div>

              {/* Desktop Navigation */}
              <div className="hidden md:flex flex-1 items-center gap-6">
                {/* Left side - New Chat button */}
                <div className="flex items-center gap-4">
                  {onNewChat && (
                    <button
                      onClick={onNewChat}
                      className="px-2 py-1 text-sm hover:bg-muted transition-colors"
                      data-tour="new-chat"
                    >
                      [ New Chat ]
                    </button>
                  )}
                  {/* Command Palette button removed from desktop view as per request */}
                  {onHistory && (
                    <button
                      onClick={onHistory}
                      className="px-2 py-1 text-sm hover:bg-muted transition-colors"
                      title="View chat history"
                    >
                      [ History ]
                    </button>
                  )}
                </div>

                {/* Spacer */}
                <div className="flex-1"></div>

                {/* Right side controls */}
                <div className="flex items-center space-x-4">
                  {/* Config button */}
                  {onConfig && (
                    <button
                      onClick={onConfig}
                      className="px-2 py-1 text-sm hover:bg-muted transition-colors"
                      title="Configure profile"
                    >
                      [ Config ]
                    </button>
                  )}
                  {/* Theme button removed as requested */}
                  {/* Import button - only show when no messages */}
                  {onImport && (
                    <button
                      onClick={onImport}
                      className="px-2 py-1 text-sm hover:bg-muted transition-colors"
                      data-tour="import"
                    >
                      [ ↑ Import ]
                    </button>
                  )}
                  {/* Export button - only show when there are messages */}
                  {onExport && (
                    <button
                      onClick={onExport}
                      className="px-2 py-1 text-sm hover:bg-muted transition-colors"
                      data-tour="export"
                    >
                      [ ↓ Export ]
                    </button>
                  )}
                  {/* Share button */}
                  {onShare && (
                    <button
                      onClick={onShare}
                      className="px-2 py-1 text-sm hover:bg-muted transition-colors"
                      title="Share conversation"
                    >
                      [ Share ]
                    </button>
                  )}
                  {/* About button */}
                  {onAbout && (
                    <button
                      onClick={onAbout}
                      className="px-2 py-1 text-sm hover:bg-muted transition-colors"
                      title="About Junas"
                    >
                      [ About ]
                    </button>
                  )}
                </div>
              </div>

              {/* Mobile Menu Button */}
              <div className="md:hidden flex items-center">
                <MobileMenu
                  onNewChat={onNewChat}
                  onCommandPalette={onCommandPalette}
                  onHistory={onHistory}
                  onConfig={onConfig}
                  onImport={onImport}
                  onExport={onExport}
                  onShare={onShare}
                  onAbout={onAbout}
                />
              </div>
            </div>
          </header>
        )}

        {!focusMode && isWebMode && (
          <div className="shrink-0 border-b bg-amber-50 text-amber-900 dark:bg-amber-950/30 dark:text-amber-100">
            <div className="max-w-7xl mx-auto px-4 md:px-8 py-2 text-[11px] md:text-xs font-mono">
              [ Web Mode ] Browser adapters are active. Desktop-only capabilities like local model
              downloads and native PDF/DOCX parsing are limited.
            </div>
          </div>
        )}

        {/* Main content */}
        <main className="flex-1 flex flex-col min-h-0 relative">{children}</main>

        {/* Footer */}
        {!focusMode && (
          <footer className="shrink-0 border-t bg-background py-3 md:py-4 px-4 md:px-8">
            <div className="max-w-7xl mx-auto text-center text-xs md:text-sm text-muted-foreground font-mono">
              <p>
                Made by{' '}
                <a
                  href="https://gabrielongzm.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary hover:underline"
                >
                  Gabriel Ong
                </a>
                {' | '}
                <a
                  href="https://github.com/gongahkia/junas"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary hover:underline"
                >
                  Source
                </a>
              </p>
            </div>
          </footer>
        )}
      </div>
    </ToastProvider>
  );
}

// Theme toggle removed; app is light-mode only for now.
