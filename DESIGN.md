# AutoTestGPT 框架设计方案

## 1. 项目概述

**AutoTestGPT** 是一个多智能体一体化测试平台，旨在实现从需求文档到测试执行的全自动化流程：
- **输入**：自然语言测试需求
- **输出**：测试用例、自动化脚本、执行报告
- **目标**：提高测试效率，降低测试成本，保证测试质量

## 2. 架构设计

### 2.1 五层架构

| 层级 | 组件 | 职责 | 技术栈 |
|------|------|------|--------|
| **交互层** | OpenClaw | 入口、用户交互、消息通知 | 聊天界面、Webhook |
| **调度层** | LiteFlow | 流程编排、状态管理、错误处理 | 自定义工作流引擎 |
| **大脑层** | 大模型集群 | 需求解析、用例生成、代码生成 | DeepSeek-Coder、GPT-4o |
| **执行层** | 执行器 | API 测试、UI 测试、性能测试 | Requests、Playwright、JMeter |
| **存储层** | 数据库 | 数据持久化、历史记录 | MySQL/SQLite |

### 2.2 四大智能体

| 智能体 | 职责 | 输入 | 输出 |
|--------|------|------|------|
| **ReqAgent** | 需求解析 | 自然语言需求 | 结构化需求（业务模块、接口清单、UI元素、测试点） |
| **CaseAgent** | 用例设计 | 结构化需求 | 测试用例（API用例、UI用例） |
| **CodeAgent** | 代码生成 | 测试用例 | 自动化脚本（Python + Requests、Playwright POM） |
| **ExecAgent** | 执行与报告 | 自动化脚本 | 执行结果、Allure 报告 |

## 3. 目录结构

```
autotestgpt/
├── agent/                # 四大智能体
│   ├── base_agent.py     # 基础智能体类
│   ├── req_agent.py      # 需求解析智能体
│   ├── case_agent.py     # 用例设计智能体
│   ├── code_agent.py     # 代码生成智能体
│   └── exec_agent.py     # 执行与报告智能体
├── flow/                 # 工作流编排
│   ├── test_flow.py      # 测试流程定义
│   └── flow_def.py       # 流程配置
├── executor/             # 执行器
│   ├── api_executor.py   # API 测试执行器
│   └── ui_executor.py    # UI 测试执行器
├── prompt/               # 提示词
│   ├── req_prompt.txt    # 需求解析提示词
│   ├── case_prompt.txt   # 用例设计提示词
│   └── code_prompt.txt   # 代码生成提示词
├── models.py             # 数据库模型
├── init_db.py            # 数据库初始化
├── config.py             # 配置文件
├── main.py               # API 入口
├── .env                  # 环境变量
├── requirements.txt      # 依赖列表
└── DESIGN.md             # 设计方案
```

## 4. 核心组件

### 4.1 工作流引擎（LiteFlow）

**核心功能**：
- 流程定义与编排
- 依赖管理与拓扑排序
- 并行执行支持
- 错误处理与重试
- 状态管理与持久化

**流程定义**：
```python
@Flow(name="autotest_full_flow")
class AutoTestFlow:
    @step(name="parse_req")
    def run_req_agent(self, data):
        return ReqAgent().parse(data["demand"])

    @step(name="gen_case", deps=["parse_req"])
    def run_case_agent(self, ctx):
        return CaseAgent().gen(ctx["parse_req"])

    @step(name="gen_code", deps=["gen_case"])
    def run_code_agent(self, ctx):
        return CodeAgent().gen(ctx["gen_case"])

    @step(name="run_exec", deps=["gen_code"])
    def run_exec_agent(self, ctx):
        return ExecAgent().run(ctx["gen_code"])
```

### 4.2 智能体系统

**ReqAgent**：
- 输入：自然语言需求
- 处理：大模型解析需求
- 输出：结构化需求 JSON

**CaseAgent**：
- 输入：结构化需求
- 处理：大模型生成测试用例
- 输出：API/UI 测试用例 JSON

**CodeAgent**：
- 输入：测试用例
- 处理：大模型生成测试脚本
- 输出：可执行的 Python 代码

**ExecAgent**：
- 输入：测试脚本
- 处理：执行脚本并生成报告
- 输出：执行结果和报告路径

### 4.3 数据库模型

**数据表**：
- `requirements` - 需求表
- `test_cases` - 测试用例表
- `test_scripts` - 测试脚本表
- `execution_records` - 执行记录表

**关系**：
- 需求 → 测试用例（一对多）
- 测试用例 → 测试脚本（一对多）
- 测试脚本 → 执行记录（一对多）

### 4.4 API 接口

| 接口 | 方法 | 路径 | 功能 |
|------|------|------|------|
| 健康检查 | GET | `/api/health` | 检查系统状态 |
| 启动测试 | POST | `/api/flow/start` | 启动测试流程 |
| 需求列表 | GET | `/api/requirements` | 获取需求历史 |
| 需求详情 | GET | `/api/requirements/<id>` | 获取单个需求 |
| 用例列表 | GET | `/api/cases` | 获取测试用例 |
| 执行记录 | GET | `/api/executions` | 获取执行历史 |

## 5. 数据流

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  用户输入   │────>│  OpenClaw   │────>│  Flask API  │
└─────────────┘     └─────────────┘     └─────────────┘
                                            │
                                            ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  执行结果   │<────│  执行器     │<────│  LiteFlow   │
└─────────────┘     └─────────────┘     └─────────────┘
                                            │
                                            ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  数据库     │<────│  智能体     │<────│  大模型     │
└─────────────┘     └─────────────┘     └─────────────┘
```

## 6. 技术栈

| 类别 | 技术 | 版本 | 用途 |
|------|------|------|------|
| **编程语言** | Python | 3.10+ | 核心开发 |
| **Web 框架** | Flask | 2.0+ | API 服务 |
| **数据库** | MySQL/SQLite | 8.0+ | 数据存储 |
| **大模型** | DeepSeek-Coder | - | 代码生成 |
| **大模型** | GPT-4o | - | 需求分析 |
| **测试工具** | Requests | 2.30+ | API 测试 |
| **测试工具** | Playwright | 1.40+ | UI 测试 |
| **测试工具** | Pytest | 7.0+ | 测试执行 |
| **测试工具** | Allure | 2.13+ | 报告生成 |
| **前端** | OpenClaw | - | 用户交互 |

## 7. 部署方案

### 7.1 本地部署

1. **环境准备**：
   - Python 3.10+
   - MySQL 8.0+ 或 SQLite
   - OpenClaw 本地服务

2. **安装步骤**：
   ```bash
   # 克隆代码
   git clone <repository>
   cd autotestgpt
   
   # 安装依赖
   pip install -r requirements.txt
   playwright install chrome
   
   # 初始化数据库
   python init_db.py
   
   # 启动服务
   python main.py
   ```

3. **OpenClaw 配置**：
   - Webhook URL: `http://localhost:8000/api/flow/start`
   - 触发方式: 消息触发
   - 响应处理: 格式化显示

### 7.2 生产部署

1. **服务器配置**：
   - 2核4G 以上云服务器
   - Ubuntu 20.04+ 或 CentOS 7+
   - MySQL 8.0+

2. **部署流程**：
   - 使用 Gunicorn 作为 WSGI 服务器
   - 使用 Nginx 作为反向代理
   - 配置 SSL 证书
   - 设置防火墙规则

3. **监控与日志**：
   - 配置 Prometheus + Grafana 监控
   - 使用 ELK 栈收集日志
   - 设置告警机制

## 8. 监控与维护

### 8.1 监控指标

| 指标 | 类型 | 说明 |
|------|------|------|
| API 响应时间 | 性能 | 接口响应时间统计 |
| 测试执行成功率 | 业务 | 测试用例执行成功率 |
| 大模型调用次数 | 资源 | 大模型 API 调用频率 |
| 数据库连接数 | 资源 | 数据库连接状态 |
| 错误率 | 质量 | 系统错误发生频率 |

### 8.2 维护计划

1. **日常维护**：
   - 检查日志文件
   - 监控系统状态
   - 备份数据库

2. **定期维护**：
   - 更新依赖包
   - 优化大模型提示词
   - 清理历史数据
   - 性能测试与优化

3. **故障处理**：
   - 建立故障响应流程
   - 制定应急方案
   - 定期演练

## 9. 扩展计划

### 9.1 功能扩展

1. **支持更多测试类型**：
   - 性能测试（JMeter 集成）
   - 安全测试（OWASP ZAP 集成）
   - 接口文档测试（Swagger/OpenAPI 集成）

2. **智能体增强**：
   - 支持多语言需求
   - 增加测试数据生成能力
   - 支持测试环境管理

3. **用户体验**：
   - 开发 Web 管理界面
   - 支持测试计划管理
   - 增加测试报告分析功能

### 9.2 技术扩展

1. **架构优化**：
   - 微服务化改造
   - 支持容器化部署（Docker/K8s）
   - 实现 CI/CD 流程

2. **AI 能力**：
   - 引入 RAG 技术增强大模型能力
   - 支持模型微调
   - 实现智能测试推荐

3. **生态集成**：
   - 与 Jira、Confluence 集成
   - 与 Jenkins、GitLab CI 集成
   - 与监控系统集成

## 10. 总结

AutoTestGPT 采用分层架构设计，通过四大智能体协同工作，实现了从需求到测试的全自动化流程。系统具有以下特点：

- **模块化设计**：各组件职责明确，易于扩展
- **智能驱动**：基于大模型实现智能测试
- **灵活配置**：支持多种部署方式和集成方案
- **可观测性**：完善的监控和日志系统
- **易维护性**：清晰的代码结构和文档

通过 OpenClaw 前端集成，用户可以通过自然语言对话轻松触发测试流程，极大简化了测试工作流程。

此设计方案为 AutoTestGPT 项目提供了完整的架构指导，确保系统的可扩展性、可靠性和易用性。
