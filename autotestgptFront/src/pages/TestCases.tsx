import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { casesApi, TestCase } from '../api'

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

const TYPES = ['all', 'api', 'ui', 'performance', 'security'] as const

const TYPE_COLORS: Record<string, { color: string; bg: string }> = {
  api: { color: '#38bdf8', bg: 'rgba(56,189,248,0.12)' },
  ui: { color: 'var(--accent-violet)', bg: 'rgba(139,92,246,0.12)' },
  performance: { color: 'var(--accent-amber)', bg: 'rgba(255,176,32,0.12)' },
  security: { color: 'var(--accent-magenta)', bg: 'rgba(255,45,120,0.12)' },
}

const PRIORITY_COLORS: Record<string, { color: string; bg: string; label: string }> = {
  high: { color: 'var(--accent-magenta)', bg: 'rgba(255,45,120,0.12)', label: 'HIGH' },
  medium: { color: 'var(--accent-amber)', bg: 'rgba(255,176,32,0.12)', label: 'MED' },
  low: { color: 'var(--accent-emerald)', bg: 'rgba(0,255,136,0.12)', label: 'LOW' },
}

function FilterButton({ label, active, onClick, color }: { label: string; active: boolean; onClick: () => void; color: string }) {
  return (
    <button onClick={onClick} style={{
      fontFamily: C.mono, fontSize: 10, fontWeight: 600, padding: '7px 16px', borderRadius: 100,
      border: `1px solid ${active ? color : 'var(--border-default)'}`,
      color: active ? color : 'var(--text-muted)',
      background: active ? `${color}12` : 'transparent',
      cursor: 'pointer', transition: 'all 0.2s ease', letterSpacing: '0.1em',
    }}>
      {label}
    </button>
  )
}

export default function TestCases() {
  const [cases, setCases] = useState<TestCase[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<string>('all')

  useEffect(() => {
    casesApi.list().then(r => setCases(r.data.items || [])).catch(console.error).finally(() => setLoading(false))
  }, [])

  const filtered = useMemo(() => filter === 'all' ? cases : cases.filter(c => c.test_type === filter), [cases, filter])

  const grouped = useMemo(() => {
    const g: Record<number, TestCase[]> = {}
    filtered.forEach(c => { if (!g[c.requirement_id]) g[c.requirement_id] = []; g[c.requirement_id].push(c) })
    return g
  }, [filtered])

  if (loading) return (
    <div style={{ textAlign: 'center', padding: 80, color: C.text3, fontFamily: C.mono, fontSize: 13 }}>
      <div style={{ display: 'inline-block', animation: 'spin-slow 1s linear infinite', fontSize: 24 }}>◆</div>
      <div style={{ marginTop: 16 }}>加载测试用例中...</div>
    </div>
  )

  return (
    <div className="page-stack animate-fade-in">
      {/* Header */}
      <section className="gradient-border-card panel-inner">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 16, marginBottom: 24 }}>
          <div>
            <div style={{ fontFamily: C.mono, fontSize: 11, letterSpacing: '0.32em', color: 'var(--accent-emerald)', textTransform: 'uppercase', marginBottom: 10 }}>
              &gt; test_cases
            </div>
            <h2 style={{ fontFamily: C.display, fontSize: 32, fontWeight: 800, color: C.text, margin: '0 0 4px', letterSpacing: '-0.01em' }}>
              测试用例
            </h2>
            <p style={{ fontFamily: C.body, fontSize: 14, color: C.text2, margin: 0 }}>
              共 <span style={{ fontFamily: C.mono, fontWeight: 700, color: 'var(--accent-emerald)' }}>{cases.length}</span> 个测试用例
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            {TYPES.map(t => {
              const tc = TYPE_COLORS[t] || { color: C.text3, bg: 'transparent' }
              return (
                <FilterButton key={t} label={t === 'all' ? 'ALL' : t.toUpperCase()} active={filter === t} onClick={() => setFilter(t)} color={tc.color} />
              )
            })}
          </div>
        </div>
      </section>

      {/* Cases grouped by requirement */}
      {!Object.keys(grouped).length ? (
        <div className="gradient-border-card panel-inner" style={{
          textAlign: 'center', padding: 64, fontFamily: C.mono, fontSize: 13, color: C.text3,
        }}>
          暂无测试用例
        </div>
      ) : (
        Object.entries(grouped).sort(([a], [b]) => Number(b) - Number(a)).map(([reqId, reqCases]) => (
          <div key={reqId} className="gradient-border-card animate-float-up data-table-wrap">
            {/* Group header */}
            <div style={{
              padding: '16px 20px', background: 'linear-gradient(90deg, rgba(0,212,255,0.04) 0%, transparent 100%)',
              borderBottom: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{
                  width: 32, height: 32, borderRadius: 8, background: 'rgba(0,212,255,0.1)',
                  border: '1px solid rgba(0,212,255,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  <span style={{ fontFamily: C.mono, fontSize: 12, fontWeight: 800, color: 'var(--accent-cyan)' }}>◈</span>
                </div>
                <div>
                  <Link to={`/requirements/${reqId}`} style={{
                    fontFamily: C.mono, fontSize: 12, fontWeight: 700, color: 'var(--accent-cyan)', textDecoration: 'none',
                  }}>
                    req://{reqId}
                  </Link>
                  <span style={{ fontFamily: C.mono, fontSize: 11, color: C.text3, marginLeft: 8 }}>
                    {reqCases.length} cases
                  </span>
                </div>
              </div>
              <span style={{
                fontFamily: C.mono, fontSize: 9, fontWeight: 600, color: 'var(--accent-emerald)',
                background: 'rgba(0,255,136,0.1)', padding: '3px 10px', borderRadius: 100,
              }}>
                {reqCases.length} items
              </span>
            </div>

            {/* Cases table */}
            <table className="data-table" style={{ minWidth: 760 }}>
              <tbody>
                {reqCases.map((c, i) => {
                  const typeStyle = TYPE_COLORS[c.test_type] || { color: C.text3, bg: 'rgba(255,255,255,0.05)' }
                  const prioStyle = PRIORITY_COLORS[c.priority] || { color: C.text3, bg: 'rgba(255,255,255,0.05)', label: c.priority }

                  return (
                    <tr key={c.id} className="animate-float-up" style={{
                      animationDelay: `${i * 0.03}s`, transition: 'background 0.2s',
                      borderTop: i > 0 ? '1px solid var(--border-subtle)' : 'none',
                    }}
                      onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.02)')}
                      onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                      <td style={{ padding: '16px 20px' }}>
                        <div style={{ fontFamily: C.display, fontSize: 14, fontWeight: 600, color: C.text, marginBottom: 4 }}>
                          {c.title}
                        </div>
                        <div style={{ fontFamily: C.body, fontSize: 12, color: C.text3, lineHeight: 1.5 }}>
                          {c.description}
                        </div>
                      </td>
                      <td style={{ width: 90 }}>
                        <span className="status-badge" style={{ color: typeStyle.color, background: typeStyle.bg }}>
                          {c.test_type.toUpperCase()}
                        </span>
                      </td>
                      <td style={{ width: 90 }}>
                        <span className="status-badge" style={{ color: prioStyle.color, background: prioStyle.bg }}>
                          {prioStyle.label}
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ))
      )}
    </div>
  )
}