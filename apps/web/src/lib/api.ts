const configuredUrl = process.env.NEXT_PUBLIC_API_URL;
const API_BASE = configuredUrl ?? "http://127.0.0.1:8000/api";

export interface IngestionRunOut {
  id: string
  status: "pending" | "cloning" | "analyzing" | "embedding" | "completed" | "failed"
  total_files: number | null
  processed_files: number
  error: string | null
  started_at: string | null
  completed_at: string | null
}

export interface RepositoryStats {
  total_files: number
  total_chunks: number
  open_issues: number
}

export interface RepositoryOut {
  id: string
  owner: string
  name: string
  full_name: string
  description: string | null
  github_url: string
  default_branch: string
  created_at: string
  stats: RepositoryStats
  latest_ingestion: IngestionRunOut | null
}

export interface RepositoryCreatedOut {
  repository_id: string
  ingestion_run_id: string
  status: string
}

export interface FileOut {
  id: string
  path: string
  language: string | null
  size_bytes: number
  chunk_count: number
}

export interface FileListOut {
  total: number
  files: FileOut[]
}

export interface IssueOut {
  id: string
  number: number
  title: string
  body: string | null
  state: string
  labels: string[]
}

export interface IssueListOut {
  total: number
  issues: IssueOut[]
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`API error ${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

export async function fetchRepositories(): Promise<RepositoryOut[]> {
  return apiFetch<RepositoryOut[]>("/repositories")
}

export async function registerRepository(
  githubUrl: string,
  pat?: string,
): Promise<RepositoryCreatedOut> {
  return apiFetch<RepositoryCreatedOut>("/repositories", {
    method: "POST",
    body: JSON.stringify({ github_url: githubUrl, github_pat: pat || undefined }),
  })
}

export async function fetchRepository(id: string): Promise<RepositoryOut> {
  return apiFetch<RepositoryOut>(`/repositories/${id}`)
}

export async function fetchIngestionStatus(id: string): Promise<IngestionRunOut> {
  return apiFetch<IngestionRunOut>(`/repositories/${id}/ingestion`)
}

export async function fetchFiles(
  id: string,
  params?: { language?: string; limit?: number; offset?: number }
): Promise<FileListOut> {
  const qs = new URLSearchParams()
  if (params?.language) qs.set("language", params.language)
  if (params?.limit != null) qs.set("limit", String(params.limit))
  if (params?.offset != null) qs.set("offset", String(params.offset))
  const query = qs.toString() ? `?${qs}` : ""
  return apiFetch<FileListOut>(`/repositories/${id}/files${query}`)
}

export async function fetchIssues(
  id: string,
  params?: { state?: string; limit?: number; offset?: number }
): Promise<IssueListOut> {
  const qs = new URLSearchParams()
  if (params?.state) qs.set("state", params.state)
  if (params?.limit != null) qs.set("limit", String(params.limit))
  if (params?.offset != null) qs.set("offset", String(params.offset))
  const query = qs.toString() ? `?${qs}` : ""
  return apiFetch<IssueListOut>(`/repositories/${id}/issues${query}`)
}

export async function retriggerIngestion(id: string): Promise<{ ingestion_run_id: string; status: string }> {
  return apiFetch(`/repositories/${id}/ingest`, { method: "POST" })
}

export async function deleteRepository(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/repositories/${id}`, { method: "DELETE" })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`API error ${res.status}: ${text}`)
  }
}

// ---------------------------------------------------------------------------
// Agent runs
// ---------------------------------------------------------------------------

export interface AgentRunResult {
  selected_issue: Record<string, unknown> | null
  plan: Record<string, unknown> | null
  code_changes: Record<string, unknown>[]
  review: Record<string, unknown> | null
  pull_request_draft: Record<string, unknown> | null
  pull_request_url: string | null
  pull_request_number: number | null
  iteration: number | null
  repair_context: Record<string, unknown> | null
}

export interface AgentRunOut {
  id: string
  repository_id: string
  target_issue_id: string | null
  status: string
  current_node: string | null
  error: string | null
  result: AgentRunResult | null
  created_at: string
  started_at: string | null
  completed_at: string | null
}

export interface AgentRunListOut {
  total: number
  runs: AgentRunOut[]
}

export interface AgentRunCreatedOut {
  run_id: string
  status: string
}

export async function fetchAgentRuns(params?: {
  repository_id?: string
  limit?: number
  offset?: number
}): Promise<AgentRunListOut> {
  const qs = new URLSearchParams()
  if (params?.repository_id) qs.set("repository_id", params.repository_id)
  if (params?.limit != null) qs.set("limit", String(params.limit))
  if (params?.offset != null) qs.set("offset", String(params.offset))
  const query = qs.toString() ? `?${qs}` : ""
  return apiFetch<AgentRunListOut>(`/agent-runs${query}`)
}

export async function fetchAgentRun(runId: string): Promise<AgentRunOut> {
  return apiFetch<AgentRunOut>(`/agent-runs/${runId}`)
}

export async function startAgentRun(body: {
  repository_id: string
  target_issue_id: string
}): Promise<AgentRunCreatedOut> {
  return apiFetch<AgentRunCreatedOut>("/agent-runs", {
    method: "POST",
    body: JSON.stringify(body),
  })
}
