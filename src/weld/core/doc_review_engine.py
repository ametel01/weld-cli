"""Review engine for verifying documentation and code changes.

Validates documentation by comparing it against the actual state of the codebase,
identifying errors, missing implementations, gaps, and incorrect evaluations.

Also provides code change review functionality for analyzing git diffs.
"""

import re
from pathlib import Path

DOC_REVIEW_PROMPT_TEMPLATE = """You are a meticulous code auditor verifying documentation accuracy \
against the actual codebase.

## Your Mission

Review the provided document and compare it against the current state of the codebase. \
Your goal is to identify **discrepancies between what the document claims and what \
actually exists**.

## Core Principles

1. **Read code, not docs** - The codebase is the source of truth
2. **Eliminate assumptions** - Verify every claim in the document
3. **Identify authoritative files** - Find the actual implementation locations
4. **Produce actionable findings** - Each issue should be specific and verifiable

If agents are not onboarded with accurate context, they will fabricate.
This mirrors Memento: without memory, agents invent narratives.

## Focus Area

{focus_area}

## Document to Review

```markdown
{document_content}
```

## Review Categories

Analyze the document for the following types of issues:

### 1. Errors
Claims in the document that are factually wrong:
- Functions/classes that don't exist or have different signatures
- File paths that don't exist or are incorrect
- API endpoints with wrong methods, paths, or parameters
- Incorrect descriptions of what code actually does

### 2. Missing Implementations
Features described in the document that aren't implemented:
- Documented functionality without corresponding code
- Planned features marked as complete but not present
- Referenced modules or components that don't exist

### 3. Missing Steps
Gaps in documented workflows or processes:
- Incomplete setup instructions
- Undocumented prerequisites
- Missing configuration steps
- Skipped error handling scenarios

### 4. Wrong Evaluations
Incorrect assessments or characterizations:
- Overstated capabilities or features
- Understated limitations or caveats
- Incorrect status assessments (e.g., "stable" when experimental)
- Misattributed responsibilities to components

### 5. Gaps
Information missing from the document that should be there:
- Undocumented but important components
- Missing architectural decisions or rationale
- Critical configuration not mentioned
- Important dependencies not listed

## Output Format

Produce a structured findings report in the following format:

# Review Findings

## Summary
- **Document reviewed:** [filename]
- **Issues found:** [total count]
- **Critical issues:** [count of errors + missing implementations]
- **Overall assessment:** [PASS/NEEDS_UPDATE/SIGNIFICANT_DRIFT]

## Errors
For each error found:
- **Location in doc:** [section/line reference]
- **Claim:** [what the document says]
- **Reality:** [what the code actually shows]
- **Evidence:** [file:line reference in codebase]

## Missing Implementations
For each missing implementation:
- **Documented feature:** [what was described]
- **Expected location:** [where it should be]
- **Search performed:** [how you looked for it]
- **Status:** NOT_FOUND / PARTIAL / PLACEHOLDER

## Missing Steps
For each missing step:
- **Process:** [which workflow/process]
- **Gap:** [what's missing]
- **Impact:** [what fails without this]

## Wrong Evaluations
For each wrong evaluation:
- **Document claim:** [the assessment made]
- **Actual status:** [what evidence shows]
- **Evidence:** [supporting files/code]

## Gaps
For each gap:
- **Missing topic:** [what should be documented]
- **Importance:** HIGH/MEDIUM/LOW
- **Suggestion:** [what to add]

## Recommendations
Prioritized list of actions to align the document with reality.

---

Be thorough but concise. Focus on substantive issues that would mislead someone \
relying on this document.
"""

DOC_REVIEW_APPLY_PROMPT_TEMPLATE = """You are a meticulous code auditor correcting documentation \
to match the actual codebase.

## Your Mission

Review the provided document, compare it against the current state of the codebase, and \
**produce a corrected version** that accurately reflects reality.

## Core Principles

1. **Read code, not docs** - The codebase is the source of truth
2. **Eliminate assumptions** - Verify every claim before keeping it
3. **Preserve intent** - Keep the document's structure and purpose while fixing inaccuracies
4. **Be conservative** - Only change what is verifiably wrong; don't rewrite for style

If agents are not onboarded with accurate context, they will fabricate.
This mirrors Memento: without memory, agents invent narratives.

## Focus Area

{focus_area}

## Document to Correct

```markdown
{document_content}
```

## Correction Guidelines

Apply these corrections:

### 1. Fix Errors
- Correct function/class names to match actual code
- Fix file paths to actual locations
- Update API endpoints, methods, parameters to match implementation
- Correct descriptions of what code actually does

### 2. Remove Missing Implementations
- Remove or mark as "planned" any features not actually implemented
- Update status markers (remove "complete" for unfinished work)
- Add "[NOT IMPLEMENTED]" markers where appropriate

### 3. Fill Missing Steps
- Add undocumented prerequisites
- Include missing configuration steps
- Complete partial workflows

### 4. Correct Evaluations
- Adjust capability claims to match reality
- Add appropriate caveats and limitations
- Fix status assessments to reflect actual state

### 5. Fill Gaps
- Add critical missing information discovered during review
- Document important undocumented components
- Include missing dependencies

## Output Format

CRITICAL: Output ONLY the corrected markdown document. Your response must contain NOTHING except \
the corrected document.

DO NOT include:
- Preamble like "I'll analyze..." or "Let me start by..."
- Explanations of what you changed
- Commentary, notes, or thinking
- The original document
- Any text before or after the document

Your ENTIRE response must be the corrected markdown document, starting with its first line \
(title, frontmatter, or heading) and ending with its last line. No wrapper text.
"""

# =============================================================================
# Code Review Prompt Templates
# =============================================================================

CODE_REVIEW_PROMPT_TEMPLATE = """You are an expert code reviewer performing a thorough analysis \
of code changes.

## Your Mission

Review the provided git diff and identify issues that could cause problems in production. \
Focus on substantive issues, not style preferences.

## Focus Area

{focus_area}

## Diff to Review

```diff
{diff_content}
```

## Review Categories

Analyze the changes for the following types of issues:

### 1. Bugs
Logic errors and correctness issues:
- Off-by-one errors, boundary conditions
- Null/undefined handling issues
- Race conditions or async problems
- Incorrect boolean logic or comparisons
- Resource leaks (memory, file handles, connections)
- Exception handling gaps

### 2. Security Vulnerabilities
Security issues introduced or exposed:
- Injection vulnerabilities (SQL, command, XSS)
- Authentication/authorization bypasses
- Sensitive data exposure
- Insecure cryptographic practices
- Missing input validation

### 3. Missing Implementations
Incomplete changes that will cause failures:
- Functions that don't handle all code paths
- Missing error handling for expected failures
- Unimplemented TODO/FIXME items in the diff
- Partial refactors leaving dead code or broken references

### 4. Test Issues
Problems with test coverage and assertions:
- Tests that don't assert expected behavior (silent passes)
- Missing test cases for edge conditions
- Tests that would pass even if the code was broken
- Mocked behavior that doesn't match real implementation
- Missing error path testing

### 5. Improvements
Significant issues that should be addressed (not style nits):
- Performance problems (N+1 queries, unnecessary iterations)
- API design issues that will be hard to change later
- Missing logging/observability for debugging
- Hardcoded values that should be configurable

## Output Format

Produce a structured findings report:

# Code Review Findings

## Summary
- **Changes reviewed:** [brief description]
- **Files modified:** [count]
- **Issues found:** [total count]
- **Critical issues:** [count of bugs + security]
- **Verdict:** APPROVE / REQUEST_CHANGES / NEEDS_DISCUSSION

## Critical Issues

### Bugs
For each bug found:
- **File:** [filename:line]
- **Issue:** [clear description of the bug]
- **Impact:** [what will go wrong]
- **Fix:** [specific fix recommendation]

### Security
For each security issue:
- **File:** [filename:line]
- **Vulnerability:** [type of vulnerability]
- **Risk:** HIGH/MEDIUM/LOW
- **Fix:** [specific remediation]

## Other Issues

### Missing Implementations
- **File:** [filename:line]
- **Gap:** [what's missing]
- **Required:** [what needs to be added]

### Test Issues
- **File:** [filename:line]
- **Problem:** [what's wrong with the test]
- **Fix:** [how to improve the test]

### Improvements
- **File:** [filename:line]
- **Issue:** [the problem]
- **Suggestion:** [recommended change]

## Approval Status

[Final recommendation with rationale]

---

Be thorough but focus on issues that matter. Skip style comments unless they indicate \
deeper problems. Every issue should be actionable with a clear fix.
"""

CODE_REVIEW_APPLY_PROMPT_TEMPLATE = """You are an expert code reviewer who fixes issues \
directly in the codebase.

## Your Mission

Review the provided git diff, identify issues, and **fix them directly** in the affected files. \
Apply fixes for all substantive issues found.

## Focus Area

{focus_area}

## Diff to Review

```diff
{diff_content}
```

## Issues to Fix

Look for and fix these types of issues:

### 1. Bugs
- Off-by-one errors, boundary conditions
- Null/undefined handling issues
- Race conditions or async problems
- Incorrect boolean logic
- Resource leaks
- Exception handling gaps

### 2. Security Vulnerabilities
- Injection vulnerabilities
- Missing input validation
- Sensitive data exposure
- Authentication/authorization issues

### 3. Missing Implementations
- Functions that don't handle all code paths
- Missing error handling
- Partial refactors leaving broken code

### 4. Test Issues
- Tests that don't assert expected behavior
- Missing edge case tests
- Assertions that would pass on broken code
- Missing error path testing

### 5. Significant Improvements
- Performance problems (N+1 queries, etc.)
- Missing error logging
- Hardcoded values that should be configurable

## Instructions

1. Read the diff carefully to understand all changes
2. Identify every file with issues that need fixing
3. For each file with issues, use your tools to:
   - Read the current file content
   - Apply all necessary fixes
   - Ensure fixes don't break other code

## Fix Guidelines

- Fix ALL issues found, not just critical ones
- Preserve existing code style and patterns
- Add error handling where missing
- Fix tests to properly assert expected behavior
- Add TODO comments only for issues you cannot fix without more context

## Output

After applying all fixes, provide a summary:

# Fixes Applied

## Summary
- **Files fixed:** [count]
- **Issues fixed:** [total]
- **Issues requiring manual review:** [count, if any]

## Changes Made

For each file modified:
### [filename]
- [Issue 1]: [what was fixed]
- [Issue 2]: [what was fixed]

## Manual Review Needed

[List any issues that couldn't be fixed automatically, with explanation]
"""


def generate_doc_review_prompt(
    document_content: str, apply_mode: bool = False, focus: str | None = None
) -> str:
    """Generate review prompt for document verification.

    Args:
        document_content: Content of the markdown document to review
        apply_mode: If True, generate prompt for correcting the document in place
        focus: Optional topic to focus the review on

    Returns:
        Formatted prompt for AI review
    """
    focus_area = focus or "Review all aspects of the document comprehensively."
    if apply_mode:
        return DOC_REVIEW_APPLY_PROMPT_TEMPLATE.format(
            document_content=document_content, focus_area=focus_area
        )
    return DOC_REVIEW_PROMPT_TEMPLATE.format(
        document_content=document_content, focus_area=focus_area
    )


def generate_code_review_prompt(
    diff_content: str, apply_mode: bool = False, focus: str | None = None
) -> str:
    """Generate review prompt for code changes.

    Args:
        diff_content: Git diff output to review
        apply_mode: If True, generate prompt for fixing issues directly
        focus: Optional topic to focus the review on

    Returns:
        Formatted prompt for AI code review
    """
    focus_area = focus or "Review all aspects of the code changes comprehensively."
    if apply_mode:
        return CODE_REVIEW_APPLY_PROMPT_TEMPLATE.format(
            diff_content=diff_content, focus_area=focus_area
        )
    return CODE_REVIEW_PROMPT_TEMPLATE.format(diff_content=diff_content, focus_area=focus_area)


def get_doc_review_dir(weld_dir: Path) -> Path:
    """Get or create document review directory.

    Args:
        weld_dir: Path to .weld directory

    Returns:
        Path to .weld/reviews/ directory
    """
    review_dir = weld_dir / "reviews"
    review_dir.mkdir(exist_ok=True)
    return review_dir


def strip_preamble(content: str) -> str:
    """Strip AI preamble from document content.

    Removes any text before the actual markdown document starts.
    Looks for common document start patterns: headings, frontmatter, horizontal rules.

    Args:
        content: Raw response that may contain preamble

    Returns:
        Cleaned content starting with actual document
    """
    lines = content.split("\n")

    # Find first line that looks like document content
    # Common patterns: # Heading, ---, or other markdown structural elements
    doc_start_pattern = re.compile(r"^(#|---|\*\*\*|___|\[|!\[|```|>|[-*+] |\d+\. |<)")

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and doc_start_pattern.match(stripped):
            return "\n".join(lines[i:])

    # No clear document start found, return as-is
    return content
