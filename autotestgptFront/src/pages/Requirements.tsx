import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Requirement, requirementsApi } from '../api'

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

const STATUSES = ['all', 'pending', 'parsed', 'cases_generated', 'code_generated', 'executing', 'executed', 'completed', 'error'] as const

const STATUS_COLORS: Record<string, { color: string; bg: string }> = {
  pending: { color: 'var(--accent-amber)', bg: 'rgba(255,176,32,0.12)' },
  parsed: { color: '#38bdf8', bg: 'rgba(56,189,248,0.12)' },
  cases_generated: { color: '#22d3ee', bg: 'rgba(34,211,238,0.12)' },
  code_generated: { color: 'var(--accent-violet)', bg: 'rgba(139,92,246,0.12)' },
  executing: { color: '#a78bfa', bg: 'rgba(167,139,250,0.12)' },
  executed: { color: 'var(--accent-emerald)', bg: 'rgba(0,255,136,0.12)' },
  completed: { color: 'var(--accent-emerald)', bg: 'rgba(0,255,136,0.12)' },
  error: { color: 'var(--accent-magenta)', bg: 'rgba(255,45,120,0.12)' },
}

function FilterChip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} style={{
      fontFamily: C.mono, fontSize: 10, fontWeight: 600, padding: '6px 14px', borderRadius: 100,
      border: `1px solid ${active ? 'var(--accent-cyan)' : 'var(--border-default)'}`,
      color: active ? 'var(--accent-cyan)' : 'var(--text-muted)',
      background: active ? 'rgba(0,212,255,0.08)' : 'transparent',
      cursor: 'pointer', transition: 'all 0.2s ease', letterSpacing: '0.08em',
    }}>
      {label}
    </button>
  )
}

export default function Requirements() {
  const [items, setItems] = useState<Requirement[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<string>('all')

  useEffect(() => {
    requirementsApi.list().then(r => setItems(r.data.items || [])).catch(console.error).finally(() => setLoading(false))
  }, [])

  const filtered = useMemo(() => filter === 'all' ? items : items.filter(i => i.status === filter), [items, filter])

  const handleDelete = async (id: number, e: React.MouseEvent) => {
    e.preventDefault(); e.stopPropagation()
    if (!window.confirm('确认删除？')) return
    try { await requirementsApi.delete(id); setItems(p => p.filter(i => i.id !== id)) } catch {}
  }

  if (loading) return (
    <div style={{ textAlign: 'center', padding: 80, color: C.text3, fontFamily: C.mono, fontSize: 13 }}>
      <div style={{ display: 'inline-block', animation: 'spin-slow 1s linear infinite', fontSize: 24 }}>◈</div>
      <div style={{ marginTop: 16 }}>loading requirements...</div>
    </div>
  )

  return (
    <div className="page-stack animate-fade-in">
      {/* Header */}
      <section className="gradient-border-card panel-inner">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 20 }}>
          <div>
            <div style={{ fontFamily: C.mono, fontSize: 11, letterSpacing: '0.32em', color: 'var(--accent-cyan)', textTransform: 'uppercase', marginBottom: 10 }}>
              &gt; requirement_board
            </div>
            <h2 style={{ fontFamily: C.display, fontSize: 32, fontWeight: 800, color: C.text, margin: '0 0 8px', letterSpacing: 0 }}>
              需求清单
            </h2>
            <p style={{ fontFamily: C.body, fontSize: 14, color: C.text2, margin: 0 }}>
              所有需求及其在 Agent 链路中的当前阶段
            </p>
          </div>
          <Link to="/new" className="btn btn-primary">
            <span>+</span> 新建需求
          </Link>
        </div>

        {/* Filter chips */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 28 }}>
          {STATUSES.map(s => (
            <FilterChip key={s} label={s === 'all' ? 'ALL' : s} active={filter === s} onClick={() => setFilter(s)} />
          ))}
        </div>
      </section>

      {/* Table */}
      {!filtered.length ? (
        <div className="gradient-border-card panel-inner" style={{
          textAlign: 'center', padding: 64, fontFamily: C.mono, fontSize: 13, color: C.text3,
        }}>
          暂无匹配需求
        </div>
      ) : (
        <div className="gradient-border-card data-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                {['需求', '状态', 'KB', '用例', '创建时间', ''].map(l => (
                  <th key={l}>{l}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((item, i) => {
                const statusStyle = STATUS_COLORS[item.status] || { color: C.text3, bg: 'rgba(255,255,255,0.05)' }
                return (
                  <tr key={item.id} className="animate-float-up" style={{
                    animationDelay: `${i * 0.03}s`, transition: 'background 0.2s',
                  }}
                    onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.02)')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                    <td>
                      <Link to={`/requirements/${item.id}`} style={{ textDecoration: 'none' }}>
                        <div style={{ fontFamily: C.display, fontSize: 14, fontWeight: 600, color: C.text, marginBottom: 4 }}>
                          {item.title}
                        </div>
                        <div style={{ fontFamily: C.mono, fontSize: 11, color: C.text3, maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {item.description}
                        </div>
                      </Link>
                    </td>
                    <td>
                      <span className={`status-badge ${item.status}`} style={{ color: statusStyle.color, background: statusStyle.bg }}>
                        {item.status}
                      </span>
                    </td>
                    <td>
                      <span style={{ fontFamily: C.mono, fontSize: 12, color: C.text3 }}>
                        {item.knowledge_base_id ? `KB#${item.knowledge_base_id}` : '--'}
                      </span>
                    </td>
                    <td>
                      <span style={{ fontFamily: C.display, fontSize: 14, fontWeight: 700, color: C.text }}>
                        {item.test_case_count || 0}
                      </span>
                    </td>
                    <td>
                      <span style={{ fontFamily: C.mono, fontSize: 11, color: C.text3 }}>
                        {new Date(item.created_at).toLocaleString('zh-CN')}
                      </span>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <button onClick={(e) => handleDelete(item.id, e)} style={{
                        fontFamily: C.mono, fontSize: 11, fontWeight: 600, color: 'var(--accent-magenta)',
                        background: 'rgba(255,45,120,0.08)', border: '1px solid rgba(255,45,120,0.15)',
                        padding: '6px 12px', borderRadius: 8, cursor: 'pointer', transition: 'all 0.2s',
                      }}
                        onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,45,120,0.15)')}
                        onMouseLeave={e => (e.currentTarget.style.background = 'rgba(255,45,120,0.08)')}>
                        del
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
