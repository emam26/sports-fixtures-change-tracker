# Instructions for Codex

## Project and reading order

This repository is the Sports Fixtures & Change Tracker: Python, Microsoft SQL Server, FastAPI, and a plain HTML/CSS/JavaScript interface using real OpenLigaDB data.

At the start of a session, read this file, docs/PROJECT_ROADMAP.md, and docs/BUILD_PLAN.md. Consult docs/MANUAL_RUNBOOK.md before proposing operational steps and docs/ARCHITECTURE.md when changing the design. Inventory the existing checkout before assuming what is implemented.

The user's instructions take precedence over this document. Preserve compatible existing repository instructions and unrelated work.

## Division of work

Codex prepares and edits code, SQL scripts, API implementation, tests, and documentation through direct file/editor tools. The user performs terminal operations, database operations, API requests, browser checks, installations, scheduler changes, and Git operations manually.

Do not execute any project command, even a read-only command. Do not run shell inspection, Python snippets, installers, SQL, tests, application servers, background processes, Git, local API requests, or operational OpenLigaDB requests. Do not bypass this rule through another tool.

You may read public technical documentation. If a needed repository inspection or edit requires shell execution, supply the command or file contents for the user and wait for the necessary output.

## Manual-step format

For each step, provide:
1. Where to execute it: WSL Bash, a confirmed SQL client, or the browser.
2. Working directory, target database, or API base address.
3. Exact command, SQL, request, or browser action.
4. Purpose and expected success pattern.
5. Non-secret output the user should return and when to stop.

Give small batches. Keep SQL separate from Bash commands. Avoid guessed paths, entry points, database names, ports, authentication, or installed tools. Stop after a failed prerequisite and diagnose it before dependent work.

Do not request passwords, tokens, or complete secret-bearing connection strings in chat. Keep actual configuration local, use placeholders in examples, and omit secrets from logs.

## Build discipline

Work on the agreed stage only. Finish its meaningful checks before dependent stages.

Update docs/BUILD_PLAN.md after every handoff with:
- What files changed and what was implemented.
- Checks that remain NOT RUN.
- User-supplied execution evidence and its limitations.
- Current blocker and exact next manual step.

Written tests are NOT RUN until the user supplies results. Distinguish offline tests, SQL Server integration checks, live-source checks, API checks, browser checks, and actual scheduled runs. Never infer one category passed because another passed.

Keep repeatable operational instructions in docs/MANUAL_RUNBOOK.md. Record significant decisions in BUILD_PLAN.md. Keep ARCHITECTURE.md aligned with implemented behavior, clearly separating remaining proposals.

## Data and database rules

Use Microsoft SQL Server for real integration checks; do not substitute SQLite for SQL Server behavior.

Start with one Bundesliga matchday from 2025/26. Expand to full 2025/26 and 2026/27 data after the smaller import is proven.

Preserve source responses and provenance. Validate before changing current records. Repeated unchanged imports must not duplicate matches or create false business changes. Keep current records, observed changes, and successful checkpoints transactionally consistent.

The initial import establishes a baseline. Do not fabricate earlier history, zero scores for missing results, source states, or source timestamp timezones. Verify result selection against source metadata.

Controlled changes and failures belong in clearly labeled tests against a separate test database. Never present simulated changes as naturally observed upstream events.

Local notes are application-owned and must not overwrite source-owned fixtures or results. Parameterize database queries, validate API input, and render source text safely.

## Scope and machine changes

Use a dedicated project environment. Do not change Conda base or unrelated projects. Do not stop CVAT or other containers, shut down WSL, alter Tailscale, or change global networking/firewall settings as a routine setup step. Explain any necessary host change before giving the user its manual instructions.

Keep secrets, local environments, logs, and raw captures out of Git by default. Respect source attribution and data-license requirements.

Do not commit, push, deploy, or create scheduled tasks. The user performs those actions manually.

## Completion report

End each stage with changed files, implemented behavior, checks supported by user output, checks NOT RUN, unresolved issues, and the next manual step. Documentation, badges, screenshots, and resume statements must reflect actual evidence.
