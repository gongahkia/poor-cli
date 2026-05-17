import {
  type KeyboardEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useRef,
} from "react";
import { Building2, Search, Send } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

interface UseAutoResizeTextareaProps {
  minHeight: number;
  maxHeight?: number;
}

function useAutoResizeTextarea({
  minHeight,
  maxHeight,
}: UseAutoResizeTextareaProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const adjustHeight = useCallback(
    (reset?: boolean) => {
      const textarea = textareaRef.current;
      if (!textarea) {
        return;
      }

      if (reset) {
        textarea.style.height = `${minHeight}px`;
        return;
      }

      textarea.style.height = `${minHeight}px`;
      const newHeight = Math.max(
        minHeight,
        Math.min(textarea.scrollHeight, maxHeight ?? Number.POSITIVE_INFINITY),
      );

      textarea.style.height = `${newHeight}px`;
    },
    [minHeight, maxHeight],
  );

  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = `${minHeight}px`;
    }
  }, [minHeight]);

  useEffect(() => {
    const handleResize = () => adjustHeight();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [adjustHeight]);

  return { textareaRef, adjustHeight };
}

const MIN_HEIGHT = 56;
const MAX_HEIGHT = 148;

type AiInputProps = {
  "aria-label": string;
  autoComplete?: string;
  disabled?: boolean;
  isSubmitting?: boolean;
  onSubmit: () => void;
  onValueChange: (value: string) => void;
  placeholder: string;
  secondaryAction?: ReactNode;
  value: string;
};

export function AiInput({
  "aria-label": ariaLabel,
  autoComplete = "off",
  disabled = false,
  isSubmitting = false,
  onSubmit,
  onValueChange,
  placeholder,
  secondaryAction,
  value,
}: AiInputProps) {
  const { textareaRef, adjustHeight } = useAutoResizeTextarea({
    minHeight: MIN_HEIGHT,
    maxHeight: MAX_HEIGHT,
  });

  useEffect(() => {
    adjustHeight();
  }, [adjustHeight, value]);

  const handleSubmit = () => {
    if (disabled || isSubmitting) {
      return;
    }
    onSubmit();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="w-full">
      <div className="relative rounded-[24px] border border-border bg-background p-1 shadow-sm transition-shadow focus-within:shadow-md">
        <div className="relative overflow-hidden rounded-[20px] border border-border/80 bg-muted/35">
          <div
            className="overflow-y-auto"
            style={{ maxHeight: `${MAX_HEIGHT}px` }}
          >
            <div className="relative">
              <Textarea
                aria-label={ariaLabel}
                autoComplete={autoComplete}
                className="min-h-14 resize-none rounded-none border-0 bg-transparent px-4 py-4 pr-12 text-base leading-6 text-foreground shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
                disabled={disabled}
                onChange={(event) => {
                  onValueChange(event.target.value);
                  adjustHeight();
                }}
                onKeyDown={handleKeyDown}
                placeholder=""
                ref={textareaRef}
                rows={1}
                value={value}
              />
              {!value ? (
                <div className="pointer-events-none absolute left-4 top-4 flex items-center gap-2 text-base text-muted-foreground">
                  <Search className="h-4 w-4" />
                  <span>{placeholder}</span>
                </div>
              ) : null}
            </div>
          </div>

          <div className="flex min-h-14 items-center justify-between gap-3 border-t border-border/70 bg-background/65 px-3 py-2">
            <div className="flex min-w-0 items-center gap-2">
              <span className="inline-flex min-w-0 items-center gap-2 rounded-full border border-border bg-background px-3 py-1.5 text-xs font-medium text-muted-foreground">
                <Building2 className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate">ACRA identity lookup</span>
              </span>
            </div>

            <div className="flex shrink-0 items-center gap-2">
              {secondaryAction}
              <Button
                aria-label="Search company name or UEN"
                className={cn(
                  "h-10 w-10 rounded-full",
                  value.trim()
                    ? "bg-primary text-primary-foreground hover:bg-primary/90"
                    : "bg-muted text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
                disabled={disabled || isSubmitting}
                onClick={handleSubmit}
                size="icon"
                type="button"
              >
                {isSubmitting ? (
                  <span className="h-4 w-4 rounded-full border-2 border-current/35 border-t-current animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
