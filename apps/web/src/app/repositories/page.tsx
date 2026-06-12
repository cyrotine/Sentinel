import { fetchRepositories, type RepositoryOut } from "@/lib/api"
import { RepositoriesListClient } from "@/components/repositories/repositories-list-client"
import { RepositoriesHeader } from "@/components/repositories/repositories-header"
import { FolderGit2 } from "lucide-react"

export default async function RepositoriesPage() {
  let repos: RepositoryOut[] = []
  try {
    repos = await fetchRepositories()
  } catch {
    // API not reachable — render empty state
  }

  return (
    <div className="max-w-6xl mx-auto py-8 space-y-8">
      <RepositoriesHeader />

      {repos.length === 0 ? (
        <div className="flex flex-col items-center justify-center p-12 rounded-xl border border-neutral-800 bg-neutral-900/30 border-dashed">
          <FolderGit2 className="h-10 w-10 text-neutral-600 mb-4" />
          <p className="text-neutral-300 font-medium">No repositories connected yet</p>
          <p className="mt-1 text-sm text-neutral-500">
            Click &ldquo;Connect Repository&rdquo; to start ingestion.
          </p>
        </div>
      ) : (
        <RepositoriesListClient initialRepos={repos} />
      )}
    </div>
  )
}
