import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { requirementsApi, casesApi, executionsApi, HealthStatus } from '../api'
import { healthApi } from '../api'

interface Stats {
  requirements: number
  cases: number
  executions: number
  passRate: number
}

export default function Dashboard() {
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [stats, setStats] = useState<Stats>({ requirements: 0, cases: 0, executions: 0, passRate: 0 })
  const [recentRequirements, setRecentRequirements] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      healthApi.check(),
      requirementsApi.list(),
      casesApi.list(),
      executionsApi.list()
    ]).then(([healthRes, reqRes, casesRes, execRes]) => {
      setHealth(healthRes.data)
      setRecentRequirements((reqRes.data.items || []).slice(0, 5))

      const executions = execRes.data.items || []
      const passed = executions.filter((e: any) => e.status === 'passed').length
      setStats({
        requirements: reqRes.data.total || 0,
        cases: casesRes.data.total || 0,
        executions: execRes.data.total || 0,
        passRate: executions.length > 0 ? Math.round((passed / executions.length) * 100) : 0
      })
    }).catch(err => {
      console.error('Failed to load dashboard:', err)
    }).finally(() => {
      setLoading(false)
    })
  }, [])

  if (loading) {
    return <div className="flex items-center justify-center h-64">
      <div className="text-gray-500">加载中...</div>
    </div>
  }
  return (
    <div>
      <h2 className="text-2xl font-bold text-gray-900 mb-6">概览</h2>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <StatCard label="需求总数" value={stats.requirements} icon="📋" color="indigo" />
        <StatCard label="测试用例" value={stats.cases} icon="🧪" color="green" />
        <StatCard label="执行次数" value={stats.executions} icon="▶️" color="blue" />
        <StatCard label="通过率" value={`${stats.passRate}%`} icon="✅" color="emerald" />
      </div>

      {/* System Status */}
      <div className="bg-white rounded-lg shadow p-6 mb-8">
        <h3 className="text-lg font-semibold mb-4">系统状态</h3>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <span className="text-gray-500">后端服务: </span>
            <span className={health?.status === 'ok' ? 'text-green-600' : 'text-red-600'}>
              {health?.status === 'ok' ? '正常' : '异常'}
            </span>
          </div>
          <div>
            <span className="text-gray-500">数据库: </span>
            <span className={health?.database === 'healthy' ? 'text-green-600' : 'text-red-600'}>
              {health?.database || '未知'}
            </span>
          </div>
          <div>
            <span className="text-gray-500">版本: </span>
            <span className="text-gray-900">{health?.version || '未知'}</span>
          </div>
        </div>
      </div>

      {/* Recent Requirements */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center">
          <h3 className="text-lg font-semibold">最近需求</h3>
          <Link to="/requirements" className="text-indigo-600 hover:text-indigo-800 text-sm">
            查看全部 →
          </Link>
        </div>
        <div className="divide-y divide-gray-200">
          {recentRequirements.length === 0 ? (
            <div className="px-6 py-8 text-center text-gray-500">
              暂无需求，<Link to="/new" className="text-indigo-600">创建第一个测试</Link>
            </div>
          ) : (
            recentRequirements.map(req => (
              <Link key={req.id} to={`/requirements/${req.id}`} className="block px-6 py-4 hover:bg-gray-50">
                <div className="flex justify-between items-start">
                  <div>
                    <h4 className="font-medium text-gray-900">{req.title}</h4>
                    <p className="text-sm text-gray-500 mt-1">{req.description}</p>
                  </div>
                  <StatusBadge status={req.status} />
                </div>
                <div className="text-xs text-gray-400 mt-2">
                  创建于 {new Date(req.created_at).toLocaleString('zh-CN')}
                  · {req.test_case_count} 个用例
                </div>
              </Link>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

function StatCard({ label, value, icon, color }: {
  label: string
  value: number | string
  icon: string
  color: string
}) {
  const colorClasses: Record<string, string> = {
    indigo: 'bg-indigo-50 text-indigo-600',
    green: 'bg-green-50 text-green-600',
    blue: 'bg-blue-50 text-blue-600',
    emerald: 'bg-emerald-50 text-emerald-600'
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center gap-4">
        <div className={`text-3xl ${colorClasses[color].split(' ')[0]} bg-indigo-50 rounded-lg w-14 h-14 flex items-center justify-center`}>
          {icon}
        </div>
        <div>
          <div className="text-sm text-gray-500">{label}</div>
          <div className="text-2xl font-bold text-gray-900">{value}</div>
        </div>
      </div>
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const statusMap: Record<string, { bg: string, text: string, label: string }> = {
    pending: { bg: 'bg-yellow-100', text: 'text-yellow-800', label: '待处理' },
    parsed: { bg: 'bg-blue-100', text: 'text-blue-800', label: '已解析' },
    completed: { bg: 'bg-green-100', text: 'text-green-800', label: '已完成' },
    executed: { bg: 'bg-purple-100', text: 'text-purple-800', label: '已执行' },
    error: { bg: 'bg-red-100', text: 'text-red-800', label: '错误' }
  }

  const s = statusMap[status] || statusMap.pending

  return (
    <span className={`px-2 py-1 rounded-full text-xs font-medium ${s.bg} ${s.text}`}>
      {s.label}
    </span>
  )
}
