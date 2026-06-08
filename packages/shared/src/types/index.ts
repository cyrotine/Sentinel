export type WorkflowStatus = "pending" | "running" | "completed" | "failed";

export type AgentRole =
  | "issue-analyzer"
  | "planner"
  | "developer"
  | "qa"
  | "reviewer"
  | "pr-agent";

export interface IssueAnalysis {
  issueType: string;
  severity: string;
  confidence: number;
  impact: number;
}

export interface PlanTask {
  id: string;
  description: string;
  dependsOn: string[];
}

export interface Plan {
  tasks: PlanTask[];
  affectedFiles: string[];
  dependencies: string[];
}

export interface CodeChange {
  filePath: string;
  patch: string;
  description: string;
}

export interface TestResult {
  name: string;
  passed: boolean;
  output: string;
  error?: string;
}

export interface Review {
  approved: boolean;
  comments: string[];
  securityIssues: string[];
  suggestions: string[];
}

export interface PullRequestDraft {
  title: string;
  body: string;
  branch: string;
  baseBranch: string;
}
