import { useState, useEffect } from 'react'
import { executionsApi, ExecutionRecord } from '../api'

export default function Executions() {
  const [executions, setExecutions] = useState<ExecutionRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<string>('all')

  useEffect(() => {
    executionsApi.list()
      .then(res => setExecutions(res.data.items || []))
      .catch(err => console.error('Failed to load executions:', err))
      .finally(() => setLoading(false))
  }, [])

  const filteredExecutions = filter === 'all'
    ? executions
    : executions.filter(e => e.status === filter)

  const stats = {
    total: executions.length,
    passed: executions.filter(e => e.status === 'passed').length,
    failed: executions.filter(e => e.status === 'failed').length,
    error: executions.filter(e => e.status === 'error').length
  }

  if (loading) {
    return <div className="text-center py-8 text-gray-500">加载中...</div>
  }

  return (
    <div>
      <h2 className="text-2xl font-bold text-gray-900 mb-6">执行记录</h2>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <StatCard label="总执行" value={stats.total} color="gray" />
        <StatCard label="通过" value={stats.passed} color="green" />
        <StatCard label="失败" value={stats.failed} color="red" />
        <StatCard label="错误" value={stats.error} color="orange" />
      </div>

      {/* Filter */}
      <div className="flex gap-2 mb-6">
        {['all', 'passed', 'failed', 'error'].map(status => (
          <button
            key={status}
            onClick={() => setFilter(status)}
            className={`px-3 py-1.5 rounded-full text-sm ${
              filter === status
                ? 'bg-indigo-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            {status === 'all' ? '全部' :
             status === 'passed' ? '通过' :
             status === 'failed' ? '失败' : '错误'}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        {filteredExecutions.length === 0 ? (
          <div className="p-8 text-center text-gray-500">暂无执行记录</div>
        ) : (
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  ID
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  状态
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  执行时间
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  开始时间
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  错误信息
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {filteredExecutions.map(exec => (
                <tr key={exec.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 text-gray-900 font-medium">
                    #{exec.id}
                  </td>
                  <td className="px-6 py-4">
                    <StatusBadge status={exec.status} />
                  </td>
                  <td className="px-6 py-4 text-gray-500">
                    {exec.execution_time ? `${exec.execution_time.toFixed(2)}s` : '-'}
                  </td>
                  <td className="px-6 py-4 text-gray-500 text-sm">
                    {new Date(exec.started_at).toLocaleString('zh-CN')}
                  </td>
                  <td className="px-6 py-4 text-red-500 text-sm max-w-md truncate">
                    {exec.error_message || '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  const colorMap: Record<string, string> = {
    gray: 'bg-gray-100 text-gray-800',
    green: 'bg-green-100 text-green-800',
    red: 'bg-red-100 text-red-800',
    orange: 'bg-orange-100 text-orange-800'
  }

  return (
    <div className={`rounded-lg p-4 ${colorMap[color]}`}>
      <div className="text-sm">{label}</div>
      <div className="text-2xl font-bold">{value}</div>
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const statusMap: Record<string, { bg: string, text: string, label: string }> = {
    passed: { bg: 'bg-green-100', text: 'text-green-800', label: '通过' },
    failed: { bg: 'bg-red-100', text: 'text-red-800', label: '失败' },
    error: { bg: 'bg-orange-100', text: 'text-orange-800', label: '错误' },
    running: { bg: 'bg-blue-100', text: 'text-blue-800', label: '运行中' }
  }

  const s = statusMap[status] || statusMap.error

  return (
    <span className={`px-2 py-1 rounded-full text-xs font-medium ${s.bg} ${s.text}`}>
      {s.label}
    </span>
  )
}
