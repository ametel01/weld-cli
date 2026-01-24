"""File path validation for Telegram bot /fetch and /push commands."""

from pathlib import Path

import pathspec

from weld.telegram.config import TelegramConfig
from weld.telegram.errors import TelegramError

# Upload directory relative to project root
UPLOADS_DIR = Path(".weld/telegram/uploads")

# Text file extensions that can be viewed via /fetch (lowercase, with leading dot)
# These are safe to display as text in Telegram messages
TEXT_EXTENSIONS: frozenset[str] = frozenset(
    {
        # Source code
        ".py",
        ".pyi",
        ".pyw",  # Python
        ".js",
        ".mjs",
        ".cjs",
        ".jsx",  # JavaScript
        ".ts",
        ".mts",
        ".cts",
        ".tsx",  # TypeScript
        ".rs",  # Rust
        ".go",  # Go
        ".rb",
        ".rake",  # Ruby
        ".java",
        ".kt",
        ".kts",  # Java/Kotlin
        ".c",
        ".h",
        ".cpp",
        ".hpp",
        ".cc",
        ".hh",
        ".cxx",
        ".hxx",  # C/C++
        ".cs",  # C#
        ".swift",  # Swift
        ".scala",
        ".sc",  # Scala
        ".php",  # PHP
        ".pl",
        ".pm",  # Perl
        ".lua",  # Lua
        ".r",  # R
        ".jl",  # Julia
        ".ex",
        ".exs",  # Elixir
        ".erl",
        ".hrl",  # Erlang
        ".clj",
        ".cljs",
        ".cljc",
        ".edn",  # Clojure
        ".hs",
        ".lhs",  # Haskell
        ".ml",
        ".mli",  # OCaml
        ".fs",
        ".fsx",
        ".fsi",  # F#
        ".v",
        ".vh",
        ".sv",
        ".svh",  # Verilog/SystemVerilog
        ".vhd",
        ".vhdl",  # VHDL
        ".asm",
        ".s",  # Assembly
        ".sql",  # SQL
        ".graphql",
        ".gql",  # GraphQL
        # Shell/scripts
        ".sh",
        ".bash",
        ".zsh",
        ".fish",
        ".ksh",
        ".csh",
        ".tcsh",
        ".ps1",
        ".psm1",
        ".psd1",  # PowerShell
        ".bat",
        ".cmd",  # Windows batch
        # Config/data
        ".json",
        ".jsonl",
        ".json5",
        ".jsonc",
        ".yaml",
        ".yml",
        ".toml",
        ".xml",
        ".xsl",
        ".xslt",
        ".xsd",
        ".dtd",
        ".ini",
        ".cfg",
        ".conf",
        ".config",
        ".env",
        ".env.example",
        ".env.local",
        ".env.development",
        ".env.production",
        ".properties",
        ".plist",
        ".csv",
        ".tsv",
        # Markup/docs
        ".md",
        ".markdown",
        ".mdown",
        ".mkd",
        ".mkdn",
        ".rst",
        ".rest",
        ".txt",
        ".text",
        ".adoc",
        ".asciidoc",
        ".org",
        ".tex",
        ".latex",
        ".sty",
        ".cls",
        ".bib",
        ".html",
        ".htm",
        ".xhtml",
        ".css",
        ".scss",
        ".sass",
        ".less",
        ".styl",
        ".svg",
        # Build/project
        ".gradle",
        ".gradle.kts",
        ".cmake",
        ".make",
        ".mk",
        ".dockerfile",
        ".containerfile",
        ".vagrantfile",
        # Git
        ".gitignore",
        ".gitattributes",
        ".gitmodules",
        # Editor/IDE
        ".editorconfig",
        ".prettierrc",
        ".prettierignore",
        ".eslintrc",
        ".eslintignore",
        ".stylelintrc",
        # Misc
        ".log",
        ".diff",
        ".patch",
        ".lock",  # package lock files
        ".sum",  # go.sum
    }
)

# Exact filenames (case-sensitive) that can be viewed as text
# These are common files without extensions
TEXT_FILENAMES: frozenset[str] = frozenset(
    {
        # Build
        "Makefile",
        "GNUmakefile",
        "makefile",
        "Dockerfile",
        "Containerfile",
        "Vagrantfile",
        "Rakefile",
        "Gemfile",
        "Brewfile",
        "Justfile",
        "justfile",
        "CMakeLists.txt",
        "BUILD",
        "BUILD.bazel",
        "WORKSPACE",
        # Python
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "requirements.txt",
        "Pipfile",
        "Pipfile.lock",
        "poetry.lock",
        "uv.lock",
        "MANIFEST.in",
        "tox.ini",
        # Node.js
        "package.json",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "tsconfig.json",
        "jsconfig.json",
        ".npmrc",
        ".nvmrc",
        ".node-version",
        # Rust
        "Cargo.toml",
        "Cargo.lock",
        # Go
        "go.mod",
        "go.sum",
        "go.work",
        # Ruby
        "Gemfile.lock",
        # Documentation
        "README",
        "README.md",
        "README.txt",
        "README.rst",
        "CHANGELOG",
        "CHANGELOG.md",
        "CHANGELOG.txt",
        "HISTORY",
        "HISTORY.md",
        "HISTORY.txt",
        "NEWS",
        "NEWS.md",
        "NEWS.txt",
        "AUTHORS",
        "AUTHORS.md",
        "AUTHORS.txt",
        "CONTRIBUTORS",
        "CONTRIBUTORS.md",
        "CONTRIBUTORS.txt",
        "MAINTAINERS",
        "MAINTAINERS.md",
        "LICENSE",
        "LICENSE.md",
        "LICENSE.txt",
        "COPYING",
        "COPYING.md",
        "COPYING.txt",
        "NOTICE",
        "NOTICE.md",
        "NOTICE.txt",
        "CODE_OF_CONDUCT.md",
        "CONTRIBUTING.md",
        "CONTRIBUTING.txt",
        "SECURITY.md",
        # Git
        ".gitignore",
        ".gitattributes",
        ".gitmodules",
        ".gitkeep",
        ".mailmap",
        # CI/CD
        ".travis.yml",
        "appveyor.yml",
        "Procfile",
        # IDE/Editor
        ".editorconfig",
        ".clang-format",
        ".clang-tidy",
        # Weld
        "CLAUDE.md",
        "AGENTS.md",
    }
)


# Extension to Telegram code block language mapping
# Telegram supports a subset of languages for syntax highlighting
EXTENSION_TO_LANGUAGE: dict[str, str] = {
    # Python
    ".py": "python",
    ".pyi": "python",
    ".pyw": "python",
    # JavaScript/TypeScript
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "typescript",
    # Web
    ".html": "html",
    ".htm": "html",
    ".xhtml": "html",
    ".css": "css",
    ".scss": "css",
    ".sass": "css",
    ".less": "css",
    # Data/Config
    ".json": "json",
    ".jsonl": "json",
    ".json5": "json",
    ".jsonc": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".xml": "xml",
    ".xsl": "xml",
    ".xslt": "xml",
    ".sql": "sql",
    # Shell
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".fish": "bash",
    # Systems languages
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".hh": "cpp",
    ".cxx": "cpp",
    ".hxx": "cpp",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".cs": "csharp",
    ".swift": "swift",
    ".scala": "scala",
    ".sc": "scala",
    # Other
    ".rb": "ruby",
    ".rake": "ruby",
    ".php": "php",
    ".pl": "perl",
    ".pm": "perl",
    ".lua": "lua",
    ".r": "r",
    ".md": "markdown",
    ".markdown": "markdown",
    ".diff": "diff",
    ".patch": "diff",
    ".graphql": "graphql",
    ".gql": "graphql",
}


def is_text_file(path: Path) -> bool:
    """Check if a file can be viewed as text based on extension or filename.

    Uses TEXT_EXTENSIONS and TEXT_FILENAMES allowlists to determine if a file
    should be treated as text content suitable for display in Telegram messages.

    Args:
        path: Path to the file to check

    Returns:
        True if file appears to be a text file based on extension/name
    """
    # Check exact filename match first (for files like Makefile, Dockerfile)
    if path.name in TEXT_FILENAMES:
        return True

    # Check extension (case-insensitive)
    suffix = path.suffix.lower()
    return suffix in TEXT_EXTENSIONS


def get_syntax_language(path: Path) -> str:
    """Get the Telegram code block language for syntax highlighting.

    Maps file extension to the appropriate language identifier for Telegram's
    markdown code blocks. Returns empty string for unknown extensions, which
    produces a plain code block without highlighting.

    Args:
        path: Path to the file

    Returns:
        Language identifier (e.g., "python", "javascript") or empty string
    """
    suffix = path.suffix.lower()
    return EXTENSION_TO_LANGUAGE.get(suffix, "")


def get_uploads_dir(project_root: Path) -> Path:
    """Get or create the uploads directory for a project.

    Args:
        project_root: Path to the project root directory

    Returns:
        Path to .weld/telegram/uploads/ directory (created if it doesn't exist)
    """
    uploads_path = project_root / UPLOADS_DIR
    uploads_path.mkdir(parents=True, exist_ok=True)
    return uploads_path


class FilePathError(TelegramError):
    """Base exception for file path validation errors."""


class PathTraversalError(FilePathError):
    """Raised when path traversal is detected."""


class PathNotAllowedError(FilePathError):
    """Raised when path is not within an allowed project directory."""


class PathNotFoundError(FilePathError):
    """Raised when path does not exist (for fetch operations)."""


def _resolve_and_validate_base(
    path: str | Path,
    config: TelegramConfig,
    *,
    must_exist: bool,
) -> tuple[Path, Path]:
    """Resolve path and validate it's within an allowed project directory.

    Args:
        path: The path to validate (relative or absolute)
        config: Telegram configuration with registered projects
        must_exist: If True, raises PathNotFoundError if path doesn't exist

    Returns:
        Tuple of (resolved_path, project_root) where resolved_path is the
        fully resolved absolute path and project_root is the project directory
        it belongs to.

    Raises:
        PathNotAllowedError: If path is not within any registered project
        PathNotFoundError: If must_exist=True and path doesn't exist
        PathTraversalError: If path attempts traversal outside project root
    """
    if not config.projects:
        raise PathNotAllowedError("No projects registered in configuration")

    path = Path(path)

    # For must_exist=True (fetch), we need to resolve symlinks to check real location
    # For must_exist=False (push), we resolve what exists and keep the rest
    if must_exist:
        if not path.exists():
            raise PathNotFoundError(f"Path does not exist: {path}")
        # Resolve symlinks to get the real path for security check
        resolved = path.resolve(strict=True)
    else:
        # For push: resolve parent if it exists, then append filename
        # This handles the case where the file doesn't exist yet
        try:
            # Try strict resolution first
            resolved = path.resolve(strict=True)
        except (FileNotFoundError, OSError):
            # File doesn't exist - resolve parent and append filename
            parent = path.parent
            if parent.exists():
                resolved = parent.resolve(strict=True) / path.name
            else:
                # Neither file nor parent exists - use non-strict resolution
                # but verify no symlink shenanigans in existing parts
                resolved = path.resolve(strict=False)

    # Check if resolved path is within any registered project
    for project in config.projects:
        project_root = project.path.resolve()
        try:
            resolved.relative_to(project_root)
            return resolved, project_root
        except ValueError:
            # Not within this project, try next
            continue

    # Path is not within any project
    project_paths = ", ".join(str(p.path) for p in config.projects)
    raise PathNotAllowedError(
        f"Path '{resolved}' is not within any registered project. "
        f"Registered projects: {project_paths}"
    )


def validate_fetch_path(path: str | Path, config: TelegramConfig) -> Path:
    """Validate a path for /fetch operations.

    Ensures the path:
    - Exists on the filesystem
    - Resolves (following symlinks) to a location within a registered project
    - Does not escape the project root via symlinks or traversal

    Args:
        path: The path to fetch (relative or absolute)
        config: Telegram configuration with registered projects

    Returns:
        The resolved absolute path that is safe to read

    Raises:
        PathNotFoundError: If path doesn't exist
        PathNotAllowedError: If path is not within any registered project
        PathTraversalError: If path attempts traversal outside project root
    """
    resolved, _ = _resolve_and_validate_base(path, config, must_exist=True)
    return resolved


def validate_push_path(path: str | Path, config: TelegramConfig) -> Path:
    """Validate a path for /push operations.

    Ensures the path:
    - Would resolve to a location within a registered project
    - Does not escape the project root via symlinks or traversal
    - The file doesn't need to exist yet (for new files)

    Args:
        path: The path to push to (relative or absolute)
        config: Telegram configuration with registered projects

    Returns:
        The resolved absolute path that is safe to write

    Raises:
        PathNotAllowedError: If path is not within any registered project
        PathTraversalError: If path attempts traversal outside project root
    """
    resolved, _ = _resolve_and_validate_base(path, config, must_exist=False)
    return resolved


# Characters allowed in sanitized filenames
_ALLOWED_FILENAME_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_"
)


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename to remove potentially dangerous characters.

    Replaces disallowed characters with underscores and handles edge cases
    like empty names, reserved names, and path traversal attempts.

    Args:
        filename: Original filename from user/Telegram

    Returns:
        Sanitized filename safe for filesystem operations
    """
    if not filename:
        return "unnamed_file"

    # Remove path separators and traversal attempts
    filename = filename.replace("/", "_").replace("\\", "_")
    filename = filename.replace("..", "_")

    # Replace disallowed characters
    sanitized = "".join(c if c in _ALLOWED_FILENAME_CHARS else "_" for c in filename)

    # Collapse multiple underscores
    while "__" in sanitized:
        sanitized = sanitized.replace("__", "_")

    # Strip leading/trailing underscores and dots
    sanitized = sanitized.strip("_.")

    # Handle empty result
    if not sanitized:
        return "unnamed_file"

    # Limit length (preserve extension if present)
    max_len = 200
    if len(sanitized) > max_len:
        # Try to preserve extension
        parts = sanitized.rsplit(".", 1)
        if len(parts) == 2 and len(parts[1]) <= 10:
            base = parts[0][: max_len - len(parts[1]) - 1]
            sanitized = f"{base}.{parts[1]}"
        else:
            sanitized = sanitized[:max_len]

    return sanitized


def resolve_upload_filename(uploads_dir: Path, filename: str) -> Path:
    """Resolve filename conflicts by appending numeric suffixes.

    If the filename already exists, tries name.1.ext, name.2.ext, etc.
    For files without extensions, uses name.1, name.2, etc.

    Args:
        uploads_dir: Directory where file will be saved
        filename: Desired filename (should already be sanitized)

    Returns:
        Path to a non-existing file in uploads_dir

    Example:
        >>> resolve_upload_filename(Path("/uploads"), "spec.md")
        Path("/uploads/spec.md")  # if doesn't exist
        >>> resolve_upload_filename(Path("/uploads"), "spec.md")
        Path("/uploads/spec.1.md")  # if spec.md exists
    """
    target = uploads_dir / filename

    if not target.exists():
        return target

    # Split into base name and extension
    # Handle multiple extensions like .tar.gz by only splitting on last dot
    parts = filename.rsplit(".", 1)
    if len(parts) == 2:
        base, ext = parts
        ext = "." + ext
    else:
        base = filename
        ext = ""

    # Find next available number
    counter = 1
    while counter < 10000:  # Safety limit
        candidate = uploads_dir / f"{base}.{counter}{ext}"
        if not candidate.exists():
            return candidate
        counter += 1

    # Fallback: use timestamp suffix if too many conflicts
    import time

    timestamp = int(time.time())
    return uploads_dir / f"{base}.{timestamp}{ext}"


def load_gitignore(project_root: Path) -> pathspec.PathSpec:
    """Load and parse .gitignore patterns from a project root.

    Reads the .gitignore file from the project root and parses it into a
    PathSpec object for pattern matching. If the .gitignore file doesn't
    exist or is empty, returns an empty PathSpec that matches nothing.

    Args:
        project_root: Path to the project root directory

    Returns:
        PathSpec object for matching paths against gitignore patterns.
        Use spec.match_file(path) to check if a path should be ignored.

    Example:
        >>> spec = load_gitignore(Path("/my/project"))
        >>> spec.match_file("node_modules/foo.js")
        True  # if node_modules/ is in .gitignore
        >>> spec.match_file("src/main.py")
        False  # not ignored
    """
    gitignore_path = project_root / ".gitignore"

    if not gitignore_path.exists():
        # Return empty PathSpec that matches nothing
        return pathspec.PathSpec.from_lines("gitwildmatch", [])

    try:
        content = gitignore_path.read_text(encoding="utf-8")
        # Filter out empty lines and comments, pathspec handles this but being explicit
        lines = content.splitlines()
        return pathspec.PathSpec.from_lines("gitwildmatch", lines)
    except (OSError, UnicodeDecodeError):
        # On read errors, return empty PathSpec
        return pathspec.PathSpec.from_lines("gitwildmatch", [])
