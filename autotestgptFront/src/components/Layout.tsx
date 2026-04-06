import { Outlet, Link, useLocation } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { healthApi } from '../api'

const navItems = [
  { path: '/', label: '首页', icon: '📊' },
  { path: '/chat', label: '对话', icon: '💬' },
  { path: '/new', label: '新建测试', icon: '➕' },
  { path: '/requirements', label: '需求管理', icon: '📋' },
  { path: '/cases', label: '测试用例', icon: '🧪' },
  { path: '/executions', label: '执行记录', icon: '▶️' },
]

export default function Layout() {
  const location = useLocation()
  const [status, setStatus] = useState<string>('checking')

  useEffect(() => {
    healthApi.check()
      .then(res => setStatus(res.data.status === 'ok' ? 'healthy' : 'unhealthy'))
      .catch(() => setStatus('error'))
  }, [])

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center gap-8">
              <h1 className="text-xl font-bold text-indigo-600">AutoTestGPT</h1>
              <nav className="flex gap-1">
                {navItems.map(item => (
                  <Link
                    key={item.path}
                    to={item.path}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                      location.pathname === item.path
                        ? 'bg-indigo-100 text-indigo-700'
                        : 'text-gray-600 hover:bg-gray-100'
                    }`}
                  >
                    <span className="mr-2">{item.icon}</span>
                    {item.label}
                  </Link>
                ))}
              </nav>
            </div>
            <div className="flex items-center gap-4">
              <span className={`text-sm px-3 py-1 rounded-full ${
                status === 'healthy' ? 'bg-green-100 text-green-700' :
                status === 'error' ? 'bg-red-100 text-red-700' :
                'bg-yellow-100 text-yellow-700'
              }`}>
                {status === 'healthy' ? '● 服务正常' :
                 status === 'error' ? '● 服务异常' : '● 检测中...'}
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Outlet />
      </main>
    </div>
  )
}
