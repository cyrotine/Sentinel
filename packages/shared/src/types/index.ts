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
  specId?: string;
  exitCode?: number;
}

export type TestAssertionType =
  | "dom_text"
  | "dom_attr"
  | "content_regex"
  | "content_contains";

export interface TestAssertion {
  type: TestAssertionType;
  selector?: string;
  attr?: string;
  expected?: string;
  contains?: string;
  pattern?: string;
}

export interface TestSpec {
  id: string;
  name: string;
  acceptanceCriterion: string;
  targetFile: string;
  framework: "html-validate" | "assertion";
  assertions: TestAssertion[];
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
