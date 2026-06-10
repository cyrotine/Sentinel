"use client"

import { useState } from "react"

interface DiffViewerProps {
  filePath: string
  patch: string
  description: string
}

type LineType = "added" | "removed" | "context" | "hunk" | "file-header"

interface DiffLine {
  type: LineType
  content: string
}

function parsePatch(patch: string): DiffLine[] {
  return patch.split("\n").map((line): DiffLine => {
    if (line.startsWith("---") || line.startsWith("+++")) return { type: "file-header", content: line }
    if (line.startsWith("@@")) return { type: "hunk", content: line }
    if (line.startsWith("+")) return { type: "added", content: line.slice(1) }
    if (line.startsWith("-")) return { type: "removed", content: line.slice(1) }
    return { type: "context", content: line.startsWith(" ") ? line.slice(1) : line }
  })
}

const lineClasses: Record<Exclude<LineType, "file-header">, string> = {
  added: "bg-green-50 text-green-800",
  removed: "bg-red-50 text-red-800",
  hunk: "bg-gray-100 text-gray-500",
  context: "bg-white text-gray-700",
}

const linePrefix: Record<Exclude<LineType, "file-header">, string> = {
  added: "+ ",
  removed: "- ",
  hunk: "",
  context: "  ",
}

export function DiffViewer({ filePath, patch, description }: DiffViewerProps) {
  const [copied, setCopied] = useState(false)

  function handleCopy() {
    navigator.clipboard.writeText(patch).catch(() => {})
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const isEmpty = !patch.trim()
  const lines = isEmpty ? [] : parsePatch(patch).filter((l) => l.type !== "file-header")

  return (
    <div className="overflow-hidden rounded-lg border border-gray-200">
      {/* File header */}
      <div className="flex items-center justify-between bg-gray-800 px-3 py-2">
        <span className="font-mono text-xs text-gray-200">{filePath}</span>
        <button
          onClick={handleCopy}
          className="text-xs text-gray-400 transition-colors hover:text-gray-200"
        >
          {copied ? "Copied!" : "Copy"}
        </button>
      </div>

      {/* Description */}
      {description && (
        <div className="border-b border-gray-200 bg-white px-3 py-1.5">
          <p className="text-xs text-gray-500">{description}</p>
        </div>
      )}

      {/* Diff body */}
      {isEmpty ? (
        <p className="px-3 py-2 text-xs italic text-gray-400">No diff available</p>
      ) : (
        <div className="overflow-x-auto">
          {lines.map((line, i) => (
            <div key={i} className={`px-3 py-0.5 ${lineClasses[line.type as Exclude<LineType, "file-header">]}`}>
              <span className="whitespace-pre font-mono text-xs">
                {linePrefix[line.type as Exclude<LineType, "file-header">]}{line.content}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
