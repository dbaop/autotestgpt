# AutoTestGPT

多智能体一体化测试平台，实现从需求文档到测试执行的全自动化流程。

## 项目概述

AutoTestGPT 是一个基于大模型的自动化测试平台，通过四大智能体协同工作，实现测试全流程自动化：

- **输入**：自然语言测试需求
- **输出**：测试用例、自动化脚本、执行报告
- **目标**：提高测试效率，降低测试成本，保证测试质量

## 架构设计

### 分层架构

| 层级 | 组件 | 职责 | 技术栈 |
|------|------|------|--------|
| **交互层** | React Web 界面 | 用户交互、需求管理、聊天对话 | React + TypeScript + Tailwind CSS |
| **API 层** | Flask REST API | 接口路由、请求处理 | Flask + Blueprint |
| **编排层** | AutoTestFlow | 工作流编排、状态管理 | Python |
| **智能体层** | 四大 Agent | 需求解析、用例生成、代码生成、测试执行 | LiteLLM + 多模型支持 |
| **服务层** | Service 模块 | 知识库、代码审查、缺陷分析、报告生成 | Python |
| **持久层** | SQLAlchemy + MySQL/SQLite | 数据持久化 | SQLAlchemy ORM |

### 四大智能体

| 智能体 | 职责 | 输入 | 输出 |
|--------|------|------|------|
| **ReqAgent** | 需求解析 | 自然语言需求 | 结构化需求 |
| **CaseAgent** | 用例设计 | 结构化需求 | 测试用例 |
| **CodeAgent** | 代码生成 | 测试用例 | 自动化脚本 |
| **ExecAgent** | 执行与报告 | 自动化脚本 | 执行结果、报告 |

### 支持的 LLM

按优先级自动选择可用的模型：
1. MiniMax (`minimax/MiniMax-M3`)
2. DeepSeek (`deepseek/deepseek-v4-flash`)
3. OpenAI (`gpt-4`)

## 目录结构

```
autotestgpt/
├── agent/                    # 智能体
│   ├── __init__.py          # 包导出
│   ├── base_agent.py        # 基础智能体类（LLM调用、JSON解析）
│   ├── req_agent.py         # 需求解析智能体
│   ├── case_agent.py        # 用例设计智能体
│   ├── code_agent.py        # 代码生成智能体
│   ├── exec_agent.py        # 执行与报告智能体
│   └── chat_agent.py        # 对话智能体（多轮对话 + 意图路由）
├── api/                     # API 接口
│   ├── __init__.py          # Blueprint 注册
│   └── routes/              # 路由模块
│       ├── requirements.py  # 需求 CRUD + 文件导入
│       ├── test_cases.py    # 测试用例查询
│       ├── executions.py    # 执行记录查询
│       ├── projects.py      # 项目管理
│       ├── conversations.py # 对话管理
│       ├── code_reviews.py  # 代码审查
│       ├── knowledge_bases.py # 知识库管理
│       ├── reports.py       # 报告生成
│       └── autofix.py       # 自动修复建议
├── flow/                    # 工作流编排
│   └── test_flow.py         # AutoTestFlow + FlowDataAccess
├── service/                 # 业务服务
│   ├── knowledge_service.py # 知识库 CRUD + 搜索
│   ├── review_service.py    # Git 代码审查
│   ├── defect_service.py    # 缺陷分析
│   ├── report_service.py    # 报告生成
│   ├── autofix_service.py   # 修复建议
│   └── document_import_service.py # 文档导入（txt/docx/xlsx/pdf）
├── executor/                # 执行器
│   ├── api_executor.py      # API 执行器
│   └── ui_executor.py       # UI 执行器（Selenium）
├── templates/               # Jinja2 模板
│   └── report.html          # 测试报告模板
├── prompt/                  # 提示词模板
├── tests/                   # TDD 测试套件（Phase 1-6）
├── autotestgptFront/        # React 前端
├── workspace/               # 运行时工作空间
├── report/                  # 生成的测试报告
├── .env                     # 环境变量
├── config.py                # 配置类
├── models.py                # 数据库模型（13 个表）
├── main.py                  # 应用入口
└── requirements.txt         # 依赖列表
```

## 快速开始

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

# 安装 Playwright 浏览器
playwright install chrome
```

### 2. 配置环境变量

编辑 `.env` 文件，至少配置一个 LLM API Key：

```env
# API Keys（按优先级，配置任一个即可）
MINIMAX_API_KEY=your_minimax_api_key
DEEPSEEK_API_KEY=your_deepseek_api_key
OPENAI_API_KEY=your_openai_api_key

# 数据库（可选，默认使用 SQLite）
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=autotestgpt

# 服务器
SERVER_PORT=8000
SECRET_KEY=your_secret_key

# 工作空间
WORKSPACE=./workspace
REPORT_DIR=./report
```

### 3. 启动服务

```bash
python main.py
# 服务在 http://localhost:8000 启动
# 数据库表自动创建
```

### 4. 使用 API

```bash
# 健康检查
curl http://localhost:8000/api/health

# 启动测试流程
curl -X POST http://localhost:8000/api/flow/start \
  -H "Content-Type: application/json" \
  -d '{"demand": "测试用户登录功能，包括用户名密码验证、记住登录状态、错误提示"}'

# 查询工作流状态
curl http://localhost:8000/api/flow/status/1

# 查看需求列表
curl http://localhost:8000/api/requirements

# 查看测试用例
curl http://localhost:8000/api/cases
```

## API 接口

| 接口 | 方法 | 路径 | 功能 |
|------|------|------|------|
| 健康检查 | GET | `/api/health` | 检查系统和数据库状态 |
| 启动测试 | POST | `/api/flow/start` | 异步启动测试流程 |
| 流程状态 | GET | `/api/flow/status/<id>` | 查询异步工作流状态 |
| 恢复流程 | POST | `/api/flow/resume/<id>` | 从失败步骤恢复 |
| 需求列表 | GET | `/api/requirements` | 分页获取需求列表 |
| 需求详情 | GET | `/api/requirements/<id>` | 获取单个需求 |
| 创建需求 | POST | `/api/requirements` | 手动创建需求 |
| 导入需求 | POST | `/api/requirements/import` | 文件导入需求 |
| 更新需求 | PUT | `/api/requirements/<id>` | 更新需求信息 |
| 删除需求 | DELETE | `/api/requirements/<id>` | 删除需求 |
| 用例列表 | GET | `/api/cases` | 获取测试用例 |
| 用例详情 | GET | `/api/cases/<id>` | 获取单个用例 |
| 执行记录 | GET | `/api/executions` | 获取执行历史 |
| 执行详情 | GET | `/api/executions/<id>` | 获取单条执行记录 |
| 项目列表 | GET | `/api/projects` | 获取项目列表 |
| 知识库列表 | GET | `/api/knowledge-bases` | 获取知识库列表 |
| 知识库搜索 | POST | `/api/knowledge-bases/search` | 搜索知识条目 |
| 代码审查 | POST | `/api/code-reviews` | 创建代码审查任务 |
| 生成报告 | POST | `/api/reports` | 生成需求分析报告 |
| 修复建议 | POST | `/api/autofix/suggestions` | 生成自动修复建议 |
| 对话列表 | GET | `/api/conversations` | 获取对话列表 |
| 发送消息 | POST | `/api/conversations/<id>/messages` | 发送聊天消息 |
| 获取脚本 | GET | `/api/scripts` | 获取需求的测试脚本 |

## 工作流程

```
用户输入需求 (Web / API)
    ↓
POST /api/flow/start  →  异步启动
    ↓
ReqAgent 解析需求  →  结构化需求
    ↓
CaseAgent 设计用例  →  测试用例 + 知识库复用
    ↓
CodeAgent 生成代码  →  pytest / Playwright 脚本
    ↓
ExecAgent 执行测试  →  测试报告（HTML + JSON）
    ↓
（可选）代码审查  →  缺陷分析  →  修复建议
    ↓
结果返回（执行进度可实时查询）
```

## 使用示例

```python
import requests

# 启动测试流程（含代码审查）
response = requests.post('http://localhost:8000/api/flow/start', json={
    'demand': '''
    测试用户登录功能：
    1. 正常登录：输入正确的用户名和密码
    2. 错误密码：输入正确的用户名，错误的密码
    3. 空用户名：用户名为空
    4. 空密码：密码为空
    5. 记住登录状态：勾选记住我
    ''',
    'review': {
        'repo_url': 'https://github.com/example/project',
        'branch': 'main',
        'days': 7,
    },
})

print(f"测试已启动，需求ID: {response.json()['requirement_id']}")

# 查询进度
import time
req_id = response.json()['requirement_id']
while True:
    status = requests.get(f'http://localhost:8000/api/flow/status/{req_id}').json()
    print(f"状态: {status['db_status']}, 进度: {status['execution_progress']}")
    if status['db_status'] in ('completed', 'error'):
        break
    time.sleep(3)
```

## 监控与日志

### 日志文件
- 应用日志：`workspace/logs/autotestgpt.log`（自动轮转，10MB × 10 个文件）
- 测试报告：`report/html/` 和 `report/json/`
- 执行脚本：`workspace/scripts/`

## 贡献指南

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 许可证

本项目采用 MIT 许可证。

---

**注意**：本项目处于开发阶段，API 可能会发生变化。
