# Exit Codes

Weld uses consistent exit codes across all commands for scripting and automation.

## General Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error / file not found / weld not initialized |
| 2 | Dependency missing / unauthenticated gh |
| 3 | Not a git repository |
| 12 | AI provider invocation failed |

## Commit-Specific Exit Codes

| Code | Meaning |
|------|---------|
| 20 | No changes to commit |
| 21 | Transcript generation failed |
| 22 | Git commit failed |
| 23 | Failed to parse Claude response |
| 24 | Editor error |

## Using Exit Codes in Scripts

### Bash Example

```bash
#!/bin/bash
set -e

weld review --diff --staged
exit_code=$?

case $exit_code in
    0)
        echo "Review passed"
        ;;
    12)
        echo "AI provider failed"
        exit 1
        ;;
    *)
        echo "Unknown error: $exit_code"
        exit 1
        ;;
esac
```

### GitHub Actions Example

```yaml
- name: Review changes
  run: weld review --diff --staged
  continue-on-error: true
  id: review

- name: Check review result
  run: |
    if [ ${{ steps.review.outcome }} == 'failure' ]; then
      echo "Review found issues"
      exit 1
    fi
```

## See Also

- [Commands Reference](../commands/index.md) - Command-specific exit codes
- [Troubleshooting](../troubleshooting.md) - Resolving common errors
