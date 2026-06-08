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

  if (run.status === "completed") return null

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
