# Physics STEM Targeted Gap-Fill Report

## Scope

This batch supplements the local physics STEM instance corpus for the main demonstration on generative-AI scaffolding, Python physics modeling, transfer, and prompt dependence. It deliberately targets missing evidence categories rather than adding broad STEM papers.

The six retained files are readable PDFs, have a recorded SHA256, and remain `human_full_text_review_pending`. They must not be treated as `human_verified` evidence until a reviewer checks the full text, methods, sample, and limitations.

## Added materials

| File | Role | Gap covered | Source |
|---|---|---|---|
| `Caballero2012_ComputationalModeling_IntroMechanics.pdf` | CORE | Computational modeling instruction, novel-task assessment, program error patterns | [arXiv:1107.5216](https://arxiv.org/abs/1107.5216) |
| `Lademann2025_AI_Chatbot_Learning.pdf` | SUPPORT | AI-supported learning, cognitive load, self-efficacy, and performance boundaries | [University of Cologne repository](https://kups.ub.uni-koeln.de/79825/1/PhysRevPhysEducRes.21.010147.pdf) |
| `Orban2019_ComputationalThinking_IntroPhysics.pdf` | SUPPORT | Computational-thinking objectives and assessment framing | [arXiv:1907.08079](https://arxiv.org/abs/1907.08079) |
| `Phillips2023_ComputationalPhysics_Agency.pdf` | CORE | Computational modeling practices, agency, iteration, and Python course work | [arXiv:2203.04134](https://arxiv.org/abs/2203.04134) |
| `Singh2008_IsomorphicProblems_Transfer.pdf` | CORE | Isomorphic problem pairs and transfer assessment | [arXiv:1602.07678](https://arxiv.org/abs/1602.07678) |
| `Gambrell2023_ComputationalThinking_Assessment.pdf` | SUPPORT | Generalized computational-thinking assessment in introductory physics | [arXiv:2308.03593](https://arxiv.org/abs/2308.03593) |

## Verification summary

- Previous active corpus: 106 PDFs.
- This batch: 6 retained PDFs.
- Current active local corpus: 112 PDFs.
- Duplicate SHA256 matches against the active corpus: none.
- Parseable PDFs in this batch: 6/6.
- Formal source metadata: recorded in `targeted_gap_fill_manifest.json`.
- Human full-text review: pending for all 6 retained files.

## Not downloaded in this batch

Several official APS PDF endpoints returned HTTP 403 from the current network environment. No unofficial mirror was used. The following remain candidates with DOI/source metadata only until an accessible official or institutional copy is found:

- Weller et al. (2022), computational-thinking practices framework;
- Mashood et al. (2022), participatory computational modeling;
- Pawlak et al. (2020), computational physics in problem-based learning;
- Chen and Wan (2025), LLM grading and feedback;
- Kortemeyer and Bauer (2024), AI/help-seeking usage in physics courses;
- Dunlap et al. (2025), LLM assumptions in an inclined-plane problem;
- Sirnoorkar and Rebello (2026), valued features in AI feedback;
- UNESCO (2023), Guidance for generative AI in education and research PDF.

These candidates are not counted as downloaded or verified materials.

## Quarantined download

The file initially downloaded under `Nohl2025_AI_GeneratedPhysicsPracticeValidation.pdf` did not match the requested title. Its first page identified a different review on ethical and societal impacts of generative AI in higher computing education. It was moved, without deletion, to:

`data/local/_quarantine_wrong_files_20260802/arxiv_2511.15768_actual_GenAI_Computing_Ethics_Review.pdf`

It is excluded from the manifest and from the active corpus.

## Full-text audit decisions

### Caballero et al. (2012) — CORE

- **Design:** computational-modeling instruction plus a proctored novel-task assessment in a calculus-based introductory mechanics course.
- **Sample and data:** 1,357 students completed 14 computational-modeling homework questions; a novel central-force task was used for the proctored evaluation; 60.4% completed it successfully. A coded subset of 324 submitted programs was used for error analysis, with 91% inter-rater agreement.
- **Usable evidence:** computational-modeling proficiency can be assessed through a new problem rather than only repeated exercises; recurring errors can be represented as code/model error categories.
- **Boundary:** no GenAI intervention, no preservice-teacher sample, single course context, and VPython rather than the planned Python task environment.

### Lademann et al. (2025) — SUPPORT

- **Design:** randomized controlled study with 214 German sixth-grade students (146 female, 66 male, 2 not reported; mean age 11.7).
- **Intervention and measures:** AI-generated explanatory material about proportional relationships in mathematical and physical contexts was compared with textbook material; the study measured emotions, situational interest, intrinsic/extrinsic cognitive load, self-efficacy, and a performance test.
- **Result:** the AI-material group showed higher positive-activating emotions, situational interest, and self-efficacy and lower cognitive load; the overall performance test difference was not significant (reported p = 0.750).
- **Boundary:** the material was generated in advance and supplied on paper; students did not independently interact with the chatbot. The sample is younger than the target preservice teachers, and the study does not test Python modeling or transfer.

### Orban and Teeling-Smith (2019) — SUPPORT

- **Design:** conceptual and instructional framework, not an intervention study with a participant sample.
- **Usable evidence:** computational thinking in physics can be operationalized through code reading, simulation/modeling, multiple representations, testing, and reasoning about model outputs; air-drag examples are directly relevant to a projectile task.
- **Boundary:** examples and recommendations are not effect estimates and must not be cited as evidence that an intervention improves learning.

### Phillips et al. (2023) — CORE

- **Design:** qualitative content analysis of student work in a computational physics course using a revised metamodel of physics modeling practices.
- **Setting and data:** the course was implemented across 2019–2021 iterations of approximately 18–30 students each; the paper analyzes the Spring 2019 implementation most thoroughly. Students used Python and Jupyter in an oscillator-making project.
- **Usable evidence:** model building is iterative and includes planning, implementation, running, testing/debugging, validation or cross-checking, visualization, interpretation, conclusion, and reporting; the framework is suitable for a modeling-performance rubric.
- **Boundary:** no control group, no causal estimate, and no GenAI or preservice-teacher comparison.

### Singh (2008) — CORE

- **Design:** isomorphic-problem study across nine calculus-based introductory physics courses, combining written responses and individual discussions.
- **Usable evidence:** quantitative/conceptual isomorphic pairs can probe transfer; context can change difficulty; students often fail to transform a conceptual question into a quantitative representation even when explicitly encouraged; robust misconceptions can block transfer.
- **Boundary:** this is not a repeated-measures AI intervention and does not specify the project’s Task A/B/C content. It supports task-equivalence and transfer design, not a claim about AI effects.

### Gambrell and Brewe (2023) — SUPPORT

- **Design:** qualitative grounded-theory/constant-comparison analysis of 26 interviews with physicists (18 academic, 8 industry).
- **Usable evidence:** Python was mentioned by 20 participants (77%) and VPython by 14 (54%); frequently discussed assessment practices included reading and commenting on code, visualization, identifying the physics, scaffolding incomplete code, and configuring existing code rather than always writing from scratch. Curriculum capacity and incoming literacy were identified as constraints.
- **Boundary:** expert interviews are not student outcome data and do not validate a finished rubric by themselves.

## Review conclusion

- Retain Caballero, Phillips, and Singh as direct core evidence for computational modeling, modeling-performance assessment, and transfer design.
- Retain Orban and Gambrell as support/framework evidence for operational definitions and rubric construction.
- Retain Lademann as support evidence for the distinction between learning experience benefits and actual performance gains.
- Do not use any of the six papers to claim that the planned GenAI intervention has already been proven effective for preservice teachers.
