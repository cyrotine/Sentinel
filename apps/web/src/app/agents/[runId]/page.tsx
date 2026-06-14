export const dynamic = "force-dynamic"

import { AgentRunDetail } from "@/components/agents/agent-run-detail"

interface Props {
  params: Promise<{ runId: string }>
}

export default async function AgentRunPage({ params }: Props) {
  const { runId } = await params
  return <AgentRunDetail runId={runId} />
}
