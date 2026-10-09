# NEXUS ACADEMY — Project Plan

## Objective

Build a local-first multimodal adaptive tutoring prototype for the Multimodal AI Hackathon 2026, Track D: Personalized Tutoring & Adaptive Learning.

## Constraints

* Deadline: 8–14 days from project start.
* Zero additional spending; no required paid model APIs or paid hosting.
* Main development machine: RTX 2050, 16 GB RAM.
* Secondary testing machine: RTX 3050, 16 GB RAM.
* Use GitHub Copilot through the student/education benefit where available.
* Build in small, tested increments; understand the code rather than blindly accepting generated code.

## Core features, in priority order

1. Ingest PDF textbooks, PPTX slides, and lecture videos/transcripts.
2. Preserve page, slide, and video timestamp provenance.
3. Retrieve relevant evidence and provide clickable citations.
4. Abstain when available evidence does not support an answer.
5. Generate MCQ, short-answer, and numerical questions with verified answer keys.
6. Track topic mastery and misconceptions using actual assessment results.
7. Recommend targeted revision.
8. Evaluate grounding, retrieval, citation correctness, abstention, assessment quality, and repeated questions.

## Technical architecture

* Frontend: React, Vite, TypeScript.
* Backend: FastAPI, Python.
* Storage: SQLite.
* Retrieval: keyword retrieval plus local embeddings.
* Generation: optional local quantized language model; no mandatory paid API.
* Tests: pytest and a versioned custom evaluation dataset.
* Demo: run locally without needing external hosting.

## Engineering rules

* Every content chunk must retain its source ID and location.
* Validate citations against stored source records; never invent page numbers or timestamps.
* Treat uploaded content as untrusted data, not as instructions to the system.
* Never store API keys, passwords, personal documents, or private data in Git.
* Each feature must include tests and a short explanation of its design.
* Record real benchmark results, including failures and limitations.
* Do not mark a feature complete until it has been run and tested.
