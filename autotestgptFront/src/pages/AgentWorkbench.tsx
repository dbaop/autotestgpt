import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { agentWorkbenchApi, AgentWorkbenchItem } from '../api'

const STATUS_LABEL: Record<string, string> = {
  queued: '排队',
  running: '进行中',
  done: '完成',
  failed: '失败',
}

const AGENT_TOOL_HINT: Record<string, string> = {
  browser_agent: 'agent-browser 探索',
  code_agent: 'Playwright 脚本沉淀',
  exec_agent: 'Playwright + pytest 执行',
}

function AgentCard({ agent }: { agent: AgentWorkbenchItem['agents'][0] }) {
  const status = agent.status
  const hint = AGENT_TOOL_HINT[agent.id]
  return (
    <div className="panel" style={{ padding: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginBottom: 8 }}>
        <strong>{agent.name}</strong>
        <span className={`status-badge status-${status === 'running' ? 'active' : status === 'done' ? 'success' : status === 'failed' ? 'error' : 'pending'}`}>
          {STATUS_LABEL[status] || status}
        </span>
      </div>
      <p style={{ margin: 0, fontSize: 13, color: 'var(--text-secondary)' }}>{agent.current_action}</p>
      {hint && (
        <p style={{ margin: '8px 0 0', fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
          {hint}
        </p>
      )}
      {agent.id === 'browser_agent' && agent.current_action.includes('agent-browser') && (
        <p style={{ margin: '6px 0 0', fontSize: 11, color: 'var(--accent-cyan)' }}>
          BrowserAgent · 页面探活与登录态复用
        </p>
      )}
    </div>
  )
}

function WorkbenchDetail({ item }: { item: AgentWorkbenchItem }) {
  const env = item.environment
  const artifacts = item.artifacts

  return (
    <div className="page-stack">
      <section className="panel">
        <div className="panel-inner">
          <h2 className="page-title">任务总览</h2>
          <p className="page-subtitle">{item.requirement.title}</p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, marginTop: 16 }}>
            <div><span className="label-muted">状态</span><div>{item.overall_progress.status}</div></div>
            <div><span className="label-muted">测试地址</span><div>{env.test_url || '未配置'}</div></div>
            <div><span className="label-muted">登录态</span><div>{env.login_state || 'unknown'}</div></div>
            <div><span className="label-muted">凭据</span><div>{env.credential_ref ? '已绑定（脱敏）' : '未绑定'}</div></div>
            <div><span className="label-muted">仓库</span><div>{item.review.repo_url || '—'}</div></div>
            <div><span className="label-muted">分支</span><div>{item.review.branch || '—'}</div></div>
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="panel-inner">
          <h3 className="section-title">Agent 看板</h3>
          <p className="page-subtitle" style={{ marginBottom: 12 }}>
            探索阶段用 agent-browser，回归执行用 Playwright；工具由平台自动编排。
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 12 }}>
            {item.agents.map(agent => (
              <AgentCard key={agent.id} agent={agent} />
            ))}
          </div>
        </div>
      </section>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <section className="panel">
          <div className="panel-inner">
            <h3 className="section-title">实时事件流</h3>
            <ul style={{ listStyle: 'none', padding: 0, margin: 0, maxHeight: 320, overflow: 'auto' }}>
              {item.events.map(event => (
                <li key={event.id} style={{ padding: '10px 0', borderBottom: '1px solid var(--border-subtle)', fontSize: 13 }}>
                  <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent-cyan)', marginRight: 8 }}>{event.agent}</span>
                  {event.message}
                </li>
              ))}
              {item.events.length === 0 && <li style={{ color: 'var(--text-muted)' }}>暂无事件</li>}
            </ul>
          </div>
        </section>

        <section className="panel">
          <div className="panel-inner">
            <h3 className="section-title">产物区</h3>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 14, lineHeight: 1.8 }}>
              <li>用例 {artifacts.cases}</li>
              <li>UI 脚本（Playwright）{artifacts.ui_scripts}</li>
              <li>API 脚本 {artifacts.api_scripts}</li>
              <li>Review 发现 {artifacts.review_findings}</li>
              <li>缺陷候选 {artifacts.defects}</li>
              <li>报告 {artifacts.reports}</li>
            </ul>
          </div>
        </section>
      </div>

      <section className="panel">
        <div className="panel-inner">
          <h3 className="section-title">人工介入</h3>
          {item.interventions.length === 0 ? (
            <p style={{ color: 'var(--text-muted)', margin: 0 }}>当前无需人工处理</p>
          ) : (
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {item.interventions.map((row, idx) => (
                <li key={idx}>{row.message || row.type}</li>
              ))}
            </ul>
          )}
          <p style={{ marginTop: 12, fontSize: 12, color: 'var(--text-muted)' }}>
            验证码、登录过期、权限不足等问题会在此提示；对话页仅同步摘要与待确认项。
          </p>
        </div>
      </section>
    </div>
  )
}

export default function AgentWorkbench() {
  const { requirementId } = useParams()
  const rid = requirementId ? Number(requirementId) : null
  const [items, setItems] = useState<AgentWorkbenchItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      if (rid) {
        const res = await agentWorkbenchApi.get(rid)
        setItems([res.data])
      } else {
        const res = await agentWorkbenchApi.list()
        setItems(res.data.items)
      }
      setError('')
    } catch {
      setError('加载工作台失败')
    } finally {
      setLoading(false)
    }
  }, [rid])

  useEffect(() => {
    load()
    const timer = window.setInterval(load, 3000)
    return () => window.clearInterval(timer)
  }, [load])

  const selected = useMemo(() => {
    if (!rid) return items[0]
    return items.find(i => i.requirement.id === rid) || items[0]
  }, [items, rid])

  if (loading) {
    return <div className="page-stack"><p>加载 Agent 工作台…</p></div>
  }

  if (error) {
    return <div className="page-stack"><p>{error}</p></div>
  }

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <h1 className="page-title">Agent 工作台</h1>
          <p className="page-subtitle">多 Agent 协作可观测 · 探索（agent-browser）→ 沉淀（Playwright）→ 执行 → 诊断</p>
        </div>
        {!rid && items.length > 1 && (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {items.map(item => (
              <Link key={item.requirement.id} className="btn btn-ghost" to={`/workbench/${item.requirement.id}`}>
                {item.requirement.title}
              </Link>
            ))}
          </div>
        )}
      </header>

      {!selected ? (
        <p>暂无进行中的任务，请从<Link to="/new">需求工作台</Link>创建流程。</p>
      ) : (
        <WorkbenchDetail item={selected} />
      )}
    </div>
  )
}
