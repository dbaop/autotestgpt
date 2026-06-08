import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { agentWorkbenchApi, AgentWorkbenchItem, EnvironmentConfig, environmentApi, flowApi } from '../api'

type EnvKey = 'test_url' | 'login_state' | 'credential_ref'
type LoginState = 'unknown' | 'no_login_required' | 'pre_authenticated' | 'requires_login'

const STATUS_LABEL: Record<string, string> = {
  queued: '排队',
  running: '进行中',
  done: '完成',
  failed: '失败',
}

const AGENT_TOOL_HINT: Record<string, string> = {
  browser_agent: 'agent-browser 探活与登录态复用',
  req_agent: '需求解析与自动补齐',
  case_agent: '测试场景与边界覆盖',
  code_agent: 'Playwright / pytest 脚本沉淀',
  exec_agent: '执行回归并收集 trace',
  bug_agent: '失败聚类与缺陷候选',
  code_review_agent: '代码变更质量审查',
}

function missingEnvironment(env: AgentWorkbenchItem['environment']) {
  const missing: { key: EnvKey; label: string }[] = []
  if (!env.test_url) missing.push({ key: 'test_url', label: '测试地址' })
  if (!env.login_state || env.login_state === 'unknown') missing.push({ key: 'login_state', label: '登录态' })
  if (env.login_state === 'pre_authenticated' && !env.credential_ref) {
    missing.push({ key: 'credential_ref', label: '凭据标识' })
  }
  return missing
}

function statusClass(status: string) {
  if (status === 'running') return 'active'
  if (status === 'done' || status === 'completed' || status === 'executed') return 'success'
  if (status === 'failed' || status === 'error') return 'error'
  return 'pending'
}

function EnvValue({ label, value, missing, onClick }: { label: string; value: string; missing?: boolean; onClick?: () => void }) {
  return (
    <button type="button" className={`env-chip ${missing ? 'is-missing' : ''}`} onClick={onClick}>
      <span>{label}</span>
      <strong>{value}</strong>
    </button>
  )
}

function MetricTile({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="workbench-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function AgentCard({ agent }: { agent: AgentWorkbenchItem['agents'][0] }) {
  return (
    <article className={`agent-card agent-card-${agent.status}`}>
      <div className="agent-card-head">
        <span className="agent-card-name">{agent.name}</span>
        <span className={`status-badge ${statusClass(agent.status)}`}>{STATUS_LABEL[agent.status] || agent.status}</span>
      </div>
      <p>{agent.current_action}</p>
      <small>{AGENT_TOOL_HINT[agent.id] || '平台自动调度'}</small>
    </article>
  )
}

function EnvSetupBanner({ item, onOpenWizard }: { item: AgentWorkbenchItem; onOpenWizard: (focus?: EnvKey) => void }) {
  const missing = missingEnvironment(item.environment)
  if (!missing.length) return null

  return (
    <section className="workbench-alert">
      <div>
        <span className="kicker">action required</span>
        <h3>补齐环境后继续执行</h3>
        <p>还差 {missing.map(row => row.label).join(' / ')}。补齐后平台会保存配置并继续推进测试流程。</p>
      </div>
      <button type="button" className="btn btn-primary" onClick={() => onOpenWizard(missing[0]?.key)}>
        立即补齐
      </button>
    </section>
  )
}

function EnvCellEditor({ requirementId, env, review, onSavedEnv, onClose, focusKey }: {
  requirementId: number
  env: EnvironmentConfig
  review: AgentWorkbenchItem['review']
  onSavedEnv: (env: EnvironmentConfig) => void
  onClose: () => void
  focusKey?: EnvKey
}) {
  const [testUrl, setTestUrl] = useState(env.test_url || '')
  const [loginState, setLoginState] = useState<LoginState>((env.login_state as LoginState) || 'unknown')
  const [credentialRef, setCredentialRef] = useState(env.credential_ref || '')
  const [allowExplore, setAllowExplore] = useState<boolean>(env.allow_explore !== false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const handleSave = async () => {
    if (!testUrl.trim()) { setError('请填写测试地址'); return }
    if (!loginState || loginState === 'unknown') { setError('请选择登录态'); return }
    if (loginState === 'pre_authenticated' && !credentialRef.trim()) {
      setError('选择已登录态时必须提供凭据标识'); return
    }

    setSaving(true)
    setError('')
    try {
      const res = await environmentApi.save({
        requirement_id: requirementId,
        test_url: testUrl.trim(),
        login_state: loginState,
        credential_ref: credentialRef.trim() || undefined,
        allow_explore: allowExplore,
      })
      onSavedEnv(res.data.environment)
      await flowApi.resume(requirementId)
      onClose()
    } catch (err: any) {
      setError(err.response?.data?.message || err.response?.data?.error || '保存或继续执行失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="env-editor" onClick={e => e.stopPropagation()}>
        <div className="env-editor-head">
          <div>
            <span className="kicker">environment</span>
            <h3>补齐测试环境</h3>
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="关闭补齐窗口">X</button>
        </div>

        <p className="section-desc">用于 BrowserAgent 探活、登录态复用、执行失败定位。保存后会自动继续测试流程。</p>

        {error && <div className="form-error">[!] {error}</div>}

        <div className="env-editor-grid">
          <label>
            <span>测试地址 *</span>
            <input
              autoFocus={focusKey === 'test_url' || !focusKey}
              value={testUrl}
              onChange={e => setTestUrl(e.target.value)}
              placeholder="https://staging.example.com"
            />
          </label>

          <label>
            <span>登录态 *</span>
            <select value={loginState} onChange={e => setLoginState(e.target.value as LoginState)}>
              <option value="unknown">未确认</option>
              <option value="no_login_required">无需登录</option>
              <option value="pre_authenticated">已预登录，需要凭据标识</option>
              <option value="requires_login">需要现场登录</option>
            </select>
          </label>

          <label>
            <span>凭据标识</span>
            <input
              value={credentialRef}
              onChange={e => setCredentialRef(e.target.value)}
              placeholder="vault://login/member-center"
            />
          </label>

          <label className="checkbox-row">
            <input type="checkbox" checked={allowExplore} onChange={e => setAllowExplore(e.target.checked)} />
            <span>允许 agent-browser 自动探活</span>
          </label>
        </div>

        {(review.repo_url || review.repo_path) && (
          <div className="review-note">
            <span className="kicker">review source</span>
            <p>{review.repo_url || review.repo_path} · {review.branch || '未指定分支'} · {review.days || 7}d</p>
          </div>
        )}

        <div className="env-editor-actions">
          <button type="button" className="btn btn-secondary" onClick={onClose}>取消</button>
          <button type="button" className="btn btn-primary" onClick={handleSave} disabled={saving}>
            {saving ? '保存并继续中...' : '保存并继续测试'}
          </button>
        </div>
      </div>
    </div>
  )
}

function WorkbenchDetail({ item, onOpenWizard }: {
  item: AgentWorkbenchItem
  onOpenWizard: (focus?: EnvKey) => void
}) {
  const env = item.environment
  const review = item.review
  const artifacts = item.artifacts
  const missing = missingEnvironment(env)
  const missingKeys = new Set(missing.map(row => row.key))

  return (
    <div className="page-stack">
      <EnvSetupBanner item={item} onOpenWizard={onOpenWizard} />

      <section className="workbench-hero">
        <div className="workbench-hero-copy">
          <span className="kicker">agent command center</span>
          <h2>{item.requirement.title}</h2>
          <p>{item.requirement.description}</p>
          <div className="workbench-hero-actions">
            <span className={`status-badge ${statusClass(item.overall_progress.status)}`}>{item.overall_progress.status}</span>
            <button type="button" className="btn btn-secondary" onClick={() => onOpenWizard(missing[0]?.key)}>
              补齐环境后继续执行
            </button>
          </div>
        </div>
        <div className="workbench-metrics">
          <MetricTile label="用例" value={artifacts.cases} />
          <MetricTile label="UI 脚本" value={artifacts.ui_scripts} />
          <MetricTile label="缺陷候选" value={artifacts.defects} />
          <MetricTile label="报告" value={artifacts.reports} />
        </div>
      </section>

      <section className="panel panel-inner">
        <div className="panel-heading-row">
          <div>
            <h3 className="section-title">执行前置条件</h3>
            <p className="section-desc">仓库和分支来自需求工作台或代码 Review；此处只补齐执行环境。</p>
          </div>
        </div>
        <div className="env-grid">
          <EnvValue label="测试地址" value={env.test_url || '未配置'} missing={missingKeys.has('test_url')} onClick={() => onOpenWizard('test_url')} />
          <EnvValue label="登录态" value={env.login_state || 'unknown'} missing={missingKeys.has('login_state')} onClick={() => onOpenWizard('login_state')} />
          <EnvValue label="凭据" value={env.credential_ref ? '已绑定（脱敏）' : '按登录态决定'} missing={missingKeys.has('credential_ref')} onClick={() => onOpenWizard('credential_ref')} />
          <EnvValue label="代码仓库" value={review.repo_url || review.repo_path || '未纳入 Review'} />
          <EnvValue label="分支" value={review.branch || '未指定'} />
        </div>
      </section>

      <div className="workbench-grid">
        <section className="panel panel-inner agent-rail">
          <div className="panel-heading-row">
            <div>
              <h3 className="section-title">Agent 编排</h3>
              <p className="section-desc">每个 Agent 只展示当前动作，避免事件噪声压住判断。</p>
            </div>
          </div>
          <div className="agent-card-list">
            {item.agents.map(agent => <AgentCard key={agent.id} agent={agent} />)}
          </div>
        </section>

        <section className="panel panel-inner timeline-panel">
          <div className="panel-heading-row">
            <div>
              <h3 className="section-title">事件流</h3>
              <p className="section-desc">保留最近的执行线索，排错时优先看这里。</p>
            </div>
          </div>
          <ol className="event-timeline">
            {item.events.map(event => (
              <li key={event.id}>
                <span>{event.agent}</span>
                <p>{event.message}</p>
                <time>{event.created_at ? new Date(event.created_at).toLocaleString('zh-CN') : '--'}</time>
              </li>
            ))}
            {!item.events.length && <li className="empty-event">暂无事件</li>}
          </ol>
        </section>
      </div>

      {item.execution_screenshots && item.execution_screenshots.length > 0 && (
        <section className="panel panel-inner">
          <div className="panel-heading-row">
            <div>
              <h3 className="section-title">执行截图</h3>
              <p className="section-desc">最近执行记录的页面截图 — 知道"通过/失败的是什么"。</p>
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 8, marginTop: 12 }}>
            {item.execution_screenshots.map((ss, i) => (
              <a key={i} href={ss.url} target="_blank" rel="noopener noreferrer"
                style={{
                  display: 'block', borderRadius: 10, overflow: 'hidden',
                  border: `1px solid ${ss.status === 'success' ? 'rgba(0,255,136,0.3)' : 'rgba(255,45,120,0.3)'}`,
                }}>
                <img src={ss.url} alt={`execution screenshot ${i + 1}`}
                  style={{ width: '100%', display: 'block', objectFit: 'cover', aspectRatio: '16/10' }} />
                <div style={{
                  padding: '4px 8px', fontSize: 10, fontFamily: 'var(--font-mono)',
                  color: ss.status === 'success' ? 'var(--accent-emerald)' : 'var(--accent-magenta)',
                  background: 'rgba(0,0,0,0.4)',
                }}>
                  {ss.status} · #{ss.execution_id}
                </div>
              </a>
            ))}
          </div>
        </section>
      )}

      <section className="panel panel-inner">
        <div className="panel-heading-row">
          <div>
            <h3 className="section-title">人工介入</h3>
            <p className="section-desc">验证码、登录过期、权限不足等阻塞项会出现在这里。</p>
          </div>
        </div>
        {item.interventions.length ? (
          <ul className="intervention-list">
            {item.interventions.map((row, idx) => <li key={idx}>{row.message || row.type}</li>)}
          </ul>
        ) : (
          <div className="empty-state">当前无需人工处理</div>
        )}
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
  const [wizardOpen, setWizardOpen] = useState(false)
  const [wizardFocus, setWizardFocus] = useState<EnvKey | undefined>(undefined)

  const load = useCallback(async () => {
    try {
      if (rid) {
        const res = await agentWorkbenchApi.get(rid)
        setItems([res.data])
      } else {
        const res = await agentWorkbenchApi.list()
        setItems(res.data.items || [])
      }
      setError('')
    } catch (err: any) {
      if (err?.response?.status === 404) {
        setError(`需求 #${rid} 不存在，可能已被删除或数据库已重置。请返回需求工作台重新创建。`)
      } else {
        setError('加载 Agent 工作台失败')
      }
    } finally {
      setLoading(false)
    }
  }, [rid])

  useEffect(() => {
    load()
    const timer = window.setInterval(load, 5000)
    return () => window.clearInterval(timer)
  }, [load])

  // Stop polling on terminal error (404 = requirement gone)
  useEffect(() => {
    if (error && error.includes('不存在')) {
      // 404 is permanent — no need to keep polling
      return
    }
  }, [error])

  const selected = useMemo(() => {
    if (!rid) return items[0]
    return items.find(item => item.requirement.id === rid) || items[0]
  }, [items, rid])

  if (loading) {
    return (
      <div className="loading-state">
        <div>
          <div className="loading-spinner" />
          加载 Agent 工作台...
        </div>
      </div>
    )
  }

  if (error) return <div className="empty-state">{error}</div>

  return (
    <div className="page-stack animate-fade-in">
      <header className="page-header workbench-page-header">
        <div>
          <span className="kicker">autotestgpt</span>
          <h1 className="page-title">Agent 工作台</h1>
          <p className="page-subtitle">对需求解析、环境补齐、脚本沉淀、执行诊断做一处可观测。</p>
        </div>
        {!rid && items.length > 1 && (
          <div className="workbench-switcher">
            {items.map(item => (
              <Link key={item.requirement.id} className="btn btn-secondary" to={`/workbench/${item.requirement.id}`}>
                #{item.requirement.id}
              </Link>
            ))}
          </div>
        )}
      </header>

      {!selected ? (
        <div className="empty-state">暂无任务，请从 <Link to="/new">需求工作台</Link> 创建流程。</div>
      ) : (
        <>
          <WorkbenchDetail
            item={selected}
            onOpenWizard={(focus) => { setWizardFocus(focus); setWizardOpen(true) }}
          />
          {wizardOpen && (
            <EnvCellEditor
              requirementId={selected.requirement.id}
              env={selected.environment}
              review={selected.review}
              onSavedEnv={(env) => {
                setItems(prev => prev.map(item => item.requirement.id === selected.requirement.id
                  ? { ...item, environment: { ...item.environment, ...env } }
                  : item))
                window.dispatchEvent(new CustomEvent('autotestgpt:env-updated', { detail: { requirementId: selected.requirement.id } }))
                load()
              }}
              onClose={() => setWizardOpen(false)}
              focusKey={wizardFocus}
            />
          )}
        </>
      )}
    </div>
  )
}
