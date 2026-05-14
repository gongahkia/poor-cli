import React, { Component, ErrorInfo, ReactNode } from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface Props {
    children?: ReactNode;
    fallback?: ReactNode;
}

interface State {
    hasError: boolean;
    error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
    public state: State = {
        hasError: false
    };

    public static getDerivedStateFromError(error: Error): State {
        return { hasError: true, error };
    }

    public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
        console.error('Uncaught error:', error, errorInfo);
    }

    private handleReload = () => {
        window.location.reload();
    };

    public render() {
        if (this.state.hasError) {
            if (this.props.fallback) {
                return this.props.fallback;
            }

            return (
                <div className="flex flex-col items-center justify-center min-h-screen p-4 text-center bg-background">
                    <div className="p-4 rounded-full bg-destructive/10 text-destructive mb-4">
                        <AlertCircle className="w-8 h-8" />
                    </div>
                    <h2 className="text-xl font-bold font-mono text-foreground mb-2">System Error</h2>
                    <p className="text-muted-foreground font-mono text-sm max-w-md mb-6">
                        An unexpected error occurred. Junas has been paused to prevent data loss.
                    </p>
                    <div className="space-y-4">
                        <div className="p-4 bg-muted/30 rounded-md font-mono text-xs text-left max-w-lg overflow-auto max-h-48 border">
                            {this.state.error?.message}
                        </div>
                        <Button onClick={this.handleReload} className="font-mono text-xs gap-2">
                            <RefreshCw className="w-3 h-3" />
                            [ Reload Application ]
                        </Button>
                    </div>
                </div>
            );
        }

        return this.props.children;
    }
}
