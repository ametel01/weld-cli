# Troubleshooting

Common issues and solutions when using weld.

## Diagnostics Checklist

When reporting issues, include:

```bash
weld --version
python --version
uname -a                    # OS info
cat .weld/config.toml       # Config (redact sensitive data)
weld doctor                 # Dependency status
```

If using `--debug`, include `.weld/debug.log`.

## Common Issues

### "Weld not initialized"

**Symptom**: Command fails with "weld not initialized" error.

**Solution**: Initialize weld in your project:

```bash
weld init
```

### Missing Dependencies

**Symptom**: `weld doctor` shows missing tools.

**Solution**: Install the required tools:

```bash
# Install GitHub CLI
brew install gh       # macOS
apt install gh        # Ubuntu/Debian

# Authenticate GitHub CLI
gh auth login

# Install Claude CLI
# See: https://claude.ai/code
```

### Not a Git Repository

**Symptom**: "Not a git repository" error.

**Solution**: Initialize git first:

```bash
git init
weld init
```

### Output Token Limit Exceeded

**Symptom**: Error like "Claude's response exceeded the output token maximum."

**Solution**: Increase the token limit in `.weld/config.toml`:

```toml
[claude]
max_output_tokens = 200000  # Increase from default 128000
```

### AI Provider Timeout

**Symptom**: Command times out waiting for Claude.

**Solution**: Increase the timeout in `.weld/config.toml`:

```toml
[claude]
timeout = 3600  # Increase to 1 hour
```

### Permission Errors

**Symptom**: Cannot write to `.weld/` directory.

**Solution**: Check directory permissions:

```bash
ls -la .weld/
chmod -R u+w .weld/
```

### Transcript Generation Failed

**Symptom**: Commit fails with exit code 21.

**Solution**:
1. Check that `gh` CLI is installed and authenticated
2. Or skip transcript generation:

```bash
weld commit --skip-transcript
```

3. Or disable transcripts in `.weld/config.toml`:

```toml
[transcripts]
enabled = false
```

### JSON Output Parsing Errors

**Symptom**: Exit code 23 when parsing Claude response.

**Solution**: This usually indicates Claude returned unexpected output. Try:
1. Run with `--debug` to see the raw response
2. Retry the command
3. Check if your specification is too complex

## Debug Mode

Enable detailed logging:

```bash
weld --debug <command>
```

Logs are written to `.weld/debug.log`.

## Getting Help

- GitHub Issues: https://github.com/ametel01/weld-cli/issues
- Include diagnostics checklist output when reporting

## See Also

- [Exit Codes](reference/exit-codes.md) - Exit code reference
- [Configuration](configuration.md) - Configuration options
- [doctor](commands/doctor.md) - Check dependencies
