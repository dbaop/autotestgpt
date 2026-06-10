import { useState, useEffect, useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { casesApi, flowApi, requirementsApi, TestCase, Requirement } from '../api'

const C = {
  bg: 'var(--bg-card)',
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

const PRIO_COLORS: Record<string, { color: string; bg: string; label: string }> = {
  high: { color: 'var(--accent-magenta)', bg: 'rgba(255,45,120,0.12)', label: 'HIGH' },
  medium: { color: 'var(--accent-amber)', bg: 'rgba(255,176,32,0.12)', label: 'MED' },
  low: { color: 'var(--accent-emerald)', bg: 'rgba(0,255,136,0.12)', label: 'LOW' },
}

const METHOD_LABELS: Record<string, string> = {
  boundary_value: '边界值',
  equivalence_partitioning: '等价类',
  error_guessing: '错误推测',
  state_transition: '状态迁移',
  decision_table: '判定表',
  pairwise: '结对测试',
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

interface EditForm {
  title: string
  description: string
  test_type: string
  priority: string
  steps: { step: number; action: string; expected: string }[]
}

const NEW_CASE_TEMPLATE: EditForm = {
  title: '',
  description: '',
  test_type: 'ui',
  priority: 'medium',
  steps: [{ step: 1, action: '', expected: '' }],
}

export default function TestCases() {
  const [searchParams] = useSearchParams()
  const highlightReqId = searchParams.get('requirement_id')

  const [cases, setCases] = useState<TestCase[]>([])
  const [requirements, setRequirements] = useState<Record<number, Requirement>>({})
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<string>('all')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editForm, setEditForm] = useState<EditForm>(NEW_CASE_TEMPLATE)
  const [addingForReq, setAddingForReq] = useState<number | null>(null)
  const [confirmingReq, setConfirmingReq] = useState<number | null>(null)
  const [error, setError] = useState('')

  const loadData = async () => {
    try {
      const [caseRes, reqRes] = await Promise.all([
        casesApi.list(),
        requirementsApi.list(),
      ])
      setCases(caseRes.data.items || [])
      const reqMap: Record<number, Requirement> = {}
      ;(reqRes.data.items || []).forEach((r: Requirement) => { reqMap[r.id] = r })
      setRequirements(reqMap)
    } catch (err) { console.error(err) }
    finally { setLoading(false) }
  }

  useEffect(() => { loadData() }, [])

  // Scroll to highlighted requirement
  useEffect(() => {
    if (highlightReqId && !loading) {
      const el = document.getElementById(`req-group-${highlightReqId}`)
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [highlightReqId, loading])

  const filtered = useMemo(() =>
    filter === 'all' ? cases : cases.filter(c => c.test_type === filter),
    [cases, filter],
  )

  const grouped = useMemo(() => {
    const g: Record<number, TestCase[]> = {}
    filtered.forEach(c => {
      if (!g[c.requirement_id]) g[c.requirement_id] = []
      g[c.requirement_id].push(c)
    })
    return g
  }, [filtered])

  // ---- actions ----

  const startEdit = (c: TestCase) => {
    setEditingId(c.id)
    setEditForm({
      title: c.title,
      description: c.description || '',
      test_type: c.test_type || 'api',
      priority: c.priority || 'medium',
      steps: (c.steps || []).length > 0
        ? c.steps
        : [{ step: 1, action: '', expected: '' }],
    })
    setError('')
  }

  const cancelEdit = () => { setEditingId(null); setAddingForReq(null); setError('') }

  const saveEdit = async (caseId: number) => {
    if (!editForm.title.trim()) { setError('标题不能为空'); return }
    try {
      await casesApi.update(caseId, {
        title: editForm.title.trim(),
        description: editForm.description.trim(),
        test_type: editForm.test_type as TestCase['test_type'],
        priority: editForm.priority as TestCase['priority'],
        steps: editForm.steps.filter(s => s.action.trim() || s.expected.trim()),
      })
      setEditingId(null)
      await loadData()
    } catch (err: any) {
      setError(err.response?.data?.message || '保存失败')
    }
  }

  const handleDelete = async (caseId: number, title: string) => {
    if (!window.confirm(`确定删除「${title}」吗？`)) return
    try {
      await casesApi.delete(caseId)
      await loadData()
    } catch (err: any) {
      setError(err.response?.data?.message || '删除失败')
    }
  }

  const startAdd = (reqId: number) => {
    setAddingForReq(reqId)
    setEditingId(null)
    setEditForm({ ...NEW_CASE_TEMPLATE })
    setError('')
  }

  const saveNew = async (reqId: number) => {
    if (!editForm.title.trim()) { setError('标题不能为空'); return }
    try {
      await casesApi.create({
        requirement_id: reqId,
        title: editForm.title.trim(),
        description: editForm.description.trim(),
        test_type: editForm.test_type as TestCase['test_type'],
        priority: editForm.priority as TestCase['priority'],
        steps: editForm.steps.filter(s => s.action.trim() || s.expected.trim()),
      })
      setAddingForReq(null)
      await loadData()
    } catch (err: any) {
      setError(err.response?.data?.message || '创建失败')
    }
  }

  const handleConfirm = async (reqId: number) => {
    if (!window.confirm('确认用例无误，继续执行后续步骤？\n（仅会执行 UI 测试用例）')) return
    setConfirmingReq(reqId)
    try {
      await flowApi.confirmCases(reqId)
      alert('已确认，流程将继续执行。请回到对话页面查看进度。')
      await loadData()
    } catch (err: any) {
      setError(err.response?.data?.message || '确认失败，请重试')
    } finally { setConfirmingReq(null) }
  }

  const isReviewGate = (reqId: number) => {
    const req = requirements[reqId]
    return req && req.status === 'cases_generated'
  }

  // ---- render helpers ----

  const renderStepsEditor = () => (
    <div style={{ marginTop: 12 }}>
      <div style={{ fontFamily: C.mono, fontSize: 10, color: C.text3, marginBottom: 6 }}>STEPS</div>
      {editForm.steps.map((s, i) => (
        <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
          <span style={{ fontFamily: C.mono, fontSize: 10, color: C.text3, minWidth: 32 }}>{i + 1}.</span>
          <input value={s.action} onChange={e => {
            const ns = [...editForm.steps]; ns[i] = { ...ns[i], action: e.target.value }; setEditForm({ ...editForm, steps: ns })
          }} placeholder="操作" style={inputStyle} />
          <input value={s.expected} onChange={e => {
            const ns = [...editForm.steps]; ns[i] = { ...ns[i], expected: e.target.value }; setEditForm({ ...editForm, steps: ns })
          }} placeholder="预期结果" style={inputStyle} />
          {editForm.steps.length > 1 && (
            <button onClick={() => setEditForm({ ...editForm, steps: editForm.steps.filter((_, j) => j !== i) })}
              style={{ ...btnSm, color: 'var(--accent-magenta)' }}>×</button>
          )}
        </div>
      ))}
      <button onClick={() => setEditForm({ ...editForm, steps: [...editForm.steps, { step: editForm.steps.length + 1, action: '', expected: '' }] })}
        style={{ ...btnSm, color: 'var(--accent-cyan)', marginTop: 4 }}>+ 添加步骤</button>
    </div>
  )

  // ---- main render ----

  if (loading) return (
    <div style={{ textAlign: 'center', padding: 80, color: C.text3, fontFamily: C.mono, fontSize: 13 }}>
      <div style={{ display: 'inline-block', animation: 'spin-slow 1s linear infinite', fontSize: 24 }}>◆</div>
      <div style={{ marginTop: 16 }}>加载测试用例中...</div>
    </div>
  )

  return (
    <div className="page-stack animate-fade-in">
      {error && (
        <div style={{ padding: '12px 18px', borderRadius: 12, border: '1px solid rgba(255,45,120,0.3)', background: 'rgba(255,45,120,0.06)', fontFamily: C.mono, fontSize: 12, color: 'var(--accent-magenta)', marginBottom: 16 }}>
          [!] {error}
          <button onClick={() => setError('')} style={{ marginLeft: 12, background: 'none', border: 'none', color: 'var(--accent-magenta)', cursor: 'pointer' }}>×</button>
        </div>
      )}

      {/* Header */}
      <section className="gradient-border-card panel-inner">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 16, marginBottom: 24 }}>
          <div>
            <div style={{ fontFamily: C.mono, fontSize: 11, letterSpacing: '0.32em', color: 'var(--accent-emerald)', textTransform: 'uppercase', marginBottom: 10 }}>
              &gt; test_cases
            </div>
            <h2 style={{ fontFamily: C.display, fontSize: 32, fontWeight: 800, color: C.text, margin: '0 0 4px', letterSpacing: 0 }}>
              测试用例
            </h2>
            <p style={{ fontFamily: C.body, fontSize: 14, color: C.text2, margin: 0 }}>
              共 <span style={{ fontFamily: C.mono, fontWeight: 700, color: 'var(--accent-emerald)' }}>{cases.length}</span> 个
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            {TYPES.map(t => {
              const tc = TYPE_COLORS[t] || { color: C.text3, bg: 'transparent' }
              return <FilterButton key={t} label={t === 'all' ? 'ALL' : t.toUpperCase()} active={filter === t} onClick={() => setFilter(t)} color={tc.color} />
            })}
          </div>
        </div>
      </section>

      {!Object.keys(grouped).length ? (
        <div className="gradient-border-card panel-inner" style={{ textAlign: 'center', padding: 64, fontFamily: C.mono, fontSize: 13, color: C.text3 }}>
          暂无测试用例
        </div>
      ) : (
        Object.entries(grouped).sort(([a], [b]) => Number(b) - Number(a)).map(([reqId, reqCases]) => {
          const showEdit = isReviewGate(Number(reqId))
          const isHighlighted = highlightReqId === reqId

          return (
            <div key={reqId} id={`req-group-${reqId}`} className="gradient-border-card animate-float-up data-table-wrap" style={isHighlighted ? { boxShadow: '0 0 0 2px var(--accent-violet)' } : undefined}>
              {/* Group header */}
              <div style={{
                padding: '16px 20px', background: 'linear-gradient(90deg, rgba(0,212,255,0.04) 0%, transparent 100%)',
                borderBottom: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{ width: 32, height: 32, borderRadius: 8, background: 'rgba(0,212,255,0.1)', border: '1px solid rgba(0,212,255,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <span style={{ fontFamily: C.mono, fontSize: 12, fontWeight: 800, color: 'var(--accent-cyan)' }}>◈</span>
                  </div>
                  <div>
                    <Link to={`/requirements/${reqId}`} style={{ fontFamily: C.mono, fontSize: 12, fontWeight: 700, color: 'var(--accent-cyan)', textDecoration: 'none' }}>
                      req://{reqId}
                    </Link>
                    <span style={{ fontFamily: C.mono, fontSize: 11, color: C.text3, marginLeft: 8 }}>
                      {reqCases.length} cases
                    </span>
                    {showEdit && (
                      <span style={{ fontFamily: C.mono, fontSize: 10, color: 'var(--accent-violet)', marginLeft: 8, background: 'rgba(139,92,246,0.15)', padding: '2px 8px', borderRadius: 100 }}>
                        待确认
                      </span>
                    )}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  {showEdit && (
                    <>
                      <button onClick={() => startAdd(Number(reqId))} style={btnPrimarySm}>
                        ➕ 添加用例
                      </button>
                      <button onClick={() => handleConfirm(Number(reqId))} disabled={confirmingReq === Number(reqId)} style={btnConfirmSm}>
                        {confirmingReq === Number(reqId) ? '处理中...' : '✅ 确认并继续'}
                      </button>
                    </>
                  )}
                  <span style={{ fontFamily: C.mono, fontSize: 9, fontWeight: 600, color: 'var(--accent-emerald)', background: 'rgba(0,255,136,0.1)', padding: '3px 10px', borderRadius: 100 }}>
                    {reqCases.length} items
                  </span>
                </div>
              </div>

              {/* Add new case form */}
              {addingForReq === Number(reqId) && (
                <div style={{ padding: '20px', borderBottom: '1px solid var(--border-subtle)', background: 'rgba(139,92,246,0.04)' }}>
                  <div style={{ fontFamily: C.mono, fontSize: 11, fontWeight: 700, color: 'var(--accent-violet)', marginBottom: 12 }}>新建测试用例</div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 12 }}>
                    <input value={editForm.title} onChange={e => setEditForm({ ...editForm, title: e.target.value })} placeholder="标题" style={inputStyle} />
                    <div style={{ display: 'flex', gap: 8 }}>
                      <select value={editForm.test_type} onChange={e => setEditForm({ ...editForm, test_type: e.target.value })} style={{ ...inputStyle, flex: 1 }}>
                        <option value="ui">UI</option>
                        <option value="api">API</option>
                        <option value="performance">PERF</option>
                        <option value="security">SEC</option>
                      </select>
                      <select value={editForm.priority} onChange={e => setEditForm({ ...editForm, priority: e.target.value })} style={{ ...inputStyle, flex: 1 }}>
                        <option value="high">HIGH</option>
                        <option value="medium">MED</option>
                        <option value="low">LOW</option>
                      </select>
                    </div>
                  </div>
                  <input value={editForm.description} onChange={e => setEditForm({ ...editForm, description: e.target.value })} placeholder="描述" style={{ ...inputStyle, width: '100%', marginBottom: 8 }} />
                  {renderStepsEditor()}
                  <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                    <button onClick={() => saveNew(Number(reqId))} style={btnPrimarySm}>保存</button>
                    <button onClick={cancelEdit} style={btnSecondarySm}>取消</button>
                  </div>
                </div>
              )}

              {/* Cases table */}
              <table className="data-table" style={{ minWidth: 760 }}>
                <tbody>
                  {reqCases.map((c, i) => {
                    const typeStyle = TYPE_COLORS[c.test_type] || { color: C.text3, bg: 'rgba(255,255,255,0.05)' }
                    const prioStyle = PRIO_COLORS[c.priority] || { color: C.text3, bg: 'rgba(255,255,255,0.05)', label: c.priority }
                    const isEditing = editingId === c.id
                    const methodLabel = c.methodology ? METHOD_LABELS[c.methodology] || c.methodology : null

                    return (
                      <tr key={c.id} className="animate-float-up" style={{
                        animationDelay: `${i * 0.03}s`, transition: 'background 0.2s',
                        borderTop: i > 0 ? '1px solid var(--border-subtle)' : 'none',
                        background: isEditing ? 'rgba(139,92,246,0.04)' : 'transparent',
                      }}
                        onMouseEnter={e => { if (!isEditing) e.currentTarget.style.background = 'rgba(255,255,255,0.02)' }}
                        onMouseLeave={e => { if (!isEditing) e.currentTarget.style.background = 'transparent' }}>
                        <td style={{ padding: '16px 20px' }}>
                          {isEditing ? (
                            <div>
                              <input value={editForm.title} onChange={e => setEditForm({ ...editForm, title: e.target.value })} placeholder="标题" style={{ ...inputStyle, width: '100%', marginBottom: 8 }} />
                              <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                                <select value={editForm.test_type} onChange={e => setEditForm({ ...editForm, test_type: e.target.value })} style={{ ...inputStyle, flex: 1 }}>
                                  <option value="ui">UI</option>
                                  <option value="api">API</option>
                                  <option value="performance">PERF</option>
                                  <option value="security">SEC</option>
                                </select>
                                <select value={editForm.priority} onChange={e => setEditForm({ ...editForm, priority: e.target.value })} style={{ ...inputStyle, flex: 1 }}>
                                  <option value="high">HIGH</option>
                                  <option value="medium">MED</option>
                                  <option value="low">LOW</option>
                                </select>
                              </div>
                              <input value={editForm.description} onChange={e => setEditForm({ ...editForm, description: e.target.value })} placeholder="描述" style={{ ...inputStyle, width: '100%', marginBottom: 8 }} />
                              {renderStepsEditor()}
                              <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                                <button onClick={() => saveEdit(c.id)} style={btnPrimarySm}>保存</button>
                                <button onClick={cancelEdit} style={btnSecondarySm}>取消</button>
                              </div>
                            </div>
                          ) : (
                            <>
                              <div style={{ fontFamily: C.display, fontSize: 14, fontWeight: 600, color: C.text, marginBottom: 4 }}>
                                {c.title}
                              </div>
                              <div style={{ fontFamily: C.body, fontSize: 12, color: C.text3, lineHeight: 1.5 }}>
                                {c.description}
                              </div>
                              {(methodLabel || (c.steps && c.steps.length > 0)) && (
                                <div style={{ marginTop: 8, display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                                  {methodLabel && (
                                    <span style={{ fontFamily: C.mono, fontSize: 9, color: 'var(--accent-emerald)', background: 'rgba(0,255,136,0.1)', padding: '2px 8px', borderRadius: 100 }}>
                                      {methodLabel}
                                    </span>
                                  )}
                                  {c.steps && c.steps.length > 0 && (
                                    <span style={{ fontFamily: C.mono, fontSize: 9, color: C.text3 }}>
                                      {c.steps.length} 个步骤
                                    </span>
                                  )}
                                </div>
                              )}
                            </>
                          )}
                        </td>
                        <td style={{ width: 90, verticalAlign: 'top', paddingTop: 16 }}>
                          <span className="status-badge" style={{ color: typeStyle.color, background: typeStyle.bg }}>
                            {c.test_type.toUpperCase()}
                          </span>
                        </td>
                        <td style={{ width: 70, verticalAlign: 'top', paddingTop: 16 }}>
                          <span className="status-badge" style={{ color: prioStyle.color, background: prioStyle.bg }}>
                            {prioStyle.label}
                          </span>
                        </td>
                        {showEdit && (
                          <td style={{ width: 100, verticalAlign: 'top', paddingTop: 16 }}>
                            <div style={{ display: 'flex', gap: 4 }}>
                              <button onClick={() => startEdit(c)} style={btnSm}>
                                ✏️
                              </button>
                              <button onClick={() => handleDelete(c.id, c.title)} style={{ ...btnSm, color: 'var(--accent-magenta)' }}>
                                🗑
                              </button>
                            </div>
                          </td>
                        )}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )
        })
      )}
    </div>
  )
}

// ---- inline styles ----

const inputStyle: React.CSSProperties = {
  padding: '10px 14px', background: 'rgba(255,255,255,0.04)',
  border: '1px solid var(--border-subtle)', borderRadius: 10, color: 'var(--text-primary)',
  fontFamily: 'var(--font-mono)', fontSize: 12,
}

const btnSm: React.CSSProperties = {
  fontFamily: 'var(--font-mono)', fontSize: 13, padding: '4px 8px',
  borderRadius: 8, border: '1px solid var(--border-subtle)', background: 'rgba(255,255,255,0.04)',
  cursor: 'pointer', color: 'var(--text-secondary)',
}

const btnPrimarySm: React.CSSProperties = {
  fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600,
  padding: '7px 16px', borderRadius: 100, border: 'none',
  background: 'linear-gradient(135deg, var(--accent-violet), var(--accent-cyan))',
  color: '#050810', cursor: 'pointer',
}

const btnSecondarySm: React.CSSProperties = {
  fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600,
  padding: '7px 16px', borderRadius: 100, border: '1px solid var(--border-subtle)',
  background: 'rgba(255,255,255,0.04)', color: 'var(--text-secondary)', cursor: 'pointer',
}

const btnConfirmSm: React.CSSProperties = {
  fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600,
  padding: '7px 16px', borderRadius: 100, border: 'none',
  background: 'linear-gradient(135deg, var(--accent-emerald), var(--accent-cyan))',
  color: '#050810', cursor: 'pointer',
}
