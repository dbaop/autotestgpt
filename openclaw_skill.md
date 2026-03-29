# AutoTestGPT OpenClaw Skill

这是一个将AutoTestGPT集成到OpenClaw的技能文件。

## 安装方法

### 方法1：直接复制技能文件夹
1. 将整个项目复制到OpenClaw技能目录：
   ```
   cp -r autotestgpt "C:\Users\dbaop\AppData\Roaming\npm\node_modules\openclaw-cn\skills\autotestgpt"
   ```

2. 重启OpenClaw服务

### 方法2：创建符号链接
```
# Windows (以管理员身份运行PowerShell)
New-Item -ItemType SymbolicLink -Path "C:\Users\dbaop\AppData\Roaming\npm\node_modules\openclaw-cn\skills\autotestgpt" -Target "D:\resources\aitest\autotestgpt"

# Linux/Mac
ln -s "D:\resources\aitest\autotestgpt" "C:\Users\dbaop\AppData\Roaming\npm\node_modules\openclaw-cn\skills\autotestgpt"
```

## 使用方法

在OpenClaw中，你可以使用以下命令：

### 1. 启动测试
```
测试登录功能
测试用户注册API
测试购物车流程
```

### 2. 查看状态
```
查看测试进度
显示测试报告
列出所有需求
```

### 3. 管理项目
```
创建测试项目
查看项目详情
删除测试项目
```

## Webhook配置

如果你希望通过Webhook触发测试，可以在OpenClaw中配置：

1. 在OpenClaw Web界面中，找到Webhook配置
2. 添加新的Webhook：
   - URL: `http://localhost:8000/api/flow/start`
   - 方法: POST
   - 内容类型: application/json
   - 触发条件: 消息包含"测试"

3. 示例Webhook数据：
```json
{
  "demand": "{{message}}",
  "project_id": 1
}
```

## 技能配置

在OpenClaw技能目录中创建 `SKILL.md` 文件：

```markdown
# AutoTestGPT Skill

## 描述
多智能体一体化测试平台，实现从需求文档到测试执行的全自动化流程。

## 命令
- `测试 <需求描述>` - 启动测试流程
- `查看测试进度` - 查看当前测试状态
- `测试报告 <ID>` - 查看测试报告
- `测试历史` - 查看测试历史记录

## 配置
需要配置环境变量：
- `DEEPSEEK_API_KEY` 或 `OPENAI_API_KEY`
- 数据库连接信息

## 依赖
- Python 3.10+
- MySQL/SQLite
- Playwright浏览器
```

## 快速测试

在OpenClaw中发送：
```
测试用户登录功能，包括：
1. 正常登录
2. 错误密码
3. 空用户名
4. 记住登录状态
```

系统将自动：
1. 解析需求
2. 设计测试用例
3. 生成测试代码
4. 执行测试
5. 生成报告

## 故障排除

### 1. 技能不显示
- 检查技能文件夹是否正确放置
- 重启OpenClaw服务
- 检查OpenClaw日志

### 2. API调用失败
- 检查AutoTestGPT服务是否运行：`python main.py`
- 检查端口是否被占用：`netstat -ano | findstr :8000`
- 检查API密钥配置

### 3. 数据库连接失败
- 检查MySQL服务是否运行
- 检查.env文件配置
- 运行 `python init_db.py` 初始化数据库

## 高级功能

### 自定义提示词
编辑 `prompt/` 目录下的文件来自定义AI行为。

### 扩展智能体
在 `agent/` 目录中添加新的智能体。

### 自定义工作流
修改 `flow/test_flow.py` 来调整工作流程。

## 支持与反馈

- GitHub: https://github.com/dbaop/autotestgpt
- 问题反馈: GitHub Issues
- 功能建议: GitHub Discussions