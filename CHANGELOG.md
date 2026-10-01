# Changelog

All notable changes to hookify-plus are documented here.

Based on upstream [hookify 0.1.0](https://github.com/anthropics/claude-code/tree/main/plugins/hookify).

## Unreleased

### Fixed
- **Stop rules were dead**: `last_assistant_message`, `content`, `response` and `response_text` now resolve to the Stop input's `last_assistant_message` (transcript tail fallback only when the key is absent). A Stop already continuing after a block is not blocked again.
- **`event: response`** is an alias of `stop`.
- **PostToolUse hook removed**: it saw the same tool input as PreToolUse and injected every warning twice.
- **Version field removed from plugin.json** so installs are versioned by git sha and `claude plugin update` picks up merged fixes.
- `transcript` field reads only the last 2 MB.

## [0.1.0-plus.3] - 2025-01-16

### Fixed
- **Import paths for symlink compatibility** - Changed `from hookify.core` to `from core` so plugin works when symlinked with different directory name

## [0.1.0-plus.2] - 2025-01-16

### Fixed
- **Python 3.8 compatibility** - Added `from __future__ import annotations` (issue #14588)
- **Claude sees block reasons** - Added `permissionDecisionReason` to hook output (issue #12446)
- **Windows paths with spaces** - Quoted `${CLAUDE_PLUGIN_ROOT}` in hooks.json (issue #16152)
- **Example file operator** - Changed `not_contains` to `not_regex_match` in require-tests example (issue #13464)

## [0.1.0-plus.1] - 2025-01-16

### Added
- **`not_regex_match` operator** - Exclude patterns (e.g., skip test files)
- **`value` key in conditions** - Alias for `pattern`, clearer for non-regex operators
- **`read` event type** - Separate event for Read/Glob/Grep/LS tools
- **Global rules** - Rules in `~/.claude/` apply to all projects (PR #13916)
- **Update tool support** - File event fires for Update tool (PR #16081)

### Fixed
- **Read tools event mapping** - Read/Glob/Grep now fire `read` event, not `file`
- **Write tool `new_text` field** - Correctly extracts content from Write tool

## [0.1.0] - Upstream

Original hookify plugin from Anthropic.

---

## Version Scheme

`0.1.0-plus.N` where:
- `0.1.0` = upstream hookify version this is based on
- `plus.N` = hookify-plus patch number

When upstream releases 0.2.0, we'll rebase and become `0.2.0-plus.1`.
