"""#251: attr-form salvage must recover acts, never infer them from prose."""
from sage.gateway.being_tool_loop import salvage_tool_calls

TOOLS = [{
    "type": "function",
    "function": {
        "name": "memory_write",
        "parameters": {"type": "object", "properties": {"path": {}, "content": {}}},
    },
}, {
    "type": "function",
    "function": {
        "name": "say",
        "parameters": {"type": "object", "properties": {"to": {}, "text": {}}},
    },
}]


def calls(text):
    return salvage_tool_calls(text, TOOLS)


def test_attr_call_as_the_whole_reply_is_salvaged():
    got = calls('memory_write path="notes/x.md" content="draft"')
    assert len(got) == 1
    assert got[0]["function"] == {
        "name": "memory_write",
        "arguments": {"path": "notes/x.md", "content": "draft"},
    }


def test_measured_bold_attr_form_is_salvaged():
    got = calls('**say to="dp" text="hello"**')
    assert len(got) == 1
    assert got[0]["function"]["name"] == "say"
    assert got[0]["function"]["arguments"] == {"to": "dp", "text": "hello"}


def test_negated_and_narrated_attr_forms_are_not_acts():
    assert calls("I won't memory_write path=\"notes/x.md\" content=\"draft\" today.") == []
    assert calls('Next time I could memory_write path="notes/y.md" content="z".') == []
    assert calls('I used memory_write path="notes/y.md" content="z" earlier.') == []


def test_tool_shaped_code_is_not_an_act():
    assert calls('`memory_write path="notes/x.md" content="draft"`') == []
    assert calls('```text\nmemory_write path="notes/x.md" content="draft"\n```') == []


def test_trailing_or_leading_prose_refuses_salvage():
    assert calls('please memory_write path="notes/x.md" content="draft"') == []
    assert calls('memory_write path="notes/x.md" content="draft" if needed') == []