# Quickstart

Get running in under 5 minutes.

## 1. Install weld globally

```bash
uv tool install weld-cli    # or: pipx install weld-cli
```

## 2. Initialize in your project

```bash
cd /path/to/your-project
weld init
```

## 3. Check your environment

```bash
weld doctor
```

## 4. Research a specification

Generate a research prompt and run Claude:

```bash
weld research specs/my-feature.md -o research.md
```

## 5. Generate a plan

Create an implementation plan from your spec:

```bash
weld plan specs/my-feature.md -o plan.md
```

## 6. Execute the plan interactively

```bash
weld implement plan.md
```

## 7. Review a document

Validate a document against the codebase:

```bash
weld review plan.md --apply
```

## 8. Review code changes

Before committing, review your changes:

```bash
weld review --diff --staged
```

## 9. Commit with transcript provenance

Auto-generate commit message with transcript link:

```bash
weld commit --all
```

## Next Steps

- [Workflow Overview](workflow.md) - Understand the full development workflow
- [Commands Reference](commands/index.md) - Detailed command documentation
- [Configuration](configuration.md) - Customize weld for your project
