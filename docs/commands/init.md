# weld init

Initialize weld in the current git repository.

## Usage

```bash
weld init
```

## Description

Creates the `.weld/` directory with default configuration and updates version control:

- `.weld/config.toml` - Configuration file
- Updates `.gitignore` to exclude `.weld/` metadata (keeps only `config.toml` tracked)

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 2 | Missing or unauthenticated tool |
| 3 | Not a git repository |

## Examples

### Initialize in current project

```bash
cd /path/to/your-project
weld init
```

### Verify after initialization

```bash
weld init && weld doctor
```

## See Also

- [doctor](doctor.md) - Verify your toolchain after initialization
- [Configuration](../configuration.md) - Customize the generated config
