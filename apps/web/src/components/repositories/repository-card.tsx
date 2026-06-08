import Link from "next/link"
import { StatusBadge } from "@/components/ui/status-badge"
import { DeleteRepositoryButton } from "@/components/repositories/delete-repository-button"
import type { RepositoryOut } from "@/lib/api"

export function RepositoryCard({ repo }: { repo: RepositoryOut }) {
  const ingestion = repo.latest_ingestion

  return (
    <div className="relative rounded-lg border border-gray-200 bg-white transition-shadow hover:border-gray-300 hover:shadow-sm">
      <Link href={`/repositories/${repo.id}`} className="block p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-gray-900">{repo.full_name}</p>
            {repo.description && (
              <p className="mt-0.5 truncate text-xs text-gray-500">{repo.description}</p>
            )}
          </div>
          {ingestion && <StatusBadge status={ingestion.status} />}
        </div>
        <div className="mt-3 flex items-center gap-4 text-xs text-gray-500">
          <span>{repo.stats.total_files} files</span>
          <span>{repo.stats.open_issues} open issues</span>
          {repo.stats.total_chunks > 0 && (
            <span>{repo.stats.total_chunks.toLocaleString()} chunks indexed</span>
          )}
        </div>
      </Link>
      <div className="flex justify-end border-t border-gray-100 px-4 py-2">
        <DeleteRepositoryButton id={repo.id} />
      </div>
    </div>
  )
}
