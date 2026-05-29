import { CSSProperties, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { casesApi, executionsApi, healthApi, HealthStatus, requirementsApi } from '../api'

const STATUS_COLORS: Record<string, { color: string; bg: string; label: string }> = {
  pending: { color: 'var(--accent-amber)', bg: 'rgba(255,207,90,0.12)', label: '待处理' },
  parsed: { color: 'var(--accent-cyan)', bg: 'rgba(86,166,255,0.12)', label: '已解析' },
  cases_generated: { color: 'var(--accent-cyan)', bg: 'rgba(86,166,255,0.12)', label: '已生成用例' },
  code_generated: { color: 'var(--accent-violet)', bg: 'rgba(167,139,250,0.12)', label: '已生成脚本' },
  executing: { color: 'var(--accent-violet)', bg: 'rgba(167,139,250,0.12)', label: '执行中' },
  executed: { color: 'var(--accent-emerald)', bg: 'rgba(94,228,167,0.12)', label: '已执行' },
  completed: { color: 'var(--accent-emerald)', bg: 'rgba(94,228,167,0.12)', label: '已完成' },
  error: { color: 'var(--accent-magenta)', bg: 'rgba(255,107,154,0.12)', label: '异常' },
}

function StatCard({ label, value, color, icon, delay }: {
  label: string
  value: string | number
  color: string
  icon: string
  delay: number
}) {
  const style = {
    '--metric-color': color,
    animationDelay: `${delay}s`,
  } as CSSProperties

  return (
    <div className="metric-card card-hover animate-float-up" style={style}>
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      <div className="metric-icon" aria-hidden="true">{icon}</div>
    </div>
  )
}

function StatusChip({ status }: { status: string }) {
  const s = STATUS_COLORS[status] || { color: 'var(--text-muted)', bg: 'rgba(148,163,184,0.12)', label: status || '未知' }

  return (
    <span className="status-badge" style={{ color: s.color, background: s.bg }}>
      {s.label}
    </span>
  )
}

function RequirementCard({ item, delay }: { item: any; delay: number }) {
  return (
    <Link
      to={`/requirements/${item.id}`}
      className="requirement-card card-hover animate-float-up"
      style={{ animationDelay: `${delay}s` }}
    >
      <div className="requirement-card-title">{item.title}</div>
      <div className="requirement-card-meta">
        <StatusChip status={item.status} />
        <span>{item.test_case_count || 0} 个用例</span>
        <span>{new Date(item.created_at).toLocaleString('zh-CN')}</span>
      </div>
    </Link>
  )
}

function SystemHealthPanel({ health }: { health: HealthStatus | null }) {
  const rows = [
    { label: 'SERVICE', val: health?.status === 'ok' ? 'operational' : 'degraded', col: 'var(--accent-emerald)' },
    { label: 'DATABASE', val: health?.database || '--', col: 'var(--accent-cyan)' },
    { label: 'VERSION', val: health?.version || '--', col: 'var(--accent-violet)' },
  ]

  return (
    <div className="health-list">
      {rows.map(({ label, val, col }) => (
        <div key={label} className="health-row" style={{ '--row-color': col } as CSSProperties}>
          <span className="health-label">{label}</span>
          <span className="health-value">{val}</span>
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
        setHealth(h.data)
        setReqs(r.data.items || [])
        setCasesCount(c.data.total || 0)
        setExecs(e.data.items || [])
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const passRate = useMemo(() => {
    if (!execs.length) return 0
    return Math.round((execs.filter((x: any) => x.status === 'success').length / execs.length) * 100)
  }, [execs])

  if (loading) {
    return (
      <div className="loading-state">
        <div>
          <div className="loading-spinner" />
          <div>正在加载工作台...</div>
        </div>
      </div>
    )
  }

  return (
    <div className="page-stack">
      <section className="dashboard-hero animate-fade-in">
        <div className="hero-copy">
          <div className="kicker">mission control</div>
          <h1>从需求到报告，一屏掌控自动化测试链路</h1>
          <p>
            汇总需求解析、知识库增强、用例生成、脚本执行和代码 Review。
            首页保留高密度信息，但把重点动作、健康状态和最新需求摆在最容易扫描的位置。
          </p>
          <div className="hero-actions">
            <Link to="/new" className="btn btn-primary">启动工作流</Link>
            <Link to="/requirements" className="btn btn-secondary">查看需求</Link>
            <Link to="/reviews" className="btn btn-secondary">代码 Review</Link>
          </div>
        </div>

        <div className="pipeline-card" aria-label="自动化测试链路">
          {[
            ['01', '需求输入', '文本、文档或知识库材料'],
            ['02', '智能生成', '用例、脚本和执行计划'],
            ['03', '执行反馈', '报告、缺陷和修复建议'],
          ].map(([index, title, desc]) => (
            <div className="pipeline-step" key={index}>
              <span className="pipeline-index">{index}</span>
              <span>
                <strong>{title}</strong>
                <span>{desc}</span>
              </span>
            </div>
          ))}
        </div>
      </section>

      <div className="metric-grid">
        <StatCard label="requirements" value={reqs.length} color="var(--accent-cyan)" icon="RQ" delay={0} />
        <StatCard label="test cases" value={casesCount} color="var(--accent-emerald)" icon="TC" delay={0.04} />
        <StatCard label="executions" value={execs.length} color="var(--accent-amber)" icon="EX" delay={0.08} />
        <StatCard label="pass rate" value={`${passRate}%`} color="var(--accent-violet)" icon="OK" delay={0.12} />
      </div>

      <div className="dashboard-grid">
        <section className="panel panel-inner animate-float-up" style={{ animationDelay: '0.12s' }}>
          <div className="panel-heading-row">
            <div>
              <div className="kicker">system health</div>
              <h2 className="section-title" style={{ fontSize: 22, marginTop: 8 }}>运行状态</h2>
            </div>
            <span className="status-dot online" aria-hidden="true" />
          </div>
          <SystemHealthPanel health={health} />
        </section>

        <section className="panel panel-inner animate-float-up" style={{ animationDelay: '0.16s' }}>
          <div className="panel-heading-row">
            <div>
              <div className="kicker">recent requirements</div>
              <h2 className="section-title" style={{ fontSize: 22, marginTop: 8 }}>最近需求</h2>
            </div>
            <Link to="/requirements" className="btn btn-secondary">全部</Link>
          </div>

          {!reqs.slice(0, 4).length ? (
            <div className="empty-state">暂无需求，启动一个工作流后这里会出现最新进度。</div>
          ) : (
            <div className="requirement-list">
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
