import { createContext, ReactNode, useCallback, useContext, useMemo, useState } from "react";
import { AlertCircle, CheckCircle2, Info, TriangleAlert, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type ToastTone = "success" | "error" | "info" | "warning";

type ToastInput = {
  title: string;
  description?: string;
  tone?: ToastTone;
};

type ToastRecord = Required<Pick<ToastInput, "title" | "tone">> & {
  id: string;
  description?: string;
};

type ToastContextValue = {
  notify: (toast: ToastInput) => string;
  dismiss: (id: string) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

const toneClasses: Record<ToastTone, string> = {
  success: "border-emerald-200 bg-emerald-50 text-emerald-950",
  error: "border-destructive/30 bg-destructive/5 text-destructive",
  info: "border-border bg-background text-foreground",
  warning: "border-amber-200 bg-amber-50 text-amber-950",
};

const toneIcons = {
  success: CheckCircle2,
  error: AlertCircle,
  info: Info,
  warning: TriangleAlert,
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastRecord[]>([]);

  const dismiss = useCallback((id: string) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const notify = useCallback((toast: ToastInput) => {
    const id = crypto.randomUUID();
    const nextToast: ToastRecord = {
      id,
      title: toast.title,
      tone: toast.tone ?? "info",
      ...(toast.description === undefined ? {} : { description: toast.description }),
    };
    setToasts((current) => [nextToast, ...current].slice(0, 4));
    window.setTimeout(() => dismiss(id), toast.tone === "error" ? 7000 : 4500);
    return id;
  }, [dismiss]);

  const value = useMemo(() => ({ dismiss, notify }), [dismiss, notify]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        aria-relevant="additions text"
        className="fixed bottom-4 right-4 z-[70] grid w-[calc(100%-2rem)] max-w-sm gap-2 sm:bottom-6 sm:right-6"
      >
        {toasts.map((toast) => (
          <ToastItem key={toast.id} toast={toast} onDismiss={() => dismiss(toast.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastItem({
  onDismiss,
  toast,
}: {
  onDismiss: () => void;
  toast: ToastRecord;
}) {
  const Icon = toneIcons[toast.tone];

  return (
    <section className={cn("rounded-lg border p-3 shadow-lg", toneClasses[toast.tone])}>
      <div className="flex items-start gap-3">
        <Icon className="mt-0.5 h-4 w-4 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold leading-5">{toast.title}</p>
          {toast.description === undefined ? null : (
            <p className="mt-1 text-xs leading-5 opacity-80">{toast.description}</p>
          )}
        </div>
        <Button
          aria-label="Dismiss notification"
          className="h-7 w-7 shrink-0"
          onClick={onDismiss}
          size="icon"
          type="button"
          variant="ghost"
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>
    </section>
  );
}

export function useToast(): ToastContextValue {
  const value = useContext(ToastContext);
  if (value === null) {
    throw new Error("useToast must be used within ToastProvider.");
  }
  return value;
}
