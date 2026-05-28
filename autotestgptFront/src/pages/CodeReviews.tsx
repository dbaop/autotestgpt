import { useEffect, useState } from 'react'
import { codeReviewsApi, CodeReviewTask } from '../api'

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

const STATUS_COLORS: Record<string, { color: string; bg: string; label: string }> = {
  pending: { color: 'var(--accent-amber)', bg: 'rgba(255,176,32,0.12)', label: 'PENDING' },
  running: { color: '#38bdf8', bg: 'rgba(56,189,248,0.12)', label: 'RUNNING' },
  completed: { color: 'var(--accent-emerald)', bg: 'rgba(0,255,136,0.12)', label: 'COMPLETED' },
  error: { color: 'var(--accent-magenta)', bg: 'rgba(255,45,120,0.12)', label: 'ERROR' },
}

export default function CodeReviews() {
  const [repoUrl, setRepoUrl] = useState('')
  const [branch, setBranch] = useState('main')
  const [days, setDays] = useState(7)
  const [tasks, setTasks] = useState<CodeReviewTask[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadTasks = async () => {
    try { setLoading(true); const r = await codeReviewsApi.list(); setTasks(r.data.items || []) }
    catch (e: any) { setError(e?.response?.data?.message || '加载失败') }
    finally { setLoading(false) }
  }

  useEffect(() => { loadTasks() }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault(); setSubmitting(true); setError('')
    try {
      await codeReviewsApi.create({ repo_url: repoUrl.trim(), branch: branch.trim(), days })
      await loadTasks(); setRepoUrl('')
    } catch (err: any) { setError(err?.response?.data?.message || '创建失败') }
    finally { setSubmitting(false) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }} className="animate-fade-in">
      {/* Header */}
      <section className="gradient-border-card" style={{ padding: '36px 32px' }}>
        <div style={{ fontFamily: C.mono, fontSize: 11, letterSpacing: '0.32em', color: 'var(--accent-violet)', textTransform: 'uppercase', marginBottom: 10 }}>
          &gt; code_review_hub
        </div>
        <h2 style={{ fontFamily: C.display, fontSize: 32, fontWeight: 800, color: C.text, margin: '0 0 8px', letterSpacing: '-0.01em' }}>
          代码 Review
        </h2>
        <p style={{ fontFamily: C.body, fontSize: 14, color: C.text2, margin: 0 }}>
          clone 仓库到 workspace/repos，按分支和时间窗口收集 commit diff，生成 review findings
        </p>
      </section>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.1fr', gap: 20 }}>
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

            <div>
              <label style={{ fontFamily: C.mono, fontSize: 10, fontWeight: 600, letterSpacing: '0.14em', color: C.text3, display: 'block', marginBottom: 8, textTransform: 'uppercase' }}>
                git_repo_url
              </label>
              <input value={repoUrl} onChange={e => setRepoUrl(e.target.value)} placeholder="https://github.com/org/repo.git"
                style={{
                  width: '100%', padding: '14px 18px', background: 'rgba(255,255,255,0.03)',
                  border: '1px solid var(--border-subtle)', borderRadius: 14, color: C.text, fontFamily: C.mono, fontSize: 13,
                }}
              />
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
                pipeline
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                {['git clone', 'git log', 'diff', 'findings'].map((step, i) => (
                  <div key={step} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{
                      padding: '6px 12px', borderRadius: 8, background: 'rgba(255,255,255,0.04)',
                      border: '1px solid var(--border-subtle)',
                    }}>
                      <span style={{ fontFamily: C.mono, fontSize: 10, fontWeight: 700, color: 'var(--accent-violet)' }}>
                        {step}
                      </span>
                    </div>
                    {i < 3 && <span style={{ fontFamily: C.mono, fontSize: 12, color: C.text3 }}>→</span>}
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

        {/* Task list */}
        <section className="gradient-border-card" style={{ padding: '32px 28px' }}>
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
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }} className="stagger-children">
              {tasks.map(t => {
                const statusStyle = STATUS_COLORS[t.status] || { color: C.text3, bg: 'rgba(255,255,255,0.05)', label: t.status }
                return (
                  <div key={t.id} className="animate-float-up card-hover" style={{
                    padding: '18px 20px', border: '1px solid var(--border-subtle)',
                    borderRadius: 16, background: 'rgba(255,255,255,0.02)', transition: 'all 0.25s',
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{
                          fontFamily: C.mono, fontSize: 12, fontWeight: 700, color: C.text,
                          maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                        }}>
                          {t.repo_url}
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
                )
              })}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}