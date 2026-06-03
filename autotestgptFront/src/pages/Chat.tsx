import { useState, useEffect, useRef, useCallback } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ChatAgentContext, conversationsApi, Conversation, Message, SSEEvent } from '../api'

const C = {
  bg: 'var(--bg-card)',
  bgElevated: 'var(--bg-elevated)',
  bgSurface: 'var(--bg-surface)',
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

const AGENT_COLORS: Record<string, { color: string; bg: string; border: string; label: string }> = {
  user: { color: 'var(--accent-cyan)', bg: 'rgba(0,212,255,0.1)', border: 'rgba(0,212,255,0.2)', label: 'YOU' },
  router: { color: 'var(--text-muted)', bg: 'rgba(255,255,255,0.04)', border: 'rgba(255,255,255,0.06)', label: 'ASST' },
  req_agent: { color: '#38bdf8', bg: 'rgba(56,189,248,0.1)', border: 'rgba(56,189,248,0.15)', label: 'REQ' },
  case_agent: { color: 'var(--accent-emerald)', bg: 'rgba(0,255,136,0.1)', border: 'rgba(0,255,136,0.15)', label: 'CASE' },
  code_agent: { color: 'var(--accent-amber)', bg: 'rgba(255,176,32,0.1)', border: 'rgba(255,176,32,0.15)', label: 'CODE' },
  exec_agent: { color: 'var(--accent-violet)', bg: 'rgba(139,92,246,0.1)', border: 'rgba(139,92,246,0.15)', label: 'EXEC' },
}

const isVisibleMessage = (msg: Message) =>
  !msg.metadata?.hidden && !msg.content.startsWith('[系统提示]')

const PHASE_LABELS: Record<string, string> = {
  idle: '空闲', clarifying: '等待确认', parsing: '解析需求',
  designing_cases: '设计用例', generating_code: '生成脚本',
  executing: '执行测试', reviewing: '代码审查', completed: '完成',
}

export default function Chat() {
  const location = useLocation()
  const navigate = useNavigate()
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [currentConv, setCurrentConv] = useState<Conversation | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [agentContext, setAgentContext] = useState<ChatAgentContext | null>(null)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const [streamingAgent, setStreamingAgent] = useState('')
  const [currentPhase, setCurrentPhase] = useState('')
  const [toolCalls, setToolCalls] = useState<{ name: string; result?: any; active: boolean }[]>([])
  const [activeQuestion, setActiveQuestion] = useState<{ question: string; context: string } | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const initializedRef = useRef(false)
  const sendingRef = useRef(false)
  const lastSentRef = useRef('')
  const lastSentTimeRef = useRef(0)
  const contextPollRef = useRef<number | null>(null)
  const sseRef = useRef<EventSource | null>(null)

  const loadAgentContext = useCallback(async (convId: number) => {
    try {
      const r = await conversationsApi.getAgentContext(convId)
      setAgentContext(r.data)
    } catch {
      setAgentContext(null)
    }
  }, [])

  // SSE connection
  const connectSSE = useCallback((convId: number) => {
    if (sseRef.current) { sseRef.current.close(); sseRef.current = null }
    setStreamingContent(''); setStreamingAgent(''); setToolCalls([])
    setActiveQuestion(null); setCurrentPhase('')

    const es = new EventSource(conversationsApi.streamUrl(convId))
    sseRef.current = es

    es.onmessage = (event) => {
      try {
        const data: SSEEvent = JSON.parse(event.data)
        switch (data.type) {
          case 'heartbeat': break
          case 'message':
            if (data.chunk) {
              // Accumulate streaming tokens
              setStreamingContent(prev => prev + (data.content || ''))
              if (data.agent) setStreamingAgent(data.agent)
            } else if (data.complete) {
              // Flush accumulated streaming to a full message
              setStreamingContent('')
              setStreamingAgent('')
              // Reload messages to get the saved message with ID
              if (currentConv?.id) loadMessages(currentConv.id)
            }
            break
          case 'tool_call':
            setToolCalls(prev => [...prev, { name: data.name || '', active: true }])
            break
          case 'tool_result':
            setToolCalls(prev => prev.map(tc =>
              tc.name === data.name && tc.active ? { ...tc, result: data.result, active: false } : tc
            ))
            break
          case 'question':
            setActiveQuestion({ question: data.question || '', context: data.context || '' })
            setLoading(false)
            break
          case 'artifact':
            setToolCalls(prev => [...prev, {
              name: `artifact:${data.key || ''}`,
              result: data.data,
              active: false,
            }])
            break
          case 'phase_change':
            setCurrentPhase(data.to || '')
            break
          case 'error':
            console.error('SSE error event:', data.message)
            setLoading(false)
            break
          case 'done':
            setLoading(false)
            setStreamingContent('')
            // Reload full message list
            if (currentConv?.id) loadMessages(currentConv.id)
            break
        }
      } catch { /* ignore parse errors */ }
    }

    es.onerror = () => {
      // SSE connection lost — fall back to polling
      if (sseRef.current) { sseRef.current.close(); sseRef.current = null }
      if (convId && currentConv?.requirement_id) {
        contextPollRef.current = window.setInterval(() => loadAgentContext(convId), 5000)
      }
    }
  }, [currentConv?.id])

  const loadMessages = async (convId: number) => {
    try {
      const r = await conversationsApi.getMessages(convId)
      setMessages((r.data.items || []).filter(isVisibleMessage))
      await loadAgentContext(convId)
    } catch { /* ignore */ }
  }

  useEffect(() => {
    loadConversations()
    const convListTimer = window.setInterval(loadConversations, 8000)
    return () => {
      if (sseRef.current) sseRef.current.close()
      if (contextPollRef.current) clearInterval(contextPollRef.current)
      window.clearInterval(convListTimer)
    }
  }, [])

  useEffect(() => {
    const state = location.state as { conversationId?: number } | null
    if (state?.conversationId) {
      initializedRef.current = true
      selectConversation(state.conversationId)
      navigate(location.pathname, { replace: true, state: {} })
      return
    }
    if (conversations.length > 0 && !currentConv && !initializedRef.current) {
      initializedRef.current = true
      selectConversation(conversations[0].id)
    }
  }, [conversations, location.state])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingContent, toolCalls])

  const loadConversations = async () => {
    try {
      const r = await conversationsApi.list()
      setConversations(r.data.items)
      // 通知 Layout 刷新侧边栏总未读数
      const total = (r.data.items || []).reduce((sum, c) => sum + (c.unread_count || 0), 0)
      window.dispatchEvent(new CustomEvent('autotestgpt:chat-unread', { detail: { total } }))
    }
    catch { console.error('加载对话列表失败') }
  }

  const createConversation = async () => {
    setCreating(true)
    try {
      const r = await conversationsApi.create()
      const c = r.data.conversation
      setConversations(prev => [c, ...prev])
      selectConversation(c.id)
    } catch { console.error('创建对话失败') }
    finally { setCreating(false) }
  }

  const selectConversation = async (id: number) => {
    if (currentConv?.id === id) return
    if (contextPollRef.current) { clearInterval(contextPollRef.current); contextPollRef.current = null }
    try {
      const r = await conversationsApi.get(id)
      setCurrentConv(r.data)
      setMessages((r.data.messages || []).filter(isVisibleMessage))
      setAgentContext(r.data.agent_context || null)
      setStreamingContent(''); setStreamingAgent(''); setToolCalls([])
      setActiveQuestion(null); setCurrentPhase('')
      // 选中后清零侧栏未读
      setConversations(prev => {
        const next = prev.map(c => c.id === id ? { ...c, unread_count: 0 } : c)
        const total = next.reduce((sum, c) => sum + (c.unread_count || 0), 0)
        window.dispatchEvent(new CustomEvent('autotestgpt:chat-unread', { detail: { total } }))
        return next
      })
      // Connect SSE for real-time streaming
      connectSSE(id)
      // Fallback polling for agent context
      if (r.data.requirement_id) {
        contextPollRef.current = window.setInterval(() => loadAgentContext(id), 5000)
      }
    } catch { console.error('加载对话失败') }
  }

  const doSendMessage = async () => {
    const userInput = input.trim()
    if (!userInput || !currentConv) return
    const now = Date.now()
    if (lastSentRef.current === userInput && now - lastSentTimeRef.current < 500) return
    if (sendingRef.current) return
    sendingRef.current = true
    lastSentRef.current = userInput
    lastSentTimeRef.current = now
    setInput(''); setLoading(true)
    setActiveQuestion(null)

    // Add user message optimistically
    const tempUserMsg: Message = {
      id: Date.now(),
      conversation_id: currentConv.id,
      sender: 'user',
      content: userInput,
      created_at: new Date().toISOString(),
    }
    setMessages(prev => [...prev, tempUserMsg])

    try {
      const r = await conversationsApi.sendMessage(currentConv.id, userInput)
      if (r.data.started_from_chat && r.data.requirement_id) {
        const requirementId = r.data.requirement_id
        setCurrentConv(prev => prev ? {
          ...prev,
          requirement_id: requirementId,
          title: prev.title.startsWith('需求 #') ? prev.title : `需求 #${requirementId} · ${prev.title}`,
        } : prev)
        setConversations(prev => prev.map(conv => conv.id === currentConv.id ? {
          ...conv,
          requirement_id: requirementId,
          title: conv.title.startsWith('需求 #') ? conv.title : `需求 #${requirementId} · ${conv.title}`,
        } : conv))
        loadAgentContext(currentConv.id)
        if (!contextPollRef.current) {
          contextPollRef.current = window.setInterval(() => loadAgentContext(currentConv.id), 5000)
        }
      }
      if (r.data.orchestrator_mode) {
        // Orchestrator mode — events come via SSE, no need to reload messages now
        if (r.data.agent_context) setAgentContext(r.data.agent_context)
      } else if (r.data.messages) {
        // Legacy mode — update from response
        setMessages(r.data.messages.filter(isVisibleMessage))
        if (r.data.agent_context) setAgentContext(r.data.agent_context)
        setLoading(false)
      }
      lastSentRef.current = ''
    } catch { console.error('发送消息失败'); setLoading(false) }
    finally { sendingRef.current = false }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); doSendMessage() }
  }

  const deleteConversation = async (id: number, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm('确定要删除这个对话吗？')) return
    try {
      await conversationsApi.delete(id)
      setConversations(prev => prev.filter(c => c.id !== id))
      if (currentConv?.id === id) {
        setCurrentConv(null); setMessages([]); setAgentContext(null)
        setStreamingContent(''); setActiveQuestion(null)
        if (sseRef.current) { sseRef.current.close(); sseRef.current = null }
        if (contextPollRef.current) { clearInterval(contextPollRef.current); contextPollRef.current = null }
      }
    } catch { console.error('删除对话失败') }
  }

  const deduped = (() => {
    const seen = new Set<number>()
    return messages
      .filter(isVisibleMessage)
      .filter(m => { if (seen.has(m.id)) return false; seen.add(m.id); return true })
  })()

  return (
    <div className="animate-fade-in" style={{
      display: 'flex', height: 'calc(100vh - 8rem)', borderRadius: 24, overflow: 'hidden',
      border: '1px solid var(--border-subtle)', background: 'var(--bg-card)',
    }}>
      {/* Left sidebar - conversations */}
      <div style={{
        width: 300, background: 'linear-gradient(180deg, var(--bg-surface) 0%, var(--bg-root) 100%)',
        borderRight: '1px solid var(--border-subtle)', display: 'flex', flexDirection: 'column', flexShrink: 0,
      }}>
        <div style={{ padding: '20px 18px', borderBottom: '1px solid var(--border-subtle)' }}>
          <button onClick={createConversation} disabled={creating} style={{
            width: '100%', fontFamily: C.mono, fontSize: 12, fontWeight: 700,
            color: '#050810', background: 'linear-gradient(135deg, var(--accent-cyan), var(--accent-emerald))',
            padding: '14px 18px', borderRadius: 12, border: 'none', cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            transition: 'all 0.2s ease', opacity: creating ? 0.5 : 1,
          }}
            onMouseEnter={e => !creating && (e.currentTarget.style.transform = 'translateY(-1px)')}
            onMouseLeave={e => e.currentTarget.style.transform = 'translateY(0)'}>
            <span style={{ fontSize: 14 }}>+</span> {creating ? '创建中...' : '新建对话'}
          </button>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '12px 10px' }}>
          {!conversations.length ? (
            <div style={{ textAlign: 'center', padding: 40, fontFamily: C.mono, fontSize: 11, color: C.text3 }}>
              暂无对话
            </div>
          ) : (
            <div className="stagger-children">
              {conversations.map(conv => (
                <div key={conv.id} onClick={() => { setCurrentConv(conv); selectConversation(conv.id) }}
                  style={{
                    padding: '14px 16px', marginBottom: 4, borderRadius: 14, cursor: 'pointer',
                    background: currentConv?.id === conv.id ? 'rgba(0,212,255,0.06)' : 'transparent',
                    border: currentConv?.id === conv.id ? '1px solid rgba(0,212,255,0.15)' : '1px solid transparent',
                    transition: 'all 0.2s ease',
                  }}
                  onMouseEnter={e => {
                    if (currentConv?.id !== conv.id) {
                      e.currentTarget.style.background = 'rgba(255,255,255,0.03)'
                      e.currentTarget.style.borderColor = 'var(--border-default)'
                    }
                  }}
                  onMouseLeave={e => {
                    if (currentConv?.id !== conv.id) {
                      e.currentTarget.style.background = 'transparent'
                      e.currentTarget.style.borderColor = 'transparent'
                    }
                  }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{ flex: 1, minWidth: 0, fontFamily: C.display, fontSize: 13, fontWeight: 600, color: C.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {conv.title}
                        </div>
                        {conv.unread_count > 0 && (
                          <span
                            title={`${conv.unread_count} 条未读`}
                            style={{
                              flexShrink: 0, minWidth: 20, height: 20, padding: '0 6px',
                              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                              fontFamily: C.mono, fontSize: 10, fontWeight: 800, color: '#050810',
                              background: 'linear-gradient(135deg, var(--accent-cyan), var(--accent-emerald))',
                              borderRadius: 10, boxShadow: '0 0 8px rgba(0,212,255,0.4)',
                            }}
                          >
                            {conv.unread_count > 99 ? '99+' : conv.unread_count}
                          </span>
                        )}
                      </div>
                      <div style={{ fontFamily: C.mono, fontSize: 10, color: C.text3, marginTop: 4 }}>
                        {conv.message_count} msgs
                        {conv.requirement_id && ` · req#${conv.requirement_id}`}
                      </div>
                    </div>
                    <button onClick={(e) => deleteConversation(conv.id, e)}
                      style={{
                        fontFamily: C.mono, fontSize: 14, color: C.text3, background: 'none',
                        border: 'none', cursor: 'pointer', padding: 0, lineHeight: 1,
                        opacity: 0.6, transition: 'opacity 0.2s',
                      }}
                      onMouseEnter={e => (e.currentTarget.style.opacity = '1', e.currentTarget.style.color = 'var(--accent-magenta)')}
                      onMouseLeave={e => (e.currentTarget.style.opacity = '0.6', e.currentTarget.style.color = C.text3)}>
                      ×
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Agent context strip — summary only, not full event log */}
      {currentConv && (
        <div style={{
          width: 280, flexShrink: 0, borderRight: '1px solid var(--border-subtle)',
          background: 'var(--bg-elevated)', display: 'flex', flexDirection: 'column', overflow: 'hidden',
        }}>
          <div style={{ padding: '16px 14px', borderBottom: '1px solid var(--border-subtle)' }}>
            <div style={{ fontFamily: C.mono, fontSize: 10, letterSpacing: '0.12em', color: C.cyan, marginBottom: 8 }}>
              任务摘要
            </div>
            <p style={{ margin: 0, fontSize: 13, color: C.text, lineHeight: 1.5 }}>
              {agentContext?.headline || '未关联需求；可在需求详情页打开对话协作。'}
            </p>
            {agentContext?.stats && (
              <p style={{ margin: '10px 0 0', fontSize: 11, color: C.text3, fontFamily: C.mono }}>
                用例 {agentContext.stats.cases} · UI脚本 {agentContext.stats.ui_scripts} · 缺陷 {agentContext.stats.defects}
              </p>
            )}
            <Link
              to={agentContext?.workbench_path || '/workbench'}
              style={{
                display: 'inline-block', marginTop: 12, fontFamily: C.mono, fontSize: 11,
                color: C.violet, textDecoration: 'none',
              }}
            >
              查看 Agent 工作台 →
            </Link>
          </div>
          <div style={{ padding: '12px 14px', flex: 1, overflowY: 'auto' }}>
            <div style={{ fontFamily: C.mono, fontSize: 10, color: C.amber, marginBottom: 8 }}>人工介入 / 待确认</div>
            {!agentContext?.pending_questions?.length ? (
              <p style={{ margin: 0, fontSize: 12, color: C.text3 }}>暂无待确认问题</p>
            ) : (
              <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12, color: C.text2, lineHeight: 1.6 }}>
                {agentContext.pending_questions.map((q, idx) => (
                  <li key={q.id ?? idx} style={{ marginBottom: 8 }}>
                    <span style={{ color: C.cyan, fontFamily: C.mono, fontSize: 10 }}>{q.agent}</span>
                    <br />
                    {q.message}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {/* Right - chat area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: 'var(--bg-surface)' }}>
        {!currentConv ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{
                width: 80, height: 80, borderRadius: 20, margin: '0 auto 24px',
                background: 'linear-gradient(135deg, rgba(0,212,255,0.1), rgba(139,92,246,0.1))',
                border: '1px solid rgba(0,212,255,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <span style={{ fontFamily: C.mono, fontSize: 36, fontWeight: 800, color: 'var(--accent-cyan)' }}>&gt;_</span>
              </div>
              <div style={{ fontFamily: C.display, fontSize: 16, fontWeight: 600, color: C.text2, marginBottom: 8 }}>
                选择对话或新建对话开始
              </div>
              <div style={{ fontFamily: C.mono, fontSize: 11, color: C.text3 }}>
                新建对话后输入需求，Agent 会自动补齐信息并启动测试
              </div>
            </div>
          </div>
        ) : (
          <>
            {/* Chat header */}
            <div style={{
              padding: '16px 24px', borderBottom: '1px solid var(--border-subtle)',
              display: 'flex', alignItems: 'center', gap: 12,
              background: 'rgba(255,255,255,0.01)',
            }}>
              <div style={{
                width: 40, height: 40, borderRadius: 12, background: 'linear-gradient(135deg, var(--accent-cyan), var(--accent-violet))',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                boxShadow: '0 4px 16px rgba(0,212,255,0.2)',
              }}>
                <span style={{ fontFamily: C.mono, fontSize: 16, fontWeight: 800, color: '#fff' }}>◈</span>
              </div>
              <div>
                <div style={{ fontFamily: C.display, fontSize: 15, fontWeight: 700, color: C.text }}>
                  {currentConv.title}
                </div>
                <div style={{ fontFamily: C.mono, fontSize: 10, color: C.text3, marginTop: 2 }}>
                  {currentConv.message_count} messages · session active
                </div>
              </div>
            </div>

            {/* Messages */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '24px', display: 'flex', flexDirection: 'column', gap: 16 }}>
              {deduped.map((msg, idx) => {
                const agent = AGENT_COLORS[msg.sender] || AGENT_COLORS.router
                const isUser = msg.sender === 'user'
                return (
                  <div key={msg.id} className="animate-float-up" style={{
                    display: 'flex', flexDirection: isUser ? 'row-reverse' : 'row', gap: 12, alignItems: 'flex-start',
                    animationDelay: `${idx * 0.03}s`,
                  }}>
                    {/* Avatar */}
                    <div style={{
                      width: 40, height: 40, borderRadius: 12, flexShrink: 0, display: 'flex',
                      alignItems: 'center', justifyContent: 'center',
                      background: agent.bg, border: `1px solid ${agent.border}`,
                      boxShadow: isUser ? '0 4px 16px rgba(0,212,255,0.15)' : 'none',
                    }}>
                      <span style={{ fontFamily: C.mono, fontSize: 10, fontWeight: 800, color: agent.color, letterSpacing: '0.06em' }}>
                        {agent.label}
                      </span>
                    </div>

                    {/* Message bubble */}
                    <div style={{ maxWidth: '65%' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, ...(isUser ? { justifyContent: 'flex-end' } : {}) }}>
                        <span style={{ fontFamily: C.mono, fontSize: 10, fontWeight: 700, color: agent.color }}>{agent.label}</span>
                        <span style={{ fontFamily: C.mono, fontSize: 9, color: C.text3 }}>
                          {new Date(msg.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      </div>
                      <div style={{
                        padding: '14px 18px', borderRadius: isUser ? '16px 4px 16px 16px' : '4px 16px 16px 16px',
                        background: agent.bg, border: `1px solid ${agent.border}`,
                        ...(isUser ? { borderRight: `3px solid ${agent.color}` } : {}),
                      }}>
                        <pre style={{ margin: 0, fontFamily: C.mono, fontSize: 12, color: C.text, whiteSpace: 'pre-wrap', lineHeight: 1.7 }}>
                          {msg.content}
                        </pre>
                      </div>
                    </div>
                  </div>
                )
              })}

              {/* Phase indicator */}
              {currentPhase && (
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 10, padding: '8px 16px',
                  background: 'rgba(0,212,255,0.06)', borderRadius: 12,
                  border: '1px solid rgba(0,212,255,0.15)', alignSelf: 'center',
                }}>
                  <span style={{
                    width: 8, height: 8, borderRadius: '50%',
                    background: 'var(--accent-cyan)', animation: 'pulse 1.5s infinite',
                  }} />
                  <span style={{ fontFamily: C.mono, fontSize: 11, color: C.cyan }}>
                    当前阶段: {PHASE_LABELS[currentPhase] || currentPhase}
                  </span>
                </div>
              )}

              {/* Tool call cards */}
              {toolCalls.filter(tc => tc.active || tc.result).map((tc, idx) => (
                <div key={idx} style={{
                  display: 'flex', gap: 12, alignItems: 'flex-start',
                  padding: '10px 16px', borderRadius: 12,
                  background: 'rgba(255,176,32,0.06)', border: '1px solid rgba(255,176,32,0.15)',
                  alignSelf: 'center', maxWidth: '80%',
                }}>
                  <span style={{ fontFamily: C.mono, fontSize: 11, color: C.amber, fontWeight: 700 }}>
                    {tc.active ? '⚙ 执行工具' : '✓ 工具完成'}
                  </span>
                  <span style={{ fontFamily: C.mono, fontSize: 11, color: C.text2 }}>{tc.name}</span>
                  {tc.result && (
                    <span style={{ fontFamily: C.mono, fontSize: 10, color: C.text3 }}>
                      ({typeof tc.result === 'object'
                        ? (tc.result as any)?.length !== undefined
                          ? (tc.result as any).length + ' 条结果'
                          : '完成'
                        : tc.result})
                    </span>
                  )}
                </div>
              ))}

              {/* Active question card */}
              {activeQuestion && (
                <div style={{
                  padding: '16px 20px', borderRadius: 16,
                  background: 'rgba(139,92,246,0.08)', border: '2px solid rgba(139,92,246,0.3)',
                  alignSelf: 'center', maxWidth: '85%',
                }}>
                  <div style={{ fontFamily: C.mono, fontSize: 10, color: C.violet, marginBottom: 8 }}>
                    ⏳ Agent 需要你的确认
                  </div>
                  <div style={{ fontFamily: C.body, fontSize: 13, color: C.text, lineHeight: 1.6 }}>
                    {activeQuestion.question}
                  </div>
                  {activeQuestion.context && (
                    <div style={{ fontFamily: C.mono, fontSize: 10, color: C.text3, marginTop: 6 }}>
                      {activeQuestion.context}
                    </div>
                  )}
                </div>
              )}

              {/* Streaming message */}
              {streamingContent && (
                <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                  <div style={{
                    width: 40, height: 40, borderRadius: 12, flexShrink: 0,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    background: 'rgba(56,189,248,0.1)', border: '1px solid rgba(56,189,248,0.15)',
                  }}>
                    <span style={{ fontFamily: C.mono, fontSize: 10, fontWeight: 800, color: '#38bdf8' }}>
                      {streamingAgent ? streamingAgent.replace('_agent', '').toUpperCase().slice(0, 4) : 'AI'}
                    </span>
                  </div>
                  <div style={{ maxWidth: '65%' }}>
                    <div style={{
                      padding: '14px 18px', borderRadius: '4px 16px 16px 16px',
                      background: 'rgba(56,189,248,0.06)', border: '1px solid rgba(56,189,248,0.12)',
                    }}>
                      <pre style={{ margin: 0, fontFamily: C.mono, fontSize: 12, color: C.text,
                        whiteSpace: 'pre-wrap', lineHeight: 1.7 }}>
                        {streamingContent}
                        <span className="cursor-blink" style={{
                          display: 'inline-block', width: 8, height: 16,
                          background: 'var(--accent-cyan)', marginLeft: 2, verticalAlign: 'middle',
                        }} />
                      </pre>
                    </div>
                  </div>
                </div>
              )}

              {/* Loading indicator */}
              {loading && !streamingContent && (
                <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                  <div style={{
                    width: 40, height: 40, borderRadius: 12, background: 'rgba(139,92,246,0.1)',
                    border: '1px solid rgba(139,92,246,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <span style={{ fontFamily: C.mono, fontSize: 10, fontWeight: 800, color: 'var(--accent-violet)' }}>...</span>
                  </div>
                  <div style={{ display: 'flex', gap: 5 }}>
                    {[0, 1, 2].map(i => (
                      <span key={i} className="status-dot checking" style={{
                        width: 8, height: 8, background: 'var(--accent-violet)',
                        animationDelay: `${i * 0.15}s`,
                      }} />
                    ))}
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input area */}
            <div style={{
              padding: '20px 24px', borderTop: '1px solid var(--border-subtle)',
              background: 'rgba(0,0,0,0.2)',
            }}>
              <div style={{
                display: 'flex', gap: 12, alignItems: 'flex-end',
                background: 'var(--bg-card)', border: '1px solid var(--border-subtle)',
                borderRadius: 16, padding: '4px 4px 4px 16px',
              }}>
                <textarea
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="请输入消息..."
                  disabled={loading || sendingRef.current}
                  rows={1}
                  style={{
                    flex: 1, padding: '12px 0', background: 'transparent', border: 'none',
                    color: C.text, fontFamily: C.mono, fontSize: 13, resize: 'none', outline: 'none',
                    opacity: (loading || sendingRef.current) ? 0.5 : 1,
                  }}
                />
                <button type="button" onClick={doSendMessage} disabled={loading || sendingRef.current} style={{
                  fontFamily: C.mono, fontSize: 12, fontWeight: 700, color: '#050810',
                  background: 'linear-gradient(135deg, var(--accent-cyan), var(--accent-emerald))',
                  padding: '12px 20px', borderRadius: 12, border: 'none', cursor: 'pointer',
                  transition: 'all 0.2s ease', opacity: (loading || sendingRef.current) ? 0.5 : 1,
                }}
                  onMouseEnter={e => !(loading || sendingRef.current) && (e.currentTarget.style.transform = 'translateY(-1px)')}
                  onMouseLeave={e => e.currentTarget.style.transform = 'translateY(0)'}>
                  发送
                </button>
              </div>

              <p style={{ margin: '12px 0 0', fontSize: 11, color: C.text3, paddingLeft: 4 }}>
                输入需求后，Agent 会自动补齐信息并启动测试；完整事件与产物请在工作台查看。
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
