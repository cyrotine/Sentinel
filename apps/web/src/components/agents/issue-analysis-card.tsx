import { ScanSearch } from "lucide-react"
import { OutputCard } from "@/components/agents/output-card"
import { cn } from "@/lib/utils"

export interface SelectedIssueShape {
  number?: number
  title?: string
  reasoning?: string
  estimated_complexity?: string
}

export interface IssueAnalysisShape {
  issue_id?: string
  number?: number
  issue_type?: string
  severity?: string
  confidence?: number
  impact?: number
  reasoning?: string
}

const SEVERITY_STYLES: Record<string, string> = {
  critical: "bg-red-500/10 text-red-400 border-red-500/20",
  high: "bg-orange-500/10 text-orange-400 border-orange-500/20",
  medium: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  low: "bg-green-500/10 text-green-400 border-green-500/20",
}

const COMPLEXITY_STYLES: Record<string, string> = {
  high: "bg-red-500/10 text-red-400 border-red-500/20",
  medium: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  low: "bg-green-500/10 text-green-400 border-green-500/20",
}

function Badge({ label, className }: { label: string; className?: string }) {
  return (
    <span
      className={cn(
        "px-2 py-0.5 rounded-md text-xs font-medium uppercase tracking-wider border",
        className ?? "bg-neutral-800 text-neutral-300 border-neutral-700",
      )}
    >
      {label}
    </span>
  )
}

function Meter({ label, value }: { label: string; value: number }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100)
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <span className="text-neutral-500 uppercase tracking-wider">{label}</span>
        <span className="text-neutral-300 font-mono">{pct}%</span>
      </div>
      <div className="h-1.5 rounded-full bg-neutral-800 overflow-hidden">
        <div className="h-full rounded-full bg-blue-500/70" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

export function IssueAnalysisCard({
  issue,
  analysis,
}: {
  issue: SelectedIssueShape
  analysis?: IssueAnalysisShape
}) {
  const severity = analysis?.severity?.toLowerCase()
  const complexity = issue.estimated_complexity?.toLowerCase()

  return (
    <OutputCard icon={ScanSearch} title="Issue Analysis">
      <div className="space-y-5">
        <div className="flex flex-wrap items-center gap-2">
          {analysis?.issue_type && <Badge label={analysis.issue_type} />}
          {severity && <Badge label={severity} className={SEVERITY_STYLES[severity]} />}
          {complexity && (
            <Badge label={`${complexity} complexity`} className={COMPLEXITY_STYLES[complexity]} />
          )}
        </div>

        {(analysis?.confidence != null || analysis?.impact != null) && (
          <div className="grid grid-cols-2 gap-4">
            {analysis?.confidence != null && <Meter label="Confidence" value={analysis.confidence} />}
            {analysis?.impact != null && <Meter label="Impact" value={analysis.impact} />}
          </div>
        )}

        {(issue.reasoning || analysis?.reasoning) && (
          <p className="text-sm text-neutral-400 leading-relaxed">
            {issue.reasoning || analysis?.reasoning}
          </p>
        )}
      </div>
    </OutputCard>
  )
}
