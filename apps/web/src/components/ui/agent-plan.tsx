import { useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  Circle,
  CircleAlert,
  CircleDotDashed,
  CircleX,
} from "lucide-react";
import { AnimatePresence, LayoutGroup, motion, type Variants, useReducedMotion } from "framer-motion";

import { cn } from "@/lib/utils";

export type AgentPlanStatus =
  | "completed"
  | "in-progress"
  | "pending"
  | "need-help"
  | "failed";

export type AgentPlanSubtask = {
  id: string;
  title: string;
  description: string;
  status: AgentPlanStatus;
  priority?: string;
  tools?: string[];
};

export type AgentPlanTask = {
  id: string;
  title: string;
  description: string;
  status: AgentPlanStatus;
  priority?: string;
  level?: number;
  dependencies?: string[];
  subtasks?: AgentPlanSubtask[];
};

export type AgentPlanProps = {
  className?: string;
  defaultExpandedTaskIds?: string[];
  description?: string;
  tasks: AgentPlanTask[];
  title?: string;
};

const statusLabel: Record<AgentPlanStatus, string> = {
  completed: "Complete",
  "in-progress": "Running",
  pending: "Queued",
  "need-help": "Needs input",
  failed: "Failed",
};

const statusClassName: Record<AgentPlanStatus, string> = {
  completed: "border-border bg-muted/50 text-muted-foreground",
  "in-progress": "border-border bg-muted/50 text-muted-foreground",
  pending: "border-border bg-muted/50 text-muted-foreground",
  "need-help": "border-border bg-muted/50 text-muted-foreground",
  failed: "border-border bg-muted/50 text-muted-foreground",
};

const iconClassName: Record<AgentPlanStatus, string> = {
  completed: "text-muted-foreground",
  "in-progress": "text-muted-foreground",
  pending: "text-muted-foreground",
  "need-help": "text-muted-foreground",
  failed: "text-muted-foreground",
};

function StatusIcon({ status, small = false }: { small?: boolean; status: AgentPlanStatus }) {
  const className = cn(small ? "h-3.5 w-3.5" : "h-[18px] w-[18px]", iconClassName[status]);

  if (status === "completed") {
    return <CheckCircle2 className={className} />;
  }
  if (status === "in-progress") {
    return <CircleDotDashed className={cn(className, "animate-spin [animation-duration:1.6s]")} />;
  }
  if (status === "need-help") {
    return <CircleAlert className={className} />;
  }
  if (status === "failed") {
    return <CircleX className={className} />;
  }
  return <Circle className={className} />;
}

function defaultExpandedIds(tasks: AgentPlanTask[], explicitIds?: string[]): string[] {
  if (explicitIds !== undefined) {
    return explicitIds;
  }

  const running = tasks.filter((task) => task.status === "in-progress").map((task) => task.id);
  if (running.length > 0) {
    return running;
  }
  return tasks[0] === undefined ? [] : [tasks[0].id];
}

export default function AgentPlan({
  className,
  defaultExpandedTaskIds,
  description,
  tasks,
  title = "Dude is working",
}: AgentPlanProps) {
  const prefersReducedMotion = useReducedMotion();
  const [expandedTasks, setExpandedTasks] = useState<string[]>(() => defaultExpandedIds(tasks, defaultExpandedTaskIds));
  const [expandedSubtasks, setExpandedSubtasks] = useState<Record<string, boolean>>({});
  const taskIds = useMemo(() => tasks.map((task) => task.id).join("|"), [tasks]);

  useEffect(() => {
    setExpandedTasks((current) => {
      const valid = current.filter((taskId) => tasks.some((task) => task.id === taskId));
      return valid.length > 0 ? valid : defaultExpandedIds(tasks, defaultExpandedTaskIds);
    });
  }, [defaultExpandedTaskIds, taskIds, tasks]);

  const taskVariants: Variants = {
    hidden: {
      opacity: 0,
      y: prefersReducedMotion ? 0 : -5,
    },
    visible: {
      opacity: 1,
      y: 0,
      transition: {
        damping: 30,
        duration: prefersReducedMotion ? 0.2 : undefined,
        stiffness: 500,
        type: prefersReducedMotion ? "tween" : "spring",
      },
    },
  };

  const subtaskListVariants: Variants = {
    hidden: {
      height: 0,
      opacity: 0,
      overflow: "hidden",
    },
    visible: {
      height: "auto",
      opacity: 1,
      overflow: "visible",
      transition: {
        duration: 0.25,
        ease: [0.2, 0.65, 0.3, 0.9],
        staggerChildren: prefersReducedMotion ? 0 : 0.04,
        when: "beforeChildren",
      },
    },
  };

  const subtaskVariants: Variants = {
    hidden: {
      opacity: 0,
      x: prefersReducedMotion ? 0 : -8,
    },
    visible: {
      opacity: 1,
      x: 0,
      transition: {
        damping: 25,
        duration: prefersReducedMotion ? 0.2 : undefined,
        stiffness: 500,
        type: prefersReducedMotion ? "tween" : "spring",
      },
    },
  };

  return (
    <section className={cn("min-w-0 rounded-lg border border-border bg-card shadow-sm", className)}>
      <div className="border-b border-border px-4 py-3 sm:px-5">
        <h2 className="text-base font-semibold tracking-normal text-foreground">{title}</h2>
        {description === undefined ? null : (
          <p className="mt-1 break-words text-sm leading-6 text-muted-foreground">{description}</p>
        )}
      </div>

      <LayoutGroup>
        <ul className="space-y-1 overflow-hidden p-2 sm:p-3">
          {tasks.map((task, index) => {
            const isExpanded = expandedTasks.includes(task.id);
            const subtasks = task.subtasks ?? [];
            const isCompleted = task.status === "completed";

            return (
              <motion.li
                animate="visible"
                className={cn(index !== 0 && "pt-1")}
                initial="hidden"
                key={task.id}
                variants={taskVariants}
              >
                <motion.button
                  className="group flex w-full min-w-0 items-center rounded-md px-3 py-2 text-left transition hover:bg-muted/60"
                  onClick={() => {
                    setExpandedTasks((current) =>
                      current.includes(task.id)
                        ? current.filter((taskId) => taskId !== task.id)
                        : [...current, task.id],
                    );
                  }}
                  type="button"
                  whileHover={prefersReducedMotion ? undefined : { backgroundColor: "hsl(var(--muted) / 0.7)" }}
                >
                  <span className="mr-2 shrink-0">
                    <AnimatePresence mode="wait">
                      <motion.span
                        animate={{ opacity: 1, rotate: 0, scale: 1 }}
                        exit={{ opacity: 0, rotate: 8, scale: 0.9 }}
                        initial={{ opacity: 0, rotate: -8, scale: 0.9 }}
                        key={task.status}
                        transition={{ duration: 0.18, ease: [0.2, 0.65, 0.3, 0.9] }}
                      >
                        <StatusIcon status={task.status} />
                      </motion.span>
                    </AnimatePresence>
                  </span>

                  <span className="min-w-0 flex-1">
                    <span
                      className={cn(
                        "block truncate text-sm font-medium text-foreground",
                        isCompleted && "text-muted-foreground line-through",
                      )}
                    >
                      {task.title}
                    </span>
                    <span className="mt-0.5 block truncate text-xs text-muted-foreground">{task.description}</span>
                  </span>

                  <span className="ml-3 flex shrink-0 items-center gap-2">
                    {task.dependencies?.map((dependency) => (
                      <span
                        className="hidden rounded border border-border bg-muted/50 px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground sm:inline"
                        key={dependency}
                      >
                        {dependency}
                      </span>
                    ))}
                    <motion.span
                      animate={{ scale: prefersReducedMotion ? 1 : [1, 1.06, 1] }}
                      className={cn("rounded border px-1.5 py-0.5 text-[11px] font-medium", statusClassName[task.status])}
                      key={task.status}
                      transition={{ duration: 0.3, ease: [0.34, 1.56, 0.64, 1] }}
                    >
                      {statusLabel[task.status]}
                    </motion.span>
                  </span>
                </motion.button>

                <AnimatePresence initial={false}>
                  {isExpanded && subtasks.length > 0 ? (
                    <motion.div
                      animate="visible"
                      className="relative overflow-hidden"
                      exit="hidden"
                      initial="hidden"
                      layout
                      variants={subtaskListVariants}
                    >
                      <div className="absolute bottom-2 left-[22px] top-1 border-l border-dashed border-muted-foreground/30" />
                      <ul className="mb-1 ml-3 mr-2 mt-1 space-y-0.5">
                        {subtasks.map((subtask) => {
                          const subtaskKey = `${task.id}-${subtask.id}`;
                          const isSubtaskExpanded = expandedSubtasks[subtaskKey] ?? false;
                          const isSubtaskCompleted = subtask.status === "completed";

                          return (
                            <motion.li
                              animate="visible"
                              className="group flex min-w-0 flex-col py-0.5 pl-6"
                              exit="hidden"
                              initial="hidden"
                              key={subtask.id}
                              layout
                              variants={subtaskVariants}
                            >
                              <button
                                className="flex min-w-0 items-center rounded-md p-1.5 text-left transition hover:bg-muted/60"
                                onClick={() => {
                                  setExpandedSubtasks((current) => ({
                                    ...current,
                                    [subtaskKey]: !isSubtaskExpanded,
                                  }));
                                }}
                                type="button"
                              >
                                <span className="mr-2 shrink-0">
                                  <StatusIcon small status={subtask.status} />
                                </span>
                                <span
                                  className={cn(
                                    "min-w-0 flex-1 truncate text-sm text-foreground",
                                    isSubtaskCompleted && "text-muted-foreground line-through",
                                  )}
                                >
                                  {subtask.title}
                                </span>
                                {subtask.tools === undefined || subtask.tools.length === 0 ? null : (
                                  <span className="ml-2 hidden max-w-[45%] shrink-0 flex-wrap justify-end gap-1 sm:flex">
                                    {subtask.tools.slice(0, 2).map((tool) => (
                                      <span
                                        className="max-w-full truncate rounded border border-border bg-muted/50 px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground"
                                        key={tool}
                                      >
                                        {tool}
                                      </span>
                                    ))}
                                    {subtask.tools.length > 2 ? (
                                      <span className="rounded border border-border bg-muted/50 px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                                        +{subtask.tools.length - 2}
                                      </span>
                                    ) : null}
                                  </span>
                                )}
                              </button>

                              <AnimatePresence initial={false}>
                                {isSubtaskExpanded ? (
                                  <motion.div
                                    animate="visible"
                                    className="ml-3 overflow-hidden border-l border-dashed border-border pl-5 text-xs text-muted-foreground"
                                    exit="hidden"
                                    initial="hidden"
                                    layout
                                    variants={subtaskListVariants}
                                  >
                                    <p className="py-1 leading-5">{subtask.description}</p>
                                    {subtask.tools === undefined || subtask.tools.length === 0 ? null : (
                                      <div className="mb-1 mt-0.5 flex flex-wrap items-center gap-1.5">
                                        <span className="font-medium text-muted-foreground">Tools:</span>
                                        {subtask.tools.map((tool) => (
                                          <span
                                            className="max-w-full break-all rounded border border-border bg-muted/50 px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground"
                                            key={tool}
                                          >
                                            {tool}
                                          </span>
                                        ))}
                                      </div>
                                    )}
                                  </motion.div>
                                ) : null}
                              </AnimatePresence>
                            </motion.li>
                          );
                        })}
                      </ul>
                    </motion.div>
                  ) : null}
                </AnimatePresence>
              </motion.li>
            );
          })}
        </ul>
      </LayoutGroup>
    </section>
  );
}
