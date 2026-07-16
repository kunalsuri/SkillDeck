
# Resumable SDD (Spec -> Checklist -> Commit loop)

A lightweight, resumable take on spec-driven development. For the full SDD
pipeline (constitution -> specify -> clarify -> plan -> tasks -> analyze ->
implement), use [GitHub Spec Kit](https://github.com/github/spec-kit) instead.

Turns any nontrivial task into a sequence of small, individually tested,
individually committed steps -- with the plan and progress themselves
committed to git. If the session dies mid-task, the next session (or a
different agent, or a human) can resume from exactly where it left off by
reading two files, not by re-deriving context from a transcript that may be
gone.

## When to use this skill

- The user explicitly asks for "SDD", "spec-driven development", or a
  process that's resilient to the agent stopping mid-way.
- The task is large enough that losing an hour of uncommitted work would be
  painful (schema changes, multi-file features, data migrations).
- The user asks you to "make a plan then implement it, testing and
  committing as you go."

Don't use this for a single-file fix or anything completable in one or two
tool calls -- the overhead isn't worth it below that size.

## The process

### 1. Write the spec first, commit it alone

Before touching any code, write `docs/SPECS-<feature>.md` covering:

- **Context** -- why this is being done, what prompted it.
- **Scope decisions** -- if there were multiple viable approaches, say
  which was chosen and why, so a future reader doesn't re-litigate it.
- **Design** -- concrete enough to implement from: files touched, data
  shapes, key functions/patterns being followed or introduced.
- **Acceptance criteria** -- a numbered list of checks that prove the work
  is done (tests pass, a build succeeds, a specific behavior is observable).

Commit this file by itself, before any implementation. It has to survive
independently -- if every other file in this session's working tree
disappeared right now, the spec alone should be enough for someone else
(a different tool, a different session, a human) to pick the work back up.

### 2. Derive a checklist, commit it alone

Write `docs/implementation-<feature>.md`: one checkbox per concrete step,
grouped into small sections that mirror the spec. Each item should be small
enough to implement and verify in one sitting. State explicitly, at the top
of the file, that this is the resume point: *"read the spec for the why,
continue from the first unchecked box below."*

Commit this file by itself too.

### 3. Loop: implement -> test -> commit -> check off -> commit

For each unchecked item, in order:

1. Implement just that item.
2. Run whatever test gate proves it works -- existing test suite, a build,
   a schema validator, a manual check. Note in the checklist what the gate
   actually was and what it showed (exit code, pass count, key output) --
   not just "tested," the actual evidence.
3. Commit the code change with a message that names which spec section it
   implements.
4. Edit the checklist: check the box, add a one-line result note (what
   happened, any numbers, any deviation from plan).
5. Commit the checklist update -- either folded into step 3's commit for
   atomicity, or as its own immediately-following commit. Pick one
   convention and stay consistent for the whole task.

Never let more than one unchecked-but-implemented item pile up uncommitted.
If you discover the task needs to be re-scoped mid-way (a blocker, a
dependency that doesn't exist, network access that isn't available), don't
silently improvise -- write the blocker and the revised plan directly into
the checklist item before continuing, so the deviation is part of the
permanent record, not lost context.

### 4. Close it out

When every box is checked, do one final pass against the spec's acceptance
criteria (section by section, not just checklist boxes), and record the
result in the checklist's last section.

## Anti-patterns this skill exists to prevent

- Doing all the work first and writing the plan/checklist retroactively --
  defeats the purpose; the plan has to exist *before* the risky part so it
  survives an interruption during that part.
- One giant commit at the end "to keep history clean" -- the opposite of
  resumable. Small, frequent, individually-tested commits are the point.
- Checking a box without writing down what the test gate actually showed --
  a future reader (or you, next session) can't tell "tested and passed"
  from "forgot to test" without the evidence.
- Treating the checklist as disposable scratch notes instead of a committed
  artifact -- if it's not committed, it doesn't help you resume.

## Minimal file templates

`docs/SPECS-<feature>.md`:

```markdown
# SPEC: <feature name>

## Context
Why this, why now.

## Scope decision
Approach chosen, and the rejected alternative(s), briefly.

## Design
Concrete enough to implement from.

## Acceptance criteria
1. ...
2. ...
```

`docs/implementation-<feature>.md`:

```markdown
# Implementation checklist: <feature name>

Resume point if interrupted: read SPECS-<feature>.md for the why,
continue from the first unchecked box below.

## 1. <section mirroring spec>
- [ ] <step>
- **Test gate:** <what proves this step works>
- [ ] Commit.
```