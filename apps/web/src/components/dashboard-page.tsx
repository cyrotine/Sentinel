import Link from "next/link"
import { fetchRepositories } from "@/lib/api"
import { ArrowRight, Play, Brain, Eye, ShieldCheck, Code2, GitPullRequest, GitBranch, Database, CheckCircle2 } from "lucide-react"

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
    // API not reachable — fallbacks
  }

  return (
    <div className="flex flex-col gap-12 max-w-6xl mx-auto py-8">
      
      {/* Hero Section */}
      <div className="flex flex-col lg:flex-row items-center gap-16">
        <div className="flex-1 space-y-8">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-neutral-900 border border-neutral-800 text-xs font-medium text-neutral-300">
            <span className="flex h-2 w-2 rounded-full bg-blue-500 animate-pulse"></span>
            Autonomous engineering, fully transparent
          </div>
          
          <div className="space-y-4">
            <h1 className="text-5xl font-bold tracking-tight text-white">Forge</h1>
            <h2 className="text-2xl font-medium text-neutral-300">Autonomous Software Engineer</h2>
            <p className="text-neutral-400 text-lg leading-relaxed max-w-lg">
              Watch AI agents transform GitHub issues into reviewed pull requests — 
              planning, writing, validating, and reviewing code in full view.
            </p>
          </div>

          <div className="flex items-center gap-4 pt-4">
            <Link
              href="/repositories"
              className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-lg bg-white text-black font-medium hover:bg-neutral-200 transition-colors"
            >
              Add Repository <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/demo-mode"
              className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-lg bg-neutral-900 text-white font-medium border border-neutral-800 hover:bg-neutral-800 transition-colors"
            >
              <Play className="h-4 w-4" /> View Past Repo
            </Link>
          </div>
        </div>

        {/* Conceptual Diagram */}
        <div className="flex-1 hidden lg:flex items-center justify-center">
          <div className="relative w-80 h-80 flex items-center justify-center">
            {/* Concentric rings */}
            <div className="absolute inset-0 rounded-full border border-neutral-800/50" />
            <div className="absolute inset-8 rounded-full border border-neutral-800/80" />
            <div className="absolute inset-16 rounded-full border border-neutral-700/50" />
            
            {/* Center icon */}
            <div className="relative z-10 w-24 h-24 bg-neutral-900 border border-neutral-700 rounded-2xl flex items-center justify-center shadow-2xl">
              <GitPullRequest className="h-10 w-10 text-white" />
            </div>

            {/* Orbiting icons */}
            <div className="absolute top-0 transform -translate-y-1/2 w-12 h-12 bg-neutral-950 border border-neutral-800 rounded-xl flex items-center justify-center shadow-lg">
              <Brain className="h-5 w-5 text-neutral-400" />
            </div>
            <div className="absolute bottom-0 transform translate-y-1/2 w-12 h-12 bg-neutral-950 border border-neutral-800 rounded-xl flex items-center justify-center shadow-lg">
              <ShieldCheck className="h-5 w-5 text-neutral-400" />
            </div>
            <div className="absolute left-0 transform -translate-x-1/2 w-12 h-12 bg-neutral-950 border border-neutral-800 rounded-xl flex items-center justify-center shadow-lg">
              <Eye className="h-5 w-5 text-neutral-400" />
            </div>
            <div className="absolute right-0 transform translate-x-1/2 w-12 h-12 bg-neutral-950 border border-neutral-800 rounded-xl flex items-center justify-center shadow-lg">
              <Code2 className="h-5 w-5 text-neutral-400" />
            </div>
          </div>
        </div>
      </div>

      {/* Metrics Section */}
      <div className="pt-12 border-t border-neutral-900">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Link href="/repositories" className="group">
            <div className="flex flex-col p-6 rounded-xl bg-neutral-900/50 border border-neutral-800 hover:border-neutral-700 transition-colors h-full">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-neutral-900 rounded-lg border border-neutral-800 group-hover:bg-neutral-800 transition-colors">
                  <Database className="h-5 w-5 text-neutral-400" />
                </div>
                <h3 className="text-sm font-medium text-neutral-400 uppercase tracking-wider">Connected Repos</h3>
              </div>
              <p className="text-4xl font-semibold text-white">{repoCount > 0 ? repoCount : "—"}</p>
            </div>
          </Link>
          
          <Link href="/repositories" className="group">
            <div className="flex flex-col p-6 rounded-xl bg-neutral-900/50 border border-neutral-800 hover:border-neutral-700 transition-colors h-full">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-neutral-900 rounded-lg border border-neutral-800 group-hover:bg-neutral-800 transition-colors">
                  <CheckCircle2 className="h-5 w-5 text-neutral-400" />
                </div>
                <h3 className="text-sm font-medium text-neutral-400 uppercase tracking-wider">Indexed Repos</h3>
              </div>
              <p className="text-4xl font-semibold text-white">{indexedCount > 0 ? indexedCount : "—"}</p>
            </div>
          </Link>

          <Link href="/repositories" className="group">
            <div className="flex flex-col p-6 rounded-xl bg-neutral-900/50 border border-neutral-800 hover:border-neutral-700 transition-colors h-full">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-neutral-900 rounded-lg border border-neutral-800 group-hover:bg-neutral-800 transition-colors">
                  <GitBranch className="h-5 w-5 text-neutral-400" />
                </div>
                <h3 className="text-sm font-medium text-neutral-400 uppercase tracking-wider">Open Issues</h3>
              </div>
              <p className="text-4xl font-semibold text-white">{openIssues > 0 ? openIssues : "—"}</p>
            </div>
          </Link>
        </div>
      </div>

    </div>
  )
}
