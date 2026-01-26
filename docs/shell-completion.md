# Shell Completion

Weld provides tab completion for commands, options, and arguments. Completions are context-aware—they suggest relevant files, flag values, and subcommands based on what you've typed.

## Automatic Installation

**Completions are installed automatically** on first run of any `weld` command. You'll see a one-time message:

```
Shell completions installed. Restart your shell or run: source ~/.bashrc
```

After restarting your shell (or sourcing the config file), completions will work immediately. No additional setup required for bash, zsh, or fish.

## Manual Installation

If automatic installation didn't work, you prefer manual control, or you're using PowerShell, use one of the methods below.

### Quick Install

The simplest manual method:

```bash
weld --install-completion
```

This auto-detects your shell and installs the completion script to the appropriate location. Restart your shell or source your config file to activate.

### Bash

**Option 1: User-level installation**

```bash
# Generate completion script
weld --show-completion > ~/.weld-complete.bash

# Add to ~/.bashrc
echo 'source ~/.weld-complete.bash' >> ~/.bashrc

# Reload
source ~/.bashrc
```

**Option 2: System-wide installation (Linux)**

```bash
# Requires sudo
weld --show-completion | sudo tee /etc/bash_completion.d/weld > /dev/null

# Reload bash
source /etc/bash_completion.d/weld
```

**macOS with Homebrew**

```bash
# Ensure bash-completion is installed
brew install bash-completion@2

# Install weld completion
weld --show-completion > $(brew --prefix)/etc/bash_completion.d/weld

# Reload
source ~/.bashrc
```

### Zsh

**Option 1: User-level installation**

```bash
# Generate completion script
weld --show-completion > ~/.weld-complete.zsh

# Add to ~/.zshrc
echo 'source ~/.weld-complete.zsh' >> ~/.zshrc

# Reload
source ~/.zshrc
```

**Option 2: Using fpath (recommended for zsh)**

```bash
# Create completions directory if needed
mkdir -p ~/.zfunc

# Generate completion
weld --show-completion > ~/.zfunc/_weld

# Add to ~/.zshrc (before compinit)
echo 'fpath=(~/.zfunc $fpath)' >> ~/.zshrc
echo 'autoload -Uz compinit && compinit' >> ~/.zshrc

# Reload
source ~/.zshrc
```

**Oh My Zsh**

```bash
# Install to Oh My Zsh completions
weld --show-completion > ~/.oh-my-zsh/completions/_weld

# Reload
source ~/.zshrc
```

### Fish

```bash
# Create completions directory if needed
mkdir -p ~/.config/fish/completions

# Generate completion
weld --show-completion > ~/.config/fish/completions/weld.fish

# Fish auto-loads from completions directory - no reload needed
# Or manually reload:
source ~/.config/fish/completions/weld.fish
```

### PowerShell

**Windows PowerShell**

```powershell
# Show your profile path
echo $PROFILE

# Generate and append completion to profile
weld --show-completion >> $PROFILE

# Reload profile
. $PROFILE
```

**PowerShell Core (Cross-platform)**

```powershell
# Create profile directory if needed
New-Item -Path (Split-Path $PROFILE) -ItemType Directory -Force

# Generate completion
weld --show-completion | Out-File -Append -FilePath $PROFILE

# Reload
. $PROFILE
```

## What Gets Completed

Weld completions include:

| Context | Completions |
|---------|-------------|
| Commands | `weld <TAB>` → init, plan, implement, commit, etc. |
| Subcommands | `weld prompt <TAB>` → list, show, export |
| Flags | `weld plan --<TAB>` → --output, --focus, --provider, etc. |
| Flag values | `weld plan --provider <TAB>` → claude, codex |
| File arguments | `weld plan <TAB>` → *.md files |
| Task types | `weld prompt show <TAB>` → discover, research, plan_generation, etc. |

## Troubleshooting

### Completions not working after installation

1. **Restart your terminal** - Most shells don't reload config automatically
2. **Check the source line** - Ensure your shell config actually sources the completion file
3. **Verify the file exists** - `ls -la ~/.weld-complete.*` or check the path used

### "command not found" in completion script

The completion script calls `weld` to generate completions. Ensure weld is in your PATH:

```bash
which weld
# Should output: /path/to/weld
```

If weld was installed with `uv tool` or `pipx`, ensure the tool bin directory is in PATH:

```bash
# uv
export PATH="$HOME/.local/bin:$PATH"

# pipx
export PATH="$HOME/.local/bin:$PATH"
```

### Completions are slow

Completions run `weld` each time to generate context-aware suggestions. If this is slow:

1. Check if weld startup is slow: `time weld --help`
2. Ensure you're not running weld from a network drive
3. On Windows, antivirus can slow Python startup

### Zsh: "command not found: compdef"

The completion system isn't initialized. Add to `~/.zshrc` before sourcing completions:

```bash
autoload -Uz compinit && compinit
```

### Zsh: Insecure directories warning

Zsh may warn about insecure completion directories. Fix permissions:

```bash
chmod 755 ~/.zfunc
chmod 644 ~/.zfunc/_weld
compaudit | xargs chmod g-w
```

Or disable the check (not recommended):

```bash
# Add to ~/.zshrc before compinit
ZSH_DISABLE_COMPFIX=true
```

### Fish: Completions not loading

Fish should auto-load from `~/.config/fish/completions/`. If not:

1. Check file exists: `ls ~/.config/fish/completions/weld.fish`
2. Check for syntax errors: `fish -c "source ~/.config/fish/completions/weld.fish"`
3. Clear completion cache: `rm -rf ~/.cache/fish/completions`

### PowerShell: Script execution disabled

Enable script execution:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### Reinstalling after weld upgrade

After upgrading weld, regenerate completions to pick up new commands:

```bash
weld --install-completion
# Or regenerate manually using the steps above
```

## Uninstalling Completions

Remove the completion script and source line from your shell config:

**Bash/Zsh:**
```bash
rm ~/.weld-complete.*
# Edit ~/.bashrc or ~/.zshrc to remove the source line
```

**Fish:**
```bash
rm ~/.config/fish/completions/weld.fish
```

**PowerShell:**
```powershell
# Edit $PROFILE to remove weld completion lines
notepad $PROFILE
```
