# Project Agent Rules & Workflows

## Engineering & Design Protocols

1. **Planning & Architecture Alignment (`grill-me` / `grill-with-docs`)**
   - For fuzzy specifications or complex architecture changes, run a structured multi-round interview.
   - Maintain stateful documentation:
     - Domain glossary and terms belong in `CONTEXT.md`.
     - Non-reversible, trade-off heavy architectural decisions belong in `docs/adr/`.

2. **Rigorous Execution (`pstack` / Poteto Mode)**
   - Follow structured task playbooks (Feature Implementation, Bug Investigation, Refactoring).
   - Require empirical runtime proof (tests, build success, logs) before completing any task step.
   - Maintain clean context windows by delegating deep research tasks to the `research` subagent.
