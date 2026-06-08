import Link from "next/link"
import { fetchRepositories } from "@/lib/api"

export async function DashboardPage() {
  let repoCount = 0
  let indexedCount = 0
  let openIssues = 0

  try {
    const repos = await fetchRepositories()
    repoCount = repos.length
    indexedCount = repos.filter((r) => r.latest_ingestion?.status === "completed").length
    openIssues = repos.reduce((sum, r) => sum + r.stats.open_issues, 0)
  } catch {
    // API not reachable — show dashes
  }

  const statCards = [
    { label: "Repositories", value: repoCount > 0 ? repoCount : "—", href: "/repositories" },
    { label: "Indexed", value: indexedCount > 0 ? indexedCount : "—", href: "/repositories" },
    { label: "Open Issues", value: openIssues > 0 ? openIssues : "—", href: "/repositories" },
    { label: "Active Agents", value: "—", href: null },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">Overview</h2>
        <p className="mt-1 text-sm text-gray-500">
          {repoCount === 0
            ? "Connect a repository to get started."
            : `${indexedCount} of ${repoCount} repositories indexed.`}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {statCards.map((card) => {
          const inner = (
            <div className="rounded-lg border border-gray-200 bg-white p-4">
              <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
                {card.label}
              </p>
              <p className="mt-2 text-2xl font-semibold text-gray-900">{card.value}</p>
            </div>
          )
          return card.href ? (
            <Link key={card.label} href={card.href} className="block hover:opacity-80">
              {inner}
            </Link>
          ) : (
            <div key={card.label}>{inner}</div>
          )
        })}
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-6">
        {repoCount === 0 ? (
          <p className="text-sm text-gray-500">
            No activity yet.{" "}
            <Link href="/repositories" className="text-blue-600 hover:underline">
              Connect a repository
            </Link>{" "}
            to begin.
          </p>
        ) : (
          <p className="text-sm text-gray-500">
            {indexedCount} repositories ready for agent analysis.
          </p>
        )}
      </div>
    </div>
  )
}
