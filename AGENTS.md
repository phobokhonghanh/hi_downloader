# Agent Leadership Bootstrap

> This file is for the **controller/lead agent**, not the executor agent.
> Read it at the beginning of a new controller session before delegating work.

## Required local instruction

In this workspace, read and follow `/home/itc/.codex/RTK.md` before running shell
commands. If that machine-local file is unavailable in another environment,
continue with the repository workflow and report the missing local instruction.

## Controller startup

1. Read `.agents/CONTROLLER.md` completely.
2. Read `.agents/general-rules.md` and `.agents/project-rules.md`.
3. Inspect the current Git status without modifying or cleaning user changes.
4. Inspect only the source needed for the user's current request.
5. Run `herdr agent list` before delegating and resolve the executor by its live
   pane ID when its display name cannot be used as a prompt target.
6. Select the lightest appropriate workflow: ask, small task, or a
   controller-authored plan grilled by the executor followed by an approved
   execute contract. The executor must not author the implementation plan for a
   medium or large task.

## Important storage note

`AGENTS.md` is repository-visible and is the durable entry point for a new lead
agent. The `.agents/` directory is intentionally ignored by Git and contains
local orchestration details, sessions, contracts, and project context.

Therefore:

- Put only stable, portable bootstrap instructions in this file.
- Do not place secrets, terminal IDs, machine-specific session state, or active
  task details here.
- A fresh clone will not contain `.agents/**` unless the local orchestration kit
  is installed or restored separately.
- If `.agents/CONTROLLER.md` is missing, the lead agent must not guess the local
  delegation workflow. It may continue cautiously without delegation or ask the
  user to restore the orchestration kit.

## Authority model

- The user defines the goal and approves meaningful scope or product changes.
- The controller owns task decomposition, plan review, scope approval, and diff
  review.
- Antigravity/Agy/Gemini is the executor and owns implementation plus the compile,
  lint, and focused tests assigned in its contract.
- The executor may ask the controller questions and propose improvements, but it
  must not implement unapproved scope or architectural changes.
