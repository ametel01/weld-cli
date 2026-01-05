"""Discover engine for codebase analysis.

Generates comprehensive technical specification documents from existing codebases,
providing detailed context for brownfield development planning.
"""

from pathlib import Path

DISCOVER_PROMPT_TEMPLATE = """You are a senior software architect creating a comprehensive \
technical specification document for an existing codebase.

## Your Mission

Produce a **detailed, exhaustive technical specification** that fully documents this \
codebase. This document will be used by developers to understand, maintain, and extend \
the system. Leave no stone unturned.

{focus_areas}

## Document Structure

Create a complete technical specification with the following sections:

### 1. Executive Summary
- What this project does in 2-3 paragraphs
- Primary use cases and target users
- Technology stack overview
- Current state and maturity level

### 2. System Architecture

#### 2.1 High-Level Design
- Architecture style (monolith, microservices, serverless, etc.)
- System boundaries and external dependencies
- Data flow diagrams (describe in text)
- Key architectural decisions and their rationale

#### 2.2 Component Breakdown
For EACH major component/module:
- Purpose and responsibility
- Public interfaces and APIs
- Dependencies (what it imports/uses)
- Dependents (what uses it)
- File locations with line references

#### 2.3 Layer Architecture
- Presentation/UI layer (if applicable)
- Business logic layer
- Data access layer
- Infrastructure/utilities layer

### 3. Codebase Structure

#### 3.1 Directory Layout
Document EVERY top-level directory:
- Purpose and contents
- Naming conventions
- Organization patterns

#### 3.2 Key Files Deep Dive
For each critical file:
- Full path and purpose
- Main classes/functions with line numbers
- Configuration and environment variables
- Entry points and initialization flow

### 4. Data Models & State Management

#### 4.1 Data Models
- All entity/model definitions with fields
- Relationships between models
- Validation rules and constraints
- Database schema (if applicable)

#### 4.2 State Management
- How state is managed (Redux, Context, local state, etc.)
- State shape and structure
- State mutations and actions

### 5. API & Interfaces

#### 5.1 External APIs
For each API endpoint:
- HTTP method and path
- Request/response formats
- Authentication requirements
- Error handling

#### 5.2 Internal Interfaces
- Key function signatures
- Class interfaces and protocols
- Event systems and callbacks

### 6. Configuration & Environment

#### 6.1 Configuration Files
- All config files and their purposes
- Environment variables (list ALL of them)
- Feature flags and toggles
- Secrets management approach

#### 6.2 Build & Deployment
- Build system and commands
- Deployment targets and processes
- CI/CD pipeline (if visible)

### 7. Dependencies & Integrations

#### 7.1 Package Dependencies
- Key dependencies and their purposes
- Version constraints
- Security considerations

#### 7.2 External Services
- Third-party APIs and services
- Database connections
- Message queues, caches, etc.

### 8. Testing Strategy

#### 8.1 Test Organization
- Test directory structure
- Test categories (unit, integration, e2e)
- Test utilities and helpers

#### 8.2 Testing Patterns
- Mocking strategies
- Fixtures and factories
- Coverage requirements

### 9. Error Handling & Logging

#### 9.1 Error Handling
- Error types and hierarchies
- Error propagation patterns
- User-facing error messages

#### 9.2 Logging & Monitoring
- Logging framework and levels
- Log formats and destinations
- Monitoring and alerting (if visible)

### 10. Security Considerations
- Authentication mechanisms
- Authorization and permissions
- Input validation patterns
- Known security measures

### 11. Performance Considerations
- Caching strategies
- Optimization patterns
- Known bottlenecks or concerns

### 12. Development Workflow
- How to set up local development
- Common development tasks
- Code style and conventions

## Output Requirements

1. **Be exhaustive** - Document everything you find
2. **Use file:line references** - e.g., `src/auth/handler.py:45-120`
3. **Include concrete details** - Actual function names, actual config keys, actual API paths
4. **Organize hierarchically** - Use headers, subheaders, and lists
5. **Write for developers** - Technical audience, no fluff

The output should be a complete markdown document that serves as the authoritative \
technical reference for this codebase.
"""


def generate_discover_prompt(focus_areas: str | None = None) -> str:
    """Generate discover prompt for codebase analysis.

    Args:
        focus_areas: Optional specific areas to focus on

    Returns:
        Formatted prompt for AI discovery
    """
    areas = focus_areas or "Analyze the entire codebase holistically."
    return DISCOVER_PROMPT_TEMPLATE.format(focus_areas=areas)


def get_discover_dir(weld_dir: Path) -> Path:
    """Get or create discover directory.

    Args:
        weld_dir: Path to .weld directory

    Returns:
        Path to .weld/discover/ directory
    """
    discover_dir = weld_dir / "discover"
    discover_dir.mkdir(exist_ok=True)
    return discover_dir
