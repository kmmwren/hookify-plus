# Hookify Plus

[![Version](https://img.shields.io/badge/version-git%20sha-blue)](CHANGELOG.md)
[![Based on](https://img.shields.io/badge/based%20on-hookify%200.1.0-gray)](https://github.com/anthropics/claude-code/tree/main/plugins/hookify)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**Community-maintained fork of the hookify plugin for Claude Code.**

The upstream hookify plugin has bugs and missing features that Anthropic hasn't addressed. This fork integrates community fixes so you don't have to wait.

## What You Get

### 5 Features Added

| Feature | What it does |
|---------|--------------|
| `not_regex_match` | Exclude patterns (e.g., skip test files from rules) |
| `value` key | Clearer syntax for non-regex operators |
| `read` event | Separate event for Read/Glob/Grep/LS (no false triggers) |
| Global rules | Rules in `~/.claude/` apply to ALL projects |
| `Update` tool | File events now fire for the Update tool |

### 6 Bugs Fixed

| Bug | Issue |
|-----|-------|
| Read tools incorrectly fired `file` rules | [#14588](https://github.com/anthropics/claude-code/issues/14588) |
| Write tool `new_text` field was broken | [#16081](https://github.com/anthropics/claude-code/pull/16081) |
| Python 3.8 type hints incompatible | [#14588](https://github.com/anthropics/claude-code/issues/14588) |
| Claude couldn't see why rules blocked | [#12446](https://github.com/anthropics/claude-code/issues/12446) |
| Windows paths with spaces failed | [#16152](https://github.com/anthropics/claude-code/issues/16152) |
| Example file used wrong operator | [#13464](https://github.com/anthropics/claude-code/issues/13464) |

**11 total improvements.** No waiting for Anthropic to merge PRs.

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/adrozdenko/hookify-plus ~/hookify-plus

# 2. Backup & link
mv ~/.claude/plugins/cache/claude-code-plugins/hookify/0.1.0{,.bak}
ln -s ~/hookify-plus ~/.claude/plugins/cache/claude-code-plugins/hookify/0.1.0

# 3. Create your first rule
mkdir -p .claude
cat > .claude/hookify.warn-rm.local.md << 'EOF'
---
name: warn-dangerous-rm
enabled: true
event: bash
pattern: rm\s+-rf
---
⚠️ **Dangerous rm command!** Double-check the path before proceeding.
EOF

# Done! Rules are active immediately.
```

---

## Rule Syntax

Rules are markdown files with YAML frontmatter:

```markdown
---
name: rule-identifier
enabled: true
event: bash|file|read|stop|prompt|all
action: warn|block
pattern: regex-pattern
---

Message shown to Claude when rule triggers.
Supports **markdown** formatting.
```

### Multiple Conditions

```yaml
---
name: warn-env-changes
enabled: true
event: file
action: warn
conditions:
  - field: file_path
    operator: regex_match
    pattern: \.env$
  - field: file_path
    operator: not_regex_match
    pattern: \.example$
---

You're editing a .env file. Make sure it's in .gitignore!
```

### Event Types

| Event | Triggers On |
|-------|-------------|
| `bash` | Bash tool |
| `file` | Edit, Write, MultiEdit, Update |
| `read` | Read, Glob, Grep, LS |
| `stop` | Agent completion |
| `prompt` | User prompt submit |
| `all` | All of the above |

### Operators

| Operator | Description |
|----------|-------------|
| `regex_match` | Pattern matches (regex) |
| `not_regex_match` | Pattern does NOT match |
| `contains` | Substring present |
| `not_contains` | Substring NOT present |
| `equals` | Exact match |
| `starts_with` | Prefix match |
| `ends_with` | Suffix match |

### Fields by Event

| Event | Available Fields |
|-------|------------------|
| `bash` | `command` |
| `file` | `file_path`, `new_text`, `old_text`, `content` |
| `read` | `file_path` |
| `stop` | `reason`, `transcript` |
| `prompt` | `user_prompt` |

### Rule Locations

| Location | Scope |
|----------|-------|
| `.claude/hookify.*.local.md` | Current project only |
| `~/.claude/hookify.*.local.md` | All projects (global) |

---

## Installation

### Install

```bash
git clone https://github.com/adrozdenko/hookify-plus ~/hookify-plus

mv ~/.claude/plugins/cache/claude-code-plugins/hookify/0.1.0 \
   ~/.claude/plugins/cache/claude-code-plugins/hookify/0.1.0.bak

ln -s ~/hookify-plus \
   ~/.claude/plugins/cache/claude-code-plugins/hookify/0.1.0
```

### Update

```bash
cd ~/hookify-plus && git pull
```

Changes take effect immediately—no restart needed.

### Revert to Upstream

```bash
rm ~/.claude/plugins/cache/claude-code-plugins/hookify/0.1.0
mv ~/.claude/plugins/cache/claude-code-plugins/hookify/0.1.0.bak \
   ~/.claude/plugins/cache/claude-code-plugins/hookify/0.1.0
```

---

## Versioning

The plugin manifest carries no version, so the installed version is the git sha of the marketplace checkout.

See [CHANGELOG.md](CHANGELOG.md) for history.

---

## Credits

| Contributor | Contribution |
|-------------|--------------|
| [@adrozdenko](https://github.com/adrozdenko) | Fork maintainer, `not_regex_match`, `value` key, `read` event |
| [@kp222x](https://github.com/kp222x) | Global rules ([#13916](https://github.com/anthropics/claude-code/pull/13916)) |
| [@heathdutton](https://github.com/heathdutton) | Write fix + Update tool ([#16081](https://github.com/anthropics/claude-code/pull/16081)) |

## Contributing

1. Fork this repo
2. Make changes
3. Add entry to CHANGELOG.md
4. Submit PR

All community contributions welcome!

## License

MIT
