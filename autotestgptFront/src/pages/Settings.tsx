import { useEffect, useState } from 'react'
import { agentConfigsApi, environmentApi, requirementsApi, Requirement } from '../api'

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

const AGENT_TYPES = [
  { type: 'req_agent', label: 'ReqAgent — 需求解析', desc: '将自然语言需求转为结构化测试需求' },
  { type: 'case_agent', label: 'CaseAgent — 用例设计', desc: '从结构化需求生成测试用例' },
  { type: 'code_agent', label: 'CodeAgent — 代码生成', desc: '从测试用例生成 pytest/Playwright 脚本' },
  { type: 'review_agent', label: 'ReviewAgent — 代码审查', desc: 'LLM 分析 git diff，发现安全/质量/性能问题' },
  { type: 'exec_agent', label: 'ExecAgent — 测试执行', desc: 'pytest 执行 + 结果收集（无 LLM 调用）' },
]

type TabKey = 'env' | 'prompts' | 'skills'

export default function Settings() {
  const [tab, setTab] = useState<TabKey>('env')
  const [requirements, setRequirements] = useState<Requirement[]>([])
  const [selectedReqId, setSelectedReqId] = useState<number | ''>('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')

  // Environment form
  const [testUrl, setTestUrl] = useState('')
  const [loginState, setLoginState] = useState('unknown')
  const [credentialRef, setCredentialRef] = useState('')

  // Agent prompt editors — keyed by agent_type
  const [promptEdits, setPromptEdits] = useState<Record<string, string>>({})
  const [skillEdits, setSkillEdits] = useState<Record<string, { enabled: boolean; modelName: string; temp: number }>>({})

  useEffect(() => {
    const load = async () => {
      try {
        const [cfgRes, reqRes] = await Promise.all([
          agentConfigsApi.list(),
          requirementsApi.list(),
        ])
        setRequirements(reqRes.data.items || [])
        // Init editors from existing configs
        const prompts: Record<string, string> = {}
        const skills: Record<string, { enabled: boolean; modelName: string; temp: number }> = {}
        AGENT_TYPES.forEach(a => {
          const found = (cfgRes.data.items || []).find(c => c.agent_type === a.type)
          prompts[a.type] = found?.system_prompt || ''
          skills[a.type] = {
            enabled: found?.is_enabled ?? true,
            modelName: found?.model_name || '',
            temp: found?.temperature ?? 0.1,
          }
        })
        setPromptEdits(prompts)
        setSkillEdits(skills)
      } catch { /* ignore */ }
      finally { setLoading(false) }
    }
    load()
  }, [])

  const loadEnv = async (reqId: number) => {
    try {
      const res = await environmentApi.get(reqId)
      const env = res.data.environment
      setTestUrl(env.test_url || '')
      setLoginState(env.login_state || 'unknown')
      setCredentialRef(env.credential_ref || '')
    } catch { /* ignore */ }
  }

  useEffect(() => {
    if (selectedReqId && tab === 'env') loadEnv(selectedReqId as number)
  }, [selectedReqId, tab])

  const showMsg = (msg: string) => { setMessage(msg); setTimeout(() => setMessage(''), 3000) }

  const handleSaveEnv = async () => {
    if (!selectedReqId) { showMsg('请先选择需求'); return }
    setSaving(true)
    try {
      await environmentApi.save({
        requirement_id: selectedReqId as number,
        test_url: testUrl.trim() || undefined,
        login_state: loginState,
        credential_ref: credentialRef.trim() || undefined,
        allow_explore: true,
      })
      showMsg('环境配置已保存')
    } catch (e: any) { showMsg(e?.response?.data?.message || '保存失败') }
    finally { setSaving(false) }
  }

  const handleSavePrompt = async (agentType: string) => {
    setSaving(true)
    try {
      await agentConfigsApi.upsert({
        agent_type: agentType,
        system_prompt: promptEdits[agentType] || undefined,
      })
      showMsg(`${agentType} 提示词已保存`)
    } catch (e: any) { showMsg(e?.response?.data?.message || '保存失败') }
    finally { setSaving(false) }
  }

  const handleSaveSkill = async (agentType: string) => {
    setSaving(true)
    const s = skillEdits[agentType]
    try {
      await agentConfigsApi.upsert({
        agent_type: agentType,
        is_enabled: s?.enabled ?? true,
        model_name: s?.modelName || undefined,
        temperature: s?.temp ?? 0.1,
      })
      showMsg(`${agentType} 技能配置已保存`)
    } catch (e: any) { showMsg(e?.response?.data?.message || '保存失败') }
    finally { setSaving(false) }
  }

  const tabs: { key: TabKey; label: string }[] = [
    { key: 'env', label: '测试环境' },
    { key: 'prompts', label: 'Agent 提示词' },
    { key: 'skills', label: 'Agent 技能' },
  ]

  if (loading) {
    return <div className="page-stack"><p style={{ color: C.text3, fontFamily: C.mono }}>加载配置中...</p></div>
  }

  return (
    <div className="page-stack animate-fade-in" style={{ gap: 20 }}>
      <section className="gradient-border-card" style={{ padding: '36px 32px' }}>
        <div style={{ fontFamily: C.mono, fontSize: 11, letterSpacing: '0.32em', color: 'var(--accent-violet)', textTransform: 'uppercase', marginBottom: 10 }}>
          &gt; agent_settings
        </div>
        <h2 style={{ fontFamily: C.display, fontSize: 32, fontWeight: 800, color: C.text, margin: '0 0 8px' }}>
          Agent 配置中心
        </h2>
        <p style={{ fontFamily: C.body, fontSize: 14, color: C.text2, margin: 0 }}>
          管理测试环境、自定义 Agent 提示词、启用/禁用技能
        </p>
      </section>

      {message && (
        <div style={{
          padding: '12px 20px', borderRadius: 12, border: '1px solid var(--accent-emerald)',
          background: 'rgba(0,255,136,0.06)', fontFamily: C.mono, fontSize: 12, color: 'var(--accent-emerald)',
        }}>
          {message}
        </div>
      )}

      <div style={{ display: 'flex', gap: 12 }}>
        {tabs.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)} style={{
            fontFamily: C.mono, fontSize: 12, fontWeight: 700, letterSpacing: '0.08em',
            padding: '10px 24px', borderRadius: 100, border: `1px solid ${tab === t.key ? 'var(--accent-violet)' : 'var(--border-subtle)'}`,
            color: tab === t.key ? '#050810' : C.text2,
            background: tab === t.key ? 'var(--accent-violet)' : 'rgba(255,255,255,0.02)',
            cursor: 'pointer', transition: 'all 0.2s',
          }}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab: Environment */}
      {tab === 'env' && (
        <section className="gradient-border-card" style={{ padding: '28px' }}>
          <h3 style={{ fontFamily: C.display, fontSize: 20, fontWeight: 700, color: C.text, margin: '0 0 18px' }}>测试环境配置</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
            <div>
              <label style={{ fontFamily: C.mono, fontSize: 10, color: C.text3, display: 'block', marginBottom: 6 }}>关联需求</label>
              <select value={selectedReqId} onChange={e => { const v = e.target.value; setSelectedReqId(v ? Number(v) : '') }}
                style={{ width: '100%', padding: '12px 16px', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border-subtle)', borderRadius: 12, color: C.text, fontFamily: C.mono, fontSize: 13 }}>
                <option value="">-- 选择需求 --</option>
                {requirements.map(r => <option key={r.id} value={r.id}>#{r.id} - {r.title}</option>)}
              </select>
            </div>
            <div>
              <label style={{ fontFamily: C.mono, fontSize: 10, color: C.text3, display: 'block', marginBottom: 6 }}>测试地址 (test_url)</label>
              <input value={testUrl} onChange={e => setTestUrl(e.target.value)} placeholder="https://test.example.com"
                style={{ width: '100%', padding: '12px 16px', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border-subtle)', borderRadius: 12, color: C.text, fontFamily: C.mono, fontSize: 13 }} />
            </div>
            <div>
              <label style={{ fontFamily: C.mono, fontSize: 10, color: C.text3, display: 'block', marginBottom: 6 }}>登录态 (login_state)</label>
              <select value={loginState} onChange={e => setLoginState(e.target.value)}
                style={{ width: '100%', padding: '12px 16px', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border-subtle)', borderRadius: 12, color: C.text, fontFamily: C.mono, fontSize: 13 }}>
                <option value="unknown">unknown</option>
                <option value="pre_authenticated">pre_authenticated</option>
                <option value="manual">manual</option>
              </select>
            </div>
            <div>
              <label style={{ fontFamily: C.mono, fontSize: 10, color: C.text3, display: 'block', marginBottom: 6 }}>凭据引用 (credential_ref)</label>
              <input value={credentialRef} onChange={e => setCredentialRef(e.target.value)} placeholder="e.g. vault/login-creds"
                style={{ width: '100%', padding: '12px 16px', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border-subtle)', borderRadius: 12, color: C.text, fontFamily: C.mono, fontSize: 13 }} />
            </div>
          </div>
          <button onClick={handleSaveEnv} disabled={saving || !selectedReqId} style={{
            fontFamily: C.mono, fontSize: 12, fontWeight: 700, color: '#050810',
            background: 'linear-gradient(135deg, var(--accent-emerald), var(--accent-cyan))',
            padding: '12px 28px', borderRadius: 100, border: 'none', cursor: 'pointer', opacity: saving || !selectedReqId ? 0.5 : 1,
          }}>
            {saving ? '保存中...' : '保存环境配置'}
          </button>
        </section>
      )}

      {/* Tab: Agent Prompts */}
      {tab === 'prompts' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {AGENT_TYPES.map(a => (
            <section key={a.type} className="gradient-border-card" style={{ padding: '24px 28px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                <div>
                  <h3 style={{ fontFamily: C.display, fontSize: 16, fontWeight: 700, color: C.text, margin: '0 0 4px' }}>{a.label}</h3>
                  <p style={{ fontFamily: C.body, fontSize: 12, color: C.text3, margin: 0 }}>{a.desc}</p>
                </div>
                <button onClick={() => handleSavePrompt(a.type)} disabled={saving} style={{
                  fontFamily: C.mono, fontSize: 11, fontWeight: 700, color: '#050810',
                  background: 'var(--accent-cyan)', padding: '6px 18px', borderRadius: 100, border: 'none', cursor: 'pointer', opacity: saving ? 0.5 : 1,
                }}>
                  保存
                </button>
              </div>
              <textarea
                value={promptEdits[a.type] || ''}
                onChange={e => setPromptEdits(prev => ({ ...prev, [a.type]: e.target.value }))}
                rows={8}
                placeholder="留空则使用默认内置提示词..."
                style={{
                  width: '100%', padding: '14px 16px', background: 'rgba(255,255,255,0.02)',
                  border: '1px solid var(--border-subtle)', borderRadius: 12, color: C.text,
                  fontFamily: C.mono, fontSize: 12, resize: 'vertical', lineHeight: 1.6,
                }}
              />
            </section>
          ))}
        </div>
      )}

      {/* Tab: Agent Skills */}
      {tab === 'skills' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {AGENT_TYPES.map(a => {
            const s = skillEdits[a.type] || { enabled: true, modelName: '', temp: 0.1 }
            return (
              <section key={a.type} className="gradient-border-card" style={{ padding: '24px 28px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                  <div>
                    <h3 style={{ fontFamily: C.display, fontSize: 16, fontWeight: 700, color: C.text, margin: '0 0 4px' }}>{a.label}</h3>
                    <p style={{ fontFamily: C.body, fontSize: 12, color: C.text3, margin: 0 }}>{a.desc}</p>
                  </div>
                  <button onClick={() => handleSaveSkill(a.type)} disabled={saving} style={{
                    fontFamily: C.mono, fontSize: 11, fontWeight: 700, color: '#050810',
                    background: 'var(--accent-cyan)', padding: '6px 18px', borderRadius: 100, border: 'none', cursor: 'pointer', opacity: saving ? 0.5 : 1,
                  }}>
                    保存
                  </button>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 14 }}>
                  <div>
                    <label style={{ fontFamily: C.mono, fontSize: 10, color: C.text3, display: 'block', marginBottom: 6 }}>启用状态</label>
                    <select value={s.enabled ? 'true' : 'false'}
                      onChange={e => setSkillEdits(prev => ({ ...prev, [a.type]: { ...prev[a.type], enabled: e.target.value === 'true' } }))}
                      style={{ width: '100%', padding: '10px 14px', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border-subtle)', borderRadius: 10, color: C.text, fontFamily: C.mono, fontSize: 12 }}>
                      <option value="true">启用</option>
                      <option value="false">禁用</option>
                    </select>
                  </div>
                  <div>
                    <label style={{ fontFamily: C.mono, fontSize: 10, color: C.text3, display: 'block', marginBottom: 6 }}>模型覆盖</label>
                    <input value={s.modelName}
                      onChange={e => setSkillEdits(prev => ({ ...prev, [a.type]: { ...prev[a.type], modelName: e.target.value } }))}
                      placeholder="留空=自动选择"
                      style={{ width: '100%', padding: '10px 14px', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border-subtle)', borderRadius: 10, color: C.text, fontFamily: C.mono, fontSize: 12 }} />
                  </div>
                  <div>
                    <label style={{ fontFamily: C.mono, fontSize: 10, color: C.text3, display: 'block', marginBottom: 6 }}>温度 (temperature)</label>
                    <input type="number" min={0} max={2} step={0.1} value={s.temp}
                      onChange={e => setSkillEdits(prev => ({ ...prev, [a.type]: { ...prev[a.type], temp: Number(e.target.value) } }))}
                      style={{ width: '100%', padding: '10px 14px', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border-subtle)', borderRadius: 10, color: C.text, fontFamily: C.mono, fontSize: 12 }} />
                  </div>
                </div>
              </section>
            )
          })}
        </div>
      )}
    </div>
  )
}
