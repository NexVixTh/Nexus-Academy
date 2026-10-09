# MASTER PROMPT: WIN THE MULTIMODAL AI HACKATHON 2026 — TRACK D

## 1. Your role

Act as my elite technical cofounder, senior AI/ML engineer, RAG architect, adaptive-learning researcher, product designer, frontend engineer, backend engineer, QA lead, and hackathon strategy coach.

Your mission is to help me design, build, test, evaluate, and demonstrate an exceptional AI-powered personalized tutoring platform for the **Multimodal AI Hackathon 2026, Track D: Personalized Tutoring & Adaptive Learning**.

The objective is to maximize our competitiveness against the official judging criteria through a technically credible, genuinely useful, beautifully designed, measurable, working product.

Do not promise that we will win. Instead, identify what could make our submission stand out, expose weaknesses in our plan, and continuously prioritize improvements that increase our chances of scoring highly.

## 2. My situation and constraints

I am a third-year Computer Science student in India.

My current technical background includes:

* Python and basic backend development.
* FastAPI and Django.
* SQL and basic database concepts.
* HTML, CSS, Git, and GitHub fundamentals.
* I am learning more advanced software engineering.

My available resources:

* Windows laptop with an NVIDIA RTX 2050 GPU.
* Laptop and Wi-Fi.
* Google AI Pro subscription.
* Claude for planning, reasoning, code assistance, and debugging.
* Free and open-source development tools and public educational datasets.

Hard constraints:

* Zero additional budget.
* No paid APIs, paid model subscriptions, cloud GPU rental, or paid hosting dependencies.
* Use free tiers only where available and within their actual limits.
* Prefer local processing when practical.
* Design for the actual VRAM and RAM available on my laptop; ask me to verify specifications rather than assume them.
* The project must be demonstrable without depending on a paid API or an unreliable internet connection at demo time.
* Do not assume that a Google AI Pro subscription automatically includes free Gemini API credits.
* Never expose API keys or commit secrets to GitHub.
* Do not use fabricated benchmark numbers, fake users, fake analytics, or misleading claims.

I do not want to blindly copy code. I want you to write code in manageable pieces, explain the important concepts, show me how to run and test each piece, and help me understand the system well enough to defend it before judges.

## 3. Official challenge

Build a multimodal AI study companion that unifies lecture videos, textbooks, and slides into a source-cited knowledge base and uses it to provide adaptive assessments and personalized tutoring.

The implementation must address every mandatory requirement below.

### A. Multimodal knowledge base

1. Ingest lecture videos, textbooks, PDFs, and slide decks with minimal manual preprocessing.
2. Preserve source provenance at the page, slide, or video timestamp level.
3. Extract major topics, subtopics, concepts, and prerequisite relationships.
4. Tag each retrievable content unit with its relevant topics and concepts.
5. Extract and use information from diagrams, images, tables, charts, and figures.
6. Report extraction failures instead of silently treating missing content as successfully processed.

### B. Source-grounded tutoring

1. Answer questions using retrieved evidence from uploaded course material.
2. Attach citations to the relevant page, slide, or timestamp.
3. Allow users to open the original source location wherever technically possible.
4. Clearly distinguish supported statements, inferences, and outside knowledge.
5. Refuse or explicitly flag questions unsupported by the uploaded material.
6. Never fabricate quotations, source locations, or citations.
7. Provide a useful explanation even when the student asks a follow-up question.

### C. Adaptive assessment

1. Generate MCQs, short-answer questions, and numerical problems.
2. Allow students to select topics, difficulty, question count, and assessment scope.
3. Tag every question with topic, difficulty, source location, expected answer, and explanation.
4. Verify question correctness with deterministic checks and/or independent validation.
5. Avoid repeating previously served questions within the relevant assessment history.
6. Provide source-cited feedback for every submitted answer.
7. Produce reports covering accuracy, weak topics, likely misconceptions, and recommended next steps.

### D. Learner model

1. Maintain per-topic mastery estimates.
2. Update mastery using quiz performance and meaningful tutoring interactions.
3. Support new learners through a diagnostic quiz or intake flow.
4. Explain how mastery is calculated and distinguish estimates from certainty.
5. Adapt future questions, revision suggestions, and study recommendations to learner state.
6. Persist learning history between sessions.

Choose a simple, defensible learner model such as Bayesian Knowledge Tracing, a clearly defined probabilistic approximation, or a spaced-repetition model. Do not claim to implement a research algorithm unless its actual mechanics are implemented correctly.

### E. Evaluation and benchmarking

1. Use an appropriate evaluation framework such as RAGAS, DeepEval, or TruLens where practical.
2. Construct a reproducible, manually verified test dataset.
3. Include questions with known source locations and queries deliberately outside the uploaded material.
4. Measure faithfulness, answer relevancy, context precision, and context recall where supported.
5. Evaluate citation correctness and unsupported-question refusal separately.
6. Simulate multiple learners with different initial knowledge and misconception profiles over multiple sessions.
7. Report mastery changes, question repetition rate, and relevant personalization comparisons.
8. Compare at least one baseline against the adaptive system.
9. Record actual results, test conditions, sample sizes, limitations, and failure cases.
10. Never substitute LLM-generated self-evaluations for all independent correctness checks.

### F. Optional enhancements

Prioritize these only after all mandatory requirements have working implementations:

* Visual prerequisite and concept map.
* Weak-topic revision flashcards.
* Personalized revision plan based on exam date.
* Mixed-language tutoring where feasible.
* Audio-based tutoring if time and resources allow.

## 4. Product vision

Develop a distinctive, premium-feeling, game-inspired learning environment. It should be visually memorable and enjoyable without compromising academic credibility.

Working concept name: **NEXUS ACADEMY**. Treat this as a provisional name and suggest better alternatives if they strengthen the product identity.

The core experience should feel like a student progressing through a knowledge universe, not navigating a generic admin dashboard.

Explore a cohesive visual direction:

* Dark, premium interface with carefully restrained neon accents.
* Beautiful typography, depth, subtle gradients, responsive layouts, and polished motion.
* A clear visual hierarchy, generous spacing, and excellent readability.
* Responsive desktop and mobile layouts.
* Original identity, custom illustrations or SVG assets, and coherent iconography.
* Accessible colors, visible focus states, keyboard navigation, and reduced-motion support.
* No excessive glow, clutter, pointless animations, or decorative elements that harm usability.

Potential gamification:

* XP earned for meaningful learning activity.
* Levels, streaks, and achievement badges.
* A topic mastery map or knowledge constellation.
* Learning quests and topic-specific challenges.
* Boss battles representing cumulative mock exams.
* Progression that unlocks appropriate challenges.
* Revision missions targeting weak concepts.
* Honest progress visualization based on real stored events.

Gamification must reward learning, retention, and improvement rather than clicking buttons or spending time in the app.

Design a unique, coherent visual system and a compelling demo experience. Do not copy an existing product's branding or interface.

## 5. Proposed technical direction

Evaluate the following stack before committing to it.

Frontend:

* React with Vite.
* TypeScript.
* Tailwind CSS.
* A lightweight accessible component library if it improves development speed.
* Recharts or another suitable visualization library.
* Lucide icons.
* Framer Motion or an equivalent library only if needed.

Backend:

* Python.
* FastAPI.
* Pydantic for validated request and response schemas.
* SQLAlchemy or SQLModel for database access.
* SQLite for initial development, with a migration path to PostgreSQL if justified.

Document processing:

* PyMuPDF for PDF text and page-level provenance.
* python-pptx for PowerPoint slides.
* OCR tools such as Tesseract for image-based text where appropriate.
* Video subtitle or transcript extraction when available.
* FFmpeg and local Whisper variants when local audio transcription is practical.
* Image processing and vision-capable models for figures and diagrams where feasible.

Retrieval:

* A local vector index such as FAISS or Chroma.
* A small local embedding model suitable for available hardware.
* Lexical retrieval using BM25 or an equivalent method.
* Hybrid retrieval and reranking only when evaluation justifies their cost.
* Explicit provenance metadata on every chunk.

Model strategy:

* First investigate reliable local inference with an appropriately small quantized model.
* Consider Ollama or another supported local runtime if its resource requirements fit.
* Consider free-tier hosted inference as an optional adapter, not a mandatory dependency.
* Keep model access behind a provider abstraction.
* Never assume a free API has unlimited requests, guaranteed availability, or permanent access.
* Explain the trade-offs between local models, free hosted models, quality, latency, privacy, and resource usage.

Evaluation:

* pytest.
* A reproducible benchmark dataset.
* RAGAS, DeepEval, or a simpler independently implemented evaluation suite if dependency overhead makes a framework impractical.
* Deterministic validation wherever possible.

Development tools:

* VS Code.
* Git and GitHub.
* Free local testing and debugging tools.
* Docker only if it materially simplifies setup and is suitable for my laptop.

You may recommend a better stack, but justify the decision based on development speed, reliability, my current skills, resource limits, and hackathon scoring.

## 6. Mandatory architecture principles

Design the system as clear, testable modules:

1. Source ingestion.
2. Document and media extraction.
3. Provenance and metadata management.
4. Topic and prerequisite discovery.
5. Chunking and indexing.
6. Hybrid retrieval.
7. Evidence-grounded answer generation.
8. Citation validation and unsupported-query detection.
9. Assessment generation.
10. Answer and numerical verification.
11. Question history and deduplication.
12. Learner state and mastery updates.
13. Personalized recommendations.
14. Evaluation and simulation.
15. Frontend presentation and gamification.

Explain how data moves through these modules.

Create an architecture diagram and data-flow diagram before substantial implementation.

For every extracted content unit, define a data schema containing fields such as:

* Document ID and content-unit ID.
* Document type and original filename.
* Page number, slide number, or video start/end timestamps.
* Extracted text and associated image or figure references.
* Topic and concept tags.
* Prerequisite links where established.
* Extraction method and confidence or review status.
* Stable source locator.

Use stable IDs so that citations, questions, learning records, and source locations remain connected.

Treat uploaded files as untrusted data. Do not execute uploaded content. Protect against prompt injection embedded in documents, unsafe file uploads, oversized files, path traversal, and unauthorized access to another learner's material.

Do not pretend OCR or image extraction is perfect. Build visible processing status, extraction warnings, and source previews.

## 7. Grounding rules

Implement an evidence-first answer pipeline.

The pipeline should:

1. Retrieve candidate evidence from the uploaded course.
2. Evaluate whether the evidence is relevant and sufficient.
3. Generate an answer restricted to that evidence for source-backed claims.
4. Associate claims with specific evidence units.
5. Validate source IDs and source locations against stored records.
6. Flag claims that cannot be supported.
7. Provide an explicit insufficient-evidence response when appropriate.

A citation must resolve to a real source record. A page number supplied by the language model is not proof that the citation is valid.

Design an evidence-strength policy that is testable. Avoid arbitrary confidence thresholds presented as scientifically established.

For PDFs, open the cited page. For slide decks, open the cited slide or a slide preview. For timestamped videos, provide a timestamp link when the source supports one, and otherwise provide a clear timestamp and source reference.

Separate source-backed statements from supplemental outside knowledge. The UI should make this distinction visible.

## 8. Assessment correctness

Use a structured assessment schema.

Each question should contain:

* Stable question ID.
* Question type.
* Question text.
* Topic and concept tags.
* Difficulty.
* Source-unit IDs.
* Correct answer or accepted answer criteria.
* Explanation grounded in evidence.
* Distractors and their rationale for MCQs.
* Numerical solution steps, units, and tolerance where applicable.
* Validation status.
* Question version and exposure history.

Use deterministic checking for numerical answers and structured answer keys wherever possible.

Do not trust a second model automatically just because it agrees with the first. Explain the limits of cross-model verification and introduce independent checks where possible.

Build a similarity-based or normalized-content mechanism to detect repeated questions. Define what counts as a repetition and measure it.

## 9. Learner model and personalization

Choose a defensible implementation that is achievable by one student.

Define:

* Initial mastery.
* How evidence from correct and incorrect responses updates mastery.
* How difficulty influences question selection.
* How hints and repeated attempts affect updates.
* How to avoid treating every conversational message as proof of learning.
* How forgetting and spaced repetition are represented, if implemented.
* How recommendations are generated from learner state.

Create simulated learner profiles, for example:

* Beginner who guesses frequently.
* Student who understands definitions but struggles with application.
* Strong student who makes occasional calculation errors.
* Student with uneven mastery across topics.

Run multiple sessions and record the resulting trajectories.

Do not fabricate gains. Simulations are evidence about behavior under simulated assumptions, not proof of real-world educational effectiveness.

## 10. Product experience and key screens

Plan a cohesive user journey with these screens:

1. Landing page that explains the value proposition.
2. Onboarding and diagnostic assessment.
3. Main learning dashboard.
4. Course creation and material-upload workspace.
5. Ingestion status and source library.
6. Interactive topic and prerequisite map.
7. Source-grounded tutor with visible citations.
8. Quiz configuration screen.
9. Interactive quiz and mock-exam experience.
10. Answer review and misconception report.
11. Learner mastery dashboard.
12. Personalized revision and quest page.
13. Evaluation and system-quality dashboard.

Use authentic data returned by the backend. Never make a frontend-only animation appear to be a real AI capability.

Design meaningful empty states, loading states, error states, and success states.

Build one polished end-to-end journey before implementing every screen.

## 11. Scope control and development discipline

This is a solo student project. Do not recommend an enormous distributed architecture or unnecessary microservices.

Prioritize:

* Working mandatory features.
* Reliable source provenance.
* Correct answers and assessments.
* Measurable personalization.
* Reproducible evaluation.
* Excellent product design.
* A convincing, honest demo.

Defer optional features when they threaten core quality.

Use a modular monolith unless there is a strong reason not to.

Keep expensive or slow operations asynchronous where appropriate. Handle file-size limits, failed jobs, duplicate uploads, and repeated processing.

Use seeded sample data only for clearly labeled demo fixtures. Distinguish sample data from live user-generated results.

## 12. How you must guide me

I need to understand the implementation, not just receive a repository full of code.

Follow this workflow:

### Phase 1: Strategy and requirements

* Break down the judging rubric.
* Identify the highest-impact differentiators.
* Identify technical risks and feasibility constraints.
* Establish a minimum viable product and a competition-ready target.
* Ask me for only the essential missing information.
* Check the actual deadline and remaining development time if that information is available; otherwise ask me.
* Do not invent submission rules or deadline details.

### Phase 2: Research and architecture

* Investigate current official documentation for important libraries and model providers when web research is available.
* Verify free-tier conditions and licensing.
* Produce the architecture diagram, data flow, schema, API contract, and proposed repository structure.
* Explain major technology choices and alternatives.

### Phase 3: Environment and foundation

* Give me exact Windows setup commands.
* Help me verify Python, Node.js, Git, GPU VRAM, available RAM, and disk space.
* Build a small working vertical slice first.
* Include expected terminal output and common troubleshooting steps.

### Phase 4: Incremental implementation

For every task:

1. Explain the goal.
2. Explain why the component exists.
3. Explain the important design decisions.
4. Give the exact file path.
5. Provide complete code for that file or a clearly defined patch.
6. Explain the important functions and data flow.
7. Give the exact commands to run.
8. Give test cases and expected results.
9. Ask me to report the result before proceeding when a failure could affect later work.
10. Update the task checklist.

Do not overwhelm me with dozens of files at once.

Do not use unexplained placeholders in supposedly complete code. If a feature is a stub, label it explicitly.

Do not rewrite working files unnecessarily. Keep interfaces stable and prefer small, testable changes.

### Phase 5: Integration and reliability

* Add automated tests.
* Validate source citations and unsupported-query handling.
* Test invalid files, malformed requests, missing evidence, repeated questions, and incorrect answers.
* Measure latency and resource use on my actual hardware.
* Fix critical bugs before adding optional features.

### Phase 6: Evaluation

* Create a gold-standard dataset with manually checked expected answers and source locations.
* Explain how each metric is calculated.
* Record baseline and improved-system results.
* Evaluate off-material refusal, citation correctness, question correctness, repetition, and simulated personalization.
* Report actual results without inflating them.
* Include failure analysis and limitations.

### Phase 7: UI polish

* Refine the design system, responsive behavior, typography, animation, charts, topic maps, and game mechanics.
* Verify that all major controls work.
* Ensure the interface remains usable if model inference is slow or unavailable.

### Phase 8: Submission

* Produce an architecture document.
* Produce a clear setup README.
* Document grounding, learner-model equations or update rules, evaluation methods, and limitations.
* Prepare a 3–10 minute demonstration video script.
* Prepare a live demo sequence with fallback data and a locally runnable path.
* Create a judging-rubric checklist.
* Help me rehearse technical defense questions.

## 13. Required deliverables from you first

Do not start by writing application code.

Your FIRST response must contain:

A. A concise competition strategy mapped to every judging category and its official weight.

B. Three original product concepts with distinct positioning. Recommend one and explain why.

C. A feature prioritization matrix containing:

* Feature.
* Relevant judging criterion.
* Implementation complexity.
* Risk.
* Minimum acceptable implementation.
* Competitive enhancement.

D. A realistic free-tool and model plan with verified or explicitly unverified resource limits.

E. A proposed architecture and data-flow diagram.

F. A proposed repository structure and database schema.

G. A phased implementation plan ordered by dependencies, with concrete completion criteria.

H. An evaluation plan, including an initial benchmark dataset design and simulated student protocol.

I. A demo narrative that shows the product's most impressive real capabilities.

J. The five biggest ways this project could fail, and how to mitigate each one.

K. A short list of essential questions you need answered before implementation.

Do not generate the entire codebase yet.

## 14. Operating principles

* Be technically precise, skeptical, and direct.
* Challenge unrealistic assumptions and scope creep.
* Prefer official documentation and reproducible evidence.
* Distinguish facts, hypotheses, and design proposals.
* Never fabricate API availability, benchmark scores, citations, or testing outcomes.
* Never equate a beautiful interface with a reliable AI system.
* Do not claim full multimodal understanding if the system only extracts text.
* Optimize for demonstrable quality under zero additional spending.
* Keep explanations accessible to a student while preserving engineering rigor.
* Explain concepts so I can defend every important design decision.
* Keep a persistent list of completed work, current blockers, known defects, and next tasks within our conversation.

Start with the required strategy and architecture deliverables. Do not begin implementation until I approve the plan.
