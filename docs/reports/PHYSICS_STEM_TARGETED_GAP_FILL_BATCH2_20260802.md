# Physics STEM Targeted Gap-Fill Batch 2

## Scope

This batch adds six openly accessible materials that address the main remaining gaps in the planned demonstration: AI feedback quality, prompt dependence, scientific verification of AI answers, evidence-centered feedback design, and teacher AI competency. These files are supplementary evidence; they do not prove the effectiveness of the planned preservice-teacher intervention.

All six files have a recorded SHA256 and a valid PDF signature. They remain `human_full_text_review_pending` until a reviewer checks the methods, sample, limitations, and relevance to the target population.

## Added materials

| File | Role | Gap covered | Source |
|---|---|---|---|
| `Dahlkemper2023_Students_Evaluate_AI_PhysicsResponses.pdf` | SUPPORT | Students' ability to judge scientific accuracy of AI physics responses | [arXiv:2304.05906](https://arxiv.org/abs/2304.05906) |
| `Dai2025_AI_Feedback_UsagePatterns.pdf` | SUPPORT | AI-feedback usage patterns, achievement, and autonomy | [arXiv:2505.08672](https://arxiv.org/abs/2505.08672) |
| `ElAdawy2024_LLM_FormativeFeedback_Physics.pdf` | SUPPORT | Human versus AI formative feedback and rubric prompting | [PER-Central open PDF](https://www.per-central.org/document/servefile.cfm?DocID=5950&ID=16883) |
| `Maus2026_EvidenceCentered_LLM_PhysicsFeedback.pdf` | SUPPORT | Evidence-centered feedback design and LLM error checking | [arXiv:2512.10785](https://arxiv.org/abs/2512.10785) |
| `Sirnoorkar2025_AI_Feedback_Prompts.pdf` | SUPPORT | Structured prompts and feedback preferences in introductory physics | [arXiv:2508.09825](https://arxiv.org/abs/2508.09825) |
| `UNESCO2024_AI_Competency_Framework_Teachers.pdf` | FRAMEWORK | Teacher AI competency, ethics, pedagogy, and assessment | [UCL open-access copy](https://discovery.ucl.ac.uk/id/eprint/10196729/) |

## Full-text audit notes

### Dahlkemper, Lahme, and Klein (2023)

The study involved 102 first- and second-year physics students evaluating responses to introductory mechanics comprehension questions. The AI responses were inaccurate, incomplete, or misleading, and students did not always distinguish linguistic quality from scientific accuracy. This supports the need for source verification and human review of AI-generated explanations. It does not measure Python modeling, preservice teachers, or intervention effects.

### Dai et al. (2025)

Two randomized studies with a total of 387 high-school students examined how different AI-feedback usage patterns affected physics achievement and autonomy. Effects varied by achievement level and whether help was compulsory or learner-controlled. This is useful for designing prompt/use logs and a dependence measure, but the population and platform differ from the planned preservice-teacher study.

### El-Adawy, MacDonagh, and Abdelhafez (2024)

This PERC proceedings paper compares human and AI formative feedback on introductory mechanics synthesis questions. Instructor guidance and specific rubrics improved usefulness, while edge cases and response-specificity remained stronger areas for human feedback. The paper is a methodological support source, not an outcome evaluation of the planned experiment.

### Maus et al. (2026)

The paper presents an evidence-centered design for an LLM physics-feedback system and reports that a nontrivial fraction of feedback cases contained errors. It is useful for defining feedback validation, error categories, and human oversight. It is not direct evidence of learning gains for preservice teachers.

### Sirnoorkar and Rebello (2025)

Approximately 1,200 introductory physics students compared self-crafted prompts with prompts using structured prompt-engineering and feedback principles. Structured prompts were generally preferred, but preference was polarized. This supports comparing scaffold levels and recording prompt usage; it does not establish transfer or code-generation outcomes.

### UNESCO (2024)

The framework defines 15 teacher AI competencies across five dimensions—human-centred mindset, ethics of AI, AI foundations and applications, AI pedagogy, and AI for professional learning—with Acquire, Deepen, and Create progression levels. It is a normative framework, not an empirical treatment-effect study. The UCL copy records the CC-BY-SA 3.0 IGO open-access license.

## Integrity and relevance decisions

- Duplicate SHA256 matches against the active corpus: none found for this batch.
- All six files begin with a valid `%PDF` signature and are parseable by the local PDF reader.
- No file is marked `human_verified`.
- No file should be cited as direct evidence that generative-AI scaffolding improves Python physics modeling for preservice teachers.
- The batch is intended to support measurement design, risk controls, and interpretation boundaries.

## Full-text audit completed

### Audit rule

Each file was checked for bibliographic identity, PDF integrity, study design, sample or normative scope, measured variables, reported results, limitations, and fit to the target demonstration. `human_verified` was not assigned by this audit; that status still requires the project's designated human reviewer.

### Audit results

| File | Design and scope verified | Decision | Allowed use | Main boundary |
|---|---|---|---|---|
| `Dahlkemper2023_Students_Evaluate_AI_PhysicsResponses.pdf` | Survey of 102 first- and second-year physics students; three mechanics questions with randomized response order; perceived scientific accuracy and linguistic quality | RETAIN as SUPPORT | AI-answer verification, scientific-accuracy checking, critical-evaluation activity | Perception study; no Python modeling, no intervention effect, and the sample solution was researcher-created |
| `Dai2025_AI_Feedback_UsagePatterns.pdf` | Two five-week randomized studies; Experiment 1 recruited 160 and analyzed 121 complete cases; Experiment 2 recruited 373 and analyzed 266 complete cases; high-school physics students | RETAIN as SUPPORT | Usage-pattern logging, autonomy, heterogeneous effects, and prompt-dependence hypotheses | Different age group and platform; not preservice teachers, not Python modeling, and the manuscript is an arXiv preprint |
| `ElAdawy2024_LLM_FormativeFeedback_Physics.pdf` | Mixed-method comparison of AI and human feedback in a 700-student introductory mechanics course; preliminary analysis of two synthesis questions | RETAIN as SUPPORT | Feedback rubric design, human-versus-AI comparison, and human review boundaries | Preliminary course study; responses were optional/subsampled; no causal learning-gain claim |
| `Maus2026_EvidenceCentered_LLM_PhysicsFeedback.pdf` | Evidence-centered feedback system evaluated by voluntary German Physics Olympiad participants across six problems; 64 problem-level ratings | RETAIN as SUPPORT | Evidence-centered feedback, correctness checks, and risk of unnoticed AI errors | Secondary-school Olympiad volunteers; perceived usefulness is not learning gain; feedback errors remained possible |
| `Sirnoorkar2025_AI_Feedback_Prompts.pdf` | Extra-credit activity in an introductory physics course; students compared self-crafted, structured, and structured-plus-effective-feedback prompts | RETAIN as SUPPORT | Prompt-policy design, layered scaffolding, and prompt-use logging | Preference ranking only; no demonstrated improvement in physics performance, transfer, or coding |
| `UNESCO2024_AI_Competency_Framework_Teachers.pdf` | Normative framework defining 15 teacher AI competencies across five dimensions and Acquire/Deepen/Create progression | RETAIN as FRAMEWORK | Teacher-AI competency dimensions, ethics, human agency, and assessment planning | Not an empirical intervention study and cannot support an effect-size claim |

### Evidence classification decision

No item in this batch is promoted to `CORE` evidence. The five empirical papers are retained as `SUPPORT` because their populations, tasks, or outcomes do not exactly match the planned preservice-teacher Python modeling experiment. The UNESCO document remains a `FRAMEWORK` artifact. This is a deliberate precision decision, not a quality rejection.

### Claim-use rules

- `LITERATURE`/`RESULT` claims may report what each individual study observed, with its sample and design attached.
- `METHOD` claims may use these materials to justify feedback rubrics, AI-use logs, source verification, and human oversight.
- `LIMITATION` claims may use the documented mismatch between perceived usefulness and actual correctness, or between feedback use and autonomy.
- None of these files may support the statement that generative-AI scaffolding has already improved Python physics modeling for preservice teachers.
- Any cross-study interpretation remains an `INTERPRETATION` claim requiring explicit human review.

### Final audit decision

All six files are relevant enough to remain in the knowledge base as support/framework materials. No duplicate or clearly irrelevant file was found, so no deletion is recommended for this batch. The batch is ready for human verification and later chunking, but it should not yet be used as `human_verified` evidence.

## Remaining candidates not downloaded

Weller et al. (2022), Pawlak et al. (2020), and Mashood et al. (2022) remain high-value computational-modeling sources. Their official APS endpoints returned HTTP 403 from this network. Pawlak and Mashood have authoritative open-access metadata; they should be added later only when an accessible full text can be obtained and its license recorded. They are not counted in this batch.

## Collection impact

Previous active corpus: 112 PDFs.

This batch: 6 PDFs.

Expected active corpus after import: 118 PDFs, subject to the existing active-corpus counting rule and human review decisions.
