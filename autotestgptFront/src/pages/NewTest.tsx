import { ChangeEvent, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { flowApi, knowledgeBasesApi, KnowledgeBase, requirementsApi } from '../api'

const defaultDemand = `会员中心登录需求
1. 手机号 + 短信验证码可以正常登录
2. 错误验证码需要给出明确提示
3. 验证码过期时需要拦截并提示重新获取
4. 连续多次输错验证码后需要触发重试限制策略
5. 登录成功后进入会员中心首页`

type InputMode = 'text' | 'file'
type FileTarget = 'requirement' | 'knowledge'

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

function ModeCard({ active, title, description, kicker, onClick, accent }: {
  active: boolean; title: string; description: string; kicker: string; onClick: () => void; accent: string
}) {
  return (
    <button type="button" onClick={onClick} style={{
      textAlign: 'left', padding: '18px 20px', borderRadius: 16,
      border: `1px solid ${active ? accent : 'var(--border-subtle)'}`,
      background: active ? `${accent}10` : 'rgba(255,255,255,0.02)',
      cursor: 'pointer', transition: 'all 0.25s ease', width: '100%',
    }}
      onMouseEnter={e => { if (!active) e.currentTarget.style.borderColor = `${accent}40` }}
      onMouseLeave={e => { if (!active) e.currentTarget.style.borderColor = 'var(--border-subtle)' }}>
      <div style={{ fontFamily: C.mono, fontSize: 10, fontWeight: 700, letterSpacing: '0.22em', color: active ? accent : 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 8 }}>
        {kicker}
      </div>
      <div style={{ fontFamily: C.display, fontSize: 15, fontWeight: 700, color: active ? C.text : 'var(--text-secondary)', marginBottom: 6 }}>
        {title}
      </div>
      <div style={{ fontFamily: C.body, fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>
        {description}
      </div>
    </button>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', borderRadius: 12, background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}>
      <span style={{ fontFamily: C.mono, fontSize: 11, color: 'var(--text-muted)' }}>{label}</span>
      <span style={{ fontFamily: C.mono, fontSize: 11, fontWeight: 600, color: C.text2 }}>{value}</span>
    </div>
  )
}

export default function NewTest() {
  const navigate = useNavigate()
  const [inputMode, setInputMode] = useState<InputMode>('text')
  const [fileTarget, setFileTarget] = useState<FileTarget>('requirement')
  const [title, setTitle] = useState('会员中心登录需求')
  const [demand, setDemand] = useState(defaultDemand)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([])
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] = useState<number | ''>('')
  const [newKnowledgeBaseName, setNewKnowledgeBaseName] = useState('')
  const [newKnowledgeBaseDesc, setNewKnowledgeBaseDesc] = useState('')
  const [tagsInput, setTagsInput] = useState('login,sms')
  const [reviewEnabled, setReviewEnabled] = useState(false)
  const [reviewRepoType, setReviewRepoType] = useState<'remote' | 'local'>('remote')
  const [reviewRepoUrl, setReviewRepoUrl] = useState('http://git.100credit.cn/group/demo-repo.git')
  const [reviewRepoPath, setReviewRepoPath] = useState('')
  const [reviewBranch, setReviewBranch] = useState('main')
  const [reviewDays, setReviewDays] = useState(7)
  const [loading, setLoading] = useState(false)
  const [creatingKnowledgeBase, setCreatingKnowledgeBase] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    knowledgeBasesApi.list().then(res => {
      const items = res.data.items || []
      setKnowledgeBases(items)
      if (!selectedKnowledgeBaseId && items.length > 0) setSelectedKnowledgeBaseId(items[0].id)
    }).catch(err => console.error('Failed to load knowledge bases:', err))
  }, [])

  const canSubmit = useMemo(() => {
    if (inputMode === 'text') {
      const hasRequirement = title.trim().length > 0 && demand.trim().length > 0
      if (!hasRequirement) return false
      if (!reviewEnabled) return true
      if (reviewRepoType === 'local') return reviewRepoPath.trim().length > 0 && reviewBranch.trim().length > 0 && reviewDays > 0
      return reviewRepoUrl.trim().length > 0 && reviewBranch.trim().length > 0 && reviewDays > 0
    }
    if (!uploadFile) return false
    if (fileTarget === 'knowledge') return !!selectedKnowledgeBaseId
    return title.trim().length > 0
  }, [demand, fileTarget, inputMode, reviewBranch, reviewDays, reviewEnabled, reviewRepoType, reviewRepoUrl, reviewRepoPath, selectedKnowledgeBaseId, title, uploadFile])

  const selectedKnowledgeBase = useMemo(
    () => knowledgeBases.find(item => item.id === selectedKnowledgeBaseId) || null,
    [knowledgeBases, selectedKnowledgeBaseId]
  )

  const handleCreateKnowledgeBase = async () => {
    if (!newKnowledgeBaseName.trim()) { setError('请先填写知识库名称。'); return }
    setCreatingKnowledgeBase(true); setError('')
    try {
      const res = await knowledgeBasesApi.create({ name: newKnowledgeBaseName.trim(), description: newKnowledgeBaseDesc.trim() })
      const created = res.data.knowledge_base
      setKnowledgeBases(prev => [created, ...prev])
      setSelectedKnowledgeBaseId(created.id)
      setNewKnowledgeBaseName(''); setNewKnowledgeBaseDesc('')
    } catch (err: any) { setError(err.response?.data?.message || err.response?.data?.error || '创建知识库失败') }
    finally { setCreatingKnowledgeBase(false) }
  }

  const handleTextFlowStart = async () => {
    const res = await flowApi.start({
      title: title.trim(), demand: demand.trim(), project_id: 1,
      knowledge_base_id: selectedKnowledgeBaseId || undefined,
      review: reviewEnabled ? (
        reviewRepoType === 'local'
          ? { repo_path: reviewRepoPath.trim(), branch: reviewBranch.trim(), days: reviewDays }
          : { repo_url: reviewRepoUrl.trim(), branch: reviewBranch.trim(), days: reviewDays }
      ) : undefined,
    })
    navigate(`/requirements/${res.data.requirement_id}`)
  }

  const handleRequirementFileImport = async () => {
    if (!uploadFile) return
    const formData = new FormData()
    formData.append('title', title.trim()); formData.append('project_id', '1')
    if (selectedKnowledgeBaseId) formData.append('knowledge_base_id', String(selectedKnowledgeBaseId))
    formData.append('file', uploadFile)
    const res = await requirementsApi.importFile(formData)
    navigate(`/requirements/${res.data.requirement.id}`)
  }

  const handleKnowledgeFileImport = async () => {
    if (!uploadFile || !selectedKnowledgeBaseId) return
    const formData = new FormData()
    formData.append('title', title.trim() || uploadFile.name)
    formData.append('tags', tagsInput); formData.append('file', uploadFile)
    await knowledgeBasesApi.importFile(selectedKnowledgeBaseId, formData)
    navigate('/requirements')
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmit) { setError('请先补齐当前模式所需的信息。'); return }
    setLoading(true); setError('')
    try {
      if (inputMode === 'text') await handleTextFlowStart()
      else if (fileTarget === 'requirement') await handleRequirementFileImport()
      else await handleKnowledgeFileImport()
    } catch (err: any) { setError(err.response?.data?.message || err.response?.data?.error || '提交失败'); setLoading(false) }
  }

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    setUploadFile(event.target.files?.[0] || null)
  }

  return (
    <div className="page-stack animate-fade-in">
      {/* Header */}
      <section className="gradient-border-card panel-inner">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
          <div>
            <div style={{ fontFamily: C.mono, fontSize: 11, letterSpacing: '0.32em', color: 'var(--accent-violet)', textTransform: 'uppercase', marginBottom: 10 }}>
              &gt; demand_workspace
            </div>
            <h2 style={{ fontFamily: C.display, fontSize: 32, fontWeight: 800, color: C.text, margin: '0 0 8px', letterSpacing: 0 }}>
              需求与知识入口
            </h2>
            <p style={{ fontFamily: C.body, fontSize: 14, color: C.text2, margin: 0, maxWidth: 520 }}>
              把需求喂给多 Agent 流程，或把文档沉淀到知识库。文本输入 / 文件导入 → Requirement 或知识条目。
            </p>
          </div>
          <button type="button" className="btn btn-secondary" onClick={() => { setInputMode('text'); setDemand(defaultDemand) }}>
            加载示例
          </button>
        </div>
      </section>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 20 }}>
        {/* Left: Main form */}
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

            {/* Mode selection */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <ModeCard active={inputMode === 'text'} kicker="Text" title="直接输入需求" description="会议纪要、临时分析、补充验收条件，提交后启动多 Agent 主流程。" onClick={() => setInputMode('text')} accent="var(--accent-cyan)" />
              <ModeCard active={inputMode === 'file'} kicker="File" title="导入需求或知识文档" description="txt / md / csv / json / log / xlsx / docx / pdf，转为 Requirement 或知识条目。" onClick={() => setInputMode('file')} accent="var(--accent-amber)" />
            </div>

            <div>
              <label style={{ fontFamily: C.mono, fontSize: 10, fontWeight: 600, letterSpacing: '0.14em', color: C.text3, display: 'block', marginBottom: 8, textTransform: 'uppercase' }}>title</label>
              <input value={title} onChange={e => setTitle(e.target.value)}
                style={{ width: '100%', padding: '14px 18px', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border-subtle)', borderRadius: 14, color: C.text, fontFamily: C.mono, fontSize: 13 }}
              />
            </div>

            {inputMode === 'text' ? (
              <div>
                <label style={{ fontFamily: C.mono, fontSize: 10, fontWeight: 600, letterSpacing: '0.14em', color: C.text3, display: 'block', marginBottom: 8, textTransform: 'uppercase' }}>demand_content</label>
                <textarea value={demand} onChange={e => setDemand(e.target.value)} rows={10}
                  style={{
                    width: '100%', padding: '16px 18px', background: 'rgba(255,255,255,0.02)',
                    border: '1px solid var(--border-subtle)', borderRadius: 16, color: C.text,
                    fontFamily: C.mono, fontSize: 12, resize: 'vertical', lineHeight: 1.7,
                  }}
                />
                <p style={{ fontFamily: C.mono, fontSize: 10, color: C.text3, marginTop: 8 }}>
                  提交后进入：需求解析 → 知识库增强用例设计 → 脚本生成 → 执行与报告
                </p>
              </div>
            ) : (
              <>
                <div>
                  <label style={{ fontFamily: C.mono, fontSize: 10, fontWeight: 600, letterSpacing: '0.14em', color: C.text3, display: 'block', marginBottom: 8, textTransform: 'uppercase' }}>file_target</label>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                    <ModeCard active={fileTarget === 'requirement'} kicker="Requirement" title="导入为需求" description="文件内容转成 Requirement，后续在详情页继续推进或补充 review。" onClick={() => setFileTarget('requirement')} accent="var(--accent-cyan)" />
                    <ModeCard active={fileTarget === 'knowledge'} kicker="Knowledge" title="沉淀到知识库" description="把规范、接口说明、测试经验导入知识库，供后续用例设计复用。" onClick={() => setFileTarget('knowledge')} accent="var(--accent-emerald)" />
                  </div>
                </div>

                <div>
                  <label style={{ fontFamily: C.mono, fontSize: 10, fontWeight: 600, letterSpacing: '0.14em', color: C.text3, display: 'block', marginBottom: 8, textTransform: 'uppercase' }}>upload_file</label>
                  <label style={{
                    display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                    minHeight: 160, padding: 24, border: `1px dashed ${uploadFile ? 'var(--accent-emerald)' : 'var(--border-default)'}`,
                    borderRadius: 16, cursor: 'pointer', background: uploadFile ? 'rgba(0,255,136,0.03)' : 'rgba(255,255,255,0.01)',
                    transition: 'all 0.2s',
                  }}
                    onMouseEnter={e => { if (!uploadFile) e.currentTarget.style.borderColor = 'var(--accent-cyan)' }}
                    onMouseLeave={e => { if (!uploadFile) e.currentTarget.style.borderColor = 'var(--border-default)' }}>
                    <span style={{ fontFamily: C.mono, fontSize: 10, fontWeight: 700, color: C.text3, letterSpacing: '0.24em' }}>IMPORT</span>
                    <span style={{ fontFamily: C.mono, fontSize: 16, fontWeight: 800, color: uploadFile ? 'var(--accent-emerald)' : C.text, marginTop: 10 }}>
                      {uploadFile ? uploadFile.name : '选择文件...'}
                    </span>
                    <span style={{ fontFamily: C.mono, fontSize: 10, color: C.text3, marginTop: 6 }}>.txt .md .csv .json .log .xlsx .docx .pdf</span>
                    <input type="file" style={{ display: 'none' }} onChange={handleFileChange} accept=".txt,.md,.markdown,.csv,.json,.log,.xlsx,.docx,.pdf" />
                  </label>
                </div>
              </>
            )}

            {/* Knowledge Binding */}
            <div style={{
              padding: '22px 20px', borderRadius: 18, border: '1px solid var(--border-subtle)',
              background: 'rgba(255,255,255,0.01)',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <div>
                  <div style={{ fontFamily: C.mono, fontSize: 10, letterSpacing: '0.2em', color: C.text3, textTransform: 'uppercase', marginBottom: 4 }}>
                    knowledge_binding
                  </div>
                  <h3 style={{ fontFamily: C.display, fontSize: 18, fontWeight: 700, color: C.text, margin: 0 }}>知识库绑定</h3>
                </div>
                <span style={{
                  fontFamily: C.mono, fontSize: 11, color: C.text3, background: 'rgba(255,255,255,0.03)',
                  padding: '5px 14px', borderRadius: 100, border: '1px solid var(--border-subtle)',
                }}>
                  {selectedKnowledgeBase ? `${selectedKnowledgeBase.entry_count} 条知识` : '未绑定'}
                </span>
              </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
                <div>
                  <label style={{ fontFamily: C.mono, fontSize: 10, color: C.text3, display: 'block', marginBottom: 6 }}>select_kb</label>
                  <select value={selectedKnowledgeBaseId} onChange={e => setSelectedKnowledgeBaseId(e.target.value ? Number(e.target.value) : '')}
                    style={{
                      width: '100%', padding: '12px 16px', background: 'rgba(255,255,255,0.03)',
                      border: '1px solid var(--border-subtle)', borderRadius: 12, color: C.text, fontFamily: C.mono, fontSize: 13,
                    }}>
                    <option value="">-- none --</option>
                    {knowledgeBases.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
                  </select>
                </div>

                <div style={{ padding: '16px', borderRadius: 14, border: '1px dashed var(--border-default)', background: 'rgba(255,255,255,0.01)' }}>
                  <div style={{ fontFamily: C.mono, fontSize: 11, fontWeight: 700, color: C.text }}>新建知识库</div>
                  <input value={newKnowledgeBaseName} onChange={e => setNewKnowledgeBaseName(e.target.value)}
                    placeholder="kb_name"
                    style={{
                      width: '100%', marginTop: 10, padding: '10px 14px', background: 'rgba(255,255,255,0.03)',
                      border: '1px solid var(--border-subtle)', borderRadius: 10, color: C.text, fontFamily: C.mono, fontSize: 12,
                    }}
                  />
                  <textarea value={newKnowledgeBaseDesc} onChange={e => setNewKnowledgeBaseDesc(e.target.value)}
                    placeholder="description" rows={2}
                    style={{
                      width: '100%', marginTop: 8, padding: '10px 14px', background: 'rgba(255,255,255,0.03)',
                      border: '1px solid var(--border-subtle)', borderRadius: 10, color: C.text, fontFamily: C.mono, fontSize: 12, resize: 'vertical',
                    }}
                  />
                  <button type="button" onClick={handleCreateKnowledgeBase} disabled={creatingKnowledgeBase}
                    style={{
                      marginTop: 10, fontFamily: C.mono, fontSize: 11, fontWeight: 700, color: '#050810',
                      background: 'linear-gradient(135deg, var(--accent-emerald), var(--accent-cyan))',
                      padding: '8px 18px', borderRadius: 100, border: 'none', cursor: 'pointer', opacity: creatingKnowledgeBase ? 0.5 : 1,
                    }}>
                    {creatingKnowledgeBase ? '创建中...' : '创建知识库'}
                  </button>
                </div>
              </div>

              {inputMode === 'file' && fileTarget === 'knowledge' && (
                <div style={{ marginTop: 14 }}>
                  <label style={{ fontFamily: C.mono, fontSize: 10, color: C.text3, display: 'block', marginBottom: 6 }}>tags</label>
                  <input value={tagsInput} onChange={e => setTagsInput(e.target.value)}
                    style={{
                      width: '100%', padding: '12px 16px', background: 'rgba(255,255,255,0.03)',
                      border: '1px solid var(--border-subtle)', borderRadius: 12, color: C.text, fontFamily: C.mono, fontSize: 13,
                    }}
                  />
                </div>
              )}
            </div>

            {/* Code Review toggle */}
            {inputMode === 'text' && (
              <div style={{
                padding: '22px 20px', borderRadius: 18, border: '1px solid var(--border-subtle)',
                background: 'rgba(255,255,255,0.01)',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
                  <div>
                    <div style={{ fontFamily: C.mono, fontSize: 10, letterSpacing: '0.2em', color: C.text3, textTransform: 'uppercase', marginBottom: 4 }}>
                      code_review
                    </div>
                    <h3 style={{ fontFamily: C.display, fontSize: 18, fontWeight: 700, color: C.text, margin: 0 }}>代码 Review</h3>
                    <p style={{ fontFamily: C.body, fontSize: 12, color: C.text2, marginTop: 4, maxWidth: 400 }}>
                      代码 Review 纳入完整流程：勾选后主流程在测试执行后自动拉取仓库，生成 review finding，统一写入报告。
                    </p>
                  </div>
                  <label style={{
                    display: 'inline-flex', alignItems: 'center', gap: 10, fontFamily: C.mono, fontSize: 12, fontWeight: 600, color: C.text2,
                    background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border-default)', borderRadius: 100, padding: '8px 18px', cursor: 'pointer',
                  }}>
                    <input type="checkbox" checked={reviewEnabled} onChange={e => setReviewEnabled(e.target.checked)}
                      style={{ accentColor: 'var(--accent-emerald)', width: 14, height: 14 }}
                    />
                    {reviewEnabled ? 'enabled' : 'enable_review'}
                  </label>
                </div>

                {reviewEnabled && (
                  <div style={{ marginTop: 16 }}>
                    {/* Repo type tab switcher */}
                    <div style={{ display: 'flex', gap: 0, borderRadius: 12, overflow: 'hidden', border: '1px solid var(--border-subtle)', marginBottom: 12 }}>
                      <button type="button" onClick={() => setReviewRepoType('remote')} style={{
                        flex: 1, padding: '8px 12px', border: 'none', cursor: 'pointer',
                        fontFamily: C.mono, fontSize: 10, fontWeight: 700, letterSpacing: '0.06em',
                        color: reviewRepoType === 'remote' ? '#050810' : C.text3,
                        background: reviewRepoType === 'remote' ? 'var(--accent-violet)' : 'rgba(255,255,255,0.02)',
                        transition: 'all 0.2s',
                      }}>
                        REMOTE URL
                      </button>
                      <button type="button" onClick={() => setReviewRepoType('local')} style={{
                        flex: 1, padding: '8px 12px', border: 'none', cursor: 'pointer',
                        fontFamily: C.mono, fontSize: 10, fontWeight: 700, letterSpacing: '0.06em',
                        color: reviewRepoType === 'local' ? '#050810' : C.text3,
                        background: reviewRepoType === 'local' ? 'var(--accent-cyan)' : 'rgba(255,255,255,0.02)',
                        transition: 'all 0.2s',
                      }}>
                        LOCAL PATH
                      </button>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
                      <div>
                        <label style={{ fontFamily: C.mono, fontSize: 10, color: C.text3, display: 'block', marginBottom: 6 }}>
                          {reviewRepoType === 'remote' ? 'git_repo_url' : 'local_repo_path'}
                        </label>
                        {reviewRepoType === 'remote' ? (
                          <input value={reviewRepoUrl} onChange={e => setReviewRepoUrl(e.target.value)}
                            placeholder="https://github.com/org/repo.git"
                            style={{
                              width: '100%', padding: '12px 16px', background: 'rgba(255,255,255,0.03)',
                              border: '1px solid var(--border-subtle)', borderRadius: 12, color: C.text, fontFamily: C.mono, fontSize: 13,
                            }}
                          />
                        ) : (
                          <input value={reviewRepoPath} onChange={e => setReviewRepoPath(e.target.value)}
                            placeholder="D:/projects/my-repo"
                            style={{
                              width: '100%', padding: '12px 16px', background: 'rgba(255,255,255,0.03)',
                              border: '1px solid var(--border-subtle)', borderRadius: 12, color: C.text, fontFamily: C.mono, fontSize: 13,
                            }}
                          />
                        )}
                      </div>
                      <div>
                        <label style={{ fontFamily: C.mono, fontSize: 10, color: C.text3, display: 'block', marginBottom: 6 }}>branch</label>
                        <input value={reviewBranch} onChange={e => setReviewBranch(e.target.value)}
                          style={{
                            width: '100%', padding: '12px 16px', background: 'rgba(255,255,255,0.03)',
                            border: '1px solid var(--border-subtle)', borderRadius: 12, color: C.text, fontFamily: C.mono, fontSize: 13,
                          }}
                        />
                      </div>
                      <div>
                        <label style={{ fontFamily: C.mono, fontSize: 10, color: C.text3, display: 'block', marginBottom: 6 }}>days</label>
                        <input type="number" min={1} value={reviewDays} onChange={e => setReviewDays(Number(e.target.value))}
                          style={{
                            width: '100%', padding: '12px 16px', background: 'rgba(255,255,255,0.03)',
                            border: '1px solid var(--border-subtle)', borderRadius: 12, color: C.text, fontFamily: C.mono, fontSize: 13,
                          }}
                        />
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16,
              borderTop: '1px solid var(--border-subtle)', paddingTop: 20,
            }}>
              <span style={{ fontFamily: C.mono, fontSize: 11, color: C.text3 }}>
                {inputMode === 'text' ? '文本输入 -> 流程执行 -> 报告生成' : fileTarget === 'requirement' ? '文件导入 -> 生成需求 -> 详情处理' : '文件导入 -> 沉淀知识库'}
              </span>
              <button type="submit" disabled={loading} className="btn btn-primary">
                {loading ? '处理中...' : inputMode === 'text' ? '启动流程' : fileTarget === 'requirement' ? '导入为需求' : '导入到知识库'}
              </button>
            </div>
          </form>
        </section>

        {/* Right sidebar */}
        <aside style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Pipeline steps */}
          <section className="gradient-border-card" style={{ padding: '28px 24px' }}>
            <div style={{ fontFamily: C.mono, fontSize: 10, letterSpacing: '0.28em', color: 'var(--accent-cyan)', textTransform: 'uppercase', marginBottom: 6 }}>
              pipeline
            </div>
            <h3 style={{ fontFamily: C.display, fontSize: 20, fontWeight: 800, color: C.text, margin: '0 0 18px' }}>
              完整协作链路
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {[
                { step: '01', text: '拿到需求：文本输入或文件导入', color: 'var(--accent-cyan)' },
                { step: '02', text: '知识库增强：历史规则、规范、缺陷经验', color: 'var(--accent-violet)' },
                { step: '03', text: '设计测试用例：API / UI / 异常场景', color: 'var(--accent-emerald)' },
                { step: '04', text: '选择仓库并做分支 + 天数代码 Review', color: 'var(--accent-amber)' },
                { step: '05', text: '需求与代码联合分析，沉淀缺陷候选', color: 'var(--accent-magenta)' },
                { step: '06', text: '接口测试 / UI 自动化 / 报告 / 修复建议', color: 'var(--accent-cyan)' },
              ].map(({ step, text, color }) => (
                <div key={step} style={{
                  padding: '14px 16px', borderRadius: 14, border: '1px solid var(--border-subtle)',
                  background: 'rgba(255,255,255,0.02)', position: 'relative', overflow: 'hidden',
                }}>
                  <div style={{
                    position: 'absolute', left: 0, top: 0, bottom: 0, width: 3,
                    background: `linear-gradient(180deg, ${color}, transparent)`,
                  }} />
                  <div style={{ fontFamily: C.mono, fontSize: 9, fontWeight: 700, letterSpacing: '0.2em', color: color, textTransform: 'uppercase', marginBottom: 4 }}>
                    step_{step}
                  </div>
                  <div style={{ fontFamily: C.body, fontSize: 12, fontWeight: 500, color: C.text2 }}>
                    {text}
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Current selection */}
          <section className="gradient-border-card" style={{ padding: '24px' }}>
            <div style={{ fontFamily: C.mono, fontSize: 10, letterSpacing: '0.24em', color: C.text3, textTransform: 'uppercase', marginBottom: 14 }}>
              current_selection
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <InfoRow label="输入模式" value={inputMode === 'text' ? '直接输入需求' : '导入文件'} />
              <InfoRow label="文件目标" value={inputMode === 'text' ? '直接跑流程' : fileTarget === 'requirement' ? '创建 Requirement' : '沉淀到知识库'} />
              <InfoRow label="绑定知识库" value={selectedKnowledgeBase?.name || '未绑定'} />
              <InfoRow label="代码 Review" value={reviewEnabled ? (reviewRepoType === 'local' ? '本地仓库' : '远程仓库') + ` / ${reviewBranch} / ${reviewDays}d` : '未纳入'} />
              <InfoRow label="选中文件" value={uploadFile?.name || '未选择文件'} />
            </div>
          </section>
        </aside>
      </div>
    </div>
  )
}
