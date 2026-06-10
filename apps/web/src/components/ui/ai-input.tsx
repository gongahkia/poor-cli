import {
  type KeyboardEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useRef,
} from "react";
import { Search } from "lucide-react";

import { Textarea } from "@/components/ui/textarea";

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
  dropdownContent?: ReactNode;
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
  dropdownContent,
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
      <div className="relative rounded-[24px] bg-background shadow-sm transition-shadow focus-within:shadow-md">
        <div className="relative overflow-hidden rounded-[24px] border border-border bg-muted/35">
          <div className="flex items-start gap-3 px-4 py-3">
            <div className="relative min-w-0 flex-1">
              <Search className="pointer-events-none absolute left-0 top-4 h-4 w-4 text-muted-foreground" />
              <div
                className="overflow-y-auto"
                style={{ maxHeight: `${MAX_HEIGHT}px` }}
              >
                <Textarea
                  aria-label={ariaLabel}
                  autoComplete={autoComplete}
                  className="min-h-12 resize-none rounded-none border-0 bg-transparent py-3 pl-7 pr-2 text-base leading-6 text-foreground shadow-none placeholder:text-muted-foreground focus-visible:ring-0 focus-visible:ring-offset-0"
                  disabled={disabled}
                  onChange={(event) => {
                    onValueChange(event.target.value);
                    adjustHeight();
                  }}
                  onKeyDown={handleKeyDown}
                  placeholder={placeholder}
                  ref={textareaRef}
                  rows={1}
                  value={value}
                />
              </div>
            </div>
            {secondaryAction ? (
              <div className="shrink-0 self-center">
                {secondaryAction}
              </div>
            ) : null}
          </div>

          {dropdownContent ? (
            <div className="border-t border-border/70 bg-background/85">
              {dropdownContent}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
