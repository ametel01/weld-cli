# weld commit

Auto-generate commit message(s) from diff, update CHANGELOG, and commit with transcript.

## Usage

```bash
weld commit [OPTIONS]
```

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--all` | `-a` | Stage all changes before committing |
| `--no-split` | | Force single commit (disable automatic splitting) |
| `--no-session-split` | | Disable session-based grouping of files |
| `--edit` | `-e` | Edit generated message in $EDITOR before commit |
| `--skip-transcript` | | Skip transcript generation |
| `--skip-changelog` | | Skip CHANGELOG.md update |
| `--quiet` | `-q` | Suppress Claude streaming output |

## Description

Automatically analyzes the diff and creates multiple logical commits when appropriate (e.g., separating typo fixes from version updates from documentation changes).

The final commit message includes a transcript trailer:

```
Implement user auth

Claude-Transcript: https://gist.github.com/...
```

## Examples

### Stage all and commit

```bash
weld commit --all
```

### Commit staged changes only

```bash
weld commit
```

### Force single commit

```bash
weld commit --no-split
```

### Edit message before commit

```bash
weld commit --edit
```

### Skip transcript generation

```bash
weld commit --skip-transcript
```

### Skip CHANGELOG update

```bash
weld commit --skip-changelog
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Committed |
| 1 | Weld not initialized |
| 20 | No changes to commit |
| 21 | Claude failed to generate message |
| 22 | Git commit failed |
| 23 | Failed to parse Claude response |
| 24 | Editor error |

## See Also

- [review](review.md) - Review changes before committing
- [Exit Codes](../reference/exit-codes.md) - Full exit code reference
- [Configuration](../configuration.md) - Configure transcript settings
