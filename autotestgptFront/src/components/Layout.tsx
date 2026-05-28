import { Outlet, Link, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { healthApi } from '../api'

const NAV_ITEMS = [
  { path: '/', label: '总览', icon: '◈', accent: 'cyan' },
  { path: '/new', label: '需求工作台', icon: '◆', accent: 'violet' },
  { path: '/requirements', label: '需求列表', icon: '◉', accent: 'cyan' },
  { path: '/cases', label: '测试用例', icon: '◇', accent: 'emerald' },
  { path: '/executions', label: '执行记录', icon: '○', accent: 'amber' },
  { path: '/reviews', label: '代码 Review', icon: '⬡', accent: 'violet' },
  { path: '/knowledge-bases', label: '知识库', icon: '◫', accent: 'magenta' },
  { path: '/chat', label: '对话协作', icon: '◐', accent: 'cyan' },
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

  const closeMobileNav = () => setMobileOpen(false)

  useEffect(() => {
    healthApi.check()
      .then(res => setStatus(res.data.status === 'ok' ? 'healthy' : 'error'))
      .catch(() => setStatus('error'))
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

  const toggleTheme = () => setTheme(prev => prev === 'dark' ? 'light' : 'dark')

  return (
    <div className="app-shell">
      <aside className={`app-sidebar ${mobileOpen ? 'mobile-open' : ''}`}>
        {/* Logo */}
        <div style={{
          padding: '24px 20px 20px', borderBottom: '1px solid var(--border-subtle)',
          background: 'linear-gradient(135deg, rgba(0,212,255,0.04) 0%, transparent 100%)',
        }}>
          {/* Logo mark */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 10, background: 'linear-gradient(135deg, var(--accent-cyan), var(--accent-violet))',
              display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 4px 20px rgba(0,212,255,0.25)',
            }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 15, fontWeight: 800, color: '#fff' }}>A</span>
            </div>
            <div>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '-0.01em' }}>
                AutoTestGPT
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, fontWeight: 600, color: 'var(--accent-cyan)', letterSpacing: '0.18em', textTransform: 'uppercase' }}>
                multi_agent studio
              </div>
            </div>
          </div>

          {/* System status */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px',
            background: 'rgba(255,255,255,0.02)', borderRadius: 8, border: '1px solid var(--border-subtle)',
          }}>
            <StatusIndicator status={status} />
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 600, color: 'var(--text-secondary)', letterSpacing: '0.1em' }}>
              {status === 'healthy' ? 'SYSTEM ONLINE' : status === 'error' ? 'SYSTEM ERROR' : 'CHECKING...'}
            </span>
          </div>
        </div>

        {/* Navigation */}
        <nav style={{ flex: 1, padding: '14px 12px', display: 'flex', flexDirection: 'column', gap: 2 }}>
          {NAV_ITEMS.map((item, idx) => {
            const active = loc.pathname === item.path ||
              (item.path !== '/' && loc.pathname.startsWith(item.path))
            const accentColor = `var(--accent-${item.accent})`

            return (
              <Link
                key={item.path}
                to={item.path}
                onClick={closeMobileNav}
                className="animate-float-up"
                style={{
                  display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px',
                  borderRadius: 10, textDecoration: 'none', position: 'relative', overflow: 'hidden',
                  fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: active ? 600 : 500,
                  color: active ? accentColor : 'var(--text-secondary)',
                  background: active ? `rgba(0,0,0,0.15)` : 'transparent',
                  border: active ? '1px solid rgba(255,255,255,0.06)' : '1px solid transparent',
                  transition: 'all 0.2s ease',
                  animationDelay: `${idx * 0.03}s`,
                  whiteSpace: 'nowrap',
                }}
                onMouseEnter={e => {
                  if (!active) {
                    e.currentTarget.style.color = 'var(--text-primary)'
                    e.currentTarget.style.background = 'rgba(255,255,255,0.03)'
                  }
                }}
                onMouseLeave={e => {
                  if (!active) {
                    e.currentTarget.style.color = 'var(--text-secondary)'
                    e.currentTarget.style.background = 'transparent'
                  }
                }}
              >
                {/* Active indicator bar */}
                {active && (
                  <div style={{
                    position: 'absolute', left: 0, top: '50%', transform: 'translateY(-50%)',
                    width: 3, height: '55%', borderRadius: '0 3px 3px 0',
                    background: `linear-gradient(180deg, ${accentColor}, transparent)`,
                    boxShadow: `0 0 10px ${accentColor}`,
                  }} />
                )}
                <span style={{ fontSize: 14, width: 18, textAlign: 'center', opacity: active ? 1 : 0.5 }}>{item.icon}</span>
                <span>{item.label}</span>
                {active && (
                  <div style={{
                    marginLeft: 'auto', width: 6, height: 6, borderRadius: '50%',
                    background: accentColor, boxShadow: `0 0 8px ${accentColor}`,
                  }} />
                )}
              </Link>
            )
          })}
        </nav>

        {/* Bottom section */}
        <div style={{ padding: '14px 12px', borderTop: '1px solid var(--border-subtle)' }}>
          <button type="button" className="theme-toggle" onClick={toggleTheme} style={{ marginBottom: 10 }}>
            {theme === 'dark' ? '切换浅色模式' : '切换深色模式'}
          </button>
          <div style={{
            padding: '12px 14px', background: 'rgba(139,92,246,0.06)', borderRadius: 12,
            border: '1px solid rgba(139,92,246,0.15)',
          }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--accent-violet)', letterSpacing: '0.12em', marginBottom: 6 }}>
              AGENTS ACTIVE
            </div>
            <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
              {['REQ', 'CASE', 'CODE', 'EXEC'].map(agent => (
                <span key={agent} style={{
                  fontFamily: 'var(--font-mono)', fontSize: 9, fontWeight: 700, letterSpacing: '0.08em',
                  color: 'var(--accent-violet)', background: 'rgba(139,92,246,0.12)',
                  padding: '2px 7px', borderRadius: 5,
                }}>{agent}</span>
              ))}
            </div>
          </div>
        </div>
      </aside>

      <div className="app-main">
        <header className="mobile-header">
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 800, color: 'var(--accent-cyan)' }}>
            AutoTestGPT
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" onClick={toggleTheme} style={{
              background: 'rgba(255,255,255,0.06)', border: '1px solid var(--border-default)',
              borderRadius: 8, color: 'var(--text-primary)', padding: '6px 10px',
              fontFamily: 'var(--font-mono)', fontSize: 11, cursor: 'pointer',
            }}>
              {theme === 'dark' ? '浅色' : '深色'}
            </button>
            <button onClick={() => setMobileOpen(!mobileOpen)} style={{
              background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border-default)',
              borderRadius: 8, color: 'var(--text-secondary)', padding: '6px 12px',
              fontFamily: 'var(--font-mono)', fontSize: 12, cursor: 'pointer',
            }}>
              {mobileOpen ? '✕' : '☰'}
            </button>
          </div>
        </header>

        {mobileOpen && <div className="mobile-overlay" onClick={closeMobileNav} />}

        <main style={{ padding: '32px 28px', maxWidth: 1400, margin: '0 auto' }}>
          <Outlet />
        </main>
      </div>
    </div>
  )
}