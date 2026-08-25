# Physics STEM Targeted Gap-Fill Batch 3

## Scope

This batch targets the remaining high-value gaps for the planned demonstration: direct preservice-physics-teacher context, validated physics problem-solving measurement, computational-thinking learning goals, and criterion-based evaluation of AI outputs.

## Retained files

| File | Role | Intended use | Source |
|---|---|---|---|
| `Chen2026_AI_Supported_CTD_PBL_PreservicePhysicsTeachers.pdf` | SUPPORT | Preservice physics teacher education, bounded AI scaffolding, TPACK and collaborative problem solving | [MDPI article](https://www.mdpi.com/2078-2489/17/7/688) |
| `Docktor2016_PhysicsProblemSolvingRubric.pdf` | CORE | Five-dimensional physics problem-solving rubric and measurement validity | [APS article record](https://doi.org/10.1103/PhysRevPhysEducRes.12.010130) |
| `Sadidi2024_CriterionBasedReflection_ProspectivePhysicsTeachers.pdf` | SUPPORT | Criterion-based reflection and critical evaluation of ChatGPT output by prospective physics teachers | [arXiv:2410.01354](https://arxiv.org/abs/2410.01354) |
| `Weller2021_ComputationalThinking_LearningGoals.pdf` | FRAMEWORK | Fourteen computational-thinking practices and learning-goal framing in computational physics | [arXiv:2105.07981](https://arxiv.org/abs/2105.07981) |

## Duplicate handling

The downloaded Küchemann et al. (2023) article was byte-for-byte identical to an existing active file. It was not added a second time; it was moved to `data/local/_quarantine_duplicate_20260802/Kuechemann2023_duplicate_of_existing.pdf`. The existing active copy remains the canonical copy.

## Preliminary relevance assessment

- **Chen and Osman (2026):** direct target-population relevance, but the outcomes are self-reported TPACK and perceived collaborative problem solving rather than Python modeling performance. Retain as SUPPORT until full-text audit.
- **Docktor et al. (2016):** strongest measurement addition in this batch. Its five dimensions—Useful Description, Physics Approach, Specific Application of Physics, Mathematical Procedures, and Logical Progression—can inform the modeling-performance rubric. It does not evaluate AI or transfer by itself.
- **Sadidi and Prestel (2024):** directly supports criterion-based AI evaluation and critical reflection in prospective physics teachers. It measures perceptions and evaluation, not Python performance.
- **Weller et al. (2021):** framework material for computational-thinking learning goals. The later published version should not be added separately unless the project deliberately chooses the published version as the canonical record.

## Verification status

- Four retained files have valid PDF signatures and recorded SHA256 values.
- Duplicate SHA256 groups in the active corpus after quarantine: none.
- Expected active corpus after import: 122 PDFs.
- Full-text audit: pending.
- `human_verified`: not assigned.

These files should not yet be used as human-verified evidence. After full-text audit, the likely final roles are one CORE measurement source, two SUPPORT empirical sources, and one FRAMEWORK source.

## Full-text audit completed

### Audit rule

Each retained PDF was checked for bibliographic identity, sample or framework scope, design, measures, results, limitations, and fit to the planned preservice-teacher Python physics modeling demonstration. This audit does not assign `human_verified`; that status still requires the designated human reviewer.

### Audit results

| File | Verified design and evidence | Decision | Allowed use | Boundary |
|---|---|---|---|---|
| `Chen2026_AI_Supported_CTD_PBL_PreservicePhysicsTeachers.pdf` | 130 third-year preservice physics teachers; two intact classes of 65; 8-week quasi-experimental pre/post design; DeepSeek used as a bounded scaffold; outcomes were self-reported TPACK and perceived CPS | RETAIN as SUPPORT | Direct teacher-education context, bounded AI scaffolding, human verification procedures, and candidate covariates | Not Python modeling performance; no objective teaching-performance measure; intact-class assignment leaves selection concerns; do not generalize its effect sizes to the planned experiment |
| `Docktor2016_PhysicsProblemSolvingRubric.pdf` | Rubric development and validity/reliability studies across 918 scored problem instances, 160 student solutions, 159 instructor/textbook solutions, expert raters, and trained graduate raters | RETAIN as CORE measurement source | Build the modeling-performance rubric around Useful Description, Physics Approach, Specific Application, Mathematical Procedures, and Logical Progression | Validates written physics problem solving, not code execution, AI support, or transfer; local task adaptation and rater training remain necessary |
| `Sadidi2024_CriterionBasedReflection_ProspectivePhysicsTeachers.pdf` | 39 German physics teacher students; criterion-based evaluation of ChatGPT 3.5 didactical content with pre/post questionnaires and group discussion | RETAIN as SUPPORT | Critical AI evaluation, source checking, criteria-based reflection, and confirmation-bias risk | Small, single-context perception study; didactical tasks rather than Python modeling; no causal performance claim |
| `Weller2021_ComputationalThinking_LearningGoals.pdf` | Framework built from literature review and classroom video data; 14 computational-thinking practices in six categories; independent coding agreement exceeded 85% on sampled video segments | RETAIN as FRAMEWORK | Define code/modeling practices, learning objectives, and observable rubric indicators | Framework and existence proofs, not an intervention effect study; developed around computationally integrated introductory physics and VPython contexts, so Python-task adaptation is required |

### Important interpretation

The Chen et al. paper is the strongest population match in this batch, but its positive findings concern self-reported TPACK and perceived collaborative problem solving. It cannot be used as direct evidence that generative-AI scaffolding improves Python physics modeling or unaided transfer. Docktor et al. is the strongest measurement addition and can inform the scoring structure, but it must be adapted and pilot-tested for code, model validation, visualization, and transfer.

### Claim-use rules

- `RESULT` claims may state only the results of the individual study with its design, population, and outcome type.
- `METHOD` claims may use Docktor's rubric dimensions, Weller's computational-thinking practices, and the criterion-based reflection procedure to justify measurement and verification design.
- `LIMITATION` claims must preserve the distinction between self-report/perception and objective performance.
- `INTERPRETATION` claims connecting these studies to the planned intervention require explicit human review.

### Final audit decision

All four retained files are relevant and should remain in the knowledge base. No deletion is recommended. The duplicate Küchemann file remains quarantined and the existing active copy remains canonical. This batch is suitable for human review and later chunking, but only after the project owner confirms the proposed role labels.
