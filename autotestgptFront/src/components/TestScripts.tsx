import React, { useState, useEffect } from 'react'
import { scriptsApi } from '../api'

interface TestScript {
  id: number
  test_case_id: number
  script_type: string
  file_path: string
  status: string
  created_at: string
  content: string
}

interface TestScriptsProps {
  requirementId: number
}

const TestScripts: React.FC<TestScriptsProps> = ({ requirementId }) => {
  const [scripts, setScripts] = useState<TestScript[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedScript, setSelectedScript] = useState<TestScript | null>(null)

  const loadScripts = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await scriptsApi.list(requirementId)
      setScripts(response.data)
    } catch (err) {
      setError('获取测试脚本失败')
      console.error('Failed to fetch test scripts:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (requirementId) {
      loadScripts()
    }
  }, [requirementId])

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'generated':
        return 'text-blue-600'
      case 'running':
        return 'text-yellow-600'
      case 'executed':
        return 'text-green-600'
      case 'error':
        return 'text-red-600'
      default:
        return 'text-gray-600'
    }
  }

  const getStatusText = (status: string) => {
    switch (status) {
      case 'generated':
        return '已生成'
      case 'running':
        return '执行中'
      case 'executed':
        return '已执行'
      case 'error':
        return '错误'
      default:
        return status
    }
  }

  return (
    <div className="bg-white rounded-lg shadow p-6 mb-6">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-semibold">测试脚本</h3>
        <button
          onClick={loadScripts}
          disabled={loading}
          className="text-sm px-3 py-1 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50"
        >
          {loading ? '加载中...' : '刷新'}
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 text-red-600 rounded">
          {error}
        </div>
      )}

      {scripts.length === 0 && !loading ? (
        <div className="text-center py-8 text-gray-500">
          暂无测试脚本
        </div>
      ) : (
        <div className="space-y-4">
          {scripts.map((script) => (
            <div key={script.id} className="border rounded-lg overflow-hidden">
              <div 
                className="p-4 bg-gray-50 cursor-pointer hover:bg-gray-100"
                onClick={() => setSelectedScript(selectedScript?.id === script.id ? null : script)}
              >
                <div className="flex justify-between items-center">
                  <div>
                    <h4 className="font-medium">{script.file_path?.split('\\').pop() || `脚本 ${script.id}`}</h4>
                    <div className="text-sm text-gray-600 mt-1">
                      类型: {script.script_type} | 用例ID: {script.test_case_id} | 
                      状态: <span className={getStatusColor(script.status)}>{getStatusText(script.status)}</span>
                    </div>
                  </div>
                  <div className="text-sm text-gray-500">
                    {new Date(script.created_at).toLocaleString('zh-CN')}
                  </div>
                </div>
              </div>
              
              {selectedScript?.id === script.id && (
                <div className="p-4 border-t">
                  <div className="text-sm text-gray-500 mb-2">脚本内容:</div>
                  <pre className="bg-gray-50 p-4 rounded overflow-x-auto max-h-96 text-sm">
                    {script.content}
                  </pre>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default TestScripts