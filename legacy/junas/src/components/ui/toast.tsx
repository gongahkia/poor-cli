import * as React from 'react';
import { X, CheckCircle, AlertCircle, Info, AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface ToastProps {
  id: string;
  title?: string;
  description?: string;
  type?: 'success' | 'error' | 'warning' | 'info';
  duration?: number;
  onClose?: () => void;
  index?: number;
}

export function Toast({ id, title, description, type = 'info', duration = 5000, onClose, index = 0 }: ToastProps) {
  const [isVisible, setIsVisible] = React.useState(true);

  React.useEffect(() => {
    if (duration > 0) {
      const timer = setTimeout(() => {
        setIsVisible(false);
        setTimeout(() => onClose?.(), 300);
      }, duration);
      return () => clearTimeout(timer);
    }
  }, [duration, onClose]);

  const handleClose = () => {
    setIsVisible(false);
    setTimeout(() => onClose?.(), 300);
  };

  const getIcon = () => {
    switch (type) {
      case 'success':
        return <CheckCircle className="h-5 w-5 text-foreground" />;
      case 'error':
        return <AlertCircle className="h-5 w-5 text-foreground" />;
      case 'warning':
        return <AlertTriangle className="h-5 w-5 text-foreground" />;
      default:
        return <Info className="h-5 w-5 text-muted-foreground" />;
    }
  };

  const getBackgroundColor = () => {
    switch (type) {
      case 'success':
        return 'bg-muted border-border';
      case 'error':
        return 'bg-muted border-border';
      case 'warning':
        return 'bg-muted border-border';
      default:
        return 'bg-muted border-border';
    }
  };

  if (!isVisible) return null;

  const verticalOffset = index * 150; // Stack toasts with 150px spacing

  return (
    <div
      className={cn(
        'fixed left-1/2 z-50 w-full max-w-md font-mono',
        isVisible ? 'opacity-100' : 'opacity-0'
      )}
      style={{
        top: `calc(50% - ${verticalOffset}px)`,
        transform: isVisible ? 'translateX(-50%)' : 'translateX(150vw)',
        transition: 'transform 500ms ease-in-out, opacity 500ms ease-in-out, top 500ms ease-in-out'
      }}
    >
      <div
        className={cn(
          'border-2 border-muted-foreground/30 p-6 shadow-lg bg-background',
          getBackgroundColor()
        )}
      >
        <div className="flex items-start gap-4">
          <div className="flex-1 min-w-0">
            {title && (
              <p className="text-base md:text-lg font-semibold mb-2">[ {title} ]</p>
            )}
            {description && (
              <p className="text-sm md:text-base text-muted-foreground">{description}</p>
            )}
          </div>
          <button
            onClick={handleClose}
            className="flex-shrink-0 text-muted-foreground hover:text-foreground transition-colors text-xs"
          >
            [ X ]
          </button>
        </div>
      </div>
    </div>
  );
}

export interface ToastContextType {
  toasts: ToastProps[];
  addToast: (toast: Omit<ToastProps, 'id'>) => void;
  removeToast: (id: string) => void;
}

const ToastContext = React.createContext<ToastContextType | undefined>(undefined);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<ToastProps[]>([]);

  const addToast = React.useCallback((toast: Omit<ToastProps, 'id'>) => {
    const id = Math.random().toString(36).substring(2, 11);
    setToasts(prev => {
      // Keep only the last 5 toasts to prevent overflow
      const newToasts = [...prev, { ...toast, id }];
      return newToasts.slice(-5);
    });
  }, []);

  const removeToast = React.useCallback((id: string) => {
    setToasts(prev => prev.filter(toast => toast.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ toasts, addToast, removeToast }}>
      {children}
      {[...toasts].reverse().map((toast, index) => (
        <Toast
          key={toast.id}
          {...toast}
          index={index}
          onClose={() => removeToast(toast.id)}
        />
      ))}
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = React.useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
}
