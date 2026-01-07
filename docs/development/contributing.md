# Contributing

Thank you for your interest in contributing to weld!

## Development Setup

```bash
git clone https://github.com/ametel01/weld-cli.git && cd weld-cli
make setup
eval $(make venv-eval)
```

## Making Changes

1. Create a branch for your changes
2. Make your changes
3. Run quality checks: `make check`
4. Run tests: `make test`
5. Submit a pull request

## Code Style

- **Line length**: 100 characters
- **Type hints**: Required on all functions
- **Docstrings**: For public APIs

### Linting and Formatting

```bash
# Auto-fix linting issues
make lint-fix

# Format code
make format

# Type checking
make typecheck
```

## Testing

### Running Tests

```bash
# All tests
make test

# Unit tests only
make test-unit

# CLI integration tests
make test-cli

# With coverage
make test-cov
```

### Test Markers

Use appropriate markers for tests:

```python
@pytest.mark.unit
def test_something():
    ...

@pytest.mark.cli
def test_cli_command():
    ...

@pytest.mark.slow
def test_slow_operation():
    ...
```

## Commit Guidelines

- Use imperative mood: "Add feature" not "Added feature"
- Keep commits small and focused
- Update CHANGELOG.md for user-facing changes

## Pull Request Process

1. Ensure `make ci` passes
2. Update documentation if needed
3. Add tests for new functionality
4. Request review

## See Also

- [Developer Guide](index.md) - Development overview
- [Architecture](architecture.md) - Understanding the codebase
