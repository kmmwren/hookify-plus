#!/usr/bin/env python3
"""Rule evaluation engine for hookify plugin."""

import json
import os
import re
import sys
from functools import lru_cache
from typing import List, Dict, Any, Optional

# Import from local module
from core.config_loader import Rule, Condition


# Cache compiled regexes (max 128 patterns)
@lru_cache(maxsize=128)
def compile_regex(pattern: str) -> re.Pattern:
    """Compile regex pattern with caching.

    Args:
        pattern: Regex pattern string

    Returns:
        Compiled regex pattern
    """
    return re.compile(pattern, re.IGNORECASE)


# Fields that name "what the assistant just said" when a Stop hook fires.
STOP_MESSAGE_FIELDS = frozenset({
    'last_assistant_message', 'content', 'response', 'response_text',
})
STOP_EVENTS = frozenset({'Stop', 'SubagentStop'})

# Transcripts grow without bound; rules only ever need the recent tail.
_TRANSCRIPT_TAIL_BYTES = 2 * 1024 * 1024


def _read_tail(path: str, max_bytes: Optional[int] = None) -> str:
    """Return the last max_bytes of a text file, dropping a split first line."""
    max_bytes = max_bytes or _TRANSCRIPT_TAIL_BYTES
    with open(path, 'rb') as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        start = max(0, size - max_bytes)
        f.seek(start)
        data = f.read()
    text = data.decode('utf-8', errors='replace')
    if start > 0:
        text = text.split('\n', 1)[-1]
    return text


def last_assistant_text(transcript_path: str) -> Optional[str]:
    """Last assistant text block in a transcript JSONL, read from the end."""
    for line in reversed(_read_tail(transcript_path).splitlines()):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        message = entry.get('message') if isinstance(entry, dict) else None
        if not isinstance(message, dict) or message.get('role') != 'assistant':
            continue
        content = message.get('content')
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts = [b.get('text', '') for b in content
                     if isinstance(b, dict) and b.get('type') == 'text']
            if texts:
                return '\n'.join(texts)
    return None


class RuleEngine:
    """Evaluates rules against hook input data."""

    def __init__(self):
        """Initialize rule engine."""
        # No need for instance cache anymore - using global lru_cache
        pass

    def evaluate_rules(self, rules: List[Rule], input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate all rules and return combined results.

        Checks all rules and accumulates matches. Blocking rules take priority
        over warning rules. All matching rule messages are combined.

        Args:
            rules: List of Rule objects to evaluate
            input_data: Hook input JSON (tool_name, tool_input, etc.)

        Returns:
            Response dict with hookSpecificOutput, decision, etc.
            Empty dict {} if no rules match.
        """
        hook_event = input_data.get('hook_event_name', '')
        # A Stop that is already continuing because of a block must not be blocked
        # again, or a rule the model cannot satisfy loops forever.
        if hook_event in STOP_EVENTS and input_data.get('stop_hook_active'):
            return {}
        blocking_rules = []
        warning_rules = []

        for rule in rules:
            if self._rule_matches(rule, input_data):
                if rule.action == 'block':
                    blocking_rules.append(rule)
                else:
                    warning_rules.append(rule)

        # If any blocking rules matched, block the operation. Matched warnings are
        # appended too: they are the guidance for doing the blocked thing correctly
        # (e.g. PR title conventions alongside a PR readiness gate), so dropping
        # them would hide exactly the advice Claude needs to satisfy the block.
        if blocking_rules:
            messages = [f"**[{r.name}]**\n{r.message}" for r in blocking_rules + warning_rules]
            combined_message = "\n\n".join(messages)

            # Use appropriate blocking format based on event type
            if hook_event == 'Stop':
                return {
                    "decision": "block",
                    "reason": combined_message,
                    "systemMessage": combined_message
                }
            elif hook_event in ['PreToolUse']:
                # permissionDecisionReason already tells Claude why it was blocked;
                # a systemMessage too would print the whole rule text at the user.
                return {
                    "hookSpecificOutput": {
                        "hookEventName": hook_event,
                        "permissionDecision": "deny",
                        "permissionDecisionReason": combined_message
                    }
                }
            else:
                # UserPromptSubmit and friends have no JSON deny mechanism (that is
                # PreToolUse only), and exit-2 blocking there would erase the user's
                # prompt. Deliver the rule as context so Claude is still bound by it.
                return self._warning_response(hook_event, combined_message)

        # If only warnings, deliver them to Claude without spamming the transcript.
        if warning_rules:
            messages = [f"**[{r.name}]**\n{r.message}" for r in warning_rules]
            combined_message = "\n\n".join(messages)
            return self._warning_response(hook_event, combined_message)

        # No matches - allow operation
        return {}

    # Events whose additionalContext is injected into Claude's context without
    # being rendered in the user's transcript.
    _ADDITIONAL_CONTEXT_EVENTS = frozenset({
        'UserPromptSubmit', 'PreToolUse', 'SessionStart',
    })

    def _warning_response(self, hook_event: str, message: str) -> Dict[str, Any]:
        """Build a non-blocking response that reaches Claude but stays out of the transcript.

        A top-level systemMessage is echoed to the user on every match, which for
        UserPromptSubmit means hundreds of lines of rule text per prompt. Where the
        event supports it, the same text is delivered via additionalContext instead,
        which is injected into Claude's context silently. Events without that channel
        fall back to systemMessage so their rules keep working.
        """
        if hook_event in self._ADDITIONAL_CONTEXT_EVENTS:
            return {
                "hookSpecificOutput": {
                    "hookEventName": hook_event,
                    "additionalContext": message,
                }
            }
        return {"systemMessage": message}

    def _rule_matches(self, rule: Rule, input_data: Dict[str, Any]) -> bool:
        """Check if rule matches input data.

        Args:
            rule: Rule to evaluate
            input_data: Hook input data

        Returns:
            True if rule matches, False otherwise
        """
        # Extract tool information
        tool_name = input_data.get('tool_name', '')
        tool_input = input_data.get('tool_input', {})

        # Check tool matcher if specified
        if rule.tool_matcher:
            if not self._matches_tool(rule.tool_matcher, tool_name):
                return False

        # If no conditions, don't match
        # (Rules must have at least one condition to be valid)
        if not rule.conditions:
            return False

        # All conditions must match
        for condition in rule.conditions:
            if not self._check_condition(condition, tool_name, tool_input, input_data):
                return False

        return True

    def _matches_tool(self, matcher: str, tool_name: str) -> bool:
        """Check if tool_name matches the matcher pattern.

        Args:
            matcher: Pattern like "Bash", "Edit|Write", "*"
            tool_name: Actual tool name

        Returns:
            True if matches
        """
        if matcher == '*':
            return True

        # Split on | for OR matching
        patterns = matcher.split('|')
        return tool_name in patterns

    def _check_condition(self, condition: Condition, tool_name: str,
                        tool_input: Dict[str, Any], input_data: Dict[str, Any] = None) -> bool:
        """Check if a single condition matches.

        Args:
            condition: Condition to check
            tool_name: Tool being used
            tool_input: Tool input dict
            input_data: Full hook input data (for Stop events, etc.)

        Returns:
            True if condition matches
        """
        # Extract the field value to check
        field_value = self._extract_field(condition.field, tool_name, tool_input, input_data)
        if field_value is None:
            return False

        # Apply operator
        operator = condition.operator
        pattern = condition.pattern

        if operator == 'regex_match':
            return self._regex_match(pattern, field_value)
        elif operator == 'not_regex_match':
            return not self._regex_match(pattern, field_value)
        elif operator == 'contains':
            return pattern in field_value
        elif operator == 'equals':
            return pattern == field_value
        elif operator == 'not_contains':
            return pattern not in field_value
        elif operator == 'starts_with':
            return field_value.startswith(pattern)
        elif operator == 'ends_with':
            return field_value.endswith(pattern)
        else:
            # Unknown operator
            return False

    def _extract_field(self, field: str, tool_name: str,
                      tool_input: Dict[str, Any], input_data: Dict[str, Any] = None) -> Optional[str]:
        """Extract field value from tool input or hook input data.

        Args:
            field: Field name like "command", "new_text", "file_path", "reason", "transcript"
            tool_name: Tool being used (may be empty for Stop events)
            tool_input: Tool input dict
            input_data: Full hook input (for accessing transcript_path, reason, etc.)

        Returns:
            Field value as string, or None if not found
        """
        # Direct tool_input fields
        if field in tool_input:
            value = tool_input[field]
            if isinstance(value, str):
                return value
            return str(value)

        # For Stop events and other non-tool events, check input_data
        if input_data:
            # Stop event specific fields
            if field == 'reason':
                return input_data.get('reason', '')
            elif field == 'transcript':
                # Read transcript file if path provided
                transcript_path = input_data.get('transcript_path')
                if transcript_path:
                    try:
                        return _read_tail(transcript_path)
                    except FileNotFoundError:
                        print(f"Warning: Transcript file not found: {transcript_path}", file=sys.stderr)
                        return ''
                    except (IOError, OSError) as e:
                        print(f"Warning: Error reading transcript {transcript_path}: {e}", file=sys.stderr)
                        return ''
            elif (field in STOP_MESSAGE_FIELDS and not tool_name
                  and input_data.get('hook_event_name') in STOP_EVENTS):
                return self._stop_message(input_data)
            elif field == 'user_prompt':
                # For UserPromptSubmit events — Claude Code sends 'prompt', not 'user_prompt'
                return input_data.get('user_prompt') or input_data.get('prompt', '')

        # Handle special cases by tool type
        if tool_name == 'Bash':
            if field == 'command':
                return tool_input.get('command', '')

        elif tool_name in ['Write', 'Edit', 'Update']:
            if field == 'content':
                # Write uses 'content', Edit has 'new_string'
                return tool_input.get('content') or tool_input.get('new_string', '')
            elif field == 'new_text' or field == 'new_string':
                return tool_input.get('new_string') or tool_input.get('content', '')
            elif field == 'old_text' or field == 'old_string':
                return tool_input.get('old_string', '')
            elif field == 'file_path':
                return tool_input.get('file_path', '')

        elif tool_name == 'MultiEdit':
            if field == 'file_path':
                return tool_input.get('file_path', '')
            elif field in ['new_text', 'content']:
                # Concatenate all edits
                edits = tool_input.get('edits', [])
                return ' '.join(e.get('new_string', '') for e in edits)

        return None

    def _stop_message(self, input_data: Dict[str, Any]) -> Optional[str]:
        """The assistant's final message for a Stop event.

        Claude Code supplies it as last_assistant_message; the transcript is a
        fallback only when that key is absent.
        """
        if 'last_assistant_message' in input_data:
            return input_data['last_assistant_message'] or ''
        transcript_path = input_data.get('transcript_path')
        if not transcript_path:
            return None
        try:
            return last_assistant_text(transcript_path)
        except (IOError, OSError) as e:
            print(f"Warning: Error reading transcript {transcript_path}: {e}", file=sys.stderr)
            return None

    def _regex_match(self, pattern: str, text: str) -> bool:
        """Check if pattern matches text using regex.

        Args:
            pattern: Regex pattern
            text: Text to match against

        Returns:
            True if pattern matches
        """
        try:
            # Use cached compiled regex (LRU cache with max 128 patterns)
            regex = compile_regex(pattern)
            return bool(regex.search(text))

        except re.error as e:
            print(f"Invalid regex pattern '{pattern}': {e}", file=sys.stderr)
            return False


# For testing
if __name__ == '__main__':
    from core.config_loader import Condition, Rule

    # Test rule evaluation
    rule = Rule(
        name="test-rm",
        enabled=True,
        event="bash",
        conditions=[
            Condition(field="command", operator="regex_match", pattern=r"rm\s+-rf")
        ],
        message="Dangerous rm command!"
    )

    engine = RuleEngine()

    # Test matching input
    test_input = {
        "tool_name": "Bash",
        "tool_input": {
            "command": "rm -rf /tmp/test"
        }
    }

    result = engine.evaluate_rules([rule], test_input)
    print("Match result:", result)

    # Test non-matching input
    test_input2 = {
        "tool_name": "Bash",
        "tool_input": {
            "command": "ls -la"
        }
    }

    result2 = engine.evaluate_rules([rule], test_input2)
    print("Non-match result:", result2)
