import { cn } from "@/lib/utils"

function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-pulse rounded-md bg-muted", className)}
      {...props}
    />
  )
}

export { Skeleton }

// Specialized skeleton components
export function MessageSkeleton() {
  return (
    <div className="space-y-2">
      <Skeleton className="h-4 w-3/4" />
      <Skeleton className="h-4 w-1/2" />
      <Skeleton className="h-4 w-2/3" />
    </div>
  )
}

export function ChatSkeleton() {
  return (
    <div className="flex-1 overflow-y-auto px-6 py-8 space-y-6 max-w-6xl mx-auto w-full">
      <div className="flex justify-start">
        <div className="max-w-[85%]">
          <MessageSkeleton />
        </div>
      </div>
      <div className="flex justify-end">
        <div className="max-w-[85%]">
          <MessageSkeleton />
        </div>
      </div>
      <div className="flex justify-start">
        <div className="max-w-[85%]">
          <MessageSkeleton />
        </div>
      </div>
    </div>
  )
}
