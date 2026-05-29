import { useEffect, useMemo, useState } from 'react'
import { executionsApi, ExecutionRecord } from '../api'

const S = {
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

const FILTERS = ['all', 'success', 'failed', 'error', 'running'] as const

const STATUS_COLORS: Record<string, { color: string; bg: string; label: string }> = {
  success: { color: 'var(--accent-emerald)', bg: 'rgba(0,255,136,0.12)', label: 'SUCCESS' },
  failed: { color: 'var(--accent-amber)', bg: 'rgba(255,176,32,0.12)', label: 'FAILED' },
  error: { color: 'var(--accent-magenta)', bg: 'rgba(255,45,120,0.12)', label: 'ERROR' },
  running: { color: '#38bdf8', bg: 'rgba(56,189,248,0.12)', label: 'RUNNING' },
}

function StatBox({ label, value, color, icon, delay }: { label: string; value: string | number; color: string; icon: string; delay: number }) {
  return (
    <div className="animate-float-up card-hover" style={{
      background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: 18,
      padding: '22px 20px', position: 'relative', overflow: 'hidden', animationDelay: `${delay}s`,
    }}>
      <div style={{
        position: 'absolute', top: 0, right: 0, width: 60, height: 60,
        background: `radial-gradient(circle, ${color}12 0%, transparent 70%)`,
        transform: 'translate(15%, -15%)',
      }} />
      <div style={{ fontFamily: S.mono, fontSize: 10, fontWeight: 600, letterSpacing: '0.16em', color: S.text3, textTransform: 'uppercase', marginBottom: 10 }}>
        {label}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ fontFamily: S.display, fontSize: 32, fontWeight: 800, color: color }}>
          {value}
        </div>
        <div style={{
          width: 40, height: 40, borderRadius: 10, background: `${color}15`,
          border: `1px solid ${color}30`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16,
        }}>
          {icon}
        </div>
      </div>
    </div>
  )
}

function FilterButton({ label, active, onClick, color }: { label: string; active: boolean; onClick: () => void; color: string }) {
  return (
    <button onClick={onClick} style={{
      fontFamily: S.mono, fontSize: 10, fontWeight: 600, padding: '7px 16px', borderRadius: 100,
      border: `1px solid ${active ? color : 'var(--border-default)'}`,
      color: active ? color : 'var(--text-muted)',
      background: active ? `${color}12` : 'transparent',
      cursor: 'pointer', transition: 'all 0.2s ease', letterSpacing: '0.1em',
    }}>
      {label}
    </button>
  )
}

export default function Executions() {
  const [items, setItems] = useState<ExecutionRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<string>('all')

  useEffect(() => {
    executionsApi.list().then(r => setItems(r.data.items || [])).catch(console.error).finally(() => setLoading(false))
  }, [])

  const filtered = useMemo(() => filter === 'all' ? items : items.filter(i => i.status === filter), [items, filter])

  const stats = useMemo(() => ({
    total: items.length,
    success: items.filter(i => i.status === 'success').length,
    failed: items.filter(i => i.status === 'failed').length,
    error: items.filter(i => i.status === 'error').length,
  }), [items])

  if (loading) return (
    <div style={{ textAlign: 'center', padding: 80, color: S.text3, fontFamily: S.mono, fontSize: 13 }}>
      <div style={{ display: 'inline-block', animation: 'spin-slow 1s linear infinite', fontSize: 24 }}>○</div>
      <div style={{ marginTop: 16 }}>加载执行记录中...</div>
    </div>
  )

  return (
    <div className="page-stack animate-fade-in">
      {/* Header */}
      <section className="gradient-border-card panel-inner">
        <div style={{ fontFamily: S.mono, fontSize: 11, letterSpacing: '0.32em', color: 'var(--accent-amber)', textTransform: 'uppercase', marginBottom: 10 }}>
          &gt; execution_ledger
        </div>
        <h2 style={{ fontFamily: S.display, fontSize: 32, fontWeight: 800, color: S.text, margin: '0 0 8px', letterSpacing: 0 }}>
          执行记录
        </h2>
        <p style={{ fontFamily: S.body, fontSize: 14, color: S.text2, margin: '0 0 28px' }}>
          API / UI 执行器的结果记录
        </p>

        {/* Stats */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 14, marginBottom: 28 }} className="stagger-children">
          <StatBox label="total" value={stats.total} color={S.text2} icon="◎" delay={0} />
          <StatBox label="success" value={stats.success} color="var(--accent-emerald)" icon="✓" delay={1} />
          <StatBox label="failed" value={stats.failed} color="var(--accent-amber)" icon="✗" delay={2} />
          <StatBox label="error" value={stats.error} color="var(--accent-magenta)" icon="!" delay={3} />
        </div>

        {/* Filters */}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {FILTERS.map(f => (
            <FilterButton key={f} label={f === 'all' ? 'ALL' : f.toUpperCase()} active={filter === f} onClick={() => setFilter(f)}
              color={STATUS_COLORS[f]?.color || S.text2} />
          ))}
        </div>
      </section>

      {/* Table */}
      {!filtered.length ? (
        <div className="gradient-border-card panel-inner" style={{
          textAlign: 'center', padding: 64, fontFamily: S.mono, fontSize: 13, color: S.text3,
        }}>
          暂无执行记录
        </div>
      ) : (
        <div className="gradient-border-card data-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                {['ID', 'STATUS', 'TIME', 'STARTED', 'ERROR'].map(l => (
                  <th key={l}>{l}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((ex, i) => {
                const statusStyle = STATUS_COLORS[ex.status] || { color: S.text3, bg: 'rgba(255,255,255,0.05)', label: ex.status?.toUpperCase() }
                return (
                  <tr key={ex.id} className="animate-float-up" style={{
                    animationDelay: `${i * 0.02}s`, transition: 'background 0.2s',
                  }}
                    onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.02)')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                    <td>
                      <span style={{ fontFamily: S.mono, fontSize: 14, fontWeight: 700, color: S.text }}>
                        #{ex.id}
                      </span>
                    </td>
                    <td>
                      <span className={`status-badge ${ex.status}`} style={{ color: statusStyle.color, background: statusStyle.bg }}>
                        {statusStyle.label}
                      </span>
                    </td>
                    <td>
                      <span style={{ fontFamily: S.mono, fontSize: 12, color: S.text2 }}>
                        {ex.execution_time ? `${ex.execution_time.toFixed(2)}s` : '--'}
                      </span>
                    </td>
                    <td>
                      <span style={{ fontFamily: S.mono, fontSize: 11, color: S.text3 }}>
                        {ex.started_at ? new Date(ex.started_at).toLocaleString('zh-CN') : '--'}
                      </span>
                    </td>
                    <td>
                      <span style={{
                        fontFamily: S.mono, fontSize: 11, color: 'var(--accent-magenta)',
                        maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block',
                      }}>
                        {ex.error_message || '--'}
                      </span>
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
