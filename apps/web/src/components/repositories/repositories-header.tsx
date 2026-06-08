"use client"

import { useRouter } from "next/navigation"
import { ConnectRepositoryModal } from "@/components/repositories/connect-repository-modal"

export function RepositoriesHeader() {
  const router = useRouter()

  return (
    <div className="flex items-center justify-between">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">Repositories</h2>
        <p className="mt-1 text-sm text-gray-500">
          Connect a GitHub repository to begin analysis.
        </p>
      </div>
      <ConnectRepositoryModal onSuccess={() => router.refresh()} />
    </div>
  )
}
