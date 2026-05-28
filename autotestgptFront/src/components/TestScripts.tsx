import { useEffect, useState } from 'react'
import { scriptsApi, TestScript } from '../api'

const S = {
  bg: 'var(--bg-elevated)', bd: 'var(--border-default)', cyan: 'var(--accent-cyan)',
  em: 'var(--accent-emerald)', am: 'var(--accent-amber)', ro: 'var(--accent-magenta)',
  tx: 'var(--text-primary)', t2: 'var(--text-secondary)', t3: 'var(--text-muted)',
  mono: 'var(--font-mono)',
}

interface TestScriptsProps { requirementId: number }

export default function TestScripts({ requirementId }: TestScriptsProps) {
  const [scripts, setScripts] = useState<TestScript[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedScriptId, setSelectedScriptId] = useState<number | null>(null)

  const loadScripts = async () => {
    if (!requirementId) return
    setLoading(true); setError(null)
    try { const r = await scriptsApi.list(requirementId); setScripts(r.data || []) }
    catch { setError('获取测试脚本失败') }
    finally { setLoading(false) }
  }

  useEffect(() => { loadScripts() }, [requirementId])

  return (
    <section className="gradient-border-card panel-inner">
      <div style={{ display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:16 }}>
        <div>
          <div style={{ fontFamily:S.mono,fontSize:11,letterSpacing:'0.28em',color:S.t3,textTransform:'uppercase',marginBottom:6 }}>/scripts</div>
          <h2 style={{ fontFamily:'var(--font-display)',fontSize:22,fontWeight:800,color:S.tx,margin:0 }}>测试脚本</h2>
        </div>
        <button type="button" onClick={loadScripts} disabled={loading} className="btn btn-secondary"
          style={{ padding: '6px 14px', fontSize: 11 }}>
          {loading ? '加载中...' : '刷新'}
        </button>
      </div>

      {error && <div style={{ marginBottom:12,padding:'10px 14px',borderRadius:10,border:`1px solid rgba(244,63,94,0.25)`,background:'rgba(244,63,94,0.06)',fontFamily:S.mono,fontSize:11,color:S.ro }}>[!] {error}</div>}

      {!scripts.length && !loading ? (
        <div style={{ textAlign:'center',padding:36,color:S.t3,fontFamily:S.mono,fontSize:12,border:`1px dashed ${S.bd}`,borderRadius:12 }}>暂无脚本</div>
      ) : (
        <div style={{ display:'flex',flexDirection:'column',gap:8 }}>
          {scripts.map(script => {
            const selected = selectedScriptId === script.id
            return (
              <article key={script.id} style={{ borderRadius:14,border:`1px solid ${S.bd}`,overflow:'hidden' }}>
                <button type="button" onClick={() => setSelectedScriptId(selected ? null : script.id)}
                  style={{ display:'flex',width:'100%',justifyContent:'space-between',alignItems:'flex-start',gap:12,padding:'14px 16px',background:selected ? 'rgba(0,229,255,0.04)' : 'rgba(255,255,255,0.01)',border:'none',cursor:'pointer',textAlign:'left',transition:'background 0.15s' }}>
                  <div>
                    <div style={{ fontFamily:S.mono,fontSize:12,fontWeight:700,color:S.tx }}>
                      {script.file_path?.split('\\').pop() || `script_${script.id}`}
                    </div>
                    <div style={{ fontFamily:S.mono,fontSize:10,color:S.t3,marginTop:2 }}>
                      {script.script_type} &middot; case #{script.test_case_id} &middot;
                      <span className={`status-badge ${script.status}`} style={{ marginLeft: 8, verticalAlign: 'middle' }}>
                        {script.status}
                      </span>
                    </div>
                  </div>
                  <div style={{ fontFamily:S.mono,fontSize:9,color:S.t3,flexShrink:0 }}>
                    {new Date(script.created_at).toLocaleString('zh-CN')}
                  </div>
                </button>

                {selected && (
                  <div style={{ borderTop:`1px solid ${S.bd}`,padding:'16px' }}>
                    <pre style={{ margin:0,padding:'16px',borderRadius:12,background:'rgba(0,0,0,0.35)',fontFamily:S.mono,fontSize:10,color:S.t2,overflowX:'auto',lineHeight:1.7,maxHeight:500,overflowY:'auto' }}>
                      {script.content}
                    </pre>
                  </div>
                )}
              </article>
            )
          })}
        </div>
      )}
    </section>
  )
}
