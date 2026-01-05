"""Document review engine for verifying documentation against codebase.

Validates documentation by comparing it against the actual state of the codebase,
identifying errors, missing implementations, gaps, and incorrect evaluations.
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


def generate_doc_review_prompt(document_content: str, apply_mode: bool = False) -> str:
    """Generate review prompt for document verification.

    Args:
        document_content: Content of the markdown document to review
        apply_mode: If True, generate prompt for correcting the document in place

    Returns:
        Formatted prompt for AI review
    """
    if apply_mode:
        return DOC_REVIEW_APPLY_PROMPT_TEMPLATE.format(document_content=document_content)
    return DOC_REVIEW_PROMPT_TEMPLATE.format(document_content=document_content)


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
