"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { RotateCcw } from "lucide-react"
import { retriggerIngestion } from "@/lib/api"

interface Props {
  id: string
  /** Pass true while an ingestion run is already in progress */
  disabled?: boolean
  variant?: "default" | "icon"
}

export function ReloadRepositoryButton({ id, disabled, variant = "default" }: Props) {
  const router = useRouter()
  const [loading, setLoading] = useState(false)

  async function handleReload(e: React.MouseEvent) {
    e.preventDefault()
    e.stopPropagation()
    setLoading(true)
    try {
      await retriggerIngestion(id)
      router.refresh()
    } catch (err) {
      alert(err instanceof Error ? err.message : "Reload failed")
      setLoading(false)
    }
  }

  if (variant === "icon") {
    return (
      <button
        onClick={handleReload}
        disabled={loading || disabled}
        title={disabled ? "Ingestion already running" : "Reload repository"}
        className="shrink-0 rounded px-2 py-0.5 text-xs font-medium transition-colors bg-gray-100 text-gray-500 hover:bg-gray-200 disabled:opacity-50"
      >
        <RotateCcw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
      </button>
    )
  }

  return (
    <button
      onClick={handleReload}
      disabled={loading || disabled}
      title={disabled ? "Ingestion already running" : undefined}
      className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50 hover:text-gray-900 disabled:cursor-not-allowed disabled:opacity-50"
    >
      <RotateCcw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
      {loading ? "Reloading…" : "Reload repo"}
    </button>
  )
}
