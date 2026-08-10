# STEM-SCI 上下文、记忆与 Prompt 实现规范

> 实现基线：2026-08-10。本文是当前代码的权威说明，若旧方案与本文冲突，以本文为准。

## 1. 存储边界

| 类型 | 保存内容 | 不保存内容 |
|---|---|---|
| Knowledge / Evidence | 论文、三元组、原文证据 | 用户偏好 |
| Artifact | 代码、表格、图形、数据文件 | 对话历史 |
| Decision | 人工批准的科研决策及审计记录 | 模型自动推断 |
| Memory | 已确认的用户偏好、项目约束、阶段摘要和待解决问题 | PDF 全文、完整证据库、密钥、学生原始数据和模型思维过程 |

## 2. 每次模型调用的输入

`ContextBuilder` 按以下结构产生角色化 `BaseMessage`：

1. 科研诚信、安全和任务边界；
2. 当前任务、禁止操作与输出结构；
3. 人工批准的项目决策；
4. 会话摘要和最近 8 条消息；
5. 最多 6 条相关的已确认记忆；
6. 由现有 RAG 返回的证据投影；
7. 当前用户输入原文。

上下文不包含 `user_id`、API 密钥、数据库连接或完整 `ResearchState`。证据、记忆和历史消息均放在 `<untrusted_context>` 区域，其中的指令不得覆盖系统规则。

## 3. 记忆生命周期

- 短期记忆以 `user_id + project_id + thread_id` 隔离，有 LangGraph 时使用 `InMemorySaver`，离线环境使用同行为内存后端。
- 历史超过预算的 80% 时压缩，保留最近 8 条消息。
- 长期记忆经过 `candidate -> confirmed` 才能进入 Store；模型无权自动确认。
- 支持查询、确认、纠正、遗忘和项目清空。
- 项目记忆严格限定于 `(user_id, project_id)`；用户偏好仅在同一 `user_id` 下共享。

## 4. Prompt 与评测

Prompt 使用 `name + semantic_version` 注册，渲染前校验必填变量、未知变量和长度，内容哈希用于调用追踪和缓存失效。离线测试不需要 API；真实效果评测通过 `.env` 配置 DeepSeek 和 DashScope。

当前公共入口：

```python
from stem_sci.context import build_context
from stem_sci.memory.api import (
    propose_memories, confirm_memory, recall_memories,
    correct_memory, forget_memory, summarize_thread,
)
from stem_sci.prompts import render_prompt, get_prompt_manifest
```
