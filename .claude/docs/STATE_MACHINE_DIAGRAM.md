# Weld CLI State Machine Diagram

This document describes the state machines that govern the weld-cli application flow.

## Mermaid Diagram

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#f4f4f4'}}}%%
stateDiagram-v2
    %% ==========================================
    %% MAIN WORKFLOW STATE MACHINE
    %% ==========================================

    state "WELD WORKFLOW" as workflow {
        [*] --> Init
        Init --> Research: weld research
        Init --> Discover: weld discover
        Init --> Interview: weld interview
        Init --> Doctor: weld doctor

        Research --> Plan: weld plan
        Discover --> Plan: weld plan
        Interview --> Plan: weld plan

        Plan --> Implement: weld implement

        Implement --> Review: weld review
        Implement --> Commit: weld commit
        Review --> Implement: fix & retry
        Review --> Commit: weld commit

        Commit --> [*]: done
    }

    %% ==========================================
    %% DISCOVER COMMAND STATE MACHINE
    %% ==========================================

    state "DISCOVER COMMAND" as discover_cmd {
        [*] --> ValidateGitRepo_D
        ValidateGitRepo_D --> LoadConfig_D
        LoadConfig_D --> GeneratePrompt_D
        GeneratePrompt_D --> DryRunCheck_D
        DryRunCheck_D --> Exit_D: --dry-run
        DryRunCheck_D --> PromptOnlyCheck_D: continue
        PromptOnlyCheck_D --> PrintPrompt_D: --prompt-only
        PrintPrompt_D --> Exit_D
        PromptOnlyCheck_D --> RunClaude_D: continue
        RunClaude_D --> StripPreamble_D
        StripPreamble_D --> WriteOutput_D
        WriteOutput_D --> LogHistory_D
        LogHistory_D --> [*]
    }

    %% ==========================================
    %% INTERVIEW COMMAND STATE MACHINE
    %% ==========================================

    state "INTERVIEW COMMAND" as interview_cmd {
        [*] --> LoadDocument_I
        LoadDocument_I --> ValidateFormat_I: warn if not .md
        ValidateFormat_I --> CheckGitRepo_I: optional tracking
        CheckGitRepo_I --> InterviewLoop_I

        state "InterviewLoop_I" as interview_loop {
            [*] --> GenerateQuestions
            GenerateQuestions --> DisplayQuestions
            DisplayQuestions --> GetUserAnswers
            GetUserAnswers --> IntegrateAnswers: Claude
            IntegrateAnswers --> UpdateDocument
            UpdateDocument --> GenerateQuestions: continue
            UpdateDocument --> Done_I: user says "done"
        }

        InterviewLoop_I --> [*]: Ctrl+C or done
    }

    %% ==========================================
    %% IMPLEMENT STATE MACHINE
    %% ==========================================

    state "IMPLEMENT COMMAND" as implement {
        [*] --> ParsePlan
        ParsePlan --> ValidatePlan
        ValidatePlan --> LoadConfig
        LoadConfig --> CheckAutoCommit

        state "CheckAutoCommit" as auto_commit_check {
            [*] --> LoadRegistry: --auto-commit set
            [*] --> SkipRegistry: no --auto-commit
        }

        CheckAutoCommit --> DetectSession
        DetectSession --> SnapshotBefore: session found
        DetectSession --> MenuLoop: no session (skip tracking)
        SnapshotBefore --> MenuLoop

        state "MenuLoop" as menu {
            [*] --> DisplayMenu
            DisplayMenu --> SelectItem: arrow keys
            SelectItem --> DisplayMenu: continue
            SelectItem --> ExecuteStep: Enter on step
            SelectItem --> ExecutePhase: Enter on phase
            SelectItem --> Exit: Esc/Q
        }

        ExecuteStep --> RunClaude
        ExecutePhase --> RunClaude: per step (fail-fast)

        state "RunClaude" as claude_run {
            [*] --> CaptureBaseline
            CaptureBaseline --> InvokeClaude
            InvokeClaude --> CheckResult
            CheckResult --> MarkComplete: success
            CheckResult --> RecoveryPrompt: failure WITH changes
            CheckResult --> StepFailed: failure NO changes
            RecoveryPrompt --> MarkComplete: user confirms
            RecoveryPrompt --> StepFailed: user declines
        }

        MarkComplete --> AtomicWrite
        AtomicWrite --> CaptureSessionForCommit

        note right of CaptureSessionForCommit
            CRITICAL: Session captured HERE
            (after step, before review)
            to ensure implementation session
            is used for transcript, not review session
        end note

        CaptureSessionForCommit --> CheckNoReview
        CheckNoReview --> PromptCommit: --no-review flag
        CheckNoReview --> PromptReview: review enabled

        state "PromptReview" as review_state {
            [*] --> AskReview
            AskReview --> RunReview: yes
            AskReview --> PromptCommit: no
            RunReview --> AskApply
            AskApply --> ApplyFixes: yes
            AskApply --> SaveArtifacts: no
            ApplyFixes --> SaveArtifacts
            SaveArtifacts --> PromptCommit
        }

        note right of PromptReview
            NON-BLOCKING: Review errors
            print warning, continue to next step
        end note

        state "PromptCommit" as commit_state {
            [*] --> CheckAutoCommitFlag
            CheckAutoCommitFlag --> AskCommit: --auto-commit
            CheckAutoCommitFlag --> BackToMenu: no flag
            AskCommit --> StageAndCommit: yes
            AskCommit --> BackToMenu: no
            StageAndCommit --> BackToMenu
        }

        note right of PromptCommit
            NON-BLOCKING: Commit errors
            print warning, continue to next step
            Uses session captured BEFORE review
        end note

        BackToMenu --> MenuLoop
        StepFailed --> MenuLoop: continue?

        state "PhaseExecution" as phase_exec {
            [*] --> NextStep
            NextStep --> ExecuteStep_P: has incomplete
            ExecuteStep_P --> NextStep: step success
            ExecuteStep_P --> PhaseFailed: step failed
            NextStep --> MarkPhaseComplete: all steps done
            MarkPhaseComplete --> [*]
            PhaseFailed --> [*]: phase NOT marked complete
        }

        note right of PhaseExecution
            ATOMIC: Phase marked complete
            ONLY if ALL steps succeed
        end note

        Exit --> SnapshotAfter
        SnapshotAfter --> RecordActivity
        RecordActivity --> SaveRegistry
        SaveRegistry --> [*]

        note right of SaveRegistry
            Snapshot timeout: 5s for large repos
            Returns partial snapshot if exceeded
        end note
    }

    %% ==========================================
    %% COMMIT STATE MACHINE
    %% ==========================================

    state "COMMIT COMMAND" as commit {
        [*] --> GetStagedFiles
        GetStagedFiles --> FilterMetadata: exclude .weld/* (except config.toml)
        FilterMetadata --> LoadRegistry
        LoadRegistry --> CheckSessionFlow

        state "CheckSessionFlow" as flow_check {
            [*] --> SessionBased: registry.sessions AND NOT --no-session-split
            [*] --> FallbackFlow: empty registry OR --no-session-split
        }

        %% Session-Based Flow
        state "SessionBased" as session_flow {
            [*] --> MapFilesToSessions
            MapFilesToSessions --> GroupBySessions
            GroupBySessions --> HandleUntracked: has untracked files

            state "HandleUntracked" as untracked {
                [*] --> PromptAttribution: tracked + untracked exist
                [*] --> SkipPrompt: only untracked OR only tracked
                PromptAttribution --> AttributeToRecent: user selects "attribute"
                PromptAttribution --> KeepSeparate: user selects "separate"
                PromptAttribution --> Cancelled: user cancels
            }

            HandleUntracked --> ProcessSessions: continue
            HandleUntracked --> [*]: cancelled

            state "ProcessSessions" as sessions {
                [*] --> NextSession
                NextSession --> ProcessSession: has more (chronological order)
                NextSession --> Done_S: done

                state "ProcessSession" as session {
                    [*] --> UnstageAll_S
                    UnstageAll_S --> StageSessionFiles
                    StageSessionFiles --> GetDiff_S
                    GetDiff_S --> GenerateMessage: Claude suggests
                    GenerateMessage --> RenderTranscript
                    RenderTranscript --> UploadGist
                    UploadGist --> AddTrailer: success
                    UploadGist --> SkipTrailer: gist error (non-blocking)
                    AddTrailer --> WriteCommit
                    SkipTrailer --> WriteCommit
                    WriteCommit --> UpdateChangelog: if entry provided
                    UpdateChangelog --> PruneRegistry: success only
                    WriteCommit --> CommitFailed: GitError
                }

                CommitFailed --> RecoveryInfo: exit 22
                note right of CommitFailed
                    RECOVERY: Registry NOT pruned
                    Files stay staged
                    User can retry `weld commit`
                end note

                PruneRegistry --> NextSession
            }

            Done_S --> [*]
        }

        %% Fallback Flow
        state "FallbackFlow" as fallback {
            [*] --> AnalyzeDiff
            AnalyzeDiff --> ClaudeGrouping: Claude suggests logical groups
            ClaudeGrouping --> ParseGroups
            ParseGroups --> MergeGroups: --no-split flag
            ParseGroups --> ProcessGroups: multiple commits OK

            state "ProcessGroups" as groups {
                [*] --> NextGroup
                NextGroup --> ProcessGroup: has more

                state "ProcessGroup" as group {
                    [*] --> UnstageAll_G
                    UnstageAll_G --> StageGroupFiles
                    StageGroupFiles --> UpdateChangelog_G
                    UpdateChangelog_G --> CheckIsLast
                    CheckIsLast --> AttachTranscripts: is last commit
                    CheckIsLast --> WriteCommit_G: not last

                    state "AttachTranscripts" as attach {
                        [*] --> FindMatchingSessions
                        FindMatchingSessions --> UploadMultiple: sessions found
                        FindMatchingSessions --> DetectCurrentSession: no matches
                        UploadMultiple --> AddAllTrailers
                        DetectCurrentSession --> UploadSingle: session found
                        DetectCurrentSession --> NoTranscript: no session
                    }

                    AttachTranscripts --> WriteCommit_G
                    WriteCommit_G --> [*]
                }

                ProcessGroup --> NextGroup
                NextGroup --> Done_G: done
            }

            Done_G --> [*]
        }

        CheckSessionFlow --> SessionBased
        CheckSessionFlow --> FallbackFlow
        SessionBased --> LogCommand
        FallbackFlow --> LogCommand
        LogCommand --> [*]
    }

    %% ==========================================
    %% REVIEW COMMAND STATE MACHINE
    %% ==========================================

    state "REVIEW COMMAND" as review_cmd {
        [*] --> ValidateFlags_R
        ValidateFlags_R --> CodeReview: --diff flag
        ValidateFlags_R --> DocReview: document path

        state "CodeReview" as code_review {
            [*] --> GetDiff_R
            GetDiff_R --> NoChanges_R: empty diff
            GetDiff_R --> GenerateReviewId_R: has changes
            NoChanges_R --> [*]: exit 0
            GenerateReviewId_R --> DryRun_R: --dry-run
            DryRun_R --> [*]
            GenerateReviewId_R --> CreateArtifacts_R: continue
            CreateArtifacts_R --> SavePrompt_R
            SavePrompt_R --> SaveDiff_R
            SaveDiff_R --> PromptOnly_R: --prompt-only
            PromptOnly_R --> [*]
            SaveDiff_R --> RunClaude_R: continue
            RunClaude_R --> SaveFindings: review mode
            RunClaude_R --> SaveFixes: --apply mode
        }

        state "DocReview" as doc_review {
            [*] --> ReadDocument
            ReadDocument --> GenerateReviewId_D
            GenerateReviewId_D --> DryRun_D: --dry-run
            GenerateReviewId_D --> CreateArtifacts_D: continue
            CreateArtifacts_D --> SaveOriginal: --apply mode
            CreateArtifacts_D --> SavePrompt_D: review mode
            SaveOriginal --> SavePrompt_D
            SavePrompt_D --> PromptOnly_D: --prompt-only
            PromptOnly_D --> [*]
            SavePrompt_D --> RunClaude_D: continue
            RunClaude_D --> StripPreamble_R
            StripPreamble_R --> SaveCorrected: --apply mode
            SaveCorrected --> WriteBackToDoc: apply to source
            StripPreamble_R --> SaveFindings_D: review mode
        }
    }

    %% ==========================================
    %% STATE PERSISTENCE
    %% ==========================================

    state "STATE PERSISTENCE" as storage {
        state "Plan File" as plan_file {
            Markdown: phases & steps
            Markers: **COMPLETE** suffix
            AtomicWrites: temp + rename
            LineVerify: pattern check before modify
        }

        state "Session Registry" as registry {
            Path: .weld/sessions/registry.jsonl
            Format: JSONL append-only
            Content: session_id, files, activities
            Semantic: last-write-wins for files
            Pruning: only after commit success
            Corruption: skip bad lines, warn
        }

        state "Command History" as history {
            Path: .weld/{cmd}/history.jsonl
            Format: JSONL append-only
            Content: timestamp, input, output
            Corruption: skip bad lines gracefully
        }

        state "Review Artifacts" as reviews {
            Path: .weld/reviews/{review_id}/
            ReviewId: {timestamp}-{type}-{mode}
            Content: prompt.md, diff.patch, findings.md, fixes.md
            DocApply: original.md, corrected.md
        }

        state "Config" as config {
            Path: .weld/config.toml
            Format: TOML
            Content: checks, models, git settings
            Tracked: only file in .weld/ committed to git
        }
    }
```

## Summary of Key State Machines

### 1. Main Workflow

```
init --> research/discover/interview --> plan --> implement <--> review --> commit
```

The primary human-in-the-loop workflow where users progress through stages of development with AI assistance.

### 2. Discover Command

Linear flow with early-exit points:
- **Dry-run**: Shows what would happen without execution
- **Prompt-only**: Generates and displays prompt without Claude
- **Full run**: Claude analyzes codebase, writes architecture doc

### 3. Interview Command

Interactive loop for specification refinement:
- Claude generates clarifying questions
- User provides answers
- Claude integrates answers into document
- Continues until user says "done" or Ctrl+C

### 4. Implement Command

The most complex state machine with these phases:

- **Entry**: Parse plan -> validate -> load config -> conditional registry load
- **Registry**: Only loaded if `--auto-commit` flag set
- **Loop**: Menu -> select -> execute step -> Claude -> mark complete -> optional review -> optional commit -> back to menu
- **Session Capture**: Captured AFTER step completion but BEFORE review (critical for transcript provenance)
- **Review**: Skipped entirely if `--no-review` flag; errors are non-blocking
- **Commit**: Only prompted if `--auto-commit`; errors are non-blocking
- **Phase Execution**: Fail-fast; phase marked complete ONLY if ALL steps succeed
- **Exit**: Snapshot -> record activity -> save registry
- **Graceful Exit**: Ctrl+C saves state via context manager finally block
- **Snapshot Timeout**: 5 seconds for large repos, returns partial if exceeded

### 5. Commit Command

Dual-path commit flow:

**Session-Based Flow** (default when registry has sessions):
- Maps staged files to originating sessions (last-write-wins)
- Processes sessions chronologically, untracked files last
- Per session: stage files -> Claude message -> render transcript -> upload gist -> commit -> prune registry
- Error recovery: Exit 22 leaves registry unpruned, files staged for retry

**Fallback Flow** (empty registry or `--no-session-split`):
- Claude analyzes diff, suggests logical groupings
- Can merge to single commit with `--no-split`
- Finds ALL matching sessions for transcript attachment
- Attaches multiple transcript URLs to LAST commit only

### 6. Review Command

Two modes based on input:
- **Code Review** (`--diff`): Reviews git diff, optionally applies fixes
- **Document Review**: Reviews markdown doc against codebase

Both modes support:
- `--dry-run`: Preview without execution
- `--prompt-only`: Generate prompt without Claude
- `--apply`: Apply fixes directly to files

### 7. State Storage

| Storage | Location | Purpose | Invariants |
|---------|----------|---------|------------|
| Plan markers | `plan.md` | Step/phase completion (`**COMPLETE**`) | Atomic writes, line verification |
| Session registry | `.weld/sessions/registry.jsonl` | File->session mapping | Last-write-wins, prune-on-success |
| Command history | `.weld/{cmd}/history.jsonl` | Audit trail | Graceful corruption handling |
| Review artifacts | `.weld/reviews/{id}/` | Review prompts & findings | Timestamped directories |
| Config | `.weld/config.toml` | Project settings | Only .weld/ file tracked in git |

## Exit Codes

| Code | Command | Meaning | Recovery |
|------|---------|---------|----------|
| 0 | All | Success (including user quit) | N/A |
| 1 | All | Validation error, weld not initialized | Run `weld init` |
| 3 | All | Not a git repository | N/A |
| 20 | commit | No staged changes | Stage changes with `git add` |
| 21 | implement | Claude execution failed | Check Claude CLI |
| 22 | commit | Git commit failed | Fix issue, retry `weld commit` |
| 23 | commit | Failed to parse Claude response | Retry or use `--no-split` |

## Architectural Layers

```
CLI Layer (commands/)
    | delegates
    v
Core Layer (core/)
    | calls
    v
Services Layer (services/)
    | wraps
    v
External CLIs (git, claude, gh)
```

## Error Recovery

- **Implement**: Ctrl+C triggers context manager finally block; step failures prompt user to continue; review/commit failures are non-blocking
- **Commit (session-based)**: Failures leave remaining sessions in registry with files staged; exit 22 indicates recoverable state; previous commits preserved
- **Commit (fallback)**: Failures exit immediately; all files still staged for retry
- **Session Tracking**: Graceful degradation if Claude session not detected; partial snapshots on timeout

## Key Invariants

### Plan File
- Step format: `### Step {N|N.N}: Title [**COMPLETE**]`
- Phase format: `## Phase N: Title [**COMPLETE**]`
- Atomic writes prevent corruption (temp file + rename)
- Line verification before modification

### Session Registry
- Last-write-wins: File touched by multiple sessions belongs to most recent
- Prune-on-success: Session pruned ONLY after commit succeeds
- Graceful degradation: Corrupted JSONL lines skipped with warning

### Transcript Generation
- Redaction: API keys, tokens, credentials removed
- Truncation: Tool results (2KB), text (10KB), thinking (5KB)
- Size limits: 1MB total, 500 messages max
