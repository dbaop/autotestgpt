import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { casesApi, TestCase } from '../api'

export default function TestCases() {
  const [cases, setCases] = useState<TestCase[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<string>('all')

  useEffect(() => {
    casesApi.list()
      .then(res => setCases(res.data.items || []))
      .catch(err => console.error('Failed to load cases:', err))
      .finally(() => setLoading(false))
  }, [])

  const filteredCases = filter === 'all'
    ? cases
    : cases.filter(c => c.test_type === filter)

  if (loading) {
    return <div className="text-center py-8 text-gray-500">加载中...</div>
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-gray-900">测试用例</h2>
        <div className="flex gap-2">
          {['all', 'api', 'ui', 'performance', 'security'].map(type => (
            <button
              key={type}
              onClick={() => setFilter(type)}
              className={`px-3 py-1.5 rounded-full text-sm ${
                filter === type
                  ? 'bg-indigo-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {type === 'all' ? '全部' : type.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      <div className="bg-white rounded-lg shadow overflow-hidden">
        {filteredCases.length === 0 ? (
          <div className="p-8 text-center text-gray-500">暂无测试用例</div>
        ) : (
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  用例名称
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  类型
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  优先级
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  关联需求
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  创建时间
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {filteredCases.map(c => (
                <tr key={c.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4">
                    <div className="font-medium text-gray-900">{c.title}</div>
                    <div className="text-sm text-gray-500">{c.description}</div>
                  </td>
                  <td className="px-6 py-4">
                    <TypeBadge type={c.test_type} />
                  </td>
                  <td className="px-6 py-4">
                    <PriorityBadge priority={c.priority} />
                  </td>
                  <td className="px-6 py-4 text-gray-500">
                    <Link
                      to={`/requirements/${c.requirement_id}`}
                      className="text-indigo-600 hover:text-indigo-800"
                    >
                      #{c.requirement_id}
                    </Link>
                  </td>
                  <td className="px-6 py-4 text-gray-500 text-sm">
                    {new Date(c.created_at).toLocaleString('zh-CN')}
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

function PriorityBadge({ priority }: { priority: string }) {
  const map: Record<string, string> = {
    high: 'bg-red-100 text-red-800',
    medium: 'bg-yellow-100 text-yellow-800',
    low: 'bg-green-100 text-green-800'
  }
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${map[priority] || map.medium}`}>
      {priority === 'high' ? '高' : priority === 'medium' ? '中' : '低'}
    </span>
  )
}

function TypeBadge({ type }: { type: string }) {
  const map: Record<string, string> = {
    api: 'bg-blue-100 text-blue-800',
    ui: 'bg-purple-100 text-purple-800',
    performance: 'bg-orange-100 text-orange-800',
    security: 'bg-red-100 text-red-800'
  }
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${map[type] || 'bg-gray-100 text-gray-800'}`}>
      {type?.toUpperCase() || 'API'}
    </span>
  )
}
