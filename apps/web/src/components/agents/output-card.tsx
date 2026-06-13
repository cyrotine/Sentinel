import type { LucideIcon } from "lucide-react"
import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

// Shared wrapper for live agent-output sections. Plays a one-shot entrance
// animation when first mounted (i.e. when the agent's output first lands), and
// stays static across the 2s poll re-renders. Animation is disabled under
// prefers-reduced-motion via the .forge-output-in rule in globals.css.
export function OutputCard({
  icon: Icon,
  iconClassName,
  title,
  action,
  className,
  children,
}: {
  icon: LucideIcon
  iconClassName?: string
  title: string
  action?: ReactNode
  className?: string
  children: ReactNode
}) {
  return (
    <div
      className={cn(
        "forge-output-in bg-neutral-900/50 border border-neutral-800 rounded-2xl overflow-hidden",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-2 px-6 py-4 border-b border-neutral-800">
        <div className="flex items-center gap-2 text-neutral-300">
          <Icon className={cn("w-5 h-5 text-blue-400", iconClassName)} />
          <h3 className="font-medium">{title}</h3>
        </div>
        {action}
      </div>
      <div className="p-6">{children}</div>
    </div>
  )
}
