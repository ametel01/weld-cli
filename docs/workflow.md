# Workflow Overview

Weld provides prompts for a structured development workflow:

```
1. Discovery (optional)  | Analyze existing codebase architecture
2. Interview (optional)  | Refine specification through Q&A
3. Research              | Deep dive into implementation approach
4. Planning              | Generate step-by-step implementation plan
5. Implement             | Execute plan steps interactively
6. Review                | Validate documents against codebase
7. Commit                | Create commit with transcript link
```

## Key Concepts

### Prompt Generation

Weld creates structured prompts that you run in Claude Code. Each command generates a focused prompt tailored to its purpose:

- **Research prompts** guide analysis of architecture and dependencies
- **Planning prompts** produce step-by-step implementation plans
- **Review prompts** validate documents against your codebase
- **Commit prompts** generate meaningful commit messages

### History Tracking

Commands log their inputs and outputs to `.weld/<command>/history.jsonl`. This provides:

- Audit trail of all AI interactions
- Ability to replay or reference past sessions
- Debugging information for troubleshooting

### Transcript Provenance

A transcript is a Claude Code session record, published as a GitHub gist and linked in commit messages:

```
Implement user auth

Claude-Transcript: https://gist.github.com/...
```

This provides full auditability of AI-assisted changes.

## Typical Workflow

### 1. Discover the Codebase

Before starting, understand the existing architecture:

```bash
weld discover -o docs/architecture.md
```

### 2. Refine Your Specification

Use interview mode to improve your spec:

```bash
weld interview specs/feature.md
```

### 3. Research the Implementation

Deep dive into the approach:

```bash
weld research specs/feature.md -o research.md
```

### 4. Generate a Plan

Create an actionable implementation plan:

```bash
weld plan specs/feature.md -o plan.md
```

### 5. Review the Plan

Validate the plan against your codebase:

```bash
weld review plan.md --apply
```

### 6. Implement Interactively

Execute the plan step by step:

```bash
weld implement plan.md
```

After each step completes, you'll be prompted to review changes:

```
Review changes from step 1.1? [y/N]:
```

This optional review prompt lets you catch issues early. You can choose to:
- Review only (get a list of findings)
- Review and apply fixes automatically

### 7. Review Your Changes (Optional)

If you skipped the per-step review prompts, you can review all changes before committing:

```bash
weld review --diff --staged
```

### 8. Commit with Provenance

Create a commit with transcript link:

```bash
weld commit --all
```

## See Also

- [Commands Reference](commands/index.md) - Detailed command documentation
- [Plan Format](reference/plan-format.md) - How plans are structured
