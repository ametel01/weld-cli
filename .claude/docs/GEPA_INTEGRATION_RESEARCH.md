# GEPA Integration Research

## Overview

This document analyzes potential integration strategies between [GEPA](https://github.com/stanfordnlp/gepa) (Genetic-Pareto optimization framework) and weld-cli.

**Date**: 2026-01-10
**GEPA Location**: `/home/ametel/source/gepa`
**Weld Location**: `/home/ametel/source/weld-cli`

---

## What is GEPA?

**GEPA (Genetic-Pareto)** is a Python framework for optimizing arbitrary systems composed of text components using LLM-based reflection and Pareto-efficient evolutionary search. It evolves text-based system components—such as AI prompts, code snippets, instructions, or textual specifications—against any evaluation metric.

### Key Innovation

GEPA leverages LLMs to reflect on system execution traces and automatically propose improvements, enabling efficient optimization with minimal evaluations. Based on the research paper "GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning" (arXiv:2507.19457).

### Real-World Impact

- Improved GPT-4.1 Mini's performance on AIME from 46.6% to 56.6% (10% improvement)
- Evolved DSPy programs from 67% to 93% accuracy on MATH benchmark
- Used by Databricks, MLflow, and other major organizations for prompt optimization

---

## GEPA Architecture

### Core Components

#### 1. **Core Layer** (`src/gepa/core/`)

**`adapter.py` - GEPAAdapter Protocol**
- Integration point between GEPA and any system
- Three key responsibilities:
  - `evaluate()`: Run a candidate on a batch and return scores/trajectories
  - `make_reflective_dataset()`: Extract relevant traces for LLM reflection
  - `propose_new_texts()`: Optional custom instruction proposal logic
- Generic over `DataInst` (input), `Trajectory` (execution traces), `RolloutOutput` (output)

**`engine.py` - GEPAEngine**
- Orchestrates the optimization loop
- Manages state across iterations
- Coordinates proposers (reflective mutation and merge)
- Handles validation evaluation and Pareto frontier tracking
- Implements graceful stopping mechanisms

**`state.py` - GEPAState**
- Maintains persistent optimizer state
- Tracks evaluated candidates and their scores
- Manages Pareto frontiers (instance-level, objective-level, hybrid, or cartesian)
- Supports serialization for resumable runs
- Stores validation evaluations and outputs

**`result.py` - GEPAResult**
- Final optimization results container
- Returns best candidate and detailed metrics

**`data_loader.py`**
- Flexible data loading with support for lists or custom loaders

#### 2. **Proposer Layer** (`src/gepa/proposer/`)

**`reflective_mutation.py` - ReflectiveMutationProposer**
- Core GEPA algorithm: Uses LLM reflection on execution traces
- Analyzes failures/successes to propose targeted improvements
- Generates improved text based on feedback and execution patterns
- Multiple reflection component selection strategies

**`merge.py` - MergeProposer**
- Optional strategy to combine two Pareto-optimal candidates
- Creates diverse candidate variants

#### 3. **Strategies Layer** (`src/gepa/strategies/`)

Pluggable strategies for customizing optimization behavior:

- **`batch_sampler.py`**: Minibatch selection strategies
- **`candidate_selector.py`**: Parent selection (Pareto, CurrentBest, EpsilonGreedy)
- **`component_selector.py`**: Component selection (RoundRobin, All)
- **`eval_policy.py`**: Validation policies (Full, Incremental)

#### 4. **Pre-Built Adapters** (`src/gepa/adapters/`)

- **`default_adapter/`**: Single-turn LLM prompt optimization
- **`dspy_adapter/`**: DSPy integration (integrated into DSPy main repo)
- **`dspy_full_program_adapter/`**: Full program evolution
- **`generic_rag_adapter/`**: RAG system optimization (vector store-agnostic)
- **`mcp_adapter/`**: Model Context Protocol optimization
- **`terminal_bench_adapter/`**: Terminal-use agent optimization
- **`anymaths_adapter/`**: Mathematical problem-solving

### Key Features

#### Optimization Capabilities
- Multi-component optimization: Evolve multiple text components simultaneously
- Pareto-aware selection: Track Pareto frontiers (instance, objective, hybrid, cartesian)
- Reflective improvement: Uses LLM to understand failures and propose fixes
- Execution-guided feedback: Leverages system traces and error messages
- Reproducibility: Seeded RNG for deterministic behavior
- State persistence: Save/resume optimization runs

#### Framework Integration
- Works with DSPy (official integration)
- Works with any LLM via LiteLLM or custom callables
- Integrates with MLflow and Weights & Biases
- Extensible adapter pattern for any system

#### Evaluation Features
- Two-stage evaluation: Minibatch for acceptance, full validation for tracking
- Multi-objective optimization support
- Custom evaluators through Protocol pattern
- Flexible validation policies

#### Advanced Features
- Candidate merging for population diversity
- Custom reflection prompt templates
- Component-specific selection strategies
- Graceful shutdown with Ctrl+C handling
- Progress bar support
- Comprehensive error handling

### GEPA Data Flow

```
1. User calls gepa.optimize() with seed candidate, datasets, configuration
   ↓
2. Engine initializes state by evaluating seed candidate on validation set
   ↓
3. Each iteration loop:
   - Proposer selects parent candidate(s) from Pareto frontier/state
   - Sample minibatch from training set
   - Adapter evaluates parent on minibatch (captures execution traces)
   - Adapter extracts reflective dataset from traces
   - Proposer uses reflection LM to generate improved candidate text
   - Adapter evaluates new candidate on same minibatch
   - If improved: run full validation evaluation
   - State updates Pareto frontiers and candidate history
   ↓
4. Check stopping conditions (budget, time, improvement plateau, etc.)
   ↓
5. Return GEPAResult with best candidate(s) and optimization metrics
```

### Dependencies

**Core**:
- No hard dependencies (minimal core)

**Optional** (`[full]` extra):
- `litellm>=1.64.0` - Multi-LLM support
- `datasets>=2.14.6` - Dataset handling
- `mlflow>=3.0.0` - Experiment tracking
- `wandb` - Weights & Biases integration
- `tqdm>=4.66.1` - Progress bars

**Development** (`[dev]` extra):
- `pytest` - Testing
- `pyright` - Type checking
- `ruff` - Linting/formatting
- `pre-commit` - Git hooks

---

## Weld-CLI Overview

**Weld** is a human-in-the-loop coding harness that generates structured prompts for AI-assisted development.

### Core Workflow

```
research → plan → implement → review → commit
```

With full transcript provenance tracking.

### Key Features

- **Research**: Generate research prompts for codebase understanding
- **Plan**: Generate phased implementation plans
- **Implement**: Interactive plan execution with checkpointing
- **Review**: Document/code review with optional auto-fix
- **Commit**: Session-based commits with transcript provenance
- **Discover**: Brownfield codebase discovery
- **Interview**: Interactive specification refinement

### Architecture Highlights

- **Commands delegate to core**: Thin CLI layer, business logic in `core/`
- **Services wrap external CLIs**: All subprocess calls through `services/` (never `shell=True`)
- **JSONL append-only logs**: Command history and session registry
- **Automatic session tracking**: Captures file changes during `weld implement`
- **Pydantic everywhere**: All data structures validated

### Shared Technology Stack

Both GEPA and Weld use:
- Python 3.10+
- `uv` for package management
- `ruff` for linting/formatting
- `pyright` for type checking
- `pytest` for testing
- Similar development workflows

---

## Integration Synergies

### Natural Alignment Points

1. **Prompt Generation**: Both deal with generating effective prompts for LLMs
2. **Execution Traces**: Both track execution outcomes (weld: transcripts, GEPA: trajectories)
3. **Iterative Improvement**: Weld provides human-in-the-loop, GEPA provides automated optimization
4. **Session Tracking**: Both maintain persistent state across runs
5. **Modular Architecture**: Both designed for extensibility

### Complementary Strengths

| Weld-CLI | GEPA |
|----------|------|
| Human-in-the-loop workflow | Automated optimization |
| Structured prompt templates | Prompt evolution via reflection |
| Session provenance tracking | Pareto frontier optimization |
| Interactive execution | Batch evaluation |
| Git integration | Experiment tracking (MLflow/WandB) |

---

## Integration Options

### Option 1: Prompt Optimization Service ⭐ **(Recommended)**

Add GEPA as an optimization layer for Weld's prompt templates.

#### Architecture

```python
# New command: weld optimize
src/weld/commands/optimize.py
  - CLI interface for optimizing weld prompts
  - Target tasks: research, plan, implement, review, discover
  - Options: --task, --dataset, --iterations, --apply

# New core module
src/weld/core/prompt_optimizer.py
  - WeldGEPAAdapter implementing GEPAAdapter protocol
  - Evaluates prompt quality using actual weld tasks
  - Tracks optimization runs in .weld/optimization/

# New service
src/weld/services/gepa_service.py
  - Wraps GEPA optimize() calls
  - Handles GEPA state management
  - Provides weld-specific evaluation metrics

# New config section in .weld/config.toml
[optimization]
enabled = true
evaluations_per_iteration = 10
max_iterations = 50
validation_size = 20
metrics = ["plan_completeness", "plan_clarity", "plan_feasibility"]
```

#### Workflow

```bash
# 1. Collect validation dataset
mkdir .weld/optimization/plan/validation/
cp examples/feature_*.md .weld/optimization/plan/validation/

# 2. Run optimization
weld optimize plan --dataset .weld/optimization/plan/validation/ --iterations 50

# 3. Preview improved prompts
weld optimize plan --show-best

# 4. Apply optimized prompt
weld optimize plan --apply

# 5. Test with real task
weld plan new_feature.md
```

#### Implementation Pseudocode

```python
# src/weld/core/prompt_optimizer.py
from gepa import optimize
from gepa.core.adapter import GEPAAdapter

class WeldPlanAdapter(GEPAAdapter):
    """Adapter for optimizing weld plan generation prompts."""

    def __init__(self, config: WeldConfig):
        self.config = config
        self.plan_engine = PlanEngine(config)

    def evaluate(self, candidate_prompt: str, batch: list[Path]) -> tuple[list[float], list[Trajectory]]:
        """Run weld plan with candidate prompt on validation specs."""
        scores = []
        trajectories = []

        for spec_path in batch:
            # Generate plan with candidate prompt
            plan, transcript = self.plan_engine.generate_with_prompt(
                candidate_prompt,
                spec_path
            )

            # Evaluate plan quality
            score = self._evaluate_plan_quality(plan, spec_path)
            trajectory = Trajectory(
                input=spec_path,
                output=plan,
                transcript=transcript,
                score=score
            )

            scores.append(score)
            trajectories.append(trajectory)

        return scores, trajectories

    def make_reflective_dataset(
        self,
        parent_text: str,
        batch: list[Path],
        trajectories: list[Trajectory]
    ) -> list[tuple[Path, Trajectory]]:
        """Extract failed plans for LLM reflection."""
        threshold = 0.7  # Configurable
        failed_examples = [
            (spec, traj)
            for spec, traj in zip(batch, trajectories)
            if traj.score < threshold
        ]
        return failed_examples

    def _evaluate_plan_quality(self, plan: Plan, spec: Path) -> float:
        """Multi-dimensional plan evaluation."""
        scores = []

        # Completeness: Does plan address all requirements?
        completeness = self._check_completeness(plan, spec)
        scores.append(completeness)

        # Clarity: Are steps well-defined and actionable?
        clarity = self._check_clarity(plan)
        scores.append(clarity)

        # Feasibility: Can steps be realistically executed?
        feasibility = self._check_feasibility(plan)
        scores.append(feasibility)

        # Structure: Proper phasing and dependencies?
        structure = self._check_structure(plan)
        scores.append(structure)

        return sum(scores) / len(scores)  # Average score

# Usage in weld optimize command
def optimize_plan_prompts(
    validation_dataset: Path,
    iterations: int,
    config: WeldConfig
) -> GEPAResult:
    """Optimize weld plan generation prompts."""

    # Load current prompt
    current_prompt = load_plan_prompt(config)

    # Load validation specs
    specs = list(validation_dataset.glob("*.md"))
    train_specs = specs[:int(0.8 * len(specs))]
    val_specs = specs[int(0.8 * len(specs)):]

    # Run GEPA optimization
    result = optimize(
        seed_candidate=current_prompt,
        adapter=WeldPlanAdapter(config),
        train_data=train_specs,
        val_data=val_specs,
        max_iterations=iterations,
        run_dir=Path(".weld/optimization/plan/runs"),
        stop_condition=MaxMetricCallsStopper(max_calls=iterations * 10)
    )

    return result
```

#### Benefits

- ✅ Systematically improve prompt quality over time
- ✅ Data-driven optimization using real project tasks
- ✅ Preserves human-in-the-loop control (user approves before applying)
- ✅ Reuses existing weld evaluation infrastructure
- ✅ Clean separation of concerns (optimization is opt-in)
- ✅ Supports all weld commands (plan, review, research, discover)

#### Risks

- ⚠️ Requires good validation datasets
- ⚠️ LLM costs for multiple evaluations
- ⚠️ Optimization might overfit to validation set

#### Estimated Effort

- **Phase 1** (Basic integration): 3-5 days
  - WeldGEPAAdapter implementation
  - `weld optimize` command skeleton
  - Plan prompt optimization only

- **Phase 2** (Full features): 5-7 days
  - Multi-task optimization (plan, review, research)
  - Evaluation metrics for each task type
  - Config management and persistence

- **Phase 3** (Polish): 2-3 days
  - Testing and documentation
  - Example datasets
  - User feedback integration

---

### Option 2: Adaptive Plan Generation

Use GEPA to dynamically optimize plan prompts based on project history.

#### Architecture

```python
# Extend existing plan command
src/weld/commands/plan.py
  - Add --optimize flag to enable GEPA-based refinement
  - Use historical plan success/failure from .weld/sessions/

# New service
src/weld/services/plan_evolution.py
  - Tracks plan execution outcomes (completed steps, errors, review findings)
  - Builds reflective dataset from session transcripts
  - Automatically evolves plan prompts based on project patterns

# New models
src/weld/models/plan_outcome.py
  - PlanOutcome: success rate, error patterns, review issues
  - OutcomeMetrics: aggregated metrics for optimization
```

#### Workflow

```bash
# User runs plan with optimization enabled
weld plan feature.md --optimize

# Internally:
# 1. Analyze previous plan executions from .weld/sessions/registry.jsonl
# 2. Extract success/failure patterns
# 3. Run GEPA optimization with historical data as training set
# 4. Generate plan using improved prompt
# 5. Track optimization provenance in plan metadata
```

#### Implementation Strategy

```python
# src/weld/services/plan_evolution.py
class PlanEvolutionService:
    """Evolves plan prompts based on project history."""

    def analyze_historical_outcomes(self) -> list[PlanOutcome]:
        """Extract plan execution outcomes from session registry."""
        registry = self._load_session_registry()
        outcomes = []

        for session in registry.sessions:
            # Load session transcript
            transcript = self._load_transcript(session.session_id)

            # Extract plan execution metrics
            outcome = PlanOutcome(
                session_id=session.session_id,
                plan_path=session.plan_path,
                completed_steps=self._count_completed_steps(transcript),
                total_steps=self._count_total_steps(transcript),
                errors=self._extract_errors(transcript),
                review_issues=self._extract_review_issues(transcript),
                completion_rate=self._calculate_completion_rate(transcript)
            )
            outcomes.append(outcome)

        return outcomes

    def build_reflective_dataset(
        self,
        outcomes: list[PlanOutcome]
    ) -> list[tuple[str, str, float]]:
        """Build GEPA training dataset from historical outcomes."""
        dataset = []

        for outcome in outcomes:
            # Load original spec and generated plan
            spec = self._load_spec(outcome.plan_path)
            plan = self._load_plan(outcome.plan_path)

            # Score based on outcome metrics
            score = self._calculate_outcome_score(outcome)

            dataset.append((spec, plan, score))

        return dataset

    def optimize_for_project(
        self,
        spec: str,
        iterations: int = 20
    ) -> tuple[str, str]:
        """Generate optimized plan for current project."""

        # Analyze project history
        outcomes = self.analyze_historical_outcomes()

        if len(outcomes) < 5:
            # Not enough history, use default prompt
            return self._generate_with_default(spec)

        # Build reflective dataset
        dataset = self.build_reflective_dataset(outcomes)
        train_data = [(spec, plan) for spec, plan, _ in dataset[:int(0.8 * len(dataset))]]
        val_data = [(spec, plan) for spec, plan, _ in dataset[int(0.8 * len(dataset)):]]

        # Optimize prompt
        result = optimize(
            seed_candidate=self._get_current_prompt(),
            adapter=WeldPlanAdapter(self.config),
            train_data=train_data,
            val_data=val_data,
            max_iterations=iterations
        )

        # Generate plan with optimized prompt
        improved_prompt = result.best_candidate
        plan = self._generate_with_prompt(improved_prompt, spec)

        return plan, improved_prompt
```

#### Benefits

- ✅ Plans improve automatically as project evolves
- ✅ Learns project-specific patterns and conventions
- ✅ Minimal user intervention required
- ✅ Leverages existing transcript infrastructure
- ✅ Adapts to team coding style over time

#### Risks

- ⚠️ Requires sufficient historical data (cold start problem)
- ⚠️ May slow down plan generation significantly
- ⚠️ Risk of overfitting to recent project patterns
- ⚠️ Harder to debug/understand why plans changed

#### Estimated Effort

- **Phase 1**: 5-7 days (historical analysis + basic optimization)
- **Phase 2**: 3-5 days (integration with plan command)
- **Phase 3**: 2-3 days (testing + fallback mechanisms)

---

### Option 3: Review Quality Enhancement

Optimize review prompts to catch more issues.

#### Architecture

```python
# Extend doc_review_engine
src/weld/core/doc_review_engine.py
  - Add GEPA-based review prompt evolution
  - Evaluate based on: issues found, false positives, fix quality

# New evaluation dataset
.weld/optimization/review/
  - known_issues/: Code samples with documented issues
  - false_positives/: Past false positives to avoid
  - project_patterns/: Project-specific anti-patterns
```

#### Workflow

```bash
# Build evaluation dataset from past reviews
weld optimize review --build-dataset

# Run optimization
weld optimize review --iterations 50

# Test improved review
weld review src/weld/commands/plan.py --use-optimized
```

#### Implementation

```python
class WeldReviewAdapter(GEPAAdapter):
    """Adapter for optimizing weld review prompts."""

    def evaluate(
        self,
        candidate_prompt: str,
        batch: list[Path]
    ) -> tuple[list[float], list[Trajectory]]:
        """Evaluate review quality on known-issue files."""
        scores = []
        trajectories = []

        for file_path in batch:
            # Load file and known issues
            code = file_path.read_text()
            known_issues = self._load_known_issues(file_path)

            # Run review with candidate prompt
            review_result = self.review_engine.review_with_prompt(
                candidate_prompt,
                code
            )

            # Evaluate review quality
            score = self._evaluate_review_quality(
                review_result.issues,
                known_issues
            )

            trajectory = Trajectory(
                input=file_path,
                output=review_result,
                score=score
            )

            scores.append(score)
            trajectories.append(trajectory)

        return scores, trajectories

    def _evaluate_review_quality(
        self,
        found_issues: list[Issue],
        known_issues: list[Issue]
    ) -> float:
        """Calculate precision, recall, and F1 for review."""

        # True positives: issues correctly identified
        tp = len(self._match_issues(found_issues, known_issues))

        # False positives: incorrect issues raised
        fp = len(found_issues) - tp

        # False negatives: issues missed
        fn = len(known_issues) - tp

        # Calculate F1 score
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        return f1
```

#### Benefits

- ✅ Higher quality code reviews
- ✅ Fewer missed issues (improved recall)
- ✅ Fewer false positives (improved precision)
- ✅ Project-specific review criteria
- ✅ Relatively isolated change (less risk)

#### Risks

- ⚠️ Need labeled datasets of code issues
- ⚠️ Subjective evaluation of "good" reviews
- ⚠️ May become too strict or too lenient

#### Estimated Effort

- **Phase 1**: 3-4 days (adapter + basic evaluation)
- **Phase 2**: 2-3 days (dataset collection + metrics)
- **Phase 3**: 2 days (integration + testing)

---

### Option 4: Standalone Integration via Adapter

Create a Weld adapter for GEPA (reverse integration - add adapter to GEPA codebase).

#### Architecture

```python
# In GEPA codebase: src/gepa/adapters/weld_adapter/
adapter.py
  - WeldAdapter for optimizing any weld workflow
  - Wraps weld CLI commands as evaluation function
  - Uses weld transcripts as execution traces

config.py
  - WeldAdapterConfig with command/task mappings

examples/weld_example.py
  - Example optimizing weld plan generation
  - Example optimizing weld review
```

#### Workflow

```python
# User script: optimize_my_weld_prompts.py
from gepa import optimize
from gepa.adapters.weld_adapter import WeldAdapter

# Configure adapter
adapter = WeldAdapter(
    weld_command="plan",
    weld_config_path=".weld/config.toml",
    evaluation_metric="plan_completeness"
)

# Load validation specs
validation_specs = list(Path("validation_specs").glob("*.md"))

# Run optimization
result = optimize(
    seed_candidate=adapter.get_current_prompt(),
    adapter=adapter,
    train_data=validation_specs[:20],
    val_data=validation_specs[20:],
    max_iterations=50
)

# Export optimized prompt
adapter.save_prompt(result.best_candidate, ".weld/optimized_prompts/plan.txt")

# Update weld config to use optimized prompt
adapter.apply_optimized_prompt(result.best_candidate)
```

#### Benefits

- ✅ No changes to weld-cli codebase required
- ✅ Users opt-in to optimization explicitly
- ✅ Keeps projects decoupled (easier to maintain separately)
- ✅ Easier to experiment without affecting weld stability
- ✅ Can optimize any weld command without core changes

#### Risks

- ⚠️ Less seamless integration (extra dependency for users)
- ⚠️ Requires users to write their own optimization scripts
- ⚠️ No built-in weld CLI support

#### Estimated Effort

- **Phase 1**: 2-3 days (basic WeldAdapter in GEPA)
- **Phase 2**: 2 days (examples + documentation)
- **Phase 3**: 1 day (testing)

---

### Option 5: Unified Optimization Command

Add comprehensive `weld evolve` command for continuous improvement.

#### Architecture

```python
# New command
src/weld/commands/evolve.py
  - Background optimization service
  - Monitors session outcomes automatically
  - Evolves prompts based on success metrics
  - Periodic improvement cycles
  - Interactive approval workflow

# New background service
src/weld/services/evolution_service.py
  - Runs optimization in background
  - Aggregates session outcomes
  - Triggers optimization when threshold reached
  - Notifies user of improvements

# New config
[evolution]
auto_optimize = true
optimization_interval = "10 sessions"  # Or "7 days", "50 commands"
target_metrics = ["plan_completion_rate", "review_issue_density"]
min_samples_required = 20
background_mode = true
```

#### Workflow

```bash
# Enable auto-evolution
weld evolve --enable

# Weld now automatically:
# 1. Tracks outcomes during normal usage (plan, implement, review)
# 2. Every 10 sessions (or configurable interval):
#    - Triggers background GEPA optimization
#    - Sends notification when improvements found
# 3. Prompts user to review and approve:
#    weld evolve --review-improvements
# 4. User previews changes, approves/rejects
# 5. Approved prompts automatically applied

# Manual triggers
weld evolve --optimize-now  # Force optimization cycle
weld evolve --status        # Show evolution metrics
weld evolve --rollback      # Revert to previous prompts
```

#### Implementation

```python
class EvolutionService:
    """Continuous improvement service for weld prompts."""

    def __init__(self, config: WeldConfig):
        self.config = config
        self.state = self._load_state()

    def track_outcome(self, command: str, outcome: CommandOutcome):
        """Track command execution outcome for future optimization."""
        self.state.outcomes.append(outcome)

        # Check if optimization threshold reached
        if self._should_trigger_optimization():
            self._trigger_optimization_cycle()

    def _should_trigger_optimization(self) -> bool:
        """Determine if enough data collected for optimization."""
        interval = self.config.evolution.optimization_interval

        if interval.endswith("sessions"):
            threshold = int(interval.split()[0])
            return len(self.state.outcomes) >= threshold

        elif interval.endswith("days"):
            days = int(interval.split()[0])
            last_opt = self.state.last_optimization_time
            return (datetime.now() - last_opt).days >= days

        return False

    def _trigger_optimization_cycle(self):
        """Run background optimization and notify user."""

        if self.config.evolution.background_mode:
            # Run in background, don't block user
            self._run_optimization_async()
        else:
            # Run immediately
            self._run_optimization_sync()

    def _run_optimization_async(self):
        """Run optimization in background thread/process."""
        import subprocess

        # Spawn background process
        subprocess.Popen(
            ["weld", "evolve", "--optimize-background"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        # Show notification
        self._notify_user("Optimization running in background...")

    def optimize_all_prompts(self) -> dict[str, GEPAResult]:
        """Run optimization for all weld commands."""
        results = {}

        for command in ["plan", "review", "research", "discover"]:
            # Extract relevant outcomes
            outcomes = [o for o in self.state.outcomes if o.command == command]

            if len(outcomes) < self.config.evolution.min_samples_required:
                continue

            # Build training dataset
            dataset = self._build_dataset_from_outcomes(outcomes)

            # Run GEPA optimization
            adapter = self._get_adapter_for_command(command)
            result = optimize(
                seed_candidate=self._get_current_prompt(command),
                adapter=adapter,
                train_data=dataset["train"],
                val_data=dataset["val"],
                max_iterations=50
            )

            results[command] = result

        return results

    def present_improvements_for_approval(
        self,
        results: dict[str, GEPAResult]
    ) -> dict[str, bool]:
        """Interactive approval workflow for prompt improvements."""
        approvals = {}

        for command, result in results.items():
            # Show comparison
            self._show_prompt_comparison(
                command,
                current=self._get_current_prompt(command),
                improved=result.best_candidate,
                metrics=result.metrics
            )

            # Ask user
            approve = self._ask_user_approval(
                f"Apply improved {command} prompt? "
                f"(Validation score: {result.best_score:.2f})"
            )

            approvals[command] = approve

        return approvals
```

#### Benefits

- ✅ Continuous improvement without manual intervention
- ✅ Data-driven optimization from actual usage
- ✅ Transparent to user workflow (happens in background)
- ✅ Builds project-specific optimization over time
- ✅ User maintains full control via approval workflow

#### Risks

- ⚠️ Most complex implementation
- ⚠️ Background processes may be hard to debug
- ⚠️ Notification/approval UX needs careful design
- ⚠️ May surprise users with unexpected changes

#### Estimated Effort

- **Phase 1**: 7-10 days (evolution service + background execution)
- **Phase 2**: 5-7 days (approval workflow + UI)
- **Phase 3**: 3-5 days (testing + error handling)
- **Total**: 15-22 days

---

## Comparison Matrix

| Feature | Option 1<br/>Prompt Optimization | Option 2<br/>Adaptive Plan | Option 3<br/>Review Enhancement | Option 4<br/>Standalone Adapter | Option 5<br/>Unified Evolution |
|---------|:--------------------------------:|:--------------------------:|:-------------------------------:|:-------------------------------:|:------------------------------:|
| **Effort** | Medium (7-12 days) | High (10-15 days) | Low (7-9 days) | Very Low (4-6 days) | Very High (15-22 days) |
| **Risk** | Low | Medium | Low | Very Low | High |
| **User Control** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Automation** | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ |
| **Weld Changes** | New command + core | Modify existing commands | Modify review only | None | New command + background service |
| **GEPA Changes** | None | None | None | New adapter | None |
| **Decoupling** | Medium | Low | High | Very High | Low |
| **Extensibility** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Cold Start** | Good (uses defaults) | Poor (needs history) | Good (uses dataset) | Good (user-controlled) | Poor (needs history) |
| **Debuggability** | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ |

---

## Recommended Implementation Path

### Phase 1: Proof of Concept (Option 4) - **1 week**

**Goal**: Validate integration works end-to-end

**Tasks**:
1. Create `WeldAdapter` in GEPA codebase
2. Implement basic evaluation for `weld plan`
3. Write example script showing optimization
4. Document integration approach

**Deliverables**:
- `src/gepa/adapters/weld_adapter/adapter.py`
- `examples/weld_example.py`
- Working optimization demo

**Success Criteria**:
- Successfully optimize a plan prompt
- Demonstrate measurable improvement
- Document lessons learned

---

### Phase 2: Native Integration (Option 1) - **2 weeks**

**Goal**: Add first-class optimization support to weld

**Tasks**:
1. Add `weld optimize` command
2. Implement `WeldGEPAAdapter` in weld codebase
3. Support plan + review optimization
4. Add config management
5. Create evaluation datasets
6. Write tests

**Deliverables**:
- `src/weld/commands/optimize.py`
- `src/weld/core/prompt_optimizer.py`
- `src/weld/services/gepa_service.py`
- Updated `.weld/config.toml` schema
- Test suite
- User documentation

**Success Criteria**:
- `weld optimize plan` works end-to-end
- `weld optimize review` works end-to-end
- Optimized prompts can be applied
- Tests pass with >70% coverage

---

### Phase 3: Automation (Option 2 + 5 hybrid) - **3-4 weeks**

**Goal**: Enable continuous improvement workflow

**Tasks**:
1. Add historical outcome tracking
2. Implement adaptive optimization triggers
3. Build approval workflow
4. Add rollback mechanism
5. Background optimization (optional)

**Deliverables**:
- `src/weld/commands/evolve.py`
- `src/weld/services/evolution_service.py`
- Updated session tracking
- Notification system
- Complete documentation

**Success Criteria**:
- Automatic improvement after N sessions
- User approval workflow works
- Rollback mechanism tested
- Performance acceptable (no blocking delays)

---

## Technical Considerations

### Shared Dependencies

Both projects already use or can benefit from:
- ✅ `litellm` - GEPA uses it, weld could add for optimization
- ✅ `pydantic` - Both use extensively
- ✅ `pytest` - Testing infrastructure
- ✅ Python 3.10+ - Compatible versions
- ✅ `ruff` + `pyright` - Code quality tools

### New Dependencies for Weld

If implementing native integration (Option 1/2/5):
```toml
[project.optional-dependencies]
optimization = [
    "gepa>=0.1.0",
    "litellm>=1.64.0",  # Required by GEPA
    "datasets>=2.14.6",  # Optional, for dataset management
]
```

### Data Requirements

#### For Plan Optimization
- **Training set**: 20-50 diverse feature specifications
- **Validation set**: 10-20 held-out specifications
- **Metrics**: Completeness, clarity, feasibility, structure
- **Source**: Real project specs or synthetic examples

#### For Review Optimization
- **Training set**: 30-100 code files with labeled issues
- **Validation set**: 10-30 held-out files
- **Metrics**: Precision, recall, F1 score
- **Source**: Past review results, known anti-patterns

#### For General Optimization
- **Historical transcripts**: Existing `.weld/sessions/` data
- **Outcome labels**: Success/failure of implementation steps
- **Metrics**: Completion rate, error frequency, review issues

### Computational Cost

GEPA optimization requires multiple LLM calls:
- **Typical budget**: 50-100 evaluations for good results
- **Per evaluation**: 1-2 LLM calls (evaluation + reflection)
- **Total cost**: ~100-200 LLM calls per optimization cycle
- **Mitigation**:
  - Use cheaper models for evaluation (haiku)
  - Cache evaluation results
  - Run in background/offline
  - Provide budget controls

### Performance Impact

| Operation | Without GEPA | With GEPA (Option 1) | With GEPA (Option 2) | With GEPA (Option 5) |
|-----------|-------------|---------------------|---------------------|---------------------|
| `weld plan` | ~10-30s | ~10-30s | ~2-5 min (first time) | ~10-30s |
| `weld review` | ~20-60s | ~20-60s | ~20-60s | ~20-60s |
| `weld optimize plan` | N/A | ~10-30 min | N/A | Background |
| Background evolution | N/A | N/A | N/A | Periodic |

### Storage Requirements

```
.weld/optimization/
├── plan/
│   ├── runs/                    # GEPA state (resumable runs)
│   │   └── run_20260110_143022/
│   │       ├── state.pkl        # ~1-10 MB per run
│   │       └── candidates.jsonl # ~100 KB - 1 MB
│   ├── validation/              # Validation datasets
│   │   └── *.md                 # User-provided specs
│   ├── best_prompts.jsonl       # History of best prompts
│   └── metrics.jsonl            # Optimization metrics
├── review/
│   └── ...                      # Similar structure
└── config.toml                  # Optimization config

# Estimated total: 50-500 MB depending on runs
```

### Security Considerations

- ✅ GEPA uses subprocess for LLM calls (already safe pattern)
- ✅ Validation datasets should be sanitized (no secrets)
- ✅ Optimization runs should respect `.gitignore`
- ⚠️ Prompts may leak info about codebase (document in privacy policy)
- ⚠️ Background processes need proper timeout/cleanup

---

## Example: End-to-End Plan Optimization

### Setup

```bash
# Install weld with optimization support
uv pip install -e ".[optimization]"

# Initialize weld
weld init

# Create validation dataset
mkdir -p .weld/optimization/plan/validation
cp docs/examples/*.md .weld/optimization/plan/validation/

# Configure optimization
cat >> .weld/config.toml << EOF
[optimization]
enabled = true
evaluations_per_iteration = 10
max_iterations = 50
validation_size = 20
EOF
```

### Run Optimization

```bash
# Optimize plan prompts
weld optimize plan \
  --dataset .weld/optimization/plan/validation/ \
  --iterations 50 \
  --metrics completeness,clarity,feasibility

# Output:
# ╭─ Optimizing plan prompts ──────────────────────────╮
# │ Seed prompt score: 0.72                            │
# │ Iteration 1/50: New candidate score 0.75 ✓         │
# │ Iteration 2/50: New candidate score 0.73 ✗         │
# │ Iteration 3/50: New candidate score 0.78 ✓         │
# │ ...                                                │
# │ Best score: 0.89 (iteration 47)                    │
# │ Improvement: +23.6%                                │
# ╰────────────────────────────────────────────────────╯
```

### Review Improvements

```bash
# Show best prompt
weld optimize plan --show-best

# Output shows:
# - Current prompt
# - Best improved prompt
# - Metrics comparison
# - Example plan differences
```

### Apply Optimized Prompt

```bash
# Apply improvement
weld optimize plan --apply

# Confirmation:
# ✓ Applied improved plan prompt (score: 0.89)
# ✓ Backed up previous prompt to .weld/optimization/plan/backups/
# ✓ Updated .weld/config.toml
```

### Test Improved Prompt

```bash
# Generate plan with optimized prompt
weld plan new_feature.md

# Should produce higher quality plans:
# - More complete phase breakdown
# - Clearer step descriptions
# - Better feasibility checking
```

---

## Migration Strategy

### For Existing Weld Users

1. **No breaking changes**: All optimization features opt-in
2. **Backward compatibility**: Existing prompts continue to work
3. **Gradual adoption**: Users can try optimization per-command
4. **Rollback support**: Easy revert to previous prompts
5. **Documentation**: Clear migration guide with examples

### For New Weld Users

1. **Default prompts**: Ship with good default prompts
2. **Optional optimization**: Suggest optimization after N uses
3. **Example datasets**: Provide starter validation sets
4. **Guided setup**: `weld doctor` checks optimization readiness

---

## Success Metrics

### For Integration Quality

- ✅ All tests pass (unit + integration)
- ✅ Type checking passes (pyright strict mode)
- ✅ Linting passes (ruff)
- ✅ Documentation complete
- ✅ Performance acceptable (<30s overhead for optimization commands)

### For Optimization Effectiveness

- ✅ Measurable improvement in prompt quality (>10% score increase)
- ✅ User satisfaction (survey/feedback)
- ✅ Adoption rate (% of users enabling optimization)
- ✅ Plan completion rate increase
- ✅ Review quality improvement (fewer false positives/negatives)

---

## Open Questions

1. **Evaluation Metrics**: How to objectively measure plan/review quality?
   - Possible: User ratings, completion rates, error frequencies
   - Challenge: Subjective and context-dependent

2. **Dataset Collection**: How to build good validation datasets?
   - Possible: Crowdsource from users, synthetic generation, real project history
   - Challenge: Quality and diversity of examples

3. **Prompt Versioning**: How to handle multiple optimized prompts?
   - Possible: Git-like versioning, A/B testing framework
   - Challenge: Complexity and user confusion

4. **Cost Management**: How to control LLM costs for optimization?
   - Possible: Budget limits, cheaper models, caching, user quotas
   - Challenge: Balance cost vs. quality

5. **Personalization vs. Generalization**: Optimize per-project or globally?
   - Possible: Both (global defaults + per-project overrides)
   - Challenge: Storage and maintenance

---

## Next Steps

1. **Stakeholder alignment**: Discuss which option to pursue (recommend Option 1)
2. **Prototype**: Build proof-of-concept (Option 4) in 1 week
3. **Validate**: Test with real weld usage, measure improvements
4. **Design review**: Finalize architecture and API
5. **Implementation**: Build native integration (Option 1) in 2 weeks
6. **Testing**: Comprehensive test suite + user testing
7. **Documentation**: User guide + developer docs
8. **Release**: Ship as experimental feature, gather feedback
9. **Iterate**: Refine based on usage data and user feedback
10. **Expand**: Add automation features (Option 5) if successful

---

## Conclusion

Integrating GEPA with weld-cli offers significant potential for systematically improving prompt quality through data-driven optimization. The recommended path is:

1. **Start with Option 4** (Standalone Adapter) for quick validation
2. **Build Option 1** (Prompt Optimization Service) for production use
3. **Expand to Option 5** (Unified Evolution) if proven valuable

This approach balances risk, effort, and value while maintaining weld's human-in-the-loop philosophy.

**Estimated total timeline**: 6-8 weeks from start to production-ready optimization features.

**Key success factor**: Building high-quality evaluation datasets and metrics that accurately reflect prompt quality for weld's specific use cases.
