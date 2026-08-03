# 物理 STEM 主 Demo：文献用途审核与支撑缺口报告

> 审核对象：`生成式 AI 分层支架对师范生 Python 物理建模表现、无辅助迁移能力和提示依赖的影响：一项随机平行组重复测量实验`
>
> 本报告不是“下载清单”，而是对每篇材料能否服务于该研究问题、任务设计、变量测量或方法论证的用途审计。它与首批 50 篇 AIMS 初筛表配套使用；首批表只记录初筛，不替代本报告的用途判断。

## 1. 审核结论

原有本地活动语料为 **101 篇 PDF**：AIMS 根目录 50 篇、IJSTEM/物理教育专题目录 34 篇、`papers/` 精选模块 17 篇。本次又加入 5 篇开放获取补充全文/框架材料，因此当前活动 PDF 数为 106 篇。重复清理后没有活动目录内的 SHA256 完全重复组；5 个重复文件已移入 `data/local/_dedupe_archive_20260731/`，2 个文件因文件名与实际内容不符移入 `data/local/_quarantine_wrong_files_20260731/`，均未删除。

结论分两层：

1. **作为三分钟主 Demo 的知识库，够用但不应全部混在一起。** 现有材料能支撑研究背景、STEM/PBL 任务设计、AI 物理教育风险、师范生 AI 素养和一般建模/评价逻辑。
2. **作为真实论文的完整证据基础，还不够。** 现有材料没有直接覆盖“师范生 + Python 物理建模 + 生成式 AI 分层支架对照静态提示 + 任务 C 无 AI 迁移 + 提示依赖”的完整因果链。最需要补的是计算建模课程与评分、迁移任务、提示/依赖过程指标，以及重复测量和任务等值的设计依据。

因此建议建立三个检索项目，而不是把 106 篇全部上传到同一个 `demo` 项目：

| 项目 ID | 用途 | 建议内容 |
|---|---|---|
| `physics-ai-stem-core` | 主 Demo 核心证据 | 直接涉及物理、AI 支架/反馈、计算建模、师范生或可迁移评价的论文 |
| `physics-ai-stem-methods` | 方法与测量支撑 | 计算思维框架、迁移、脚手架撤除、任务等值、过程日志、评分量规 |
| `physics-ai-stem-background` | 背景与边界 | STEM/PBL 综述、AI 素养、身份/动机、伦理与学术诚信、泛 STEM 研究 |

“暂缓”不等于删除：与主 Demo 无关或无法核对的材料继续留在本地隔离目录，不进入正式检索项目。

## 2. 用途分级规则

每篇论文只允许一个主用途标签，另可有备注：

| 标签 | 判定标准 | 能否直接支撑论文主结论 |
|---|---|---|
| `CORE` | 直接涉及物理学习、计算建模、AI 支架/反馈、师范生或本研究的关键测量/设计 | 只能支撑对应构念，不能自动支撑本研究的因果结论 |
| `SUPPORT` | 可用于任务设计、理论框架、量规或边界条件，但样本/干预/结果不完全匹配 | 只能支撑方法或解释边界 |
| `BACKGROUND` | 综述、趋势、AI 素养、STEM/PBL 背景或伦理讨论 | 不能支撑干预效果数字 |
| `HOLD` | 与研究问题关联弱、文件名与内容不符、重复或来源尚未核对 | 不进入正式证据检索 |

正式论文中的文献主张仍须逐篇人工核对全文、方法、样本、结果和 DOI；摘要级判断不能替代 `human_verified`。

## 3. 原有 101 篇与新增补充全文的实际用途判断

### 3.1 可以进入 `physics-ai-stem-core` 的材料

以下不是“论文质量排名”，而是对本 Demo 的直接用途：

- AIMS：01（物理教育 AI 系统综述）、03（物理 PBL/热力学任务）、05（师范生数字支架）、06（STEM 项目任务）、08/09/16（师范生 AI 接受与素养）、13/14（设计与工程任务）、17（AI 教育整合框架）、18（ChatGPT 编程助教）、19（学术诚信/反馈边界）、21/22（科学整合与建模思维）、29（图形理解）、35（计算建模项目）、40/41（多重表征与评价）、43（数学建模元分析）、44（选择性/有边界的 AI 使用）。
- `papers`：McLure iSTEM 项目综述、Baptista 电路 STEM、Ben-Zion 生成式 AI 物理模拟、Bitzenbauer 物理活动、Chen LLM 评分解释、Dahlkemper 学生评价 AI、Kuchemann 师范生物理任务、Polverini 运动学图表与物理教育两篇、Yeadon AI 物理综述、Computational Physics Essays、Gambrell 计算思维评价、Kurniawan/Wu 科学建模技能。
- IJSTEM/物理专题：Nader 物理 PBL 自我效能、物理设计—科学连接、STEM-PBL 物理模块、实验室脚手架、元认知脚手架、技术增强反馈、物理模拟/表征教程、ElectronixTutor、bMCU 力学概念测量、计算/模拟课程设计。

这些材料足以构成主 Demo 的“证据地图”，但其中多数是机制或设计证据，不是本研究干预的直接复制证据。

### 3.2 适合 `SUPPORT` 的材料

物理学习动机、自我效能、身份、教师发展、STEM 数字技术、项目式学习一般综述、AI 接受度量表和泛学科建模研究有用，但它们主要用于：

- 选择协变量或解释变量；
- 设计学习投入、自我效能、认知负荷等次要结果；
- 说明为什么需要静态提示对照、无 AI 任务和过程日志；
- 约束外推范围。

它们不能被写成“生成式 AI 分层支架已经被证明能提高师范生 Python 物理建模能力”。

### 3.3 应暂缓进入主检索的材料

与本研究只有远距离关系的心理健康、护理、体育、艺术、创业、纯职业取向、纯数学或纯元宇宙研究，不应和物理 AI 证据混在同一检索项目。它们可保留作背景候选，但在 `physics-ai-stem-core` 中应标记 `HOLD` 或不导入。

两个文件已明确隔离：

- `Tufino2025_NotebookLM_Socratic_Physics.pdf` 实际内容是 LLM 知识编辑基准，不是 NotebookLM 物理研究；
- `PICUP_Computation_Physics_Review.pdf` 实际内容是高中 ISLE 主动学习文章，不是 PICUP 计算物理综述。

## 4. 对主 Demo 各证据格子的判断

| 证据格子 | 现有覆盖 | 判断 | 说明 |
|---|---:|---|---|
| 物理 STEM/PBL 任务与真实情境 | 多篇直接研究 | **足够** | 可支撑任务 A/B 的情境化、建模和项目式结构 |
| 生成式 AI 在物理教育中的能力、错误与风险 | 综述、物理任务、图表和反馈研究 | **背景足够，因果不足** | 能支撑为什么采用分层、受限、可审计的支架 |
| 师范生/未来教师背景 | AI 接受、AI 素养、师范生任务研究 | **部分足够** | 可设计前测和协变量，但缺少“师范生 Python 物理建模”直接研究 |
| Python/计算物理建模 | 少量计算思维、VPython、计算项目研究 | **不足** | 需要更明确的建模实践、代码/模型评分和教师学习材料 |
| 任务 A/B 的物理与数学等值 | 有物理表征、模型和任务设计文献 | **不足** | 不能仅凭两题都叫“物理题”就宣称等值，仍需 TaskEquivalenceReport |
| 任务 C 无 AI 近迁移/远迁移 | 有迁移与等构题研究，但未形成当前任务量规 | **不足** | 必须补迁移测量和脚手架撤除证据 |
| 提示依赖、过度依赖与 AI 使用质量 | 学生评价 AI、AI 风险、选择性使用研究 | **明显不足** | 需同时记录提示次数、提示层级、复制率、修改率、独立解释和错误识别 |
| 重复测量、顺序平衡、前测协变量 | 当前集合较弱 | **不足** | 设计论证不能被普通两独立组 ANCOVA 替代 |
| 伦理、学术诚信、数据审计 | 有框架和风险讨论 | **足够作边界** | 还需结合本校伦理审批和真实数据方案 |

## 5. 必须补充的论文（已核对正式来源，待下载和全文人工审核）

下面只补“能填补缺口”的论文，不再扩张泛 STEM 数量。网页/DOI 元数据已经核对；正式进入 `source_verified` 前仍应保存全文、检查方法和版本。

| 优先级 | 论文 | DOI/正式来源 | 填补的缺口 |
|---|---|---|---|
| P0 | Weller et al., *Development and illustration of a framework for computational thinking practices in introductory physics* (2022) | [10.1103/PhysRevPhysEducRes.18.020106](https://doi.org/10.1103/PhysRevPhysEducRes.18.020106) | 将 Python/VPython 物理活动拆成可评分的计算思维实践 |
| P0 | Mashood et al., *Participatory approach to introduce computational modeling at the undergraduate level* (2022) | [10.1103/PhysRevPhysEducRes.18.020136](https://doi.org/10.1103/PhysRevPhysEducRes.18.020136) | 计算建模教学模块、教师实施和从推导到模型的渐进支架 |
| P0 | Caballero et al., *Implementing and assessing computational modeling in introductory mechanics* (2012) | [10.1103/PhysRevSTPER.8.020106](https://doi.org/10.1103/PhysRevSTPER.8.020106) | 机械运动建模和建模能力评价，直接贴近抛体运动任务 |
| P0 | Pawlak et al., *Learning assistant approaches to teaching computational physics problems in a problem-based learning course* (2020) | [10.1103/PhysRevPhysEducRes.16.010139](https://doi.org/10.1103/PhysRevPhysEducRes.16.010139) | 计算物理 PBL 中的支架与过程支持 |
| P0 | *Using an isomorphic problem pair to learn introductory physics: Transferring from a two-step problem to a three-step problem* (2013) | [10.1103/PhysRevSTPER.9.020114](https://doi.org/10.1103/PhysRevSTPER.9.020114) | 近迁移/远迁移任务和“会做原题但不能迁移”的测量逻辑 |
| P0 | Sayer, Marshman & Singh, *Facilitating students’ problem-solving performance by explicitly addressing the problem-solving approach* (2016) | [10.1103/PhysRevPhysEducRes.12.020133](https://doi.org/10.1103/PhysRevPhysEducRes.12.020133) | 建模—指导—逐步撤除支架（weaning）的设计依据 |
| P1 | Phillips et al., *Physicality, modeling, and agency in a computational physics class* (2023) | [10.1103/PhysRevPhysEducRes.19.010121](https://doi.org/10.1103/PhysRevPhysEducRes.19.010121) | 计算物理中物理意义、模型构建和学习者能动性的联合评价 |
| P1 | Lademann, Henze & Becker-Genschow, *Augmenting learning environments using AI custom chatbots: Effects on learning performance, cognitive load, and affective variables* (2025) | [10.1103/PhysRevPhysEducRes.21.010147](https://doi.org/10.1103/PhysRevPhysEducRes.21.010147) | AI 聊天机器人干预、学习表现、认知负荷和情感结果的对照依据 |
| P1 | Kortemeyer & Bauer, *Cheat sites and artificial intelligence usage in online introductory physics courses* (2024) | [10.1103/PhysRevPhysEducRes.20.010145](https://doi.org/10.1103/PhysRevPhysEducRes.20.010145) | AI/外部帮助使用日志与监督性评估之间的关系，支持提示依赖边界 |
| P1 | Wan & Chen, *Accuracy of ChatGPT responses to physics comprehension questions* (2024) | [10.1103/PhysRevPhysEducRes.20.010152](https://doi.org/10.1103/PhysRevPhysEducRes.20.010152) | 物理 AI 反馈的正确性、解释质量与人工复核必要性 |
| P1 | Sirnoorkar & Rebello, *Introductory physics students’ valued features in AI feedback generated from self-crafted and engineered prompts* (2026) | [10.1103/v3pj-8491](https://doi.org/10.1103/v3pj-8491) | 提示工程、反馈特征和提示质量指标；正式版本需再核对发表状态 |
| P1 | Lademann et al., *Augmenting learning environments using AI custom chatbots* 的补充材料 | 通过 APS 正式论文页面获取 | 提取干预脚本、量规、认知负荷和效应估计，不凭摘要复制数字 |

补充策略是先加入 P0 的六篇，再加入 P1 的四篇；如果负责人只允许增加少量论文，优先 P0，不要用更多泛 STEM 论文填充数量。

### 本次定向检索新增的高匹配候选

本次检索又发现了几篇比泛 STEM 论文更贴近主 Demo 的研究。它们先登记为“候选补充”，不能因为检索到摘要就直接视为正式证据：

| 优先级 | 论文 | DOI/正式来源 | 建议用途 |
|---|---|---|---|
| P0 | Sijmkens, De Laet & De Cock, *Understanding and enhancing students’ use of evaluation strategies during physics problem solving through reflective prompts* (2026) | [10.1103/y6cq-bklb](https://doi.org/10.1103/y6cq-bklb) | 直接支持反思提示、解题评价策略和后续迁移指标 |
| P0 | Jiang et al., *Generative AI for feedback and collaborative knowledge construction in preservice physics teacher education* (2026) | [10.1103/hm13-jv98](https://doi.org/10.1103/hm13-jv98) | 直接涉及师范生、GenAI 反馈、人工反馈对照和独立能力；尤其提醒“AI 辅助质量提高”不等于独立能力提高 |
| P0 | Tong et al., *DeepSeek-assisted physics instructional design: An empirical study of high school physics teaching* (2026) | [APS 正式文章页面](https://journals.aps.org/prper/recent) | 提供师范生 AI 交互日志、主动/被动提示模式和认知过程编码思路；需从正式页面补齐 DOI 后再入库 |
| P0 | Reshef-Israeli & Kapon, *Dynamics of collaborative modeling in an ill-structured real-world problem* (2026) | [APS 正式文章页面](https://journals.aps.org/prper/highlights) | 支持物理建模阶段、模型假设协调和时间序列过程编码 |
| P1 | Leblond et al., *Using digital prompts to support physics students’ self-regulated learning* (2026) | [10.1103/cftx-hfw5](https://doi.org/10.1103/cftx-hfw5) | 支持提示类型、学习自我调节、前测协变量和过程提示记录 |
| P1 | *When AI evaluates its own work: Validating learner-initiated, AI-generated physics practice problems* (2026) | [10.1103/9hh9-vt4d](https://doi.org/10.1103/9hh9-vt4d) | 支持 AI 生成任务的专家核验和结构性质量检查，不直接支撑学习效果 |
| P1 | Karlsen & Aalbergsjø, *Developing pre-service teachers’ TPACK for programming simulations* (2026) | [10.1007/s11423-026-10674-3](https://doi.org/10.1007/s11423-026-10674-3) | 补充师范生编程模拟、计算思维与教学知识之间的连接 |

本次检索后，建议优先下载并全文审核前四篇 P0 候选；它们分别填补了“迁移提示”“师范生 AI 反馈”“交互过程日志”“物理建模过程”四个缺口。APS 页面显示，Sijmkens 等人的研究确实记录了提示触发的评价策略及其向后续问题迁移的情况；Jiang 等人的研究则直接比较了师范生接受专家、助教或 GenAI 反馈后的设计质量与独立能力，二者都比泛泛的 AI 接受度调查更适合当前 Demo。[Sijmkens 等人](https://journals.aps.org/prper/abstract/10.1103/y6cq-bklb)、[Jiang 等人](https://journals.aps.org/prper/abstract/10.1103/hm13-jv98)

目前已实际下载 4 篇开放获取补充全文，均已计算 SHA256：Karlsen 2026（22 页，师范生编程模拟）、Sorge 2025（13 页，师范生物理反思的 LLM 个性化反馈）、Gerdesmann 2026（34 页，物理模拟探究表现因素）和 Wulff & Kubsch 2025（7 页，GenAI 在 STEM 学习中的风险与“表现不等于学习”边界）。这些文件仍需人工全文审核后才能升级为正式证据；其余 APS 候选仅登记了正式 DOI/页面，没有把反爬验证页伪装成 PDF。

补充全文目录：

```text
data/local/literature_pdfs/additional_instance_support/
├── Gerdesmann2026_SimulationInquiryPhysics.pdf
├── Karlsen2026_PSTP_ProgrammingSimulations.pdf
├── Sorge2025_LLM_Feedback_PreservicePhysicsTeachers.pdf
└── Wulff2025_GenAI_STEM_LearningRisks.pdf
```

另外加入 1 份开放课程框架（不计入论文 PDF 数量）：

```text
data/local/literature_pdfs/additional_instance_support/non_paper_sources/
└── AAPT2016_ComputationalPhysics_UndergraduateCurriculum.pdf
```

该 AAPT 文件为 25 页官方课程建议，包含计算物理学习成果、代码调试/验证、数据可视化、科学论证以及运动和振子等示例任务，适合直接转化为 `TaskCard` 和 `ModelingPerformanceRubric` 的设计依据。配套 CPSUP 的大文件下载出现了不完整传输，已隔离，未把残缺文件放入知识库。

补充文件的来源、用途、开放获取状态和 SHA256 记录在 `data/local/literature_pdfs/additional_instance_support/supplement_manifest.json`。这些本地材料目录仍由 `data/local/` 忽略规则保护，不会自动进入 Git 提交。

## 6. 这批材料是否足以演示全流程

### 可以演示的内容

1. 用户提出研究想法后，系统如何从物理 STEM、AI 物理、计算建模和迁移文献构建 EvidenceMatrix；
2. 如何识别“AI 可能提高即时完成表现”与“AI 是否提高独立建模能力”不是同一个问题；
3. 如何据此形成实验组分层支架、对照组静态提示、任务 C 无 AI 的 StudyProtocol；
4. 如何把论文中的建模实践、迁移困难、认知负荷和提示风险映射到 AnalysisPlan 的变量与量规；
5. 如何展示一篇论文不能替代另一篇论文：AI 物理能力论文只能支撑工具边界，不能直接支撑学习效果因果结论。

### 还不能诚实演示的内容

- 不能声称已有文献证明本研究干预对师范生 Python 抛体运动/弹簧振子建模有效；
- 不能从现有材料直接生成一个经过验证的“提示依赖量表”；
- 不能仅凭文献宣布任务 A/B 等值或样本量已确定；
- 不能把现有 102 篇的数量当作证据充分性的指标。

## 7. 建议的下一步顺序

1. 先把现有 102 篇按 `CORE/SUPPORT/BACKGROUND/HOLD` 写入机器可读清单；
2. 下载并人工核验 P0 六篇，提取样本、任务、干预、测量、效应与限制；
3. 为任务 A（抛体运动）、任务 B（弹簧振子）和任务 C（无 AI 迁移）各建立一页 TaskCard；
4. 单独建立 `PromptDependenceMeasureDraft` 和 `TaskEquivalenceReport` 草案，明确哪些是文献依据、哪些是本研究自定义指标；
5. 只有完成以上审核后，才决定是否再补第二轮论文。第二轮不应超过 10 篇，并且必须针对尚未填满的证据格子。

## 8. 当前应给组员的简短结论

这批资料不是“没用”，而是用途层级不同：它已经足够搭出主 Demo 的文献证据骨架，但不能把 102 篇都当作核心证据，也不能据此直接宣称研究假设已经被支持。当前真正缺的不是更多泛 STEM 论文，而是计算物理建模、迁移测量、提示依赖和重复测量设计的少量高匹配论文。补齐 P0 六篇并完成全文人工审核后，才适合进入 StudyProtocol 和 PreregisteredAnalysisPlan 的正式编译。
