"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { deleteRepository } from "@/lib/api"

export function DeleteRepositoryButton({ id }: { id: string }) {
  const router = useRouter()
  const [confirming, setConfirming] = useState(false)
  const [loading, setLoading] = useState(false)

  async function handleDelete(e: React.MouseEvent) {
    e.preventDefault()
    e.stopPropagation()

    if (!confirming) {
      setConfirming(true)
      // Auto-reset confirm state after 3s if user doesn't click again
      setTimeout(() => setConfirming(false), 3000)
      return
    }

    setLoading(true)
    try {
      await deleteRepository(id)
      router.push("/repositories")
      router.refresh()
    } catch (err) {
      setLoading(false)
      setConfirming(false)
      alert(err instanceof Error ? err.message : "Delete failed")
    }
  }

  return (
    <button
      onClick={handleDelete}
      disabled={loading}
      className={`shrink-0 rounded px-2 py-0.5 text-xs font-medium transition-colors ${
        confirming
          ? "bg-red-100 text-red-700 hover:bg-red-200"
          : "bg-gray-100 text-gray-500 hover:bg-gray-200"
      } disabled:opacity-50`}
    >
      {loading ? "Deleting…" : confirming ? "Confirm?" : "Delete"}
    </button>
  )
}
