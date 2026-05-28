import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from 'react'
import { KnowledgeBase, KnowledgeEntry, knowledgeBasesApi } from '../api'

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

function StatBox({ label, val, color }: { label: string; val: string; color: string }) {
  return (
    <div style={{
      padding: '16px', borderRadius: 14, background: 'rgba(255,255,255,0.02)',
      border: '1px solid var(--border-subtle)',
    }}>
      <div style={{ fontFamily: C.mono, fontSize: 10, fontWeight: 600, letterSpacing: '0.14em', color: C.text3, textTransform: 'uppercase', marginBottom: 6 }}>
        {label}
      </div>
      <div style={{ fontFamily: C.display, fontSize: 24, fontWeight: 800, color: color }}>
        {val}
      </div>
    </div>
  )
}

export default function KnowledgeBases() {
  const [kbs, setKbs] = useState<KnowledgeBase[]>([])
  const [selectedId, setSelectedId] = useState<number | ''>('')
  const [selectedDetail, setSelectedDetail] = useState<KnowledgeBase | null>(null)
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [fileTitle, setFileTitle] = useState('')
  const [tagsInput, setTagsInput] = useState('login,sms,retry')
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [importing, setImporting] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [error, setError] = useState('')

  const loadKbs = async (preferredId?: number) => {
    setLoading(true); setError('')
    try {
      const r = await knowledgeBasesApi.list(); const items = r.data.items || []
      setKbs(items); setSelectedId(preferredId || selectedId || items[0]?.id || '')
    } catch (e: any) { setError(e?.response?.data?.message || '加载失败') }
    finally { setLoading(false) }
  }

  useEffect(() => { loadKbs() }, [])

  useEffect(() => {
    if (!selectedId) { setSelectedDetail(null); return }
    knowledgeBasesApi.get(selectedId).then(r => setSelectedDetail(r.data)).catch(() => {})
  }, [selectedId])

  const selectedKb = useMemo(() => selectedDetail || kbs.find(k => k.id === selectedId) || null, [kbs, selectedDetail, selectedId])
  const entries: KnowledgeEntry[] = selectedDetail?.entries || []

  const handleCreate = async () => {
    if (!newName.trim()) { setError('请填写知识库名称'); return }
    setCreating(true); setError('')
    try {
      const r = await knowledgeBasesApi.create({ name: newName.trim(), description: newDesc.trim() })
      setNewName(''); setNewDesc(''); await loadKbs(r.data.knowledge_base.id)
    } catch (e: any) { setError(e?.response?.data?.message || '创建失败') }
    finally { setCreating(false) }
  }

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] || null; setUploadFile(f)
    if (f && !fileTitle.trim()) setFileTitle(f.name)
  }

  const handleImport = async (e: FormEvent) => {
    e.preventDefault()
    if (!selectedId || !uploadFile) { setError('请选择知识库并上传文件'); return }
    setImporting(true); setUploadProgress(0); setError('')
    try {
      const fd = new FormData(); fd.append('title', fileTitle.trim() || uploadFile.name)
      fd.append('tags', tagsInput); fd.append('file', uploadFile)
      await knowledgeBasesApi.importFile(selectedId, fd, pct => setUploadProgress(pct))
      setUploadFile(null); setFileTitle('')
      if (selectedId) { const r = await knowledgeBasesApi.get(selectedId); setSelectedDetail(r.data) }
      await loadKbs(selectedId)
    } catch (e: any) { setError(e?.response?.data?.message || '导入失败') }
    finally { setImporting(false); setUploadProgress(0) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }} className="animate-fade-in">
      {/* Header */}
      <section className="gradient-border-card" style={{ padding: '36px 32px' }}>
        <div style={{ fontFamily: C.mono, fontSize: 11, letterSpacing: '0.32em', color: 'var(--accent-magenta)', textTransform: 'uppercase', marginBottom: 10 }}>
          &gt; knowledge_hub
        </div>
        <h2 style={{ fontFamily: C.display, fontSize: 32, fontWeight: 800, color: C.text, margin: '0 0 8px', letterSpacing: '-0.01em' }}>
          知识库
        </h2>
        <p style={{ fontFamily: C.body, fontSize: 14, color: C.text2, margin: 0 }}>
          规范、缺陷经验、验收规则绑定到知识库，供 CaseAgent 上下文增强
        </p>
      </section>

      {error && (
        <div style={{
          padding: '14px 18px', borderRadius: 14, border: '1px solid rgba(255,45,120,0.3)',
          background: 'rgba(255,45,120,0.06)', fontFamily: C.mono, fontSize: 12, color: 'var(--accent-magenta)',
        }}>
          [!] {error}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '0.85fr 1.15fr', gap: 20 }}>
        {/* Left: KB selector + create */}
        <section className="gradient-border-card" style={{ padding: '28px 24px' }}>
          {/* Stats */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 24 }}>
            <StatBox label="知识库" val={loading ? '...' : String(kbs.length)} color="var(--accent-cyan)" />
            <StatBox label="条目" val={selectedKb ? String(selectedKb.entry_count) : '0'} color="var(--accent-magenta)" />
          </div>

          {/* KB selector */}
          <div style={{ marginBottom: 20 }}>
            <label style={{ fontFamily: C.mono, fontSize: 10, fontWeight: 600, letterSpacing: '0.14em', color: C.text3, display: 'block', marginBottom: 8, textTransform: 'uppercase' }}>
              select_kb
            </label>
            <select value={selectedId} onChange={e => setSelectedId(e.target.value ? Number(e.target.value) : '')}
              style={{
                width: '100%', padding: '14px 18px', background: 'rgba(255,255,255,0.03)',
                border: '1px solid var(--border-subtle)', borderRadius: 14, color: C.text, fontFamily: C.mono, fontSize: 13,
              }}>
              <option value="">-- select --</option>
              {kbs.map(k => <option key={k.id} value={k.id}>{k.name}</option>)}
            </select>
          </div>

          {/* Create new KB */}
          <div style={{
            padding: '18px', borderRadius: 16, border: '1px dashed var(--border-default)',
            background: 'rgba(255,255,255,0.01)',
          }}>
            <div style={{ fontFamily: C.mono, fontSize: 11, fontWeight: 700, color: C.text, marginBottom: 12 }}>
              新建知识库
            </div>
            <input value={newName} onChange={e => setNewName(e.target.value)} placeholder="kb_name"
              style={{
                width: '100%', padding: '12px 16px', background: 'rgba(255,255,255,0.03)',
                border: '1px solid var(--border-subtle)', borderRadius: 12, color: C.text, fontFamily: C.mono, fontSize: 13, marginBottom: 10,
              }}
            />
            <textarea value={newDesc} onChange={e => setNewDesc(e.target.value)} placeholder="description" rows={2}
              style={{
                width: '100%', padding: '12px 16px', background: 'rgba(255,255,255,0.03)',
                border: '1px solid var(--border-subtle)', borderRadius: 12, color: C.text, fontFamily: C.mono, fontSize: 13, resize: 'vertical', marginBottom: 12,
              }}
            />
            <button onClick={handleCreate} disabled={creating}
              style={{
                fontFamily: C.mono, fontSize: 12, fontWeight: 700, color: '#050810',
                background: 'linear-gradient(135deg, var(--accent-emerald), var(--accent-cyan))',
                padding: '10px 20px', borderRadius: 100, border: 'none', cursor: 'pointer', opacity: creating ? 0.5 : 1,
              }}>
              {creating ? '创建中...' : '创建知识库'}
            </button>
          </div>
        </section>

        {/* Right: File upload + entries */}
        <section className="gradient-border-card" style={{ padding: '28px 24px' }}>
          {/* Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
            <div>
              <div style={{ fontFamily: C.mono, fontSize: 11, letterSpacing: '0.28em', color: C.text3, textTransform: 'uppercase', marginBottom: 6 }}>
                /kb/file_binding
              </div>
              <h3 style={{ fontFamily: C.display, fontSize: 22, fontWeight: 800, color: C.text, margin: 0 }}>
                绑定文件到知识库
              </h3>
              <p style={{ fontFamily: C.body, fontSize: 12, color: C.text2, marginTop: 4 }}>
                支持 txt / md / csv / json / xlsx / docx / pdf
              </p>
            </div>
            <span style={{
              fontFamily: C.mono, fontSize: 11, color: C.text3, background: 'rgba(255,255,255,0.03)',
              padding: '6px 16px', borderRadius: 100, border: '1px solid var(--border-subtle)',
            }}>
              {selectedKb?.name || '未选择'}
            </span>
          </div>

          {/* Upload form */}
          <form onSubmit={handleImport} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <label style={{ fontFamily: C.mono, fontSize: 10, fontWeight: 600, letterSpacing: '0.14em', color: C.text3, display: 'block', marginBottom: 6, textTransform: 'uppercase' }}>
                  title
                </label>
                <input value={fileTitle} onChange={e => setFileTitle(e.target.value)}
                  style={{
                    width: '100%', padding: '12px 16px', background: 'rgba(255,255,255,0.03)',
                    border: '1px solid var(--border-subtle)', borderRadius: 12, color: C.text, fontFamily: C.mono, fontSize: 13,
                  }}
                />
              </div>
              <div>
                <label style={{ fontFamily: C.mono, fontSize: 10, fontWeight: 600, letterSpacing: '0.14em', color: C.text3, display: 'block', marginBottom: 6, textTransform: 'uppercase' }}>
                  tags
                </label>
                <input value={tagsInput} onChange={e => setTagsInput(e.target.value)}
                  style={{
                    width: '100%', padding: '12px 16px', background: 'rgba(255,255,255,0.03)',
                    border: '1px solid var(--border-subtle)', borderRadius: 12, color: C.text, fontFamily: C.mono, fontSize: 13,
                  }}
                />
              </div>
            </div>

            <label style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
              minHeight: 140, padding: 24, border: `1px dashed ${uploadFile ? 'var(--accent-emerald)' : 'var(--border-default)'}`,
              borderRadius: 16, cursor: 'pointer', background: uploadFile ? 'rgba(0,255,136,0.03)' : 'rgba(255,255,255,0.01)',
              transition: 'all 0.2s',
            }}
              onMouseEnter={e => { if (!uploadFile) e.currentTarget.style.borderColor = 'var(--accent-cyan)' }}
              onMouseLeave={e => { if (!uploadFile) e.currentTarget.style.borderColor = 'var(--border-default)' }}>
              <span style={{ fontFamily: C.mono, fontSize: 12, fontWeight: 700, color: C.text3, letterSpacing: '0.2em' }}>UPLOAD</span>
              <span style={{ fontFamily: C.mono, fontSize: 16, fontWeight: 800, color: uploadFile ? 'var(--accent-emerald)' : C.text, marginTop: 10 }}>
                {uploadFile ? uploadFile.name : '选择文件...'}
              </span>
              <span style={{ fontFamily: C.mono, fontSize: 10, color: C.text3, marginTop: 6 }}>.txt .md .csv .json .xlsx .docx .pdf</span>
              <input type="file" style={{ display: 'none' }} onChange={handleFileChange} accept=".txt,.md,.markdown,.csv,.json,.log,.xlsx,.docx,.pdf" />
            </label>

            {importing && (
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span style={{ fontFamily: C.mono, fontSize: 11, color: C.text2 }}>上传中...</span>
                  <span style={{ fontFamily: C.mono, fontSize: 11, color: 'var(--accent-cyan)' }}>{uploadProgress}%</span>
                </div>
                <div style={{ height: 4, borderRadius: 2, background: 'rgba(255,255,255,0.05)', overflow: 'hidden' }}>
                  <div className="shimmer" style={{ height: '100%', borderRadius: 2, width: `${uploadProgress}%`, transition: 'width 0.3s' }} />
                </div>
              </div>
            )}

            <button type="submit" disabled={importing || !selectedId || !uploadFile}
              style={{
                fontFamily: C.mono, fontSize: 13, fontWeight: 700, color: '#050810',
                background: 'linear-gradient(135deg, var(--accent-cyan), var(--accent-emerald))',
                padding: '13px 24px', borderRadius: 100, border: 'none', cursor: 'pointer',
                opacity: (importing || !selectedId || !uploadFile) ? 0.4 : 1, transition: 'all 0.2s',
              }}>
              {importing ? '上传中...' : '绑定文件'}
            </button>
          </form>

          {/* Entries */}
          <div style={{ marginTop: 28, borderTop: '1px solid var(--border-subtle)', paddingTop: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
              <span style={{ fontFamily: C.display, fontSize: 15, fontWeight: 700, color: C.text }}>
                条目列表
              </span>
              <span style={{ fontFamily: C.mono, fontSize: 11, color: C.text3 }}>
                {entries.length} items
              </span>
            </div>
            {!entries.length ? (
              <div style={{
                textAlign: 'center', padding: 40, color: C.text3, fontFamily: C.mono, fontSize: 12,
                border: '1px dashed var(--border-default)', borderRadius: 14,
              }}>
                当前知识库暂无条目
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }} className="stagger-children">
                {entries.map(entry => (
                  <div key={entry.id} className="animate-float-up card-hover" style={{
                    padding: '16px 18px', border: '1px solid var(--border-subtle)',
                    borderRadius: 14, background: 'rgba(255,255,255,0.02)', transition: 'all 0.25s',
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
                      <span style={{ fontFamily: C.display, fontSize: 14, fontWeight: 600, color: C.text }}>
                        {entry.title}
                      </span>
                      <span style={{
                        fontFamily: C.mono, fontSize: 9, color: C.text3,
                        background: 'rgba(255,255,255,0.04)', padding: '3px 8px', borderRadius: 6,
                      }}>
                        {entry.source_type}
                      </span>
                    </div>
                    <div style={{ display: 'flex', gap: 6, marginTop: 10, flexWrap: 'wrap' }}>
                      {entry.tags.map(tag => (
                        <span key={tag} style={{
                          fontFamily: C.mono, fontSize: 9, fontWeight: 600, color: 'var(--accent-emerald)',
                          background: 'rgba(0,255,136,0.1)', padding: '3px 10px', borderRadius: 100, border: '1px solid rgba(0,255,136,0.15)',
                        }}>
                          {tag}
                        </span>
                      ))}
                    </div>
                    <p style={{
                      fontFamily: C.body, fontSize: 12, color: C.text2, marginTop: 10, lineHeight: 1.6,
                      display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden',
                    }}>
                      {entry.content}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}