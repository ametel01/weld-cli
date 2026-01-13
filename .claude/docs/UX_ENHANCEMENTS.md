# UX Enhancements Research Document

## Executive Summary

This document identifies opportunities to enhance the user experience of weld-cli based on current feature analysis, pain points, and modern CLI UX patterns. The focus is on reducing friction, improving feedback, and making the human-in-the-loop workflow more intuitive.

---

## Current State Analysis

### Strengths
- Well-structured workflow pipeline (research → plan → implement → review → commit)
- Interactive arrow-key navigation for step selection
- Graceful Ctrl+C handling preserves progress
- Comprehensive CLI options for automation
- Session-based commit grouping with transcript provenance

### Pain Points Identified
1. **Token limit management is manual** - Users must manually adjust config for large documents
2. **No conversational memory between steps** - Each step is independent, losing context
3. **External dependency failures are opaque** - Transcript/gist failures need better guidance
4. **Long-running operations lack feedback** - No progress indicators during AI calls
5. **Error recovery requires manual intervention** - No guided recovery flows
6. **Onboarding friction** - New users need to configure multiple external tools

---

## Proposed UX Enhancements

### Category 1: Progress & Feedback

#### 1.1 Rich Progress Indicators
**Problem**: Long-running AI operations (implement, review) provide minimal feedback.

**Proposal**: Add rich progress indicators during AI interactions:
- Spinner with elapsed time
- Token count display (input/output)
- Streaming status ("Analyzing...", "Generating code...", "Validating...")
- Estimated time remaining based on historical data

**Implementation Notes**:
- Use `rich` library for terminal UI
- Store timing data in history.jsonl for estimates
- Show phase/step context in progress bar

**Priority**: High
**Effort**: Medium

---

#### 1.2 Step Completion Notifications
**Problem**: Users context-switch during long operations and miss completion.

**Proposal**: System notifications when steps complete:
- Desktop notification on step/phase completion
- Optional sound alert
- Summary in notification (success/failure, duration, next step)

**Implementation Notes**:
- Use `plyer` or `notify-py` for cross-platform notifications
- Make configurable in `config.toml`
- Respect `--quiet` flag

**Priority**: Medium
**Effort**: Low

---

#### 1.3 Inline Diff Preview
**Problem**: `weld review --diff` outputs findings, but users must manually view diffs.

**Proposal**: Inline syntax-highlighted diff display:
- Show diff hunks inline with review findings
- Color-coded additions/deletions
- Collapsible sections for large diffs
- Side-by-side option for terminal width > 160 chars

**Implementation Notes**:
- Use `rich.syntax` for highlighting
- Add `--inline-diff` flag to review command
- Store user preference in config

**Priority**: Medium
**Effort**: Medium

---

### Category 2: Context & Continuity

#### 2.1 Step Context Summaries
**Problem**: Each step is independent; AI loses context from previous steps.

**Proposal**: Automatic context injection from completed steps:
- Generate brief summary after each step completes
- Include summary of previous 2-3 steps in prompt
- Store summaries in session registry
- Option to include file change summaries

**Implementation Notes**:
- Use smaller model (Claude Haiku) for summarization
- Cap summary at 500 tokens per step
- Add `[context]` section to step prompts

**Priority**: High
**Effort**: High

---

#### 2.2 Conversation Mode for Implementation
**Problem**: Complex steps often need follow-up refinement.

**Proposal**: Optional conversation mode after step execution:
- After step completes, prompt: "Refine this step? (y/n)"
- If yes, enter conversational mode with full context
- Conversation history persisted for the step
- Exit with `/done` or Ctrl+D

**Implementation Notes**:
- Use Claude's multi-turn conversation API
- Store conversation in `.weld/sessions/{session_id}/conversations/`
- Add `--no-conversation` flag to skip prompt

**Priority**: Medium
**Effort**: High

---

#### 2.3 Smart Step Dependencies
**Problem**: Plan steps are independent but often have implicit dependencies.

**Proposal**: Detect and visualize step dependencies:
- Parse plan for file dependencies between steps
- Warn when executing step before its dependencies
- Show dependency graph with `weld plan --graph`
- Auto-suggest execution order

**Implementation Notes**:
- Analyze "Files" section of each step
- Build directed graph of file dependencies
- Use `graphviz` or ASCII art for visualization

**Priority**: Low
**Effort**: Medium

---

### Category 3: Error Recovery & Resilience

#### 3.1 Guided Error Recovery
**Problem**: Failures require users to interpret exit codes and troubleshoot manually.

**Proposal**: Interactive error recovery wizard:
- On failure, show contextual recovery options
- Common recoveries: retry, skip, rollback, edit plan
- Show relevant troubleshooting steps from docs
- Log recovery attempts for debugging

**Example Flow**:
```
Step 3 failed: Claude returned unexpected format (exit code 23)

What would you like to do?
  > Retry this step
    Simplify and retry (reduces prompt complexity)
    Skip this step
    View full error details
    Open troubleshooting guide
```

**Priority**: High
**Effort**: Medium

---

#### 3.2 Automatic Rollback Points
**Problem**: Failed steps can leave partial changes in the repository.

**Proposal**: Git stash-based rollback points:
- Create stash before each step
- On failure, offer to restore stash
- Keep last N rollback points (configurable)
- Show rollback history with `weld implement --rollbacks`

**Implementation Notes**:
- Use `git stash push -m "weld: before step N"`
- Store stash refs in session registry
- Clean up old stashes on successful commit

**Priority**: Medium
**Effort**: Low

---

#### 3.3 Graceful Degradation for External Dependencies
**Problem**: Missing `gh` or `claude` CLI causes hard failures.

**Proposal**: Degrade gracefully with clear alternatives:
- If `gh` missing: Skip transcript upload, offer local file alternative
- If `claude` missing: Prompt to install or switch provider
- Show one-time setup guide for missing tools
- Remember user preference to skip missing tool prompts

**Implementation Notes**:
- Enhance `weld doctor` with interactive setup
- Add `--offline` flag to skip all external calls
- Store setup preferences in config

**Priority**: Medium
**Effort**: Low

---

### Category 4: Onboarding & Discovery

#### 4.1 Interactive Setup Wizard
**Problem**: Initial setup requires manual config file editing.

**Proposal**: Interactive `weld init` wizard:
- Detect available tools (claude, codex, gh)
- Prompt for preferences (provider, model, transcript visibility)
- Generate config with explanatory comments
- Offer to run `weld doctor` after setup

**Example Flow**:
```
$ weld init

Welcome to Weld! Let's configure your project.

Detected tools:
  [x] git (required)
  [x] gh (GitHub CLI)
  [x] claude (Claude Code CLI)
  [ ] codex (not found)

Which AI provider would you like to use?
  > Claude (recommended)
    Codex
    Both (configure per-task)

Enable transcript generation?
  > Yes, private gists (recommended)
    Yes, public gists
    No

Configuration saved to .weld/config.toml
```

**Priority**: High
**Effort**: Medium

---

#### 4.2 Command Suggestions
**Problem**: New users don't know the optimal workflow sequence.

**Proposal**: Contextual command suggestions:
- After each command, suggest logical next steps
- Detect workflow state and offer relevant commands
- Show tips for unused features
- Add `weld next` command to show suggestions

**Example**:
```
$ weld plan spec.md

Plan generated: .weld/plans/spec-plan.md

Next steps:
  weld implement .weld/plans/spec-plan.md    # Execute the plan
  weld plan spec.md --interactive            # Refine plan interactively

Tip: Use --auto-commit to automatically commit after each step.
```

**Priority**: Medium
**Effort**: Low

---

#### 4.3 Template Gallery
**Problem**: Users create similar specs/plans repeatedly.

**Proposal**: Built-in template system:
- Ship common templates (API endpoint, React component, test suite)
- `weld template list` - show available templates
- `weld template use <name>` - scaffold from template
- Custom template directory in `.weld/templates/`

**Template Example**:
```
$ weld template use api-endpoint

Template: REST API Endpoint

Questions:
  Resource name: users
  HTTP methods: GET, POST, PUT, DELETE
  Authentication required? yes

Generated: .weld/specs/users-api-spec.md
```

**Priority**: Low
**Effort**: Medium

---

### Category 5: Efficiency & Shortcuts

#### 5.1 Quick Commands
**Problem**: Common workflows require multiple commands.

**Proposal**: Shortcut commands for common workflows:
- `weld quick-fix <file>` - review + apply fixes in one command
- `weld quick-plan <description>` - generate plan from one-liner
- `weld finish` - commit all sessions with transcripts

**Implementation Notes**:
- Compose existing commands internally
- Add aliases in config for custom shortcuts
- Support shell completion for quick commands

**Priority**: Medium
**Effort**: Low

---

#### 5.2 Bookmarks for Steps
**Problem**: Large plans make it hard to track important steps.

**Proposal**: Step bookmarking system:
- `weld implement --bookmark <step>` to mark important steps
- Show bookmarked steps in separate section
- Quick-jump to bookmarked steps
- Add notes to bookmarks

**Priority**: Low
**Effort**: Low

---

#### 5.3 Keyboard Shortcuts in Interactive Mode
**Problem**: Arrow navigation is the only interaction method.

**Proposal**: Extended keyboard shortcuts:
- `r` - re-run current step
- `s` - skip step
- `d` - show diff from last step
- `c` - commit current changes
- `q` - quit (with confirmation)
- `?` - show help
- `/` - search steps

**Implementation Notes**:
- Extend `simple-term-menu` with custom handlers
- Show shortcut hints in footer
- Add `--vim-keys` for hjkl navigation

**Priority**: Medium
**Effort**: Low

---

### Category 6: Visibility & Debugging

#### 6.1 Session Dashboard
**Problem**: Hard to understand session state across multiple implement runs.

**Proposal**: Session overview command:
- `weld session` - show current session status
- Display: files changed, steps completed, pending commits
- Show transcript preview
- Link to gist if uploaded

**Example**:
```
$ weld session

Session: abc123 (active)
Started: 2 hours ago
Plan: .weld/plans/feature-plan.md

Progress:
  Phase 1: Setup [COMPLETE]
    Step 1.1: Create models [COMPLETE]
    Step 1.2: Add migrations [COMPLETE]
  Phase 2: Implementation [IN PROGRESS]
    Step 2.1: API endpoints [CURRENT]
    Step 2.2: Tests [PENDING]

Files changed: 7 (4 created, 3 modified)
Pending commits: 1 session

Actions:
  weld commit          # Commit with transcript
  weld session --diff  # View all changes
```

**Priority**: High
**Effort**: Medium

---

#### 6.2 Prompt Preview Mode
**Problem**: Users can't see what prompts are sent to AI.

**Proposal**: Prompt inspection commands:
- `weld implement --show-prompt` - display prompt without executing
- `weld research --show-prompt` - preview research prompt
- Save prompts to `.weld/prompts/` for review
- Add `--edit-prompt` to modify before sending

**Priority**: Low
**Effort**: Low

---

#### 6.3 Token Usage Dashboard
**Problem**: Token usage is invisible, leading to unexpected limits.

**Proposal**: Token usage tracking and display:
- Track input/output tokens per command
- `weld usage` - show token usage summary
- Warn when approaching limits
- Suggest optimizations for high-token operations

**Example**:
```
$ weld usage

Token Usage (last 7 days):
  Total: 1.2M tokens

  By Command:
    implement: 800K (67%)
    research:  250K (21%)
    review:    150K (12%)

  By Model:
    claude-sonnet-4-20250514: 1.0M
    claude-haiku-3-5-20241022: 200K

  Trend: +15% from last week
  Tip: Consider using claude-haiku-3-5-20241022 for review tasks.
```

**Priority**: Low
**Effort**: Medium

---

## Implementation Roadmap

### Phase 1: Quick Wins (Low Effort, High Impact)
1. Command suggestions after each command
2. Keyboard shortcuts in interactive mode
3. Automatic rollback points
4. Graceful degradation for external dependencies

### Phase 2: Core Improvements (Medium Effort)
1. Rich progress indicators
2. Interactive setup wizard
3. Session dashboard
4. Guided error recovery

### Phase 3: Advanced Features (High Effort)
1. Step context summaries
2. Conversation mode for implementation
3. Inline diff preview
4. Template gallery

---

## Metrics for Success

### User Experience Metrics
- Time to first successful commit (onboarding)
- Commands per workflow completion
- Error recovery rate (failures resolved without manual intervention)
- Feature discovery rate (% of features used)

### Engagement Metrics
- Session duration
- Steps completed per session
- Auto-commit adoption rate
- Transcript generation rate

### Satisfaction Indicators
- Help command usage (lower is better)
- Error rate (exit codes != 0)
- Retry rate per step

---

## Technical Considerations

### Dependencies
- `rich` - Terminal UI components (progress, syntax, tables)
- `plyer` or `notify-py` - Cross-platform notifications
- Consider maintaining minimal dependencies for fast startup

### Backward Compatibility
- All enhancements should be additive
- Existing config files must continue to work
- New config options should have sensible defaults
- CI/CD workflows must not break (respect `--quiet`, `--json`)

### Performance
- Avoid adding startup latency (lazy-load heavy modules)
- Cache token usage data locally
- Don't block on optional features (notifications, templates)

---

## Open Questions

1. **Conversation mode persistence**: How long should conversation history be retained?
2. **Template distribution**: Should templates be fetched from a registry or bundled?
3. **Notification permissions**: How to handle systems that block notifications?
4. **Token tracking**: Should usage data be sent to a central dashboard (opt-in)?
5. **Rollback storage**: How many rollback points before cleanup?

---

## References

- [Current CLI Reference](../reference/cli.md)
- [Workflow Guide](../guides/workflow.md)
- [Troubleshooting Guide](../guides/troubleshooting.md)
- [Rich Library](https://rich.readthedocs.io/)
- [12 Factor CLI Apps](https://medium.com/@jdxcode/12-factor-cli-apps-dd3c227a0e46)

---

*Document Version: 1.0*
*Created: 2026-01-11*
*Status: Draft - Pending Review*
