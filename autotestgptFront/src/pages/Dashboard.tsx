import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { casesApi, executionsApi, healthApi, HealthStatus, requirementsApi } from '../api'

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

function StatCard({ label, value, color, icon, delay }: { label: string; value: string | number; color: string; icon: string; delay: number }) {
  return (
    <div className="animate-float-up card-hover" style={{
      background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: 20,
      padding: '22px 18px', position: 'relative', overflow: 'hidden', animationDelay: `${delay}s`,
    }}>
      {/* Decorative glow */}
      <div style={{
        position: 'absolute', top: 0, right: 0, width: 80, height: 80,
        background: `radial-gradient(circle, ${color}12 0%, transparent 70%)`,
        transform: 'translate(20%, -20%)',
      }} />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
        <div style={{ fontFamily: C.mono, fontSize: 9, fontWeight: 600, letterSpacing: '0.18em', color: C.text3, textTransform: 'uppercase' }}>
          {label}
        </div>
        <div style={{
          width: 34, height: 34, borderRadius: 9, background: `${color}15`,
          border: `1px solid ${color}30`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 15,
        }}>
          {icon}
        </div>
      </div>
      <div style={{ fontFamily: C.display, fontSize: 34, fontWeight: 800, color: color, lineHeight: 1 }}>
        {value}
      </div>
    </div>
  )
}

function StatusChip({ status }: { status: string }) {
  const map: Record<string, { color: string; bg: string }> = {
    pending: { color: 'var(--accent-amber)', bg: 'rgba(255,176,32,0.12)' },
    parsed: { color: '#38bdf8', bg: 'rgba(56,189,248,0.12)' },
    cases_generated: { color: '#22d3ee', bg: 'rgba(34,211,238,0.12)' },
    code_generated: { color: 'var(--accent-violet)', bg: 'rgba(139,92,246,0.12)' },
    executing: { color: '#a78bfa', bg: 'rgba(167,139,250,0.12)' },
    executed: { color: 'var(--accent-emerald)', bg: 'rgba(0,255,136,0.12)' },
    completed: { color: 'var(--accent-emerald)', bg: 'rgba(0,255,136,0.12)' },
    error: { color: 'var(--accent-magenta)', bg: 'rgba(255,45,120,0.12)' },
  }
  const s = map[status] || { color: C.text3, bg: 'rgba(255,255,255,0.05)' }
  return (
    <span style={{
      fontFamily: C.mono, fontSize: 9, fontWeight: 700, letterSpacing: '0.1em',
      color: s.color, background: s.bg, padding: '3px 9px', borderRadius: 100, whiteSpace: 'nowrap',
    }}>
      {status}
    </span>
  )
}

function RequirementCard({ item, delay }: { item: any; delay: number }) {
  return (
    <Link to={`/requirements/${item.id}`} className="animate-float-up card-hover" style={{
      display: 'block', padding: '16px 18px', textDecoration: 'none',
      background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)',
      borderRadius: 14, transition: 'all 0.25s ease', animationDelay: `${delay}s`,
    }}
      onMouseEnter={e => {
        e.currentTarget.style.borderColor = 'rgba(0,212,255,0.35)'
        e.currentTarget.style.transform = 'translateY(-2px)'
        e.currentTarget.style.boxShadow = '0 6px 24px rgba(0,0,0,0.25)'
      }}
      onMouseLeave={e => {
        e.currentTarget.style.borderColor = 'var(--border-subtle)'
        e.currentTarget.style.transform = 'translateY(0)'
        e.currentTarget.style.boxShadow = 'none'
      }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontFamily: C.display, fontSize: 13, fontWeight: 600, color: C.text, marginBottom: 8, lineHeight: 1.3 }}>
            {item.title}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <StatusChip status={item.status} />
            <span style={{ fontFamily: C.mono, fontSize: 10, color: C.text3 }}>
              {item.test_case_count || 0} cases
            </span>
          </div>
        </div>
        <div style={{
          width: 36, height: 36, borderRadius: 9, background: 'rgba(0,212,255,0.08)',
          border: '1px solid rgba(0,212,255,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: 'var(--accent-cyan)', fontSize: 16, flexShrink: 0,
        }}>
          →
        </div>
      </div>
      <div style={{ marginTop: 10, fontFamily: C.mono, fontSize: 10, color: C.text3 }}>
        {new Date(item.created_at).toLocaleString('zh-CN')}
      </div>
    </Link>
  )
}

function SystemHealthPanel({ health }: { health: HealthStatus | null }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {[
        { label: 'SERVICE', val: health?.status === 'ok' ? 'operational' : 'degraded', col: 'var(--accent-emerald)' },
        { label: 'DATABASE', val: health?.database || '--', col: 'var(--accent-cyan)' },
        { label: 'VERSION', val: health?.version || '--', col: 'var(--accent-violet)' },
      ].map(({ label, val, col }) => (
        <div key={label} style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '12px 14px', background: 'rgba(255,255,255,0.02)', borderRadius: 10,
          border: '1px solid var(--border-subtle)',
        }}>
          <span style={{ fontFamily: C.mono, fontSize: 10, fontWeight: 600, letterSpacing: '0.1em', color: C.text3 }}>{label}</span>
          <span style={{ fontFamily: C.mono, fontSize: 11, fontWeight: 600, color: col }}>{val}</span>
        </div>
      ))}
    </div>
  )
}

export default function Dashboard() {
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [reqs, setReqs] = useState<any[]>([])
  const [casesCount, setCasesCount] = useState(0)
  const [execs, setExecs] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([healthApi.check(), requirementsApi.list(), casesApi.list(), executionsApi.list()])
      .then(([h, r, c, e]) => {
        setHealth(h.data); setReqs(r.data.items || []); setCasesCount(c.data.total || 0); setExecs(e.data.items || [])
      }).catch(console.error).finally(() => setLoading(false))
  }, [])

  const passRate = useMemo(() => {
    if (!execs.length) return 0
    return Math.round((execs.filter((x: any) => x.status === 'success').length / execs.length) * 100)
  }, [execs])

  if (loading) return (
    <div style={{ textAlign: 'center', padding: 80, color: C.text3, fontFamily: C.mono, fontSize: 13 }}>
      <div style={{ display: 'inline-block', animation: 'spin-slow 1s linear infinite', fontSize: 24 }}>◈</div>
      <div style={{ marginTop: 16 }}>initializing...</div>
    </div>
  )

  return (
    <div className="page-stack">
      {/* Hero Section */}
      <section className="gradient-border-card animate-fade-in" style={{
        padding: '40px 36px', position: 'relative', overflow: 'hidden',
      }}>
        {/* Background decoration */}
        <div style={{
          position: 'absolute', top: -50, right: -50, width: 280, height: 280,
          background: 'radial-gradient(circle, rgba(0,212,255,0.07) 0%, transparent 70%)',
          pointerEvents: 'none',
        }} />
        <div style={{
          position: 'absolute', bottom: -30, left: 80, width: 180, height: 180,
          background: 'radial-gradient(circle, rgba(139,92,246,0.05) 0%, transparent 70%)',
          pointerEvents: 'none',
        }} />

        <div style={{ position: 'relative', zIndex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
            <span style={{ fontFamily: C.mono, fontSize: 10, fontWeight: 600, letterSpacing: '0.28em', color: 'var(--accent-cyan)', textTransform: 'uppercase' }}>
              &gt; mission_control
            </span>
            <span style={{ fontFamily: C.mono, fontSize: 9, color: C.text3 }}>v2.0</span>
          </div>

          <h1 style={{ fontFamily: C.display, fontSize: 38, fontWeight: 900, color: C.text, lineHeight: 1.2, margin: '0 0 14px', letterSpacing: '-0.02em' }}>
            <span className="gradient-text-cyan">需求</span>
            <span style={{ color: C.text2, fontWeight: 400, margin: '0 8px' }}>→</span>
            <span style={{ color: 'var(--accent-violet)' }}>知识</span>
            <span style={{ color: C.text2, fontWeight: 400, margin: '0 8px' }}>→</span>
            <span style={{ color: 'var(--accent-emerald)' }}>用例</span>
            <span style={{ color: C.text2, fontWeight: 400, margin: '0 8px' }}>→</span>
            <span style={{ color: 'var(--accent-amber)' }}>脚本</span>
            <span style={{ color: C.text2, fontWeight: 400, margin: '0 8px' }}>→</span>
            <span className="gradient-text-violet">执行</span>
          </h1>

          <p style={{ fontFamily: C.body, fontSize: 14, color: C.text2, maxWidth: 560, lineHeight: 1.7, margin: 0 }}>
            多智能体协作平台，将原始需求转化为结构化用例、可执行脚本与可视化报告。
            支持知识库增强、代码 Review 联动与智能修复建议。
          </p>

          <div style={{ display: 'flex', gap: 12, marginTop: 28, flexWrap: 'wrap' }}>
            <Link to="/new" className="btn btn-primary">
              <span>▶</span> 启动工作流
            </Link>
            <Link to="/reviews" className="btn btn-secondary">
              ⚡ 代码 Review
            </Link>
          </div>
        </div>
      </section>

      {/* Stats Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 14 }} className="stagger-children">
        <StatCard label="requirements" value={reqs.length} color="var(--accent-cyan)" icon="◈" delay={0} />
        <StatCard label="test_cases" value={casesCount} color="var(--accent-emerald)" icon="◆" delay={1} />
        <StatCard label="executions" value={execs.length} color="var(--accent-amber)" icon="○" delay={2} />
        <StatCard label="pass_rate" value={`${passRate}%`} color="var(--accent-violet)" icon="✓" delay={3} />
      </div>

      {/* Bottom Section - Two Equal Columns */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
        {/* System Health */}
        <section className="gradient-border-card animate-float-up" style={{ padding: '24px 20px', animationDelay: '0.15s' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 18 }}>
            <div style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent-emerald)', boxShadow: '0 0 12px var(--accent-emerald)' }} />
            <span style={{ fontFamily: C.mono, fontSize: 10, fontWeight: 600, letterSpacing: '0.22em', color: C.text3, textTransform: 'uppercase' }}>
              system_health
            </span>
          </div>
          <SystemHealthPanel health={health} />
        </section>

        {/* Recent Requirements */}
        <section className="gradient-border-card animate-float-up" style={{ padding: '24px 20px', animationDelay: '0.2s' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <span style={{ fontFamily: C.mono, fontSize: 10, fontWeight: 600, letterSpacing: '0.22em', color: C.text3, textTransform: 'uppercase' }}>
              recent_requirements
            </span>
            <Link to="/requirements" style={{
              fontFamily: C.mono, fontSize: 10, color: 'var(--accent-cyan)', textDecoration: 'none',
              display: 'flex', alignItems: 'center', gap: 4, fontWeight: 600,
            }}>
              查看全部 <span>→</span>
            </Link>
          </div>

          {!reqs.slice(0, 4).length ? (
            <div style={{
              textAlign: 'center', padding: 40, color: C.text3, fontFamily: C.mono, fontSize: 12,
              border: '1px dashed var(--border-subtle)', borderRadius: 14,
            }}>
              暂无数据
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }} className="stagger-children">
              {reqs.slice(0, 4).map((item, i) => (
                <RequirementCard key={item.id} item={item} delay={i * 0.04} />
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}