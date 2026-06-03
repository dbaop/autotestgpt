import { Outlet, Link, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { healthApi } from '../api'

const NAV_ITEMS = [
  { path: '/', label: '总览', icon: '01', accent: 'cyan' },
  { path: '/new', label: '需求工作台', icon: '+', accent: 'violet' },
  { path: '/workbench', label: 'Agent 工作台', icon: 'WB', accent: 'violet' },
  { path: '/requirements', label: '需求列表', icon: 'RQ', accent: 'cyan' },
  { path: '/cases', label: '测试用例', icon: 'TC', accent: 'emerald' },
  { path: '/executions', label: '执行记录', icon: 'EX', accent: 'amber' },
  { path: '/reviews', label: '代码 Review', icon: '<>', accent: 'violet' },
  { path: '/knowledge-bases', label: '知识库', icon: 'KB', accent: 'magenta' },
  { path: '/chat', label: '对话协作', icon: 'AI', accent: 'cyan' },
  { path: '/settings', label: 'Agent 配置', icon: '⚙', accent: 'amber' },
]

function StatusIndicator({ status }: { status: string }) {
  const map: Record<string, string> = {
    healthy: 'online',
    error: 'error',
    checking: 'checking',
    unhealthy: 'warning',
  }
  return <span className={`status-dot ${map[status] || 'checking'}`} />
}

export default function Layout() {
  const loc = useLocation()
  const [status, setStatus] = useState<string>('checking')
  const [mobileOpen, setMobileOpen] = useState(false)
  const [theme, setTheme] = useState<'dark' | 'light'>('dark')
  const [chatUnread, setChatUnread] = useState(0)

  useEffect(() => {
    healthApi.check()
      .then(res => setStatus(res.data.status === 'ok' ? 'healthy' : 'error'))
      .catch(() => setStatus('error'))
  }, [])

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as { total?: number } | undefined
      if (detail && typeof detail.total === 'number') setChatUnread(detail.total)
    }
    window.addEventListener('autotestgpt:chat-unread', handler)
    return () => window.removeEventListener('autotestgpt:chat-unread', handler)
  }, [])

  useEffect(() => {
    const saved = window.localStorage.getItem('autotestgpt-theme')
    if (saved === 'dark' || saved === 'light') {
      setTheme(saved)
      return
    }
    const prefersLight = window.matchMedia('(prefers-color-scheme: light)').matches
    setTheme(prefersLight ? 'light' : 'dark')
  }, [])

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    window.localStorage.setItem('autotestgpt-theme', theme)
  }, [theme])

  useEffect(() => {
    setMobileOpen(false)
  }, [loc.pathname])

  const toggleTheme = () => setTheme(prev => prev === 'dark' ? 'light' : 'dark')
  const statusText = status === 'healthy' ? '系统在线' : status === 'error' ? '连接异常' : '检查中'
  const themeText = theme === 'dark' ? '明亮模式' : '深色模式'

  return (
    <div className="app-shell">
      <aside className={`app-sidebar ${mobileOpen ? 'mobile-open' : ''}`} aria-label="主导航">
        <div className="brand-panel">
          <div className="brand-row">
            <div className="brand-mark" aria-hidden="true">A</div>
            <div>
              <h1 className="brand-title">AutoTestGPT</h1>
              <div className="brand-subtitle">quality agent studio</div>
            </div>
          </div>

          <div className="status-pill">
            <StatusIndicator status={status} />
            <span>{statusText}</span>
          </div>
        </div>

        <nav className="nav-list">
          {NAV_ITEMS.map((item, idx) => {
            const active = loc.pathname === item.path ||
              (item.path !== '/' && loc.pathname.startsWith(item.path))
            const showUnread = item.path === '/chat' && chatUnread > 0

            return (
              <Link
                key={item.path}
                to={item.path}
                aria-current={active ? 'page' : undefined}
                className={`nav-link accent-${item.accent} ${active ? 'active' : ''} animate-float-up`}
                style={{ animationDelay: `${idx * 0.025}s` }}
              >
                <span className="nav-icon" aria-hidden="true">{item.icon}</span>
                <span className="nav-text">{item.label}</span>
                {showUnread && (
                  <span
                    aria-label={`${chatUnread} 条未读`}
                    style={{
                      marginLeft: 'auto', minWidth: 20, height: 20, padding: '0 6px',
                      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                      fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 800, color: '#050810',
                      background: 'linear-gradient(135deg, var(--accent-cyan), var(--accent-emerald))',
                      borderRadius: 10, boxShadow: '0 0 8px rgba(0,212,255,0.4)',
                    }}
                  >
                    {chatUnread > 99 ? '99+' : chatUnread}
                  </span>
                )}
                {active && <span className="nav-current" aria-hidden="true" />}
              </Link>
            )
          })}
        </nav>

        <div className="sidebar-footer">
          <button type="button" className="theme-toggle" onClick={toggleTheme} aria-label="切换主题">
            <span>{themeText}</span>
            <span aria-hidden="true">{theme === 'dark' ? 'LT' : 'DK'}</span>
          </button>

          <div className="agent-strip">
            <div className="agent-strip-title">agents active</div>
            <div className="agent-strip-list">
              {['REQ', 'CASE', 'CODE', 'EXEC'].map(agent => (
                <span key={agent} className="agent-token">{agent}</span>
              ))}
            </div>
          </div>
        </div>
      </aside>

      <div className="app-main">
        <header className="mobile-header">
          <div className="mobile-title">AutoTestGPT</div>
          <div className="mobile-actions">
            <button type="button" className="icon-button" onClick={toggleTheme} aria-label="切换主题">
              <span aria-hidden="true">{theme === 'dark' ? 'LT' : 'DK'}</span>
            </button>
            <button
              type="button"
              className="icon-button"
              onClick={() => setMobileOpen(prev => !prev)}
              aria-label={mobileOpen ? '关闭导航' : '打开导航'}
              aria-expanded={mobileOpen}
            >
              <span aria-hidden="true">{mobileOpen ? 'X' : '='}</span>
            </button>
          </div>
        </header>

        {mobileOpen && <div className="mobile-overlay" onClick={() => setMobileOpen(false)} />}

        <main className="content-frame">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
