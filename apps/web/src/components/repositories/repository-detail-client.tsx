"use client"

import { useRouter } from "next/navigation"
import { IngestionProgress } from "@/components/repositories/ingestion-progress"
import type { IngestionRunOut } from "@/lib/api"

interface Props {
  repositoryId: string
  initialIngestion: IngestionRunOut
}

export function RepositoryDetailClient({ repositoryId, initialIngestion }: Props) {
  const router = useRouter()

  return (
    <IngestionProgress
      repositoryId={repositoryId}
      initial={initialIngestion}
      onComplete={() => router.refresh()}
    />
  )
}
