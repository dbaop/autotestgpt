import { useState, useEffect, useRef } from 'react'
import { conversationsApi, Conversation, Message } from '../api'

const AGENT_INFO: Record<string, { name: string; avatar: string; color: string }> = {
  user: { name: '我', avatar: '👤', color: 'bg-indigo-100' },
  router: { name: '助手', avatar: '🤖', color: 'bg-gray-100' },
  req_agent: { name: '小Req', avatar: '📋', color: 'bg-blue-100' },
  case_agent: { name: '小Case', avatar: '🧪', color: 'bg-green-100' },
  code_agent: { name: '小Code', avatar: '💻', color: 'bg-orange-100' },
  exec_agent: { name: '小Exec', avatar: '📊', color: 'bg-purple-100' }
}

export default function Chat() {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [currentConv, setCurrentConv] = useState<Conversation | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const pollingRef = useRef<number | null>(null)
  const initializedRef = useRef(false)

  // 加载对话列表
  useEffect(() => {
    loadConversations()
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current)
    }
  }, [])

  // 自动选择第一个对话
  useEffect(() => {
    if (conversations.length > 0 && !currentConv && !initializedRef.current) {
      initializedRef.current = true
      selectConversation(conversations[0].id)
    }
  }, [conversations])

  // 加载消息后滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const loadConversations = async () => {
    try {
      const res = await conversationsApi.list()
      setConversations(res.data.items)
    } catch (err) {
      console.error('加载对话列表失败:', err)
    }
  }

  const createConversation = async () => {
    setCreating(true)
    try {
      const res = await conversationsApi.create()
      const newConv = res.data.conversation
      setConversations(prev => [newConv, ...prev])
      selectConversation(newConv.id)
    } catch (err) {
      console.error('创建对话失败:', err)
    } finally {
      setCreating(false)
    }
  }

  const selectConversation = async (id: number) => {
    if (currentConv?.id === id) return
    try {
      const res = await conversationsApi.get(id)
      setCurrentConv(res.data)
      setMessages(res.data.messages || [])
      startPolling(id)
    } catch (err) {
      console.error('加载对话失败:', err)
    }
  }

  const startPolling = (_id: number) => {
    // 暂时禁用轮询，只依赖 sendMessage 返回更新
  }

  const sendingRef = useRef(false)
  const lastSentRef = useRef('')
  const lastSentTimeRef = useRef(0)

  const doSendMessage = async () => {
    const userInput = input.trim()
    if (!userInput || !currentConv) return

    // 500ms 内相同内容不重复发送
    const now = Date.now()
    if (lastSentRef.current === userInput && now - lastSentTimeRef.current < 500) {
      console.log('=== blocked by same message within 500ms ===')
      return
    }

    // 先锁定，防止重复调用
    if (sendingRef.current) {
      console.log('=== blocked by sendingRef ===')
      return
    }
    sendingRef.current = true
    lastSentRef.current = userInput
    lastSentTimeRef.current = now
    setInput('')
    setLoading(true)

    try {
      const res = await conversationsApi.sendMessage(currentConv.id, userInput)
      setMessages(res.data.messages || [])
      lastSentRef.current = ''
    } catch (err) {
      console.error('发送消息失败:', err)
    } finally {
      sendingRef.current = false
      setLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      doSendMessage()
    }
  }

  const deleteConversation = async (id: number, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm('确定要删除这个对话吗？')) return

    try {
      await conversationsApi.delete(id)
      setConversations(prev => prev.filter(c => c.id !== id))
      if (currentConv?.id === id) {
        setCurrentConv(null)
        setMessages([])
      }
    } catch (err) {
      console.error('删除对话失败:', err)
    }
  }

  return (
    <div className="flex h-[calc(100vh-8rem)]">
      {/* 左侧对话列表 */}
      <div className="w-80 bg-white border-r border-gray-200 flex flex-col">
        <div className="p-4 border-b border-gray-200">
          <button
            onClick={createConversation}
            disabled={creating}
            className="w-full px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
          >
            {creating ? '创建中...' : '+ 新建对话'}
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {conversations.length === 0 ? (
            <div className="p-4 text-center text-gray-500">
              暂无对话<br />
              <button onClick={createConversation} className="text-indigo-600 hover:text-indigo-800">
                创建第一个对话
              </button>
            </div>
          ) : (
            conversations.map(conv => (
              <div
                key={conv.id}
                onClick={() => {
                  setCurrentConv(conv)
                  selectConversation(conv.id)
                }}
                className={`p-4 border-b border-gray-100 cursor-pointer hover:bg-gray-50 ${
                  currentConv?.id === conv.id ? 'bg-indigo-50' : ''
                }`}
              >
                <div className="flex justify-between items-start">
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-gray-900 truncate">{conv.title}</div>
                    <div className="text-xs text-gray-500 mt-1">
                      {conv.message_count} 条消息
                    </div>
                  </div>
                  <button
                    onClick={(e) => deleteConversation(conv.id, e)}
                    className="text-gray-400 hover:text-red-500 ml-2"
                  >
                    ×
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* 右侧聊天区域 */}
      <div className="flex-1 flex flex-col bg-gray-50">
        {!currentConv ? (
          <div className="flex-1 flex items-center justify-center text-gray-500">
            <div className="text-center">
              <div className="text-4xl mb-4">🤖</div>
              <div>选择一个对话或新建对话开始聊天</div>
            </div>
          </div>
        ) : (
          <>
            {/* 消息列表 */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {(() => {
                // 基于 ID 去重渲染
                const seen = new Set<number>()
                return messages.filter(msg => {
                  if (seen.has(msg.id)) return false
                  seen.add(msg.id)
                  return true
                }).map(msg => {
                const agent = AGENT_INFO[msg.sender] || AGENT_INFO.router
                return (
                  <div key={msg.id} className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`flex gap-3 max-w-[70%] ${msg.sender === 'user' ? 'flex-row-reverse' : ''}`}>
                      <div className={`w-10 h-10 rounded-full flex items-center justify-center text-xl ${agent.color}`}>
                        {agent.avatar}
                      </div>
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-sm font-medium text-gray-700">{agent.name}</span>
                          <span className="text-xs text-gray-400">
                            {new Date(msg.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
                          </span>
                        </div>
                        <div className={`rounded-2xl px-4 py-2 ${
                          msg.sender === 'user'
                            ? 'bg-indigo-600 text-white'
                            : 'bg-white shadow-sm border border-gray-200'
                        }`}>
                          <pre className="whitespace-pre-wrap text-sm font-sans">{msg.content}</pre>
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })
              })()}
              {loading && (
                <div className="flex justify-start">
                  <div className="flex gap-3">
                    <div className="w-10 h-10 rounded-full flex items-center justify-center text-xl bg-gray-100">
                      🤖
                    </div>
                    <div className="bg-white shadow-sm border border-gray-200 rounded-2xl px-4 py-3">
                      <div className="flex gap-1">
                        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                      </div>
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* 输入框 */}
            <div className="p-4 bg-white border-t border-gray-200">
              <div className="flex gap-3">
                <textarea
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="输入消息，Enter 发送..."
                  disabled={loading || sendingRef.current}
                  className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 resize-none disabled:opacity-50"
                  rows={2}
                />
                <button
                  type="button"
                  onClick={doSendMessage}
                  disabled={loading || sendingRef.current}
                  className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
                >
                  发送
                </button>
              </div>
              <div className="mt-2 text-xs text-gray-400">
                <span className="mr-4">🤖 小Req - 需求分析</span>
                <span className="mr-4">🧪 小Case - 用例设计</span>
                <span className="mr-4">💻 小Code - 代码生成</span>
                <span>📊 小Exec - 执行报告</span>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
