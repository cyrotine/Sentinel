import type { FileOut } from "@/lib/api"

const LANG_COLORS: Record<string, string> = {
  python: "bg-blue-500",
  typescript: "bg-blue-400",
  tsx: "bg-cyan-400",
  javascript: "bg-yellow-400",
  jsx: "bg-yellow-300",
  go: "bg-teal-400",
  rust: "bg-orange-500",
  java: "bg-red-500",
  ruby: "bg-red-400",
  cpp: "bg-pink-500",
  c: "bg-pink-400",
  c_sharp: "bg-purple-500",
}

export function LanguageBreakdown({ files }: { files: FileOut[] }) {
  const counts: Record<string, number> = {}
  for (const f of files) {
    const lang = f.language ?? "other"
    counts[lang] = (counts[lang] ?? 0) + 1
  }
  const total = files.length
  if (total === 0) return null

  const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1])

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Languages</h3>
      <div className="mt-3 space-y-2">
        {sorted.map(([lang, count]) => {
          const pct = Math.round((count / total) * 100)
          return (
            <div key={lang}>
              <div className="flex justify-between text-xs text-gray-600 mb-1">
                <span>{lang}</span>
                <span>{count} files ({pct}%)</span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-100">
                <div
                  className={`h-full rounded-full ${LANG_COLORS[lang] ?? "bg-gray-400"}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
