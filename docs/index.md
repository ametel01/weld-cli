# Weld

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

## Documentation

| Section | Description |
|---------|-------------|
| [Installation](installation.md) | Install weld and prerequisites |
| [Quickstart](quickstart.md) | Get running in under 5 minutes |
| [Workflow](workflow.md) | Understand the development workflow |
| [Commands](commands/index.md) | Full command reference |
| [Telegram Bot](telegram.md) | Remote weld access via Telegram |
| [Configuration](configuration.md) | Configure weld for your project |
| [Troubleshooting](troubleshooting.md) | Common issues and solutions |
| [Development](development/index.md) | Contributing and architecture |

## Quick Links

```bash
# Install
uv tool install weld-cli

# Initialize in your project
weld init && weld doctor

# Generate a plan from a spec
weld plan specs/feature.md -o plan.md

# Execute the plan
weld implement plan.md

# Commit with transcript
weld commit --all
```

## License

Apache-2.0. See [LICENSE](https://github.com/ametel01/weld-cli/blob/master/LICENSE) for details.
