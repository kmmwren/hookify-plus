"""Stop-event rules, event aliases and Write/Edit content behaviour."""
import json
import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import config_loader  # noqa: E402
from core.config_loader import Condition, Rule, load_rules  # noqa: E402
from core.rule_engine import RuleEngine  # noqa: E402

STOP = {'hook_event_name': 'Stop'}


def stop_rule(field='last_assistant_message', pattern='long-term', **kw):
    return Rule(name='r', enabled=True, event='stop',
                conditions=[Condition(field=field, operator='regex_match', pattern=pattern)],
                message='msg', **kw)


def fires(rule, data):
    return bool(RuleEngine().evaluate_rules([rule], data))


@pytest.mark.parametrize('field', ['last_assistant_message', 'content', 'response', 'response_text'])
def test_stop_rule_fires_on_last_assistant_message(field):
    data = dict(STOP, last_assistant_message='this is a long-term fix')
    assert fires(stop_rule(field=field), data)


def test_stop_rule_does_not_fire_on_clean_message():
    assert not fires(stop_rule(), dict(STOP, last_assistant_message='done'))


def test_stop_rule_block_uses_stop_decision():
    result = RuleEngine().evaluate_rules(
        [stop_rule(action='block')], dict(STOP, last_assistant_message='long-term'))
    assert result['decision'] == 'block'


def test_stop_hook_active_never_reblocks():
    data = dict(STOP, last_assistant_message='long-term', stop_hook_active=True)
    assert not fires(stop_rule(action='block'), data)


def test_legacy_pattern_stop_rule_fires():
    rule = Rule.from_dict({'name': 'legacy', 'event': 'stop', 'pattern': 'PR is ready'}, 'm')
    assert rule.conditions[0].field == 'content'
    assert fires(rule, dict(STOP, last_assistant_message='the PR is ready'))


def test_transcript_fallback_only_when_key_absent(tmp_path):
    t = tmp_path / 't.jsonl'
    lines = [
        {'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': 'old long-term'}]}},
        {'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': 'latest answer'}]}},
        {'message': {'role': 'assistant', 'content': [{'type': 'tool_use', 'name': 'Bash'}]}},
        {'message': {'role': 'user', 'content': 'hi'}},
    ]
    t.write_text('\n'.join(json.dumps(l) for l in lines))
    data = dict(STOP, transcript_path=str(t))
    assert not fires(stop_rule(), data)
    assert fires(stop_rule(pattern='latest'), data)
    # An explicit (even empty) key wins over the transcript.
    assert not fires(stop_rule(pattern='latest'), dict(data, last_assistant_message=''))


def test_transcript_tail_is_bounded(tmp_path, monkeypatch):
    from core import rule_engine
    monkeypatch.setattr(rule_engine, '_TRANSCRIPT_TAIL_BYTES', 200)
    t = tmp_path / 't.jsonl'
    t.write_text('A' * 5000 + '\n' + 'TAIL\n')
    value = RuleEngine()._extract_field('transcript', '', {}, dict(STOP, transcript_path=str(t)))
    assert 'TAIL' in value and 'AAAA' not in value


def test_missing_transcript_degrades():
    assert not fires(stop_rule(), dict(STOP, transcript_path='/nonexistent/t.jsonl'))


def test_non_stop_event_does_not_read_assistant_message():
    data = {'hook_event_name': 'UserPromptSubmit', 'prompt': 'x', 'last_assistant_message': 'long-term'}
    assert not fires(stop_rule(), data)


@pytest.mark.parametrize('tool,key', [('Write', 'content'), ('Edit', 'new_string')])
def test_write_edit_content_unchanged(tool, key):
    rule = Rule(name='r', enabled=True, event='file',
                conditions=[Condition(field='content', operator='regex_match', pattern='def foo')],
                message='m')
    data = {'hook_event_name': 'PreToolUse', 'tool_name': tool,
            'tool_input': {key: 'def foo(): pass'},
            'last_assistant_message': 'unrelated'}
    assert fires(rule, data)


def _load(tmp_home, monkeypatch, files, event):
    (tmp_home / '.claude').mkdir()
    for name, body in files.items():
        (tmp_home / '.claude' / name).write_text(body)
    monkeypatch.setenv('HOME', str(tmp_home))
    monkeypatch.chdir(tmp_home)
    return [r.name for r in load_rules(event=event)]


RESP = '---\nname: resp\nevent: response\nconditions:\n  - field: response\n    operator: regex_match\n    pattern: x\n---\nm\n'


def test_response_event_is_alias_of_stop(tmp_path, monkeypatch):
    assert _load(tmp_path, monkeypatch, {'hookify.resp.local.md': RESP}, 'stop') == ['resp']


def test_response_rule_not_loaded_for_other_events(tmp_path, monkeypatch):
    assert _load(tmp_path, monkeypatch, {'hookify.resp.local.md': RESP}, 'bash') == []


def test_response_rule_end_to_end(tmp_path, monkeypatch):
    names = _load(tmp_path, monkeypatch, {'hookify.resp.local.md': RESP}, 'stop')
    assert names == ['resp']
    rules = load_rules(event='stop')
    assert fires(rules[0], dict(STOP, last_assistant_message='xyz'))
