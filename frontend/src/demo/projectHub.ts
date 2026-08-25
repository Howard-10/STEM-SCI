import type { ApiProjectDocument, ApiResearchProject } from "../api/auth";
import { demoRuntime, demoWorkflowState } from "./data";

export const demoProjects: ApiResearchProject[] = [
  {
    project_id: "physics-ai-demo",
    owner_user_id: "user-demo",
    title: "生成式 AI 分层支架研究",
    research_direction: "研究生成式 AI 分层支架对师范生 Python 物理建模能力的影响",
    abstract: "围绕研究设计、证据链、数据分析和审计验证构建的演示项目。",
    status: "active",
    role: "owner",
    created_at: "2026-08-20T09:00:00Z",
    updated_at: "2026-08-23T08:30:00Z",
  },
  {
    project_id: "stem-design-lab",
    owner_user_id: "user-demo",
    title: "STEM 研究设计实验室",
    research_direction: "面向教学法研究的证据整理与设计草案库",
    abstract: "用于展示文献筛选、设计草案和审查记录的第二个项目。",
    status: "active",
    role: "editor",
    created_at: "2026-08-18T10:00:00Z",
    updated_at: "2026-08-22T16:20:00Z",
  },
  {
    project_id: "assessment-workbench",
    owner_user_id: "user-demo",
    title: "学习成效评估工作台",
    research_direction: "围绕结果变量、评分量表和结果验证建立的归档项目",
    abstract: "展示归档项目与审计视图的补充样本。",
    status: "archived",
    role: "viewer",
    created_at: "2026-08-10T09:00:00Z",
    updated_at: "2026-08-21T13:40:00Z",
  },
];

export const demoDocumentsByProject: Record<string, ApiProjectDocument[]> = {
  "physics-ai-demo": [
    {
      document_id: "doc-manuscript-001",
      project_id: "physics-ai-demo",
      title: "论文草稿",
      document_type: "manuscript",
      format: "markdown",
      status: "active",
      current_version: 3,
      current_sha256: "demo-sha-001",
      size_bytes: 12488,
      created_by: "user-demo",
      updated_by: "user-demo",
      created_at: "2026-08-20T10:00:00Z",
      updated_at: "2026-08-23T08:12:00Z",
    },
    {
      document_id: "doc-reference-001",
      project_id: "physics-ai-demo",
      title: "核心参考文献",
      document_type: "reference",
      format: "pdf",
      status: "active",
      current_version: 1,
      current_sha256: "demo-sha-002",
      size_bytes: 4856320,
      created_by: "user-demo",
      updated_by: "user-demo",
      created_at: "2026-08-20T10:12:00Z",
      updated_at: "2026-08-20T10:12:00Z",
    },
    {
      document_id: "doc-protocol-001",
      project_id: "physics-ai-demo",
      title: "研究方案",
      document_type: "protocol",
      format: "markdown",
      status: "active",
      current_version: 2,
      current_sha256: "demo-sha-003",
      size_bytes: 6123,
      created_by: "user-demo",
      updated_by: "user-demo",
      created_at: "2026-08-21T09:20:00Z",
      updated_at: "2026-08-22T14:40:00Z",
    },
  ],
  "stem-design-lab": [
    {
      document_id: "doc-manuscript-002",
      project_id: "stem-design-lab",
      title: "设计草案",
      document_type: "manuscript",
      format: "markdown",
      status: "active",
      current_version: 1,
      current_sha256: "demo-sha-004",
      size_bytes: 8021,
      created_by: "user-demo",
      updated_by: "user-demo",
      created_at: "2026-08-18T10:15:00Z",
      updated_at: "2026-08-22T11:30:00Z",
    },
  ],
  "assessment-workbench": [
    {
      document_id: "doc-note-001",
      project_id: "assessment-workbench",
      title: "评估笔记",
      document_type: "note",
      format: "text",
      status: "archived",
      current_version: 1,
      current_sha256: "demo-sha-005",
      size_bytes: 1840,
      created_by: "user-demo",
      updated_by: "user-demo",
      created_at: "2026-08-10T09:10:00Z",
      updated_at: "2026-08-21T13:40:00Z",
    },
  ],
};

export const demoDocumentContents: Record<string, string> = {
  "doc-manuscript-001": `# 生成式 AI 分层支架与师范生 Python 物理建模能力

## 1. 研究问题

生成式 AI 分层支架是否能够改善师范生的 Python 物理建模能力、模型解释质量和迁移表现？

## 2. 研究设计

本研究采用前测、后测与迁移测验相结合的准实验设计。实验组使用分层提示、解释反馈和逐步撤除支架，对照组使用常规教学材料。

## 3. 主要结果变量

- Python 物理建模任务评分
- 模型假设与变量关系的解释质量
- 新情境迁移测验得分

## 4. 分析计划

将前测成绩作为协变量，并在正式分析前冻结结果变量、分组方式和稳健性检查方案。`,
  "doc-reference-001": `# 核心参考文献

- Generative AI scaffolding for physics modeling
- Model-based reasoning in teacher physics education
- Learning analytics for computational STEM instruction`,
  "doc-protocol-001": `# 研究方案

## 研究对象

师范生，预计来自同一门 Python 物理建模课程。

## 干预

实验组使用分层支架，对照组使用常规教学材料。

## 人工审批点

研究者需要确认主要结果变量、自然班分组方式和迁移测验评分量表。`,
  "doc-manuscript-002": `# STEM 研究设计草案

先完成问题界定和证据综述，再进入研究设计候选生成。`,
  "doc-note-001": `# 评估笔记

结果验证仍需补充冻结数据和独立审查记录。`,
};

export { demoRuntime, demoWorkflowState };
