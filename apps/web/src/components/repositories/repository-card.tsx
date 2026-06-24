import Link from "next/link"
import { StatusBadge } from "@/components/ui/status-badge"
import { DeleteRepositoryButton } from "@/components/repositories/delete-repository-button"
import { ReloadRepositoryButton } from "@/components/repositories/reload-repository-button"
import type { RepositoryOut } from "@/lib/api"
import { FileCode2, GitPullRequest, Database } from "lucide-react"

export function RepositoryCard({ repo }: { repo: RepositoryOut }) {
  const ingestion = repo.latest_ingestion

  return (
    <div className="group relative rounded-xl border border-neutral-800 bg-neutral-900/50 transition-all hover:bg-neutral-800 hover:border-neutral-700">
      <Link href={`/repositories/${repo.id}`} className="block p-5">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate text-base font-semibold text-white group-hover:text-blue-400 transition-colors">
              {repo.full_name}
            </p>
            {repo.description && (
              <p className="mt-1 truncate text-xs text-neutral-500">{repo.description}</p>
            )}
          </div>
          {ingestion && <StatusBadge status={ingestion.status} />}
        </div>
        <div className="mt-6 flex flex-wrap items-center gap-4 text-xs font-medium text-neutral-400">
          <div className="flex items-center gap-1.5 bg-neutral-950 px-2 py-1 rounded-md border border-neutral-800">
            <FileCode2 className="w-3.5 h-3.5 text-neutral-500" />
            <span>{repo.stats.total_files}</span>
          </div>
          <div className="flex items-center gap-1.5 bg-neutral-950 px-2 py-1 rounded-md border border-neutral-800">
            <GitPullRequest className="w-3.5 h-3.5 text-neutral-500" />
            <span>{repo.stats.open_issues} open</span>
          </div>
          {repo.stats.total_chunks > 0 && (
            <div className="flex items-center gap-1.5 bg-neutral-950 px-2 py-1 rounded-md border border-neutral-800">
              <Database className="w-3.5 h-3.5 text-neutral-500" />
              <span>{(repo.stats.total_chunks / 1000).toFixed(1)}k chunks</span>
            </div>
          )}
        </div>
      </Link>
      <div className="absolute top-4 right-4 flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
        <ReloadRepositoryButton
          id={repo.id}
          variant="icon"
          disabled={!!ingestion && !["completed", "failed"].includes(ingestion.status)}
        />
        <DeleteRepositoryButton id={repo.id} />
      </div>
    </div>
  )
}
