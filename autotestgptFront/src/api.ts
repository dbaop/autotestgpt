import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

export interface Requirement {
  id: number
  title: string
  description: string
  status: 'pending' | 'parsed' | 'cases_generated' | 'code_generated' | 'executing' | 'executed' | 'completed' | 'error'
  execution_progress?: any
  created_at: string
  updated_at: string
  test_case_count: number
  knowledge_base_id?: number | null
}

export interface RequirementDetail extends Requirement {
  structured_data?: any
  test_cases: TestCase[]
}

export interface TestCase {
  id: number
  requirement_id: number
  title: string
  description: string
  test_type: 'api' | 'ui' | 'performance' | 'security'
  priority: 'high' | 'medium' | 'low'
  steps: any[]
  expected_results: any
  created_at: string
  script_count: number
}

export interface ExecutionRecord {
  id: number
  test_script_id: number
  status: 'success' | 'failed' | 'error' | 'running'
  execution_time: number
  error_message: string
  started_at: string
  finished_at: string
  report_path: string
}

export interface TestScript {
  id: number
  test_case_id: number
  script_type: string
  file_path: string
  status: string
  created_at: string
  content: string
}

export interface CodeReviewTask {
  id: number
  repo_url?: string | null
  repo_path?: string | null
  repo_type: 'local' | 'remote'
  branch: string
  days: number
  status: string
  summary?: string
  error_message?: string
  created_at: string
  started_at?: string
  finished_at?: string
  finding_count: number
  findings?: CodeReviewFinding[]
}

export interface CodeReviewFinding {
  id: number
  task_id: number
  commit_sha?: string
  file_path?: string
  severity: string
  category?: string
  review_type?: string
  suggestion?: string
  title: string
  detail?: string
  created_at: string
}

export interface Project {
  id: number
  name: string
  description: string
  created_at: string
  requirement_count: number
}

export interface KnowledgeBase {
  id: number
  name: string
  description: string
  entry_count: number
  created_at: string
  updated_at: string
  entries?: KnowledgeEntry[]
}

export interface KnowledgeEntry {
  id: number
  knowledge_base_id: number
  title: string
  content: string
  tags: string[]
  source_type: string
  source_ref?: string
  created_at: string
  updated_at: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  per_page: number
  pages: number
}

export interface ChatAgentContext {
  requirement_id?: number | null
  title?: string
  status?: string
  headline: string
  running_agents?: Array<{ id: string; name: string; action: string }>
  stats?: {
    cases: number
    ui_scripts: number
    defects: number
    review_findings: number
  }
  pending_questions: Array<{
    id?: number | null
    agent?: string
    message?: string
    event_type?: string
  }>
  workbench_path: string
}

export interface Conversation {
  id: number
  title: string
  requirement_id?: number
  status: 'active' | 'closed'
  created_at: string
  updated_at: string
  last_read_at?: string | null
  message_count: number
  unread_count: number
  messages?: Message[]
  agent_context?: ChatAgentContext | null
}

export interface Message {
  id: number
  conversation_id: number
  sender: 'user' | 'req_agent' | 'case_agent' | 'code_agent' | 'exec_agent' | 'router'
  content: string
  agent_type?: string
  metadata?: any
  created_at: string
}

// SSE event types for conversation streaming
export type SSEEventType =
  | 'connected' | 'heartbeat'
  | 'message' | 'tool_call' | 'tool_result'
  | 'question' | 'artifact' | 'phase_change'
  | 'error' | 'done'

export interface SSEEvent {
  type: SSEEventType
  content?: string; chunk?: boolean; complete?: boolean
  name?: string; arguments?: Record<string, any>; result?: any
  question?: string; context?: string
  key?: string; data?: any
  from?: string; to?: string; agent?: string
  message?: string
  conversation_id?: number
}

export interface SendMessageResponse {
  message: string
  messages?: Message[]
  last_id?: number
  agent_context?: ChatAgentContext | null
  orchestrator_mode?: boolean
  started_from_chat?: boolean
  requirement_id?: number
  flow?: {
    message?: string
    status?: string
    flow_id?: string
    requirement_id?: number
  } | null
}

export interface HealthStatus {
  status: string
  database: string
  version: string
}

export interface FlowStartResponse {
  message: string
  requirement_id: number
  conversation_id?: number
  status: string
  flow_id?: string
  orchestrator_mode?: boolean
}

export interface FlowResumeResponse {
  message: string
  requirement_id: number
  previous_status?: string
  status: string
}

export interface FlowStartPayload {
  demand: string
  title?: string
  project_id?: number
  knowledge_base_id?: number | null
  review?: {
    repo_url?: string
    repo_path?: string
    branch?: string
    days?: number
  }
}

export interface ReportSummary {
  id: number
  requirement_id: number
  review_task_id?: number | null
  report_type: string
  title: string
  summary?: string
  created_at: string
  updated_at: string
}

export interface ReportDetail extends ReportSummary {
  html_content: string
  execution_summary?: {
    total: number
    success: number
    failed: number
    error: number
    other: number
  }
}

export interface FixSuggestion {
  id: number
  requirement_id: number
  defect_candidate_id: number
  mode: 'suggestion_only'
  title: string
  root_cause: string
  suggested_action: string
  target_files: string[]
  patch_preview: string
  confidence: number
}

export const healthApi = {
  check: () => api.get<HealthStatus>('/health'),
}

export const flowApi = {
  start: (payload: FlowStartPayload) => api.post<FlowStartResponse>('/flow/start', payload),
  resume: (requirementId: number) => api.post<FlowResumeResponse>(`/flow/resume/${requirementId}`),
  status: (requirementId: number) => api.get<{ requirement_id: number; db_status: string; flow_status: string; execution_progress: any }>(`/flow/status/${requirementId}`),
  retryScript: (scriptId: number) => api.post<{ message: string; script_id: number; status: string; execution_time: number; error?: string }>(`/flow/retry-script/${scriptId}`),
}

export const requirementsApi = {
  list: () => api.get<PaginatedResponse<Requirement>>('/requirements'),
  get: (id: number) => api.get<RequirementDetail>(`/requirements/${id}`),
  create: (data: { title: string; description: string; raw_text: string; knowledge_base_id?: number | null }) =>
    api.post<{ message: string; requirement: Requirement; conversation_id: number }>('/requirements', data),
  importFile: (formData: FormData) =>
    api.post<{ message: string; requirement: Requirement; conversation_id: number }>('/requirements/import', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  update: (id: number, data: Partial<Requirement>) =>
    api.put<{ message: string; requirement: Requirement }>(`/requirements/${id}`, data),
  delete: (id: number) => api.delete(`/requirements/${id}`),
}

export const casesApi = {
  list: (requirementId?: number) =>
    api.get<PaginatedResponse<TestCase>>('/cases', {
      params: requirementId ? { requirement_id: requirementId } : undefined,
    }),
  get: (id: number) => api.get<TestCase>(`/cases/${id}`),
}

export const executionsApi = {
  list: () => api.get<PaginatedResponse<ExecutionRecord>>('/executions'),
  get: (id: number) => api.get<ExecutionRecord>(`/executions/${id}`),
}

export const scriptsApi = {
  list: (requirementId: number) => api.get<TestScript[]>('/scripts', { params: { requirement_id: requirementId } }),
}

export const projectsApi = {
  list: () => api.get<PaginatedResponse<Project>>('/projects'),
  get: (id: number) => api.get<Project>(`/projects/${id}`),
  create: (data: { name: string; description: string }) => api.post<Project>('/projects', data),
}

export const knowledgeBasesApi = {
  list: () => api.get<{ items: KnowledgeBase[] }>('/knowledge-bases'),
  get: (id: number) => api.get<KnowledgeBase>(`/knowledge-bases/${id}`),
  create: (data: { name: string; description?: string }) =>
    api.post<{ message: string; knowledge_base: KnowledgeBase }>('/knowledge-bases', data),
  createEntry: (knowledgeBaseId: number, data: { title: string; content: string; tags?: string[]; source_type?: string; source_ref?: string }) =>
    api.post<{ message: string; entry: KnowledgeEntry }>(`/knowledge-bases/${knowledgeBaseId}/entries`, data),
  importFile: (knowledgeBaseId: number, formData: FormData, onProgress?: (pct: number) => void) =>
    api.post<{ message: string; entry: KnowledgeEntry }>(`/knowledge-bases/${knowledgeBaseId}/import`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (event) => {
        if (event.total && onProgress) {
          onProgress(Math.round((event.loaded / event.total) * 100))
        }
      },
    }),
  search: (data: { query: string; knowledge_base_ids?: number[]; limit?: number }) =>
    api.post<{ items: KnowledgeEntry[]; total: number }>('/knowledge-bases/search', data),
}

export const codeReviewsApi = {
  list: () => api.get<PaginatedResponse<CodeReviewTask>>('/code-reviews'),
  get: (id: number) => api.get<CodeReviewTask>(`/code-reviews/${id}`),
  create: (data: { repo_url?: string; repo_path?: string; branch: string; days: number }) =>
    api.post<{ task: CodeReviewTask; run_result: any }>('/code-reviews', data),
}

export const reportsApi = {
  create: (data: { requirement_id: number; review_task_id?: number | null }) =>
    api.post<{ message: string; report: ReportSummary }>('/reports', data),
  get: (id: number) => api.get<{ report: ReportDetail }>(`/reports/${id}`),
  previewUrl: (id: number) => `/api/reports/${id}/preview`,
}

export const autofixApi = {
  suggest: (requirementId: number) =>
    api.post<{ requirement_id: number; suggestion_count: number; items: FixSuggestion[] }>('/autofix/suggestions', {
      requirement_id: requirementId,
    }),
}

export interface AgentWorkbenchAgent {
  id: string
  name: string
  status: 'queued' | 'running' | 'done' | 'failed'
  current_action: string
}

export interface AgentWorkbenchItem {
  requirement: Requirement
  environment: {
    test_url?: string | null
    login_state?: string
    credential_ref?: string | null
    allow_explore?: boolean
    last_probe_at?: string | null
    probe_status?: string | null
  }
  review: {
    repo_url?: string | null
    repo_path?: string | null
    repo_type?: string | null
    branch?: string | null
    days?: number | null
    status?: string | null
  }
  artifacts: {
    cases: number
    ui_scripts: number
    api_scripts: number
    review_findings: number
    defects: number
    reports: number
  }
  agents: AgentWorkbenchAgent[]
  events: Array<{
    id: number
    agent: string
    event_type: string
    message: string
    created_at: string
    payload?: Record<string, unknown>
  }>
  interventions: Array<{ type?: string; message?: string; test_url?: string }>
  overall_progress: { status: string; updated_at?: string | null }
}

export interface AgentWorkbenchListResponse {
  summary: { total_requirements: number }
  items: AgentWorkbenchItem[]
}

export const agentWorkbenchApi = {
  list: () => api.get<AgentWorkbenchListResponse>('/agent-workbench'),
  get: (requirementId: number, sinceId?: number) =>
    api.get<AgentWorkbenchItem>(`/agent-workbench/${requirementId}`, {
      params: sinceId ? { since_id: sinceId } : undefined,
    }),
}

export const conversationsApi = {
  list: () => api.get<{ items: Conversation[]; total: number }>('/conversations'),
  get: (id: number) => api.get<Conversation>(`/conversations/${id}`),
  getAgentContext: (id: number) => api.get<ChatAgentContext>(`/conversations/${id}/agent-context`),
  create: (data?: { title?: string; requirement_id?: number }) =>
    api.post<{ message: string; conversation: Conversation }>('/conversations', data || {}),
  delete: (id: number) => api.delete(`/conversations/${id}`),
  getMessages: (id: number, lastId?: number) =>
    api.get<{ items: Message[]; count: number }>(`/conversations/${id}/messages`, {
      params: lastId ? { last_id: lastId } : undefined,
    }),
  sendMessage: (id: number, content: string) =>
    api.post<SendMessageResponse>(
      `/conversations/${id}/messages`,
      { content },
    ),
  markRead: (id: number) =>
    api.post<{ message: string; conversation_id: number; unread_count: number }>(`/conversations/${id}/read`),
  /** Connect to the SSE stream for real-time agent events. */
  streamUrl: (id: number) => `/api/conversations/${id}/stream`,
}

export interface AgentConfig {
  id: number
  agent_type: string
  project_id?: number | null
  system_prompt?: string
  model_name?: string
  temperature: number
  max_tokens: number
  is_enabled: boolean
  extra_config: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface EnvironmentConfig {
  test_url?: string | null
  login_state?: string
  credential_ref?: string | null
  allow_explore?: boolean
  last_probe_at?: string | null
  probe_status?: string | null
}

export const agentConfigsApi = {
  list: (projectId?: number) =>
    api.get<{ items: AgentConfig[]; total: number }>('/agent-configs', { params: projectId ? { project_id: projectId } : undefined }),
  upsert: (data: Partial<AgentConfig> & { agent_type: string }) =>
    api.post<{ message: string; config: AgentConfig }>('/agent-configs', data),
  update: (id: number, data: Partial<AgentConfig>) =>
    api.put<{ message: string; config: AgentConfig }>(`/agent-configs/${id}`, data),
}

export const environmentApi = {
  get: (requirementId: number) =>
    api.get<{ requirement_id: number; environment: EnvironmentConfig }>(`/environment/${requirementId}`),
  save: (data: { requirement_id: number; test_url?: string; login_state?: string; credential_ref?: string; allow_explore?: boolean }) =>
    api.post<{ message: string; environment: EnvironmentConfig }>('/environment', data),
}

export default api
