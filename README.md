<p align="center">
  <img src=".github/weld-logo.png" alt="Weld Logo" width="400">
</p>

**Human-in-the-loop coding harness with transcript provenance**

Weld generates structured prompts for AI-assisted development workflows. Instead of ad-hoc prompting, weld provides templates for: research → plan → implement → review → commit.

## Why Weld?

- **Structured Prompts**: Generate focused prompts for research, planning, and review
- **Full Auditability**: Every AI interaction linked via transcript gists in commits
- **Codebase Discovery**: Analyze existing codebases before making changes
- **Spec Refinement**: Interview-style Q&A to improve specifications

```
Spec Doc  -->  Research Prompt  -->  Plan Prompt  -->  Review  -->  Commit
                                                                  + transcript
```

## Install

```bash
uv tool install weld-cli          # or: pipx install weld-cli
uv tool upgrade weld-cli          # upgrade to latest
```

## Quick Start

```bash
weld init                              # Initialize in your project
weld doctor                            # Check environment
weld plan specs/feature.md -o plan.md  # Generate implementation plan
weld implement plan.md                 # Execute plan interactively
weld commit --all                      # Commit with transcript
```

## Documentation

| | |
|---|---|
| **[Installation](docs/installation.md)** | Prerequisites and setup |
| **[Quickstart](docs/quickstart.md)** | Get running in 5 minutes |
| **[Workflow](docs/workflow.md)** | Full development workflow |
| **[Commands](docs/commands/index.md)** | Command reference |
| **[Configuration](docs/configuration.md)** | Config options |
| **[Troubleshooting](docs/troubleshooting.md)** | Common issues |
| **[Development](docs/development/index.md)** | Contributing guide |

## License

See [LICENSE](LICENSE) for details.
