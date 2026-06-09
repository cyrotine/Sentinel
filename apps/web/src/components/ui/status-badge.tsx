import { cn } from "@/lib/utils"

const STATUS_STYLES: Record<string, string> = {
  pending: "bg-gray-100 text-gray-600",
  cloning: "bg-blue-100 text-blue-700",
  analyzing: "bg-blue-100 text-blue-700",
  embedding: "bg-indigo-100 text-indigo-700",
  running: "bg-blue-100 text-blue-700",
  completed: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
}

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        STATUS_STYLES[status] ?? "bg-gray-100 text-gray-600"
      )}
    >
      {status}
    </span>
  )
}
