import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000
})

export interface Requirement {
  id: number
  title: string
  description: string
  status: 'pending' | 'parsed' | 'cases_generated' | 'code_generated' | 'executed' | 'error'
  created_at: string
  updated_at: string
  test_case_count: number
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
  status: 'passed' | 'failed' | 'error' | 'running'
  execution_time: number
  error_message: string
  started_at: string
  finished_at: string
  report_path: string
}

export interface Project {
  id: number
  name: string
  description: string
  created_at: string
  requirement_count: number
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  per_page: number
  pages: number
}

export interface Conversation {
  id: number
  title: string
  requirement_id?: number
  status: 'active' | 'closed'
  created_at: string
  updated_at: string
  message_count: number
  messages?: Message[]
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

export interface HealthStatus {
  status: string
  database: string
  version: string
}

export interface FlowStartResponse {
  message: string
  requirement_id: number
  status: string
  flow_id: string
}

export interface FlowResumeResponse {
  message: string
  requirement_id: number
  previous_status: string
  status: string
}

export const healthApi = {
  check: () => api.get<HealthStatus>('/health')
}

export const flowApi = {
  start: (demand: string, projectId?: number) =>
    api.post<FlowStartResponse>('/flow/start', { demand, project_id: projectId }),
  resume: (requirementId: number) =>
    api.post<FlowResumeResponse>(`/flow/resume/${requirementId}`)
}

export const requirementsApi = {
  list: () => api.get<PaginatedResponse<Requirement>>('/requirements'),
  get: (id: number) => api.get<Requirement>(`/requirements/${id}`),
  create: (data: { title: string; description: string; raw_text: string }) =>
    api.post<Requirement>('/requirements', data),
  update: (id: number, data: Partial<Requirement>) =>
    api.put<Requirement>(`/requirements/${id}`, data),
  delete: (id: number) => api.delete(`/requirements/${id}`)
}

export const casesApi = {
  list: (requirementId?: number) =>
    api.get<PaginatedResponse<TestCase>>('/cases', { params: requirementId ? { requirement_id: requirementId } : undefined }),
  get: (id: number) => api.get<TestCase>(`/cases/${id}`)
}

export const executionsApi = {
  list: () => api.get<PaginatedResponse<ExecutionRecord>>('/executions'),
  get: (id: number) => api.get<ExecutionRecord>(`/executions/${id}`)
}

export const scriptsApi = {
  list: (requirementId: number) =>
    api.get<any[]>('/scripts', { params: { requirement_id: requirementId } })
}

export const projectsApi = {
  list: () => api.get<PaginatedResponse<Project>>('/projects'),
  get: (id: number) => api.get<Project>(`/projects/${id}`),
  create: (data: { name: string; description: string }) =>
    api.post<Project>('/projects', data)
}

export const conversationsApi = {
  list: () => api.get<{ items: Conversation[]; total: number }>('/conversations'),
  get: (id: number) => api.get<Conversation>(`/conversations/${id}`),
  create: (data?: { title?: string; requirement_id?: number }) =>
    api.post<{ message: string; conversation: Conversation }>('/conversations', data || {}),
  delete: (id: number) => api.delete(`/conversations/${id}`),
  getMessages: (id: number, lastId?: number) =>
    api.get<{ items: Message[]; count: number }>(`/conversations/${id}/messages`, {
      params: lastId ? { last_id: lastId } : undefined
    }),
  sendMessage: (id: number, content: string) =>
    api.post<{ message: string; messages: Message[]; last_id: number }>(`/conversations/${id}/messages`, { content })
}

export default api
