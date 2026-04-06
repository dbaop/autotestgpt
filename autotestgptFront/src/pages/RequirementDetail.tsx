import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { requirementsApi, casesApi, flowApi, Requirement, TestCase } from '../api'
import TestScripts from '../components/TestScripts'

const WORKFLOW_STEPS = [
  { step: 1, name: '需求解析', agent: 'ReqAgent', status: 'pending' },
  { step: 2, name: '用例设计', agent: 'CaseAgent', status: 'parsed' },
  { step: 3, name: '代码生成', agent: 'CodeAgent', status: 'cases_generated' },
  { step: 4, name: '执行测试', agent: 'ExecAgent', status: 'code_generated' }
]

export default function RequirementDetail() {
  const { id } = useParams<{ id: string }>()
  const [requirement, setRequirement] = useState<Requirement | null>(null)
  const [cases, setCases] = useState<TestCase[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const pollingRef = useRef<number | null>(null)
  const mountedRef = useRef(true)

  const loadData = useCallback(async (showRefreshing = false) => {
    if (!id) return

    if (showRefreshing) setRefreshing(true)
    setError(null)

    try {
      const reqId = parseInt(id)
      const [reqRes, casesRes] = await Promise.all([
        requirementsApi.get(reqId),
        casesApi.list(reqId)
      ])
      
      if (!mountedRef.current) return
      
      setRequirement(reqRes.data)
      setCases(casesRes.data.items || [])
    } catch (err: any) {
      console.error('Failed to load:', err)
      if (mountedRef.current) {
        if (err.code === 'ERR_NETWORK' || err.message?.includes('Network Error')) {
          setError('网络连接失败，正在尝试重连...')
        } else {
          setError(err.response?.data?.error || '加载数据失败')
        }
      }
    } finally {
      if (mountedRef.current) {
        setLoading(false)
        setRefreshing(false)
      }
    }
  }, [id])

  useEffect(() => {
    mountedRef.current = true
    loadData()
    
    return () => {
      mountedRef.current = false
      if (pollingRef.current) {
        clearInterval(pollingRef.current)
        pollingRef.current = null
      }
    }
  }, [loadData])

  useEffect(() => {
    if (!requirement || !mountedRef.current) return

    const isProcessing = ['pending', 'parsed'].includes(requirement.status)

    if (isProcessing && !pollingRef.current) {
      pollingRef.current = window.setInterval(() => {
        if (mountedRef.current) {
          loadData()
        }
      }, 3000)
    } else if (!isProcessing && pollingRef.current) {
      clearInterval(pollingRef.current)
      pollingRef.current = null
    }

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current)
        pollingRef.current = null
      }
    }
  }, [requirement, loadData])

  const handleRefresh = () => {
    loadData(true)
  }

  const handleResume = async () => {
    if (!requirement) return
    try {
      await flowApi.resume(requirement.id)
      loadData(true)
    } catch (err: any) {
      console.error('Failed to resume:', err)
      setError(err.response?.data?.error || '恢复流程失败')
    }
  }

  const getCurrentStep = () => {
    if (!requirement) return 0
    const status = requirement.status
    if (status === 'pending') return 1
    if (status === 'parsed') return 2
    if (status === 'cases_generated') return 3
    if (status === 'code_generated') return 4
    if (status === 'executing') return 5
    if (status === 'executed') return 5
    if (status === 'error') return 0
    return 0
  }

  const getStepStatus = (stepStatus: string) => {
    if (!requirement) return 'pending'
    const currentStep = getCurrentStep()
    const stepIndex = WORKFLOW_STEPS.findIndex(s => s.status === stepStatus) + 1
    if (stepIndex < currentStep) return 'completed'
    if (stepIndex === currentStep) return requirement.status === 'error' ? 'error' : 'active'
    return 'pending'
  }

  if (loading && !requirement) {
    return (
      <div className="text-center py-8">
        <div className="flex items-center justify-center gap-2 text-gray-500">
          <svg className="animate-spin w-5 h-5" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          加载中...
        </div>
      </div>
    )
  }

  if (!requirement && !loading) {
    return (
      <div className="text-center py-8">
        <div className="text-gray-500 mb-4">需求不存在</div>
        <Link to="/requirements" className="text-indigo-600 hover:text-indigo-800">
          返回需求列表
        </Link>
      </div>
    )
  }

  const isProcessing = requirement ? ['pending', 'parsed', 'cases_generated', 'code_generated'].includes(requirement.status) : false

  return (
    <div>
      <div className="mb-6 flex justify-between items-center">
        <Link to="/requirements" className="text-indigo-600 hover:text-indigo-800 text-sm">
          ← 返回需求列表
        </Link>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="mb-6 bg-yellow-50 border border-yellow-200 rounded-lg p-4 flex items-center justify-between">
          <div className="flex items-center gap-2 text-yellow-800">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <span>{error}</span>
          </div>
          <button
            onClick={handleRefresh}
            className="text-yellow-800 hover:text-yellow-900 underline text-sm"
          >
            重试
          </button>
        </div>
      )}

      {/* Header */}
      {requirement && (
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <div className="flex justify-between items-start">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">{requirement.title}</h1>
              <p className="text-gray-500 mt-2">{requirement.description}</p>
            </div>
            <div className="flex items-center gap-3">
              {isProcessing && (
                <span className="flex items-center gap-2 text-sm text-indigo-600">
                  <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  处理中...
                </span>
              )}
              <StatusBadge status={requirement.status} />
            </div>
          </div>
          <div className="mt-4 text-sm text-gray-400">
            创建于 {new Date(requirement.created_at).toLocaleString('zh-CN')}
          </div>
        </div>
      )}

      {/* Workflow Progress */}
      {requirement && (
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-semibold">工作流进度</h3>
            <span className="text-sm text-gray-500">
              当前进度: 第 {getCurrentStep()} / 4 步
            </span>
          </div>

          {/* Progress Bar */}
          <div className="mb-6">
            <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
              <div
                className={`h-full transition-all duration-500 ${
                  requirement.status === 'error' ? 'bg-red-500' : 'bg-indigo-600'
                }`}
                style={{ width: `${(getCurrentStep() / 4) * 100}%` }}
              />
            </div>
          </div>

          {/* Steps */}
          <div className="grid grid-cols-4 gap-4">
            {WORKFLOW_STEPS.map((step) => {
              const status = getStepStatus(step.status)
              return (
                <WorkflowProgressStep
                  key={step.step}
                  step={step.step}
                  name={step.name}
                  agent={step.agent}
                  status={status}
                />
              )
            })}
          </div>

          {/* Execution Progress */}
          {requirement.status === 'executing' && requirement.execution_progress && (
            <div className="mt-6 p-4 bg-blue-50 rounded-lg">
              <h4 className="font-medium mb-2">执行进度</h4>
              <div className="flex justify-between text-sm mb-2">
                <span>当前执行: {requirement.execution_progress.current_script_name || '准备中'}</span>
                <span>{requirement.execution_progress.executed}/{requirement.execution_progress.total} 个脚本</span>
              </div>
              <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
                <div
                  className="h-full bg-green-500 transition-all duration-300"
                  style={{ 
                    width: `${(requirement.execution_progress.executed / requirement.execution_progress.total) * 100}%` 
                  }}
                />
              </div>
              {requirement.execution_progress.current_case_id && (
                <div className="mt-2 text-sm text-gray-600">
                  对应测试用例ID: {requirement.execution_progress.current_case_id}
                </div>
              )}
              
              {/* 执行详情 */}
              {requirement.execution_progress.details && requirement.execution_progress.details.length > 0 && (
                <div className="mt-4">
                  <h5 className="text-sm font-medium mb-2">执行详情</h5>
                  <div className="space-y-2">
                    {requirement.execution_progress.details.map((detail: any, index: number) => (
                      <div key={detail.script_id} className="border rounded p-3">
                        <div className="flex justify-between items-center">
                          <span className="font-medium">
                            脚本 {index + 1}: {detail.script_name?.split('\\').pop() || detail.script_name}
                          </span>
                          <span className={`text-sm px-2 py-1 rounded ${detail.status === 'running' ? 'bg-yellow-100 text-yellow-800' : detail.status === 'error' ? 'bg-red-100 text-red-800' : 'bg-green-100 text-green-800'}`}>
                            {detail.status === 'running' ? '执行中' : detail.status === 'error' ? '失败' : '完成'}
                          </span>
                        </div>
                        <div className="text-xs text-gray-500 mt-1">
                          开始时间: {new Date(detail.start_time).toLocaleString('zh-CN')}
                          {detail.end_time && (
                            <span className="ml-4">
                              结束时间: {new Date(detail.end_time).toLocaleString('zh-CN')}
                            </span>
                          )}
                          {detail.execution_time && (
                            <span className="ml-4">
                              执行时间: {detail.execution_time.toFixed(2)}秒
                            </span>
                          )}
                        </div>
                        {detail.error && (
                          <div className="mt-2 text-xs text-red-600 bg-red-50 p-2 rounded">
                            错误: {detail.error}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Execution Results */}
          {requirement.status === 'executed' && requirement.execution_progress && requirement.execution_progress.details && (
            <div className="mt-6 p-4 bg-gray-50 rounded-lg">
              <h4 className="font-medium mb-2">执行结果</h4>
              <div className="flex justify-between text-sm mb-4">
                <span>总脚本数: {requirement.execution_progress.total}</span>
                <span>成功: {requirement.execution_progress.details.filter((d: any) => d.status === 'completed').length}</span>
                <span>失败: {requirement.execution_progress.details.filter((d: any) => d.status === 'error').length}</span>
                <span>总耗时: {(() => {
                  const start = new Date(requirement.execution_progress.start_time).getTime()
                  const end = new Date(requirement.execution_progress.end_time).getTime()
                  return ((end - start) / 1000).toFixed(2) + '秒'
                })()}</span>
              </div>
              <div className="space-y-2">
                {requirement.execution_progress.details.map((detail: any, index: number) => (
                  <div key={detail.script_id} className="border rounded p-3">
                    <div className="flex justify-between items-center">
                      <span className="font-medium">
                        脚本 {index + 1}: {detail.script_name?.split('\\').pop() || detail.script_name}
                      </span>
                      <span className={`text-sm px-2 py-1 rounded ${detail.status === 'error' ? 'bg-red-100 text-red-800' : 'bg-green-100 text-green-800'}`}>
                        {detail.status === 'error' ? '失败' : '成功'}
                      </span>
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      开始时间: {new Date(detail.start_time).toLocaleString('zh-CN')}
                      <span className="ml-4">
                        结束时间: {new Date(detail.end_time).toLocaleString('zh-CN')}
                      </span>
                      <span className="ml-4">
                        执行时间: {detail.execution_time?.toFixed(2) || 0}秒
                      </span>
                    </div>
                    {detail.error && (
                      <div className="mt-2 text-xs text-red-600 bg-red-50 p-2 rounded">
                        错误: {detail.error}
                      </div>
                    )}
                    {detail.result && Object.keys(detail.result).length > 0 && (
                      <div className="mt-2 text-xs text-blue-600 bg-blue-50 p-2 rounded">
                        结果: {JSON.stringify(detail.result)}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Action Buttons */}
          <div className="mt-4 flex justify-end gap-2">
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="flex items-center gap-2 px-3 py-1.5 text-sm bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
            >
              <svg className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              {refreshing ? '刷新中...' : '刷新进度'}
            </button>
            {isProcessing && (
              <button
                onClick={handleResume}
                className="flex items-center gap-2 px-3 py-1.5 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                恢复流程
              </button>
            )}
          </div>
        </div>
      )}

      {/* Test Cases */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-semibold">测试用例 ({cases.length})</h3>
        </div>
        {cases.length === 0 ? (
          <div className="p-6 text-center text-gray-500">
            {isProcessing ? (
              <div className="flex items-center justify-center gap-2">
                <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                正在生成测试用例...
              </div>
            ) : '暂无测试用例'}
          </div>
        ) : (
          <div className="divide-y divide-gray-200">
            {cases.map(c => (
              <div key={c.id} className="px-6 py-4">
                <div className="flex justify-between items-start">
                  <div>
                    <h4 className="font-medium text-gray-900">{c.title}</h4>
                    <p className="text-sm text-gray-500 mt-1">{c.description}</p>
                  </div>
                  <div className="flex gap-2">
                    <PriorityBadge priority={c.priority} />
                    <TypeBadge type={c.test_type} />
                  </div>
                </div>
                {c.steps && c.steps.length > 0 && (
                  <div className="mt-3">
                    <div className="text-xs text-gray-500 mb-1">测试步骤:</div>
                    <ol className="list-decimal list-inside text-sm text-gray-700 space-y-2">
                      {c.steps.map((step: any, idx: number) => (
                        <li key={idx} className="pl-1">
                          <span className="font-medium">{step.action || step}</span>
                          {step.expected && (
                            <span className="text-gray-500 ml-2">→ {step.expected}</span>
                          )}
                        </li>
                      ))}
                    </ol>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Test Scripts */}
      <TestScripts requirementId={parseInt(id)} />
    </div>
  )
}

function WorkflowProgressStep({
  step, name, agent, status
}: {
  step: number
  name: string
  agent: string
  status: 'completed' | 'active' | 'pending' | 'error'
}) {
  const bgClass = {
    completed: 'bg-green-50 border-green-200',
    active: 'bg-indigo-50 border-indigo-200',
    pending: 'bg-gray-50 border-gray-200',
    error: 'bg-red-50 border-red-200'
  }[status]

  const iconClass = {
    completed: 'bg-green-500 text-white',
    active: 'bg-indigo-600 text-white',
    pending: 'bg-gray-300 text-gray-600',
    error: 'bg-red-500 text-white'
  }[status]

  const textClass = {
    completed: 'text-green-700',
    active: 'text-indigo-700',
    pending: 'text-gray-500',
    error: 'text-red-700'
  }[status]

  return (
    <div className={`rounded-lg p-4 text-center border-2 ${bgClass} transition-all duration-300`}>
      <div className={`w-10 h-10 rounded-full flex items-center justify-center mx-auto mb-2 text-sm font-bold ${iconClass}`}>
        {status === 'completed' ? (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        ) : status === 'active' ? (
          <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
        ) : status === 'error' ? (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        ) : (
          step
        )}
      </div>
      <div className={`font-medium ${textClass}`}>{name}</div>
      <div className="text-xs text-gray-500 mt-1">{agent}</div>
      {status === 'active' && (
        <div className="text-xs text-indigo-600 mt-2">处理中...</div>
      )}
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const statusMap: Record<string, { bg: string, text: string, label: string }> = {
    pending: { bg: 'bg-yellow-100', text: 'text-yellow-800', label: '待处理' },
    parsed: { bg: 'bg-blue-100', text: 'text-blue-800', label: '已解析' },
    cases_generated: { bg: 'bg-green-100', text: 'text-green-800', label: '用例已生成' },
    code_generated: { bg: 'bg-indigo-100', text: 'text-indigo-800', label: '代码已生成' },
    executing: { bg: 'bg-orange-100', text: 'text-orange-800', label: '执行中' },
    executed: { bg: 'bg-purple-100', text: 'text-purple-800', label: '已执行' },
    error: { bg: 'bg-red-100', text: 'text-red-800', label: '错误' }
  }

  const s = statusMap[status] || statusMap.pending

  return (
    <span className={`px-3 py-1.5 rounded-full text-sm font-medium ${s.bg} ${s.text}`}>
      {s.label}
    </span>
  )
}

function PriorityBadge({ priority }: { priority: string }) {
  const map: Record<string, string> = {
    high: 'bg-red-100 text-red-800',
    medium: 'bg-yellow-100 text-yellow-800',
    low: 'bg-green-100 text-green-800'
  }
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${map[priority] || map.medium}`}>
      {priority === 'high' ? '高' : priority === 'medium' ? '中' : '低'}
    </span>
  )
}

function TypeBadge({ type }: { type: string }) {
  const map: Record<string, string> = {
    api: 'bg-blue-100 text-blue-800',
    ui: 'bg-purple-100 text-purple-800',
    performance: 'bg-orange-100 text-orange-800',
    security: 'bg-red-100 text-red-800'
  }
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${map[type] || 'bg-gray-100 text-gray-800'}`}>
      {type?.toUpperCase() || 'API'}
    </span>
  )
}
