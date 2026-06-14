"use client"

import { useEffect, useState } from "react"
import { fetchRepositories } from "@/lib/api"
import type { RepositoryOut } from "@/lib/api"
import { RepositoryCard } from "@/components/repositories/repository-card"

const TERMINAL = new Set(["completed", "failed"])
const POLL_INTERVAL_MS = 3000

function hasPendingIngestion(repos: RepositoryOut[]): boolean {
  return repos.some(
    (r) => r.latest_ingestion != null && !TERMINAL.has(r.latest_ingestion.status)
  )
}

export function RepositoriesListClient({ initialRepos }: { initialRepos: RepositoryOut[] }) {
  const [repos, setRepos] = useState<RepositoryOut[]>(initialRepos)

  // Sync when the Server Component re-renders with fresh data (e.g. after
  // router.refresh() triggered by connect or delete).
  useEffect(() => {
    setRepos(initialRepos)
  }, [initialRepos])

  useEffect(() => {
    if (!hasPendingIngestion(repos)) return

    let active = true
    let timer: ReturnType<typeof setTimeout>

    async function poll() {
      try {
        const updated = await fetchRepositories()
        if (!active) return
        setRepos(updated)
        if (hasPendingIngestion(updated)) {
          timer = setTimeout(poll, POLL_INTERVAL_MS)
        }
      } catch {
        // swallow — retry next tick
        if (active) timer = setTimeout(poll, POLL_INTERVAL_MS)
      }
    }

    timer = setTimeout(poll, POLL_INTERVAL_MS)
    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [repos])

  return (
    <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
      {repos.map((repo) => (
        <RepositoryCard key={repo.id} repo={repo} />
      ))}
    </div>
  )
}
