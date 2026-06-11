"use client"

import { useRouter } from "next/navigation"
import { ConnectRepositoryModal } from "@/components/repositories/connect-repository-modal"

export function RepositoriesHeader() {
  const router = useRouter()

  return (
    <div className="flex items-center justify-between">
      <div>
        <h1 className="text-3xl font-semibold text-white tracking-tight">Repositories</h1>
        <p className="mt-2 text-neutral-400">
          Connect a GitHub repository to begin autonomous analysis.
        </p>
      </div>
      <ConnectRepositoryModal onSuccess={() => router.refresh()} />
    </div>
  )
}
