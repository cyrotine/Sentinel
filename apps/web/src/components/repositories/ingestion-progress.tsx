"use client"

import { useEffect, useState } from "react"
import { fetchIngestionStatus } from "@/lib/api"
import type { IngestionRunOut } from "@/lib/api"
import { StatusBadge } from "@/components/ui/status-badge"

const TERMINAL = new Set(["completed", "failed"])

interface IngestionProgressProps {
  repositoryId: string
  initial: IngestionRunOut
  onComplete: () => void
}

export function IngestionProgress({ repositoryId, initial, onComplete }: IngestionProgressProps) {
  const [run, setRun] = useState<IngestionRunOut>(initial)
  const [warningDismissed, setWarningDismissed] = useState(false)

  useEffect(() => {
    if (TERMINAL.has(run.status)) return

    const id = setInterval(async () => {
      try {
        const updated = await fetchIngestionStatus(repositoryId)
        setRun(updated)
        if (TERMINAL.has(updated.status)) {
          clearInterval(id)
          onComplete()
        }
      } catch {
        // swallow — will retry next tick
      }
    }, 2000)

    return () => clearInterval(id)
  }, [repositoryId, run.status, onComplete])

  const percent =
    run.total_files && run.total_files > 0
      ? Math.min(100, Math.round((run.processed_files / run.total_files) * 100))
      : run.status === "completed"
        ? 100
        : null

  if (run.status === "completed") {
    if (!run.warning || warningDismissed) return null

    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-2">
            <svg className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
            </svg>
            <p className="text-sm text-amber-800">{run.warning}</p>
          </div>
          <button
            onClick={() => setWarningDismissed(true)}
            className="shrink-0 text-amber-500 hover:text-amber-700"
            aria-label="Dismiss warning"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-gray-700">Ingestion in progress</p>
        <StatusBadge status={run.status} />
      </div>

      {run.error && (
        <p className="mt-2 text-xs text-red-600">{run.error}</p>
      )}

      {percent !== null && (
        <div className="mt-3">
          <div className="flex justify-between text-xs text-gray-500 mb-1">
            <span>{run.processed_files} / {run.total_files ?? "?"} files</span>
            <span>{percent}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-100">
            <div
              className="h-full rounded-full bg-gray-800 transition-all duration-500"
              style={{ width: `${percent}%` }}
            />
          </div>
        </div>
      )}
    </div>
  )
}
