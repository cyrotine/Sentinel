import { ShieldCheck, Eye, Brain, Play } from "lucide-react"

export default function SettingsPage() {
  return (
    <div className="max-w-4xl mx-auto py-8 space-y-12">
      <div className="space-y-4">
        <h1 className="text-3xl font-semibold text-white tracking-tight">Forge Principles</h1>
        <p className="text-neutral-400 text-lg leading-relaxed">
          Forge is designed as an autonomous software engineer, prioritizing transparency, explainability, and safety over speed. These principles guide its execution pipeline.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        
        <div className="p-8 rounded-2xl bg-[#0f0f0f] border border-neutral-800 space-y-4">
          <div className="w-12 h-12 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center">
            <Eye className="w-6 h-6 text-blue-400" />
          </div>
          <h2 className="text-xl font-semibold text-white">Radical Transparency</h2>
          <p className="text-neutral-400 leading-relaxed">
            Every decision, file read, and code generation step is fully observable. You can trace the exact reasoning behind why Forge modified a specific line of code.
          </p>
        </div>

        <div className="p-8 rounded-2xl bg-[#0f0f0f] border border-neutral-800 space-y-4">
          <div className="w-12 h-12 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center">
            <ShieldCheck className="w-6 h-6 text-purple-400" />
          </div>
          <h2 className="text-xl font-semibold text-white">Validation First</h2>
          <p className="text-neutral-400 leading-relaxed">
            Forge does not push code blindly. It runs local builds, syntax checks, and test suites to validate changes before ever proposing them for review.
          </p>
        </div>

        <div className="p-8 rounded-2xl bg-[#0f0f0f] border border-neutral-800 space-y-4">
          <div className="w-12 h-12 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
            <Brain className="w-6 h-6 text-emerald-400" />
          </div>
          <h2 className="text-xl font-semibold text-white">Human Oversight</h2>
          <p className="text-neutral-400 leading-relaxed">
            While Forge can write code autonomously, it operates as a junior engineer. It creates Pull Requests and waits for human approval before merging.
          </p>
        </div>

        <div className="p-8 rounded-2xl bg-[#0f0f0f] border border-neutral-800 space-y-4">
          <div className="w-12 h-12 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
            <Play className="w-6 h-6 text-amber-400" />
          </div>
          <h2 className="text-xl font-semibold text-white">Autonomous Execution</h2>
          <p className="text-neutral-400 leading-relaxed">
            Using LangGraph, Forge iterates recursively. If a test fails, it patches the code and tries again without requiring manual intervention.
          </p>
        </div>

      </div>
    </div>
  )
}
