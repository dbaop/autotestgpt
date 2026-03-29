# AutoTestGPT

多智能体一体化测试平台，实现从需求文档到测试执行的全自动化流程。

## 🚀 项目概述

AutoTestGPT 是一个基于大模型的自动化测试平台，通过四大智能体协同工作，实现测试全流程自动化：

- **输入**：自然语言测试需求
- **输出**：测试用例、自动化脚本、执行报告
- **目标**：提高测试效率，降低测试成本，保证测试质量

## 🏗️ 架构设计

### 五层架构

| 层级 | 组件 | 职责 | 技术栈 |
|------|------|------|--------|
| **交互层** | OpenClaw/Web界面 | 用户交互、消息通知 | 聊天界面、Webhook |
| **调度层** | LiteFlow | 流程编排、状态管理 | 自定义工作流引擎 |
| **大脑层** | 大模型集群 | 需求解析、用例生成、代码生成 | DeepSeek-Coder、GPT-4 |
| **执行层** | 执行器 | API测试、UI测试、性能测试 | Requests、Playwright |
| **存储层** | 数据库 | 数据持久化、历史记录 | MySQL/SQLite |

### 四大智能体

| 智能体 | 职责 | 输入 | 输出 |
|--------|------|------|------|
| **ReqAgent** | 需求解析 | 自然语言需求 | 结构化需求 |
| **CaseAgent** | 用例设计 | 结构化需求 | 测试用例 |
| **CodeAgent** | 代码生成 | 测试用例 | 自动化脚本 |
| **ExecAgent** | 执行与报告 | 自动化脚本 | 执行结果、报告 |

## 📁 目录结构

```
autotestgpt/
├── agent/                 # 四大智能体
│   ├── base_agent.py     # 基础智能体类
│   ├── req_agent.py      # 需求解析智能体
│   ├── case_agent.py     # 用例设计智能体
│   ├── code_agent.py     # 代码生成智能体
│   └── exec_agent.py     # 执行与报告智能体
├── api/                  # API接口
│   ├── __init__.py
│   └── routes/          # 路由定义
├── flow/                # 工作流编排
│   └── test_flow.py    # 测试流程定义
├── executor/            # 执行器（待实现）
├── prompt/              # 提示词模板
├── workspace/           # 工作空间
├── report/              # 测试报告
├── .env                 # 环境变量
├── config.py           # 配置文件
├── models.py           # 数据库模型
├── init_db.py          # 数据库初始化
├── main.py             # 主应用入口
├── requirements.txt    # 依赖列表
└── README.md           # 项目说明
```

## 🛠️ 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone https://github.com/dbaop/autotestgpt.git
cd autotestgpt

# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 安装Playwright浏览器
playwright install chrome
```

### 2. 数据库配置

```bash
# 复制环境变量文件
cp .env.example .env

# 编辑.env文件，配置数据库和API密钥
# 需要配置：
# - DEEPSEEK_API_KEY 或 OPENAI_API_KEY
# - 数据库连接信息

# 初始化数据库
python init_db.py
```

### 3. 启动服务

```bash
# 启动开发服务器
python main.py

# 服务将在 http://localhost:8000 启动
```

### 4. 使用API

```bash
# 健康检查
curl http://localhost:8000/api/health

# 启动测试流程
curl -X POST http://localhost:8000/api/flow/start \
  -H "Content-Type: application/json" \
  -d '{
    "demand": "测试用户登录功能，包括用户名密码验证、记住登录状态、错误提示"
  }'

# 查看需求列表
curl http://localhost:8000/api/requirements

# 查看测试用例
curl http://localhost:8000/api/cases
```

## 📡 API接口

| 接口 | 方法 | 路径 | 功能 |
|------|------|------|------|
| 健康检查 | GET | `/api/health` | 检查系统状态 |
| 启动测试 | POST | `/api/flow/start` | 启动测试流程 |
| 需求列表 | GET | `/api/requirements` | 获取需求历史 |
| 需求详情 | GET | `/api/requirements/<id>` | 获取单个需求 |
| 用例列表 | GET | `/api/cases` | 获取测试用例 |
| 执行记录 | GET | `/api/executions` | 获取执行历史 |
| 项目列表 | GET | `/api/projects` | 获取项目列表 |

## 🔧 配置说明

### 环境变量 (.env)

```env
# API Keys
DEEPSEEK_API_KEY=your_deepseek_api_key
OPENAI_API_KEY=your_openai_api_key

# 数据库配置
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=autotestgpt

# 服务器配置
SERVER_PORT=8000
SECRET_KEY=your_secret_key

# 工作空间
WORKSPACE=./workspace
REPORT_DIR=./report
```

### 模型配置

支持的大模型：
- DeepSeek-Coder: `deepseek/deepseek-chat`
- GPT-4: `gpt-4`
- 其他LiteLLM支持的模型

## 🧪 使用示例

### 示例1：测试登录功能

```python
import requests

# 启动测试流程
response = requests.post('http://localhost:8000/api/flow/start', json={
    'demand': '''
    测试用户登录功能：
    1. 正常登录：输入正确的用户名和密码
    2. 错误密码：输入正确的用户名，错误的密码
    3. 空用户名：用户名为空
    4. 空密码：密码为空
    5. 记住登录状态：勾选记住我
    6. 错误提示：显示友好的错误信息
    '''
})

print(f"测试已启动，需求ID: {response.json()['requirement_id']}")
```

### 示例2：测试API接口

```python
import requests

# 启动API测试
response = requests.post('http://localhost:8000/api/flow/start', json={
    'demand': '''
    测试用户管理API：
    1. 用户注册接口：POST /api/users/register
    2. 用户登录接口：POST /api/users/login
    3. 获取用户信息：GET /api/users/{id}
    4. 更新用户信息：PUT /api/users/{id}
    5. 删除用户：DELETE /api/users/{id}
    
    要求测试：
    - 参数验证
    - 权限控制
    - 错误处理
    - 响应格式
    '''
})
```

## 📊 监控与日志

### 日志文件
- 应用日志：`workspace/logs/autotestgpt.log`
- 测试报告：`report/html/` 和 `report/json/`
- 执行脚本：`workspace/scripts/`

### 监控指标
- API响应时间
- 测试执行成功率
- 大模型调用次数
- 数据库连接状态

## 🔄 工作流程

```
用户输入需求
    ↓
OpenClaw接收 → Webhook调用
    ↓
ReqAgent解析需求 → 结构化需求
    ↓
CaseAgent设计用例 → 测试用例
    ↓
CodeAgent生成代码 → 自动化脚本
    ↓
ExecAgent执行测试 → 测试报告
    ↓
结果返回用户
```

## 🤝 贡献指南

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🙏 致谢

- [OpenClaw](https://openclaw.ai) - 提供优秀的AI助手框架
- [LiteLLM](https://github.com/BerriAI/litellm) - 统一的大模型调用接口
- [Playwright](https://playwright.dev) - 优秀的浏览器自动化工具
- [Flask](https://flask.palletsprojects.com/) - 轻量级Web框架

## 📞 联系方式

- 项目地址：https://github.com/dbaop/autotestgpt
- 问题反馈：GitHub Issues
- 讨论交流：GitHub Discussions

---

**注意**：本项目处于开发阶段，API可能会发生变化。建议在生产环境使用前进行充分测试。