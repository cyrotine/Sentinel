"use client"

import { useState } from "react"
import { GitPullRequestDraft, ChevronDown } from "lucide-react"
import { OutputCard } from "@/components/agents/output-card"
import { cn } from "@/lib/utils"

export interface PrShape {
  title?: string
  body?: string
  branch?: string
  base_branch?: string
}

// Shown while the PR draft exists but a real PR URL does not yet — gives the
// Pull Request stage visible output before/instead of the "View Pull Request"
// button. Once a real PR is opened, the hero button supersedes this.
export function PrDraftCard({ pr }: { pr: PrShape }) {
  const [open, setOpen] = useState(false)
  const body = pr.body ?? ""

  return (
    <OutputCard icon={GitPullRequestDraft} title="Pull Request Draft">
      <div className="space-y-3">
        {pr.title && <p className="text-neutral-200 font-medium">{pr.title}</p>}

        {(pr.branch || pr.base_branch) && (
          <div className="flex items-center gap-2 font-mono text-xs text-neutral-500">
            <span className="text-neutral-400">{pr.branch}</span>
            <span>→</span>
            <span className="text-neutral-400">{pr.base_branch || "main"}</span>
          </div>
        )}

        {body && (
          <div>
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              className="flex items-center gap-1.5 text-xs text-neutral-400 hover:text-neutral-200 transition-colors"
            >
              <ChevronDown className={cn("w-3.5 h-3.5 transition-transform", open && "rotate-180")} />
              {open ? "Hide description" : "Show description"}
            </button>
            {open && (
              <pre className="mt-3 whitespace-pre-wrap break-words font-mono text-xs text-neutral-400 bg-neutral-950 border border-neutral-800 rounded-lg p-4 max-h-72 overflow-y-auto">
                {body}
              </pre>
            )}
          </div>
        )}
      </div>
    </OutputCard>
  )
}
