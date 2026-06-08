import type { FileOut } from "@/lib/api"

function groupByLanguage(files: FileOut[]): Record<string, FileOut[]> {
  const groups: Record<string, FileOut[]> = {}
  for (const f of files) {
    const key = f.language ?? "other"
    if (!groups[key]) groups[key] = []
    groups[key].push(f)
  }
  return groups
}

export function FileTree({ files }: { files: FileOut[] }) {
  if (files.length === 0) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <p className="text-xs text-gray-500">No files indexed.</p>
      </div>
    )
  }

  const groups = groupByLanguage(files)
  const sorted = Object.entries(groups).sort((a, b) => b[1].length - a[1].length)

  return (
    <div className="rounded-lg border border-gray-200 bg-white">
      <div className="border-b border-gray-200 px-4 py-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
          Files ({files.length})
        </h3>
      </div>
      <div className="divide-y divide-gray-100 max-h-96 overflow-y-auto">
        {sorted.map(([lang, langFiles]) => (
          <details key={lang} className="group" open={sorted.length === 1}>
            <summary className="flex cursor-pointer items-center justify-between px-4 py-2 text-xs font-medium text-gray-700 hover:bg-gray-50 select-none">
              <span>{lang}</span>
              <span className="text-gray-400">{langFiles.length}</span>
            </summary>
            <ul className="divide-y divide-gray-50 bg-gray-50/50">
              {langFiles.map((f) => (
                <li
                  key={f.id}
                  className="flex items-center justify-between px-6 py-1.5 text-xs text-gray-600"
                >
                  <span className="truncate font-mono">{f.path}</span>
                  <span className="ml-2 shrink-0 text-gray-400">{f.chunk_count}c</span>
                </li>
              ))}
            </ul>
          </details>
        ))}
      </div>
    </div>
  )
}
