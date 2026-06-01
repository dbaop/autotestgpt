import { useEffect, useState } from 'react'
import { codeReviewsApi, CodeReviewTask, CodeReviewFinding } from '../api'

const C = {
  bg: 'var(--bg-card)',
  bgElevated: 'var(--bg-elevated)',
  bd: 'var(--border-subtle)',
  cyan: 'var(--accent-cyan)',
  violet: 'var(--accent-violet)',
  magenta: 'var(--accent-magenta)',
  emerald: 'var(--accent-emerald)',
  amber: 'var(--accent-amber)',
  text: 'var(--text-primary)',
  text2: 'var(--text-secondary)',
  text3: 'var(--text-muted)',
  mono: 'var(--font-mono)',
  display: 'var(--font-display)',
  body: 'var(--font-body)',
}

const STATUS_COLORS: Record<string, { color: string; bg: string; label: string }> = {
  pending: { color: 'var(--accent-amber)', bg: 'rgba(255,176,32,0.12)', label: 'PENDING' },
  running: { color: '#38bdf8', bg: 'rgba(56,189,248,0.12)', label: 'RUNNING' },
  completed: { color: 'var(--accent-emerald)', bg: 'rgba(0,255,136,0.12)', label: 'COMPLETED' },
  error: { color: 'var(--accent-magenta)', bg: 'rgba(255,45,120,0.12)', label: 'ERROR' },
}

const SEVERITY_COLORS: Record<string, { color: string; bg: string }> = {
  critical: { color: '#ff2d78', bg: 'rgba(255,45,120,0.15)' },
  high: { color: '#ff7b3d', bg: 'rgba(255,123,61,0.12)' },
  medium: { color: '#ffb020', bg: 'rgba(255,176,32,0.12)' },
  low: { color: '#38bdf8', bg: 'rgba(56,189,248,0.12)' },
  info: { color: 'var(--text3)', bg: 'rgba(255,255,255,0.05)' },
}

const CATEGORY_LABELS: Record<string, string> = {
  security: '安全',
  logic: '逻辑',
  data_integrity: '数据',
  quality: '质量',
  performance: '性能',
  best_practice: '实践',
}

const REVIEW_TYPE_LABELS: Record<string, { label: string; color: string }> = {
  security_logic: { label: '安全/逻辑', color: 'var(--accent-magenta)' },
  quality_perf: { label: '质量/性能', color: 'var(--accent-cyan)' },
}

export default function CodeReviews() {
  const [repoType, setRepoType] = useState<'remote' | 'local'>('remote')
  const [repoUrl, setRepoUrl] = useState('')
  const [repoPath, setRepoPath] = useState('')
  const [branch, setBranch] = useState('main')
  const [days, setDays] = useState(7)
  const [tasks, setTasks] = useState<CodeReviewTask[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [expandedTaskId, setExpandedTaskId] = useState<number | null>(null)
  const [expandedTask, setExpandedTask] = useState<CodeReviewTask | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)

  const loadTasks = async () => {
    try { setLoading(true); const r = await codeReviewsApi.list(); setTasks(r.data.items || []) }
    catch (e: any) { setError(e?.response?.data?.message || '加载失败') }
    finally { setLoading(false) }
  }

  useEffect(() => { loadTasks() }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault(); setSubmitting(true); setError('')
    try {
      const payload = repoType === 'local'
        ? { repo_path: repoPath.trim(), branch: branch.trim(), days }
        : { repo_url: repoUrl.trim(), branch: branch.trim(), days }
      await codeReviewsApi.create(payload)
      await loadTasks(); setRepoUrl(''); setRepoPath('')
    } catch (err: any) { setError(err?.response?.data?.message || '创建失败') }
    finally { setSubmitting(false) }
  }

  const handleToggleDetail = async (taskId: number) => {
    if (expandedTaskId === taskId) {
      setExpandedTaskId(null)
      setExpandedTask(null)
      return
    }
    setExpandedTaskId(taskId)
    setLoadingDetail(true)
    try {
      const r = await codeReviewsApi.get(taskId)
      setExpandedTask(r.data)
    } catch {
      setExpandedTask(null)
    } finally {
      setLoadingDetail(false)
    }
  }

  const pipelineSteps = repoType === 'remote'
    ? ['git clone', 'git log', 'diff', 'MiniMax(安全) + DeepSeek(质量)', 'findings']
    : ['git log', 'diff', 'MiniMax(安全) + DeepSeek(质量)', 'findings']

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }} className="animate-fade-in">
      {/* Header */}
      <section className="gradient-border-card" style={{ padding: '36px 32px' }}>
        <div style={{ fontFamily: C.mono, fontSize: 11, letterSpacing: '0.32em', color: 'var(--accent-violet)', textTransform: 'uppercase', marginBottom: 10 }}>
          &gt; code_review_hub
        </div>
        <h2 style={{ fontFamily: C.display, fontSize: 32, fontWeight: 800, color: C.text, margin: '0 0 8px', letterSpacing: 0 }}>
          代码 Review
        </h2>
        <p style={{ fontFamily: C.body, fontSize: 14, color: C.text2, margin: 0 }}>
          LLM 双 Agent 并行审查: MiniMax（安全/逻辑） + DeepSeek（质量/性能）
        </p>
      </section>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr', gap: 20 }}>
        {/* Create form */}
        <section className="gradient-border-card" style={{ padding: '32px 28px' }}>
          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {error && (
              <div style={{
                padding: '14px 18px', borderRadius: 14, border: '1px solid rgba(255,45,120,0.3)',
                background: 'rgba(255,45,120,0.06)', fontFamily: C.mono, fontSize: 12, color: 'var(--accent-magenta)',
              }}>
                [!] {error}
              </div>
            )}

            {/* Repo type switcher */}
            <div style={{ display: 'flex', gap: 0, borderRadius: 14, overflow: 'hidden', border: '1px solid var(--border-subtle)' }}>
              <button type="button" onClick={() => setRepoType('remote')} style={{
                flex: 1, padding: '10px 16px', border: 'none', cursor: 'pointer',
                fontFamily: C.mono, fontSize: 11, fontWeight: 700, letterSpacing: '0.08em',
                color: repoType === 'remote' ? '#050810' : C.text3,
                background: repoType === 'remote' ? 'var(--accent-violet)' : 'rgba(255,255,255,0.02)',
                transition: 'all 0.2s',
              }}>
                REMOTE URL
              </button>
              <button type="button" onClick={() => setRepoType('local')} style={{
                flex: 1, padding: '10px 16px', border: 'none', cursor: 'pointer',
                fontFamily: C.mono, fontSize: 11, fontWeight: 700, letterSpacing: '0.08em',
                color: repoType === 'local' ? '#050810' : C.text3,
                background: repoType === 'local' ? 'var(--accent-cyan)' : 'rgba(255,255,255,0.02)',
                transition: 'all 0.2s',
              }}>
                LOCAL PATH
              </button>
            </div>

            <div>
              <label style={{ fontFamily: C.mono, fontSize: 10, fontWeight: 600, letterSpacing: '0.14em', color: C.text3, display: 'block', marginBottom: 8, textTransform: 'uppercase' }}>
                {repoType === 'remote' ? 'git_repo_url' : 'local_repo_path'}
              </label>
              {repoType === 'remote' ? (
                <input value={repoUrl} onChange={e => setRepoUrl(e.target.value)} placeholder="https://github.com/org/repo.git"
                  style={{
                    width: '100%', padding: '14px 18px', background: 'rgba(255,255,255,0.03)',
                    border: '1px solid var(--border-subtle)', borderRadius: 14, color: C.text, fontFamily: C.mono, fontSize: 13,
                  }}
                />
              ) : (
                <input value={repoPath} onChange={e => setRepoPath(e.target.value)} placeholder="D:/projects/my-repo"
                  style={{
                    width: '100%', padding: '14px 18px', background: 'rgba(255,255,255,0.03)',
                    border: '1px solid var(--border-subtle)', borderRadius: 14, color: C.text, fontFamily: C.mono, fontSize: 13,
                  }}
                />
              )}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
              <div>
                <label style={{ fontFamily: C.mono, fontSize: 10, fontWeight: 600, letterSpacing: '0.14em', color: C.text3, display: 'block', marginBottom: 8, textTransform: 'uppercase' }}>
                  branch
                </label>
                <input value={branch} onChange={e => setBranch(e.target.value)}
                  style={{
                    width: '100%', padding: '14px 18px', background: 'rgba(255,255,255,0.03)',
                    border: '1px solid var(--border-subtle)', borderRadius: 14, color: C.text, fontFamily: C.mono, fontSize: 13,
                  }}
                />
              </div>
              <div>
                <label style={{ fontFamily: C.mono, fontSize: 10, fontWeight: 600, letterSpacing: '0.14em', color: C.text3, display: 'block', marginBottom: 8, textTransform: 'uppercase' }}>
                  days
                </label>
                <input type="number" min={1} value={days} onChange={e => setDays(Number(e.target.value))}
                  style={{
                    width: '100%', padding: '14px 18px', background: 'rgba(255,255,255,0.03)',
                    border: '1px solid var(--border-subtle)', borderRadius: 14, color: C.text, fontFamily: C.mono, fontSize: 13,
                  }}
                />
              </div>
            </div>

            {/* Pipeline visualization */}
            <div style={{
              padding: '18px 20px', borderRadius: 16, border: '1px solid var(--border-subtle)',
              background: 'linear-gradient(135deg, rgba(139,92,246,0.06) 0%, rgba(0,212,255,0.04) 100%)',
            }}>
              <div style={{ fontFamily: C.mono, fontSize: 10, letterSpacing: '0.2em', color: C.text3, textTransform: 'uppercase', marginBottom: 12 }}>
                pipeline (双 Agent 并行)
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                {pipelineSteps.map((step, i, arr) => (
                  <div key={step} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{
                      padding: '6px 12px', borderRadius: 8, background: 'rgba(255,255,255,0.04)',
                      border: '1px solid var(--border-subtle)',
                    }}>
                      <span style={{ fontFamily: C.mono, fontSize: 10, fontWeight: 700, color: 'var(--accent-violet)' }}>
                        {step}
                      </span>
                    </div>
                    {i < arr.length - 1 && <span style={{ fontFamily: C.mono, fontSize: 12, color: C.text3 }}>→</span>}
                  </div>
                ))}
              </div>
            </div>

            <button type="submit" disabled={submitting} style={{
              fontFamily: C.mono, fontSize: 13, fontWeight: 700, color: '#050810',
              background: 'linear-gradient(135deg, var(--accent-cyan), var(--accent-violet))',
              padding: '14px 24px', borderRadius: 100, border: 'none', cursor: 'pointer',
              transition: 'all 0.25s ease', opacity: submitting ? 0.5 : 1,
            }}
              onMouseEnter={e => !submitting && (e.currentTarget.style.transform = 'translateY(-2px)')}
              onMouseLeave={e => (e.currentTarget.style.transform = 'translateY(0)')}>
              {submitting ? '执行中...' : '启动审查'}
            </button>
          </form>
        </section>

        {/* Task list + expanded detail */}
        <section className="gradient-border-card" style={{ padding: '32px 28px', maxHeight: expandedTaskId ? 'calc(100vh - 160px)' : 'auto', overflow: 'auto' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
            <div>
              <div style={{ fontFamily: C.mono, fontSize: 11, letterSpacing: '0.28em', color: C.text3, textTransform: 'uppercase', marginBottom: 6 }}>
                /review/tasks
              </div>
              <h3 style={{ fontFamily: C.display, fontSize: 22, fontWeight: 800, color: C.text, margin: 0 }}>
                最近任务
              </h3>
            </div>
            <button onClick={loadTasks} style={{
              fontFamily: C.mono, fontSize: 11, color: C.text3, background: 'none',
              border: '1px solid var(--border-default)', borderRadius: 100, padding: '6px 16px', cursor: 'pointer',
            }}>
              刷新
            </button>
          </div>

          {loading ? (
            <div style={{ textAlign: 'center', padding: 48, color: C.text3, fontFamily: C.mono }}>
              <div style={{ display: 'inline-block', animation: 'spin-slow 1s linear infinite', fontSize: 24 }}>⬡</div>
              <div style={{ marginTop: 16 }}>加载中...</div>
            </div>
          ) : !tasks.length ? (
            <div style={{
              textAlign: 'center', padding: 48, color: C.text3, fontFamily: C.mono, fontSize: 13,
              border: '1px dashed var(--border-default)', borderRadius: 16,
            }}>
              暂无审查任务
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {tasks.map(t => {
                const statusStyle = STATUS_COLORS[t.status] || { color: C.text3, bg: 'rgba(255,255,255,0.05)', label: t.status }
                const isExpanded = expandedTaskId === t.id
                return (
                  <div key={t.id}>
                    <div className="animate-float-up card-hover" onClick={() => handleToggleDetail(t.id)} style={{
                      padding: '18px 20px', border: '1px solid var(--border-subtle)',
                      borderRadius: 16, background: isExpanded ? 'rgba(139,92,246,0.08)' : 'rgba(255,255,255,0.02)',
                      transition: 'all 0.25s', cursor: 'pointer',
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{
                            fontFamily: C.mono, fontSize: 12, fontWeight: 700, color: C.text,
                            maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                          }}>
                            {t.repo_type === 'local' ? (t.repo_path || '') : (t.repo_url || '')}
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
                            <span style={{ fontFamily: C.mono, fontSize: 10, color: C.text3 }}>{t.branch}</span>
                            <span style={{ fontFamily: C.mono, fontSize: 10, color: C.text3 }}>·</span>
                            <span style={{ fontFamily: C.mono, fontSize: 10, color: C.text3 }}>{t.days}d</span>
                            <span style={{ fontFamily: C.mono, fontSize: 10, color: C.text3 }}>·</span>
                            <span style={{ fontFamily: C.mono, fontSize: 10, color: 'var(--accent-violet)' }}>{t.finding_count} findings</span>
                          </div>
                        </div>
                        <span style={{
                          fontFamily: C.mono, fontSize: 9, fontWeight: 700, letterSpacing: '0.12em',
                          color: statusStyle.color, background: statusStyle.bg,
                          padding: '4px 10px', borderRadius: 100, flexShrink: 0,
                        }}>
                          {statusStyle.label}
                        </span>
                      </div>
                      {t.summary && (
                        <div style={{
                          fontFamily: C.body, fontSize: 12, color: C.text2, marginTop: 10,
                          lineHeight: 1.5, padding: '12px 14px', borderRadius: 10,
                          background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)',
                        }}>
                          {t.summary.substring(0, 160)}
                        </div>
                      )}
                    </div>

                    {/* Expanded findings detail */}
                    {isExpanded && (
                      <div style={{
                        marginTop: 8, padding: '20px 20px 16px',
                        border: '1px solid var(--border-subtle)', borderRadius: 16,
                        background: 'rgba(0,0,0,0.15)',
                      }}>
                        {loadingDetail ? (
                          <div style={{ textAlign: 'center', padding: 24, color: C.text3, fontFamily: C.mono, fontSize: 12 }}>
                            加载详情中...
                          </div>
                        ) : expandedTask?.findings && expandedTask.findings.length > 0 ? (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                            <div style={{ fontFamily: C.mono, fontSize: 10, letterSpacing: '0.14em', color: C.text3, textTransform: 'uppercase', marginBottom: 4 }}>
                              findings ({expandedTask.findings.length})
                            </div>
                            {expandedTask.findings.map((f: CodeReviewFinding) => {
                              const sev = SEVERITY_COLORS[f.severity] || SEVERITY_COLORS.info
                              const rt = REVIEW_TYPE_LABELS[f.review_type || ''] || null
                              const catLabel = CATEGORY_LABELS[f.category || ''] || f.category
                              return (
                                <div key={f.id} style={{
                                  padding: '14px 16px', borderRadius: 12, border: '1px solid var(--border-subtle)',
                                  background: 'rgba(255,255,255,0.02)',
                                  borderLeft: `3px solid ${sev.color}`,
                                }}>
                                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 6 }}>
                                    <span style={{
                                      fontFamily: C.mono, fontSize: 9, fontWeight: 700, letterSpacing: '0.1em',
                                      color: sev.color, background: sev.bg, padding: '2px 8px', borderRadius: 100,
                                    }}>
                                      {f.severity.toUpperCase()}
                                    </span>
                                    {catLabel && (
                                      <span style={{
                                        fontFamily: C.mono, fontSize: 9, color: 'var(--accent-amber)',
                                        background: 'rgba(255,176,32,0.1)', padding: '2px 8px', borderRadius: 100,
                                      }}>
                                        {catLabel}
                                      </span>
                                    )}
                                    {rt && (
                                      <span style={{
                                        fontFamily: C.mono, fontSize: 9, color: rt.color,
                                        background: 'rgba(0,212,255,0.08)', padding: '2px 8px', borderRadius: 100,
                                      }}>
                                        {rt.label}
                                      </span>
                                    )}
                                    {f.commit_sha && (
                                      <span style={{ fontFamily: C.mono, fontSize: 9, color: C.text3 }}>
                                        {f.commit_sha.substring(0, 7)}
                                      </span>
                                    )}
                                  </div>
                                  <div style={{ fontFamily: C.body, fontSize: 13, fontWeight: 600, color: C.text, marginBottom: 4 }}>
                                    {f.title}
                                  </div>
                                  {f.detail && (
                                    <div style={{ fontFamily: C.body, fontSize: 12, color: C.text2, lineHeight: 1.5, marginBottom: 4 }}>
                                      {f.detail.substring(0, 300)}
                                    </div>
                                  )}
                                  {f.suggestion && (
                                    <div style={{
                                      fontFamily: C.body, fontSize: 11, color: 'var(--accent-emerald)',
                                      padding: '8px 12px', borderRadius: 8, marginTop: 6,
                                      background: 'rgba(0,255,136,0.06)', border: '1px solid rgba(0,255,136,0.15)',
                                    }}>
                                      <span style={{ fontWeight: 700 }}>Fix: </span>
                                      {f.suggestion.substring(0, 300)}
                                    </div>
                                  )}
                                </div>
                              )
                            })}
                          </div>
                        ) : (
                          <div style={{ textAlign: 'center', padding: 24, color: C.text3, fontFamily: C.mono, fontSize: 12 }}>
                            暂无 findings
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
