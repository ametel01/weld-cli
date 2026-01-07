# Plan Format

Plans follow a hierarchical **Phase → Step** structure designed for systematic implementation.

## Structure

```markdown
## Phase 1: <Title>

Brief description of what this phase accomplishes.

### Phase Validation
```bash
# Command(s) to verify the entire phase is complete
```

### Step 1: <Title>

#### Goal
What this step accomplishes.

#### Files
- `path/to/file.py` - What changes to make

#### Validation
```bash
# Command to verify this step works
```

#### Failure modes
- What could go wrong and how to detect it

---

### Step 2: <Title>
...

## Phase 2: <Title>

### Step 1: <Title>
(Step numbers restart at 1 for each phase)
...
```

## Phase Guidelines

- Each phase is a logical milestone (e.g., "Data Models", "Core Logic", "CLI Integration")
- Phases are incremental - each builds on the foundation of previous phases
- Include Phase Validation to verify the entire phase works before moving on

## Step Guidelines

- Step numbers restart at 1 within each phase
- Each step should be atomic and independently verifiable
- Include specific file paths and validation commands

## Completion Tracking

When a step is completed by `weld implement`, it's marked in the plan:

```markdown
### Step 1: Create data models [COMPLETE]
```

This allows resuming implementation from where you left off.

## Example Plan

```markdown
## Phase 1: Data Models

Define the core data structures for the feature.

### Phase Validation
```bash
python -c "from myapp.models import User; print('OK')"
```

### Step 1: Create User model

#### Goal
Define the User model with authentication fields.

#### Files
- `src/myapp/models/user.py` - Create User class with email, password_hash

#### Validation
```bash
pytest tests/test_models.py -v
```

#### Failure modes
- Import errors if dependencies missing
- Validation errors if fields incorrectly typed

---

### Step 2: Add database migration

#### Goal
Create migration for User table.

#### Files
- `migrations/001_create_users.py` - Migration script

#### Validation
```bash
python -m migrations upgrade
```

## Phase 2: Authentication

Implement login and session management.

### Step 1: Create auth service
...
```

## See Also

- [plan](../commands/plan.md) - Generate a plan
- [implement](../commands/implement.md) - Execute a plan
