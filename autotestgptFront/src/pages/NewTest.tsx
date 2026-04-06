import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { flowApi } from '../api'

const defaultDemand = `测试用户登录功能：
1. 正常登录：输入正确的用户名和密码
2. 错误密码：输入正确的用户名，错误的密码
3. 空用户名：用户名为空
4. 空密码：密码为空
5. 记住登录状态：勾选记住我
6. 错误提示：显示友好的错误信息`

export default function NewTest() {
  const navigate = useNavigate()
  const [demand, setDemand] = useState('')
  const [projectId] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!demand.trim()) {
      setError('请输入测试需求')
      return
    }

    setLoading(true)
    setError('')

    try {
      const res = await flowApi.start(demand, projectId)
      navigate(`/requirements/${res.data.requirement_id}`)
    } catch (err: any) {
      setError(err.response?.data?.error || '启动测试流程失败')
      setLoading(false)
    }
  }

  const handleUseTemplate = (template: string) => {
    setDemand(template)
  }

  return (
    <div className="max-w-4xl mx-auto">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">新建测试</h2>

      <div className="bg-white rounded-lg shadow">
        <form onSubmit={handleSubmit} className="p-6">
          {error && (
            <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
              {error}
            </div>
          )}

          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              测试需求描述
            </label>
            <textarea
              value={demand}
              onChange={e => setDemand(e.target.value)}
              rows={12}
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-gray-900"
              placeholder="请输入测试需求，使用自然语言描述..."
            />
          </div>

          {/* Templates */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-2">快速模板</label>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => handleUseTemplate(defaultDemand)}
                className="px-3 py-1.5 bg-gray-100 hover:bg-gray-200 rounded-full text-sm text-gray-700"
              >
                用户登录测试
              </button>
              <button
                type="button"
                onClick={() => handleUseTemplate('测试API接口：\n1. GET /api/users - 获取用户列表\n2. POST /api/users - 创建用户\n3. GET /api/users/{id} - 获取单个用户\n4. PUT /api/users/{id} - 更新用户\n5. DELETE /api/users/{id} - 删除用户')}
                className="px-3 py-1.5 bg-gray-100 hover:bg-gray-200 rounded-full text-sm text-gray-700"
              >
                REST API 测试
              </button>
              <button
                type="button"
                onClick={() => handleUseTemplate('测试网页表单：\n1. 表单验证\n2. 提交成功\n3. 提交失败处理\n4. 文件上传')}
                className="px-3 py-1.5 bg-gray-100 hover:bg-gray-200 rounded-full text-sm text-gray-700"
              >
                Web表单测试
              </button>
            </div>
          </div>

          <div className="flex justify-end gap-4">
            <button
              type="button"
              onClick={() => navigate('/')}
              className="px-6 py-2.5 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-6 py-2.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? '启动中...' : '启动测试流程'}
            </button>
          </div>
        </form>
      </div>

      {/* Workflow Description */}
      <div className="mt-8 bg-gray-50 rounded-lg p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">自动化测试流程</h3>
        <div className="grid grid-cols-4 gap-4">
          <WorkflowStep step={1} name="需求解析" desc="大模型解析需求" agent="ReqAgent" />
          <WorkflowStep step={2} name="用例设计" desc="生成测试用例" agent="CaseAgent" />
          <WorkflowStep step={3} name="代码生成" desc="生成自动化脚本" agent="CodeAgent" />
          <WorkflowStep step={4} name="执行测试" desc="运行并生成报告" agent="ExecAgent" />
        </div>
      </div>
    </div>
  )
}

function WorkflowStep({ step, name, desc, agent }: {
  step: number
  name: string
  desc: string
  agent: string
}) {
  return (
    <div className="bg-white rounded-lg p-4 text-center">
      <div className="w-8 h-8 bg-indigo-600 text-white rounded-full flex items-center justify-center mx-auto mb-2 text-sm font-bold">
        {step}
      </div>
      <div className="font-medium text-gray-900">{name}</div>
      <div className="text-sm text-gray-500 mt-1">{desc}</div>
      <div className="text-xs text-indigo-600 mt-1">{agent}</div>
    </div>
  )
}
