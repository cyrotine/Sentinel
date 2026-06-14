export const dynamic = "force-dynamic"

import { notFound } from "next/navigation"
import { fetchFiles, fetchIngestionStatus, fetchIssues, fetchRepository } from "@/lib/api"
import { StatusBadge } from "@/components/ui/status-badge"
import { FileTree } from "@/components/repositories/file-tree"
import { LanguageBreakdown } from "@/components/repositories/language-breakdown"
import { IssuesList } from "@/components/repositories/issues-list"
import { IngestionProgress } from "@/components/repositories/ingestion-progress"
import { RepositoryDetailClient } from "@/components/repositories/repository-detail-client"

interface Props {
  params: Promise<{ id: string }>
}

export default async function RepositoryDetailPage({ params }: Props) {
  const { id } = await params

  let repo, ingestion, fileData, issueData
  try {
    ;[repo, ingestion, fileData, issueData] = await Promise.all([
      fetchRepository(id),
      fetchIngestionStatus(id),
      fetchFiles(id, { limit: 500 }),
      fetchIssues(id, { limit: 50 }),
    ])
  } catch {
    notFound()
  }

  const isTerminal = ingestion.status === "completed" || ingestion.status === "failed"

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold text-gray-900">{repo.full_name}</h2>
            <StatusBadge status={ingestion.status} />
          </div>
          {repo.description && (
            <p className="mt-1 text-sm text-gray-500">{repo.description}</p>
          )}
          <a
            href={repo.github_url}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-1 text-xs text-blue-600 hover:underline"
          >
            {repo.github_url}
          </a>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Files", value: repo.stats.total_files },
          { label: "Chunks indexed", value: repo.stats.total_chunks.toLocaleString() },
          { label: "Open issues", value: repo.stats.open_issues },
        ].map((s) => (
          <div key={s.label} className="rounded-lg border border-gray-200 bg-white p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{s.label}</p>
            <p className="mt-1 text-2xl font-semibold text-gray-900">{s.value}</p>
          </div>
        ))}
      </div>

      {/* Ingestion progress — live polling client island */}
      {!isTerminal && (
        <RepositoryDetailClient
          repositoryId={id}
          initialIngestion={ingestion}
        />
      )}

      {/* Content only shown after indexing */}
      {ingestion.status === "completed" && (
        <>
          <LanguageBreakdown files={fileData.files} />
          <FileTree files={fileData.files} />
          <IssuesList issues={issueData.issues} total={issueData.total} repositoryId={id} />
        </>
      )}

      {ingestion.status === "failed" && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <p className="text-sm font-medium text-red-700">Ingestion failed</p>
          {ingestion.error && (
            <p className="mt-1 text-xs text-red-600">{ingestion.error}</p>
          )}
        </div>
      )}
    </div>
  )
}
