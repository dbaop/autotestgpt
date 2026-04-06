import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { requirementsApi, Requirement } from '../api'

export default function Requirements() {
  const [requirements, setRequirements] = useState<Requirement[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    requirementsApi.list()
      .then(res => setRequirements(res.data.items || []))
      .catch(err => console.error('Failed to load requirements:', err))
      .finally(() => setLoading(false))
  }, [])

  const handleDelete = async (id: number, e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (!confirm('确定要删除这个需求吗？')) return

    try {
      await requirementsApi.delete(id)
      setRequirements(prev => prev.filter(r => r.id !== id))
    } catch (err) {
      console.error('Failed to delete:', err)
    }
  }

  if (loading) {
    return <div className="text-center py-8 text-gray-500">加载中...</div>
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-gray-900">需求管理</h2>
        <Link
          to="/new"
          className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
        >
          新建测试
        </Link>
      </div>

      <div className="bg-white rounded-lg shadow overflow-hidden">
        {requirements.length === 0 ? (
          <div className="p-8 text-center text-gray-500">
            暂无需求，
            <Link to="/new" className="text-indigo-600 hover:text-indigo-800">创建第一个测试</Link>
          </div>
        ) : (
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  需求
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  状态
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  用例数
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  创建时间
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                  操作
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {requirements.map(req => (
                <tr key={req.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4">
                    <Link to={`/requirements/${req.id}`} className="block">
                      <div className="font-medium text-gray-900 hover:text-indigo-600">
                        {req.title}
                      </div>
                      <div className="text-sm text-gray-500 truncate max-w-md">
                        {req.description}
                      </div>
                    </Link>
                  </td>
                  <td className="px-6 py-4">
                    <StatusBadge status={req.status} />
                  </td>
                  <td className="px-6 py-4 text-gray-500">
                    {req.test_case_count}
                  </td>
                  <td className="px-6 py-4 text-gray-500 text-sm">
                    {new Date(req.created_at).toLocaleString('zh-CN')}
                  </td>
                  <td className="px-6 py-4 text-right">
                    <button
                      onClick={(e) => handleDelete(req.id, e)}
                      className="text-red-600 hover:text-red-800 text-sm"
                    >
                      删除
                    </button>
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
