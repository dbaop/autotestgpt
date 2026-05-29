import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  autofixApi, codeReviewsApi, CodeReviewTask, conversationsApi, FixSuggestion,
  flowApi, reportsApi, ReportSummary,
  RequirementDetail as RequirementDetailType, requirementsApi, TestCase,
} from '../api'
import TestScripts from '../components/TestScripts'

const C = {
  bg: 'var(--bg-card)',
  bgElevated: 'var(--bg-elevated)',
  bd: 'var(--border-subtle)',
  cyan: 'var(--accent-cyan)',
  violet: 'var(--accent-violet)',
  magenta: 'var(--accent-magenta)',
  emerald: 'var(--accent-emerald)',
  amber: 'var(--accent-amber)',
  rose: 'var(--accent-magenta)',
  text: 'var(--text-primary)',
  text2: 'var(--text-secondary)',
  text3: 'var(--text-muted)',
  mono: 'var(--font-mono)',
  display: 'var(--font-display)',
  body: 'var(--font-body)',
}

const WORKFLOW_STEPS = [
  { key: 'pending', name: '需求解析', agent: 'ReqAgent', color: 'var(--accent-cyan)' },
  { key: 'parsed', name: '用例设计', agent: 'CaseAgent', color: 'var(--accent-emerald)' },
  { key: 'cases_generated', name: '脚本生成', agent: 'CodeAgent', color: 'var(--accent-amber)' },
  { key: 'code_generated', name: '执行测试', agent: 'ExecAgent', color: 'var(--accent-violet)' },
]

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div style={{
      padding: '16px', borderRadius: 14, background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)',
    }}>
      <div style={{ fontFamily: C.mono, fontSize: 10, fontWeight: 600, letterSpacing: '0.14em', color: C.text3, textTransform: 'uppercase', marginBottom: 6 }}>
        {label}
      </div>
      <div style={{ fontFamily: C.display, fontSize: 22, fontWeight: 800, color: C.text }}>
        {value}
      </div>
    </div>
  )
}

function WorkflowStep({ name, agent, status, color }: { name: string; agent: string; status: 'completed' | 'active' | 'pending'; color: string }) {
  const style = status === 'completed'
    ? { borderColor: 'rgba(0,255,136,0.3)', bg: 'rgba(0,255,136,0.06)', textColor: 'var(--accent-emerald)' }
    : status === 'active'
    ? { borderColor: `${color}40`, bg: `${color}08`, textColor: color }
    : { borderColor: 'var(--border-subtle)', bg: 'rgba(255,255,255,0.01)', textColor: 'var(--text-muted)' }

  return (
    <div style={{
      padding: '16px', borderRadius: 14, border: `1px solid ${style.borderColor}`, background: style.bg,
    }}>
      <div style={{ fontFamily: C.display, fontSize: 14, fontWeight: 700, color: style.textColor, marginBottom: 4 }}>
        {name}
      </div>
      <div style={{ fontFamily: C.mono, fontSize: 9, fontWeight: 600, letterSpacing: '0.16em', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
        {agent}
      </div>
      {status === 'completed' && (
        <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 4 }}>
          <span style={{ fontFamily: C.mono, fontSize: 10, color: 'var(--accent-emerald)' }}>✓</span>
        </div>
      )}
    </div>
  )
}

function TinyBadge({ text, color }: { text: string; color: string }) {
  return (
    <span style={{
      fontFamily: C.mono, fontSize: 9, fontWeight: 700, letterSpacing: '0.1em', color, background: `${color}18`,
      padding: '3px 8px', borderRadius: 100,
    }}>
      {text}
    </span>
  )
}

export default function RequirementDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const requirementId = Number(id)

  const [requirement, setRequirement] = useState<RequirementDetailType | null>(null)
  const [cases, setCases] = useState<TestCase[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reviewTasks, setReviewTasks] = useState<CodeReviewTask[]>([])
  const [selectedReviewTaskId, setSelectedReviewTaskId] = useState<number | ''>('')
  const [report, setReport] = useState<ReportSummary | null>(null)
  const [fixSuggestions, setFixSuggestions] = useState<FixSuggestion[]>([])
  const [generatingReport, setGeneratingReport] = useState(false)
  const [generatingFixes, setGeneratingFixes] = useState(false)
  const [retryingScriptIds, setRetryingScriptIds] = useState<Set<number>>(new Set())
  const pollingRef = useRef<number | null>(null)

  const loadData = useCallback(async (showRefreshing = false) => {
    if (!requirementId) return
    if (showRefreshing) setRefreshing(true)
    setError(null)
    try {
      const [reqRes, casesRes, reviewsRes] = await Promise.all([
        requirementsApi.get(requirementId),
        requirementsApi.get(requirementId),
        codeReviewsApi.list(),
      ])
      setRequirement(reqRes.data)
      setCases(casesRes.data.test_cases || [])
      setReviewTasks(reviewsRes.data.items || [])
    } catch (err: any) {
      setError(err.response?.data?.message || err.response?.data?.error || '加载需求详情失败')
    } finally { setLoading(false); setRefreshing(false) }
  }, [requirementId])

  useEffect(() => {
    loadData()
    return () => { if (pollingRef.current) window.clearInterval(pollingRef.current) }
  }, [loadData])

  useEffect(() => {
    if (!requirement) return
    const shouldPoll = ['pending', 'parsed', 'cases_generated', 'code_generated', 'executing'].includes(requirement.status)
    if (shouldPoll && !pollingRef.current) {
      pollingRef.current = window.setInterval(() => loadData(), 3000)
    } else if (!shouldPoll && pollingRef.current) {
      window.clearInterval(pollingRef.current); pollingRef.current = null
    }
  }, [loadData, requirement])

  const currentStep = useMemo(() => {
    if (!requirement) return 0
    const order = ['pending', 'parsed', 'cases_generated', 'code_generated', 'executing', 'executed', 'completed']
    const idx = order.indexOf(requirement.status)
    if (idx <= 0) return 1; if (idx === 1) return 2; if (idx === 2) return 3
    return 4
  }, [requirement])

  const selectedReviewTask = useMemo(
    () => reviewTasks.find(item => item.id === selectedReviewTaskId) || null,
    [reviewTasks, selectedReviewTaskId]
  )

  const executionDetails = requirement?.execution_progress?.details || []

  const handleResume = async () => {
    if (!requirement) return
    try { await flowApi.resume(requirement.id); await loadData(true) }
    catch (err: any) { setError(err.response?.data?.message || err.response?.data?.error || '恢复流程失败') }
  }

  const handleRetryScript = async (scriptId: number) => {
    setRetryingScriptIds(prev => new Set(prev).add(scriptId))
    setError(null)
    try { await flowApi.retryScript(scriptId); await loadData(true) }
    catch (err: any) { setError(err.response?.data?.message || err.response?.data?.error || '重试脚本失败') }
    finally {
      setRetryingScriptIds(prev => { const n = new Set(prev); n.delete(scriptId); return n })
    }
  }

  const handleGenerateReport = async () => {
    if (!requirement) return
    setGeneratingReport(true); setError(null)
    try {
      const res = await reportsApi.create({ requirement_id: requirement.id, review_task_id: selectedReviewTaskId || undefined })
      setReport(res.data.report)
    } catch (err: any) { setError(err.response?.data?.message || err.response?.data?.error || '生成报告失败') }
    finally { setGeneratingReport(false) }
  }

  const openRequirementChat = async () => {
    if (!requirement) return
    try {
      const res = await conversationsApi.create({
        title: `需求 #${requirement.id} · ${requirement.title}`,
        requirement_id: requirement.id,
      })
      navigate('/chat', { state: { conversationId: res.data.conversation.id } })
    } catch (err: any) {
      setError(err.response?.data?.message || err.response?.data?.error || '打开对话失败')
    }
  }

  const handleGenerateFixes = async () => {
    if (!requirement) return
    setGeneratingFixes(true); setError(null)
    try { const res = await autofixApi.suggest(requirement.id); setFixSuggestions(res.data.items || []) }
    catch (err: any) { setError(err.response?.data?.message || err.response?.data?.error || '生成修复建议失败') }
    finally { setGeneratingFixes(false) }
  }

  if (loading) return (
    <div style={{ textAlign: 'center', padding: 80, color: C.text3, fontFamily: C.mono, fontSize: 13 }}>
      <div style={{ display: 'inline-block', animation: 'spin-slow 1s linear infinite', fontSize: 24 }}>◈</div>
      <div style={{ marginTop: 16 }}>加载中...</div>
    </div>
  )

  if (!requirement) return (
    <div style={{ textAlign: 'center', padding: 80, color: C.text3, fontFamily: C.mono }}>
      需求不存在。<Link to="/requirements" style={{ color: 'var(--accent-cyan)' }}>返回需求列表</Link>
    </div>
  )

  return (
    <div className="page-stack animate-fade-in">
      {/* Top bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Link to="/requirements" style={{
          fontFamily: C.mono, fontSize: 12, fontWeight: 600, color: 'var(--accent-cyan)',
          textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 6,
        }}>
          ← 返回需求列表
        </Link>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Link
            to={`/workbench/${requirement.id}`}
            style={{
              fontFamily: C.mono, fontSize: 11, fontWeight: 600, color: C.violet,
              textDecoration: 'none', border: '1px solid rgba(139,92,246,0.35)',
              borderRadius: 100, padding: '6px 16px',
            }}
          >
            Agent 工作台
          </Link>
          <button type="button" onClick={openRequirementChat}
            style={{
              fontFamily: C.mono, fontSize: 11, color: C.cyan, background: 'none',
              border: '1px solid rgba(0,212,255,0.35)', borderRadius: 100, padding: '6px 16px', cursor: 'pointer',
            }}>
            对话协作
          </button>
          <button type="button" onClick={() => loadData(true)} disabled={refreshing}
            style={{
              fontFamily: C.mono, fontSize: 11, color: C.text3, background: 'none',
              border: '1px solid var(--border-default)', borderRadius: 100, padding: '6px 16px', cursor: 'pointer',
              opacity: refreshing ? 0.5 : 1,
            }}>
            {refreshing ? '刷新中...' : '刷新'}
          </button>
        </div>
      </div>

      {error && (
        <div style={{
          padding: '14px 18px', borderRadius: 14, border: '1px solid rgba(255,45,120,0.3)',
          background: 'rgba(255,45,120,0.06)', fontFamily: C.mono, fontSize: 12, color: 'var(--accent-magenta)',
        }}>
          [!] {error}
        </div>
      )}

      {/* Overview */}
      <section className="gradient-border-card panel-inner">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 20 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontFamily: C.mono, fontSize: 11, letterSpacing: '0.32em', color: 'var(--accent-cyan)', textTransform: 'uppercase', marginBottom: 10 }}>
              &gt; requirement_overview
            </div>
            <h1 style={{ fontFamily: C.display, fontSize: 28, fontWeight: 800, color: C.text, margin: '0 0 10px', letterSpacing: 0 }}>
              {requirement.title}
            </h1>
            <p style={{ fontFamily: C.body, fontSize: 14, color: C.text2, margin: 0, lineHeight: 1.7 }}>
              {requirement.description}
            </p>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 10 }}>
            <span className={`status-badge ${requirement.status}`}>
              {requirement.status}
            </span>
            <span style={{ fontFamily: C.mono, fontSize: 10, color: C.text3 }}>
              created {new Date(requirement.created_at).toLocaleString('zh-CN')}
            </span>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginTop: 28 }}>
          <StatCard label="知识库绑定" value={requirement.knowledge_base_id ? `KB#${requirement.knowledge_base_id}` : '--'} />
          <StatCard label="测试用例" value={String(cases.length)} />
          <StatCard label="执行明细" value={String(executionDetails.length)} />
          <StatCard label="当前阶段" value={`Step ${currentStep}/4`} />
        </div>
      </section>

      {/* Main content */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 20 }}>
        {/* Left column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Workflow progress */}
          <section className="gradient-border-card" style={{ padding: '28px 24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <div>
                <div style={{ fontFamily: C.mono, fontSize: 11, letterSpacing: '0.28em', color: C.text3, textTransform: 'uppercase', marginBottom: 6 }}>
                  /workflow
                </div>
                <h2 style={{ fontFamily: C.display, fontSize: 22, fontWeight: 800, color: C.text, margin: 0 }}>
                  主流程进度
                </h2>
              </div>
              <span style={{ fontFamily: C.mono, fontSize: 12, color: 'var(--accent-cyan)' }}>
                step {currentStep} / 4
              </span>
            </div>

            {/* Progress bar */}
            <div style={{ height: 4, borderRadius: 2, background: 'rgba(255,255,255,0.05)', marginBottom: 24, overflow: 'hidden' }}>
              <div style={{
                height: '100%', borderRadius: 2, width: `${(currentStep / 4) * 100}%`,
                background: 'linear-gradient(90deg, var(--accent-cyan), var(--accent-emerald))',
                transition: 'width 0.6s ease',
              }} />
            </div>

            {/* Steps grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 20 }} className="stagger-children">
              {WORKFLOW_STEPS.map((step, i) => {
                const status = i + 1 < currentStep ? 'completed' : i + 1 === currentStep ? 'active' : 'pending'
                return <WorkflowStep key={step.name} status={status} name={step.name} agent={step.agent} color={step.color} />
              })}
            </div>

            <button type="button" onClick={handleResume} className="btn btn-primary">
              继续执行流程
            </button>
          </section>

          {/* Test Cases */}
          <section className="gradient-border-card" style={{ padding: '28px 24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <div>
                <div style={{ fontFamily: C.mono, fontSize: 11, letterSpacing: '0.28em', color: C.text3, textTransform: 'uppercase', marginBottom: 6 }}>
                  /cases
                </div>
                <h2 style={{ fontFamily: C.display, fontSize: 22, fontWeight: 800, color: C.text, margin: 0 }}>
                  测试用例
                </h2>
              </div>
              <span style={{
                fontFamily: C.mono, fontSize: 11, color: 'var(--accent-emerald)',
                background: 'rgba(0,255,136,0.08)', padding: '5px 14px', borderRadius: 100, border: '1px solid rgba(0,255,136,0.2)',
              }}>
                {cases.length} items
              </span>
            </div>

            {!cases.length ? (
              <div style={{
                textAlign: 'center', padding: 48, color: C.text3, fontFamily: C.mono, fontSize: 12,
                border: '1px dashed var(--border-default)', borderRadius: 14,
              }}>
                暂无测试用例
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }} className="stagger-children">
                {cases.map(item => (
                  <article key={item.id} className="animate-float-up card-hover" style={{
                    padding: '18px 20px', border: '1px solid var(--border-subtle)',
                    borderRadius: 16, background: 'rgba(255,255,255,0.02)', transition: 'all 0.25s',
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontFamily: C.display, fontSize: 14, fontWeight: 600, color: C.text, marginBottom: 4 }}>
                          {item.title}
                        </div>
                        <div style={{ fontFamily: C.body, fontSize: 12, color: C.text3, lineHeight: 1.5 }}>
                          {item.description}
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                        <TinyBadge text={item.test_type.toUpperCase()} color="#38bdf8" />
                        <TinyBadge text={item.priority.toUpperCase()} color="var(--accent-amber)" />
                      </div>
                    </div>
                    {item.steps?.length ? (
                      <ol style={{ margin: 0, marginTop: 14, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {item.steps.map((step: any, i: number) => (
                          <li key={i} style={{
                            padding: '12px 16px', borderRadius: 10, background: 'rgba(255,255,255,0.02)',
                            border: '1px solid var(--border-subtle)', fontFamily: C.body, fontSize: 12, color: C.text2,
                          }}>
                            <span style={{ fontFamily: C.mono, fontWeight: 700, color: 'var(--accent-cyan)', marginRight: 8 }}>
                              #{i + 1}
                            </span>
                            {step.action || step}
                            {step.expected && (
                              <span style={{ color: C.text3, marginLeft: 8 }}>
                                · 预期：{step.expected}
                              </span>
                            )}
                          </li>
                        ))}
                      </ol>
                    ) : null}
                  </article>
                ))}
              </div>
            )}
          </section>

          {/* Execution Results */}
          <section className="gradient-border-card" style={{ padding: '28px 24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <div>
                <div style={{ fontFamily: C.mono, fontSize: 11, letterSpacing: '0.28em', color: C.text3, textTransform: 'uppercase', marginBottom: 6 }}>
                  /exec/results
                </div>
                <h2 style={{ fontFamily: C.display, fontSize: 22, fontWeight: 800, color: C.text, margin: 0 }}>
                  执行结果
                </h2>
              </div>
              <span style={{
                fontFamily: C.mono, fontSize: 11, color: C.text3, background: 'rgba(255,255,255,0.03)',
                padding: '5px 14px', borderRadius: 100, border: '1px solid var(--border-subtle)',
              }}>
                {executionDetails.length} scripts
              </span>
            </div>

            {!executionDetails.length ? (
              <div style={{
                textAlign: 'center', padding: 48, color: C.text3, fontFamily: C.mono, fontSize: 12,
                border: '1px dashed var(--border-default)', borderRadius: 14,
              }}>
                暂无执行记录
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }} className="stagger-children">
                {executionDetails.map((detail: any) => {
                  const isFailed = detail.status === 'error' || detail.status === 'failed'
                  const isRetrying = retryingScriptIds.has(detail.script_id)
                  const sc = isFailed ? 'var(--accent-magenta)' : 'var(--accent-emerald)'
                  return (
                    <article key={detail.script_id} className="animate-float-up" style={{
                      padding: '16px 18px', borderRadius: 16,
                      border: `1px solid ${isFailed ? 'rgba(255,45,120,0.25)' : 'rgba(0,255,136,0.25)'}`,
                      background: isFailed ? 'rgba(255,45,120,0.04)' : 'rgba(0,255,136,0.04)',
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                            <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: sc, flexShrink: 0, boxShadow: `0 0 8px ${sc}` }} />
                            <span style={{ fontFamily: C.display, fontSize: 13, fontWeight: 700, color: C.text }}>
                              {detail.script_name ? String(detail.script_name).split('/').pop()?.split('\\').pop() : `script #${detail.script_id}`}
                            </span>
                            <span style={{
                              fontFamily: C.mono, fontSize: 9, fontWeight: 700, letterSpacing: '0.1em', color: sc,
                              background: `${sc}18`, padding: '3px 10px', borderRadius: 100,
                            }}>
                              {detail.status}
                            </span>
                          </div>
                          <div style={{ fontFamily: C.mono, fontSize: 10, color: C.text3, marginTop: 6 }}>
                            case #{detail.case_id} · {detail.execution_time ? `${Number(detail.execution_time).toFixed(2)}s` : '--'}
                          </div>
                          {detail.error && (
                            <div style={{
                              marginTop: 10, padding: '12px 16px', borderRadius: 12,
                              background: 'rgba(255,45,120,0.06)', fontFamily: C.mono, fontSize: 11, color: 'var(--accent-magenta)',
                              maxHeight: 80, overflowY: 'auto', lineHeight: 1.6,
                            }}>
                              {String(detail.error).substring(0, 300)}
                            </div>
                          )}
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
                          <span style={{ fontFamily: C.mono, fontSize: 10, color: C.text3 }}>
                            {detail.end_time ? new Date(detail.end_time).toLocaleTimeString('zh-CN') : '--'}
                          </span>
                          {isFailed && (
                            <button type="button" onClick={() => handleRetryScript(detail.script_id)} disabled={isRetrying} style={{
                              fontFamily: C.mono, fontSize: 10, fontWeight: 700, color: '#fff',
                              background: 'var(--accent-magenta)', padding: '6px 14px', borderRadius: 100, border: 'none',
                              cursor: 'pointer', opacity: isRetrying ? 0.5 : 1, transition: 'all 0.2s',
                            }}>
                              {isRetrying ? '重试中...' : '重试'}
                            </button>
                          )}
                        </div>
                      </div>
                    </article>
                  )
                })}
              </div>
            )}
          </section>

          <TestScripts requirementId={requirementId} />
        </div>

        {/* Right sidebar */}
        <aside style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Code Review binding */}
          <section className="gradient-border-card" style={{ padding: '24px' }}>
            <div style={{ fontFamily: C.mono, fontSize: 11, letterSpacing: '0.28em', color: C.text3, textTransform: 'uppercase', marginBottom: 8 }}>
              /review/binding
            </div>
            <h2 style={{ fontFamily: C.display, fontSize: 18, fontWeight: 800, color: C.text, margin: '0 0 8px' }}>
              绑定 Review
            </h2>
            <p style={{ fontFamily: C.body, fontSize: 12, color: C.text2, margin: 0, lineHeight: 1.5 }}>
              选择已完成的 Review 任务，生成报告时串联需求、用例、finding 和执行结果。
            </p>

            <select value={selectedReviewTaskId} onChange={e => setSelectedReviewTaskId(e.target.value ? Number(e.target.value) : '')}
              style={{
                width: '100%', marginTop: 16, padding: '12px 16px', background: 'rgba(255,255,255,0.03)',
                border: '1px solid var(--border-subtle)', borderRadius: 12, color: C.text, fontFamily: C.mono, fontSize: 12,
              }}>
              <option value="">-- none --</option>
              {reviewTasks.map(t => (
                <option key={t.id} value={t.id}>#{t.id} · {t.branch} · {t.repo_url}</option>
              ))}
            </select>

            {selectedReviewTask && (
              <div style={{
                marginTop: 14, padding: '16px', borderRadius: 14, border: '1px solid var(--border-subtle)',
                background: 'rgba(255,255,255,0.02)',
              }}>
                <div style={{ fontFamily: C.mono, fontSize: 12, fontWeight: 700, color: C.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {selectedReviewTask.repo_url}
                </div>
                <div style={{ fontFamily: C.mono, fontSize: 11, color: C.text3, marginTop: 6 }}>
                  branch: {selectedReviewTask.branch} · {selectedReviewTask.days}d · {selectedReviewTask.finding_count} findings
                </div>
                <div style={{ fontFamily: C.body, fontSize: 12, color: C.text2, marginTop: 6, lineHeight: 1.5 }}>
                  {selectedReviewTask.summary || selectedReviewTask.error_message || '--'}
                </div>
              </div>
            )}

            <Link to="/reviews" style={{
              display: 'inline-block', marginTop: 14, fontFamily: C.mono, fontSize: 11, fontWeight: 600,
              color: 'var(--accent-violet)', textDecoration: 'none', border: '1px solid rgba(139,92,246,0.3)',
              borderRadius: 100, padding: '6px 16px', background: 'rgba(139,92,246,0.06)',
            }}>
              + new_review
            </Link>
          </section>

          {/* Reports */}
          <section className="gradient-border-card" style={{ padding: '24px' }}>
            <div style={{ fontFamily: C.mono, fontSize: 11, letterSpacing: '0.28em', color: C.text3, textTransform: 'uppercase', marginBottom: 8 }}>
              /reports
            </div>
            <h2 style={{ fontFamily: C.display, fontSize: 18, fontWeight: 800, color: C.text, margin: '0 0 8px' }}>
              HTML 报告
            </h2>
            <p style={{ fontFamily: C.body, fontSize: 12, color: C.text2, margin: 0, lineHeight: 1.5 }}>
              聚合需求、Review、缺陷分析和 API/UI 执行结果。
            </p>

            <div style={{ display: 'flex', gap: 10, marginTop: 16, flexWrap: 'wrap' }}>
              <button type="button" onClick={handleGenerateReport} disabled={generatingReport} style={{
                fontFamily: C.mono, fontSize: 12, fontWeight: 700, color: '#050810',
                background: 'linear-gradient(135deg, var(--accent-emerald), var(--accent-cyan))',
                padding: '12px 20px', borderRadius: 100, border: 'none', cursor: 'pointer',
                opacity: generatingReport ? 0.5 : 1, transition: 'all 0.2s',
              }}>
                {generatingReport ? '生成中...' : '生成报告'}
              </button>
              {report && (
                <a href={reportsApi.previewUrl(report.id)} target="_blank" rel="noreferrer"
                  style={{
                    fontFamily: C.mono, fontSize: 12, fontWeight: 600, color: 'var(--accent-cyan)',
                    textDecoration: 'none', border: '1px solid rgba(0,212,255,0.3)',
                    borderRadius: 100, padding: '12px 20px', background: 'rgba(0,212,255,0.06)',
                  }}>
                  预览报告
                </a>
              )}
            </div>

            {report && (
              <div style={{
                marginTop: 14, padding: '16px', borderRadius: 14, border: '1px solid var(--border-subtle)',
                background: 'rgba(255,255,255,0.02)',
              }}>
                <div style={{ fontFamily: C.display, fontSize: 14, fontWeight: 700, color: C.text }}>
                  {report.title}
                </div>
                <div style={{ fontFamily: C.body, fontSize: 12, color: C.text2, marginTop: 6, lineHeight: 1.5 }}>
                  {report.summary || '报告已生成，可直接预览。'}
                </div>
              </div>
            )}
          </section>

          {/* AutoFix */}
          <section className="gradient-border-card" style={{ padding: '24px' }}>
            <div style={{ fontFamily: C.mono, fontSize: 11, letterSpacing: '0.28em', color: C.text3, textTransform: 'uppercase', marginBottom: 8 }}>
              /autofix
            </div>
            <h2 style={{ fontFamily: C.display, fontSize: 18, fontWeight: 800, color: C.text, margin: '0 0 8px' }}>
              修复建议
            </h2>
            <p style={{ fontFamily: C.body, fontSize: 12, color: C.text2, margin: 0, lineHeight: 1.5 }}>
              suggestion only 模式，不自动改代码，只生成修复方向和补丁草案。
            </p>

            <button type="button" onClick={handleGenerateFixes} disabled={generatingFixes} style={{
              marginTop: 14, fontFamily: C.mono, fontSize: 12, fontWeight: 700, color: '#050810',
              background: 'linear-gradient(135deg, var(--accent-violet), var(--accent-magenta))',
              padding: '12px 20px', borderRadius: 100, border: 'none', cursor: 'pointer',
              opacity: generatingFixes ? 0.5 : 1, transition: 'all 0.2s',
            }}>
              {generatingFixes ? '分析中...' : '生成修复建议'}
            </button>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 14 }}>
              {!fixSuggestions.length ? (
                <div style={{
                  textAlign: 'center', padding: 32, color: C.text3, fontFamily: C.mono, fontSize: 11,
                  border: '1px dashed var(--border-default)', borderRadius: 14,
                }}>
                  暂无修复建议
                </div>
              ) : (
                fixSuggestions.map(item => (
                  <article key={item.id} style={{
                    padding: '16px 18px', border: '1px solid var(--border-subtle)',
                    borderRadius: 14, background: 'rgba(255,255,255,0.02)',
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                      <span style={{ fontFamily: C.display, fontSize: 13, fontWeight: 700, color: C.text }}>
                        {item.title}
                      </span>
                      <TinyBadge text={`${Math.round(item.confidence * 100)}%`} color="var(--accent-emerald)" />
                    </div>
                    <div style={{ fontFamily: C.body, fontSize: 12, color: C.text2, marginTop: 8, lineHeight: 1.5 }}>
                      <span style={{ color: C.text3 }}>根因：</span>{item.root_cause}
                    </div>
                    <div style={{ fontFamily: C.body, fontSize: 12, color: C.text2, marginTop: 4, lineHeight: 1.5 }}>
                      <span style={{ color: C.text3 }}>建议：</span>{item.suggested_action}
                    </div>
                    {item.target_files.length > 0 && (
                      <div style={{ fontFamily: C.mono, fontSize: 10, color: C.text3, marginTop: 6 }}>
                        target: {item.target_files.join(', ')}
                      </div>
                    )}
                    <pre style={{
                      marginTop: 12, padding: '14px 16px', borderRadius: 12, background: 'rgba(0,0,0,0.3)',
                      fontFamily: C.mono, fontSize: 10, color: C.text2, overflowX: 'auto', lineHeight: 1.6,
                    }}>
                      {item.patch_preview}
                    </pre>
                  </article>
                ))
              )}
            </div>
          </section>
        </aside>
      </div>
    </div>
  )
}
