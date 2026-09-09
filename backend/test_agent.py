"""Offline checks for the turn pipeline — no Azure credentials needed.

The model is stubbed, so this exercises what we actually own: the safety gate,
the tool loop, argument passing, session memory and the NDJSON envelope. Run it
before a demo to be sure nothing structural broke.

    python test_agent.py
"""

from __future__ import annotations

import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import chat
import config
import languages
import safety
import session as sessions
import tools

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASSED if condition else FAILED).append(name)
    print(f"  {'OK  ' if condition else 'FAIL'} {name}{'' if condition else f' — {detail}'}")


def collect(session, message, locale=None) -> dict:
    """Run a turn and fold the NDJSON stream into something assertable."""
    events = [json.loads(line) for line in chat.process_turn(session, message, locale)]
    return {
        "events": events,
        "types": [e["type"] for e in events],
        "tools": [e["name"] for e in events if e["type"] == "tool"],
        "done": next((e for e in events if e["type"] == "done"), None),
        "error": next((e for e in events if e["type"] == "error"), None),
    }


def stub_llm(script):
    """Replace chat.llm_chat with a scripted sequence of assistant messages."""
    calls = {"n": 0, "seen": []}

    def fake(messages, tools=None):
        calls["seen"].append(messages)
        index = min(calls["n"], len(script) - 1)
        calls["n"] += 1
        return script[index]

    chat.llm_chat = fake
    return calls


def tool_call(call_id, name, arguments):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
        ],
    }


def main() -> None:
    original = chat.llm_chat
    config.AZURE_OPENAI_ENDPOINT = "https://stub.invalid/chat"
    config.AZURE_OPENAI_KEY = "stub"

    print("\n1. Safety gate (runs before the model)")
    for text, expected in [
        ("I am having chest pain", "en-IN"),
        ("mujhe seene mein dard ho raha hai", "hi-IN"),
        ("என் மார்பு வலி அதிகமாக உள்ளது", "ta-IN"),
    ]:
        state = sessions.create("hi-IN")
        stub_llm([{"role": "assistant", "content": "should never be reached"}])
        result = collect(state, text)
        done = result["done"]
        check(
            f"emergency short-circuits ({text[:26]}…)",
            done and done.get("guardrail") == "emergency" and done["locale"] == expected,
            f"got {done}",
        )
        check(
            "  emergency reply is in the caller's language",
            done and done["reply"] == safety.emergency_reply(expected),
        )
        check("  no tools were called during an emergency", not result["tools"])

    print("\n2. Tool loop")
    state = sessions.create("en-IN")
    stub_llm(
        [
            tool_call("c1", "search_catalogue", {"query": "full body checkup price"}),
            {"role": "assistant", "content": "Full Body Wellness is 799 rupees for 80 tests."},
        ]
    )
    result = collect(state, "what does a full body checkup cost?")
    check("search_catalogue was called", result["tools"] == ["search_catalogue"], str(result["tools"]))
    check("stream is meta -> tool -> delta -> done",
          result["types"] == ["meta", "tool", "delta", "done"], str(result["types"]))
    check("reply reaches the client", "799" in (result["done"] or {}).get("reply", ""))
    check("tools_used is reported", (result["done"] or {}).get("tools_used") == ["search_catalogue"])

    print("\n3. Multi-step tools and session memory")
    state = sessions.create("en-IN")
    stub_llm(
        [
            tool_call("c1", "check_pincode", {"pincode": "110092"}),
            tool_call("c2", "get_available_slots", {"pincode": "110092"}),
            {"role": "assistant", "content": "We cover Preet Vihar. Morning slots are open."},
        ]
    )
    result = collect(state, "do you collect from 110092?")
    check("both tools ran in order",
          result["tools"] == ["check_pincode", "get_available_slots"], str(result["tools"]))
    check("pincode remembered on the session", state.known.get("pincode") == "110092", str(state.known))

    print("\n4. Round limit is enforced")
    state = sessions.create("en-IN")
    stub_llm([tool_call("loop", "search_catalogue", {"query": "x"})])  # never stops
    result = collect(state, "loop forever please")
    check("stops at MAX_TOOL_ROUNDS",
          len(result["tools"]) == config.MAX_TOOL_ROUNDS, f"{len(result['tools'])} calls")
    check("still produces a final answer", result["done"] is not None)

    print("\n5. A failing tool does not kill the turn")
    state = sessions.create("en-IN")
    stub_llm(
        [
            tool_call("c1", "lookup_booking", {}),  # no phone, no booking id
            {"role": "assistant", "content": "Could you share your registered mobile number?"},
        ]
    )
    result = collect(state, "where is my booking")
    check("turn completes", result["done"] is not None and not result["error"])

    print("\n6. Tools against real data")
    catalogue = tools.search_catalogue("thyroid package", max_results=3)
    check("catalogue search returns hits", len(catalogue["results"]) > 0)
    booking = tools.lookup_booking(phone="9800000002")
    check("known demo booking is found", booking["found"] and booking["bookings"][0]["report_status"] == "ready")
    check("unknown number is not invented", not tools.lookup_booking(phone="9999999999")["found"])
    check("serviceable pincode", tools.check_pincode("110092")["serviceable"])
    check("unserviceable pincode", not tools.check_pincode("999999")["serviceable"])
    created = tools.create_booking("9800000009", "Full Body Wellness", "110092")
    check("booking can be created", created["created"], str(created))
    check("bad phone is rejected", not tools.create_booking("123", "Full Body Wellness", "110092")["created"])
    check("mock results are labelled", tools.check_pincode("110092")["source"] == "mock")

    print("\n7. Language plumbing")
    check("6 demo languages", len(languages.LANGUAGES) == 6)
    check("LID candidates within Azure's limit of 10", len(languages.stt_candidates()) <= 10)
    check("every demo language has a voice", all(languages.can_speak(l.locale) for l in languages.LANGUAGES))
    check("voice and xml:lang agree",
          all(languages.tts_voice_for(l.locale)[1] == l.locale for l in languages.LANGUAGES))
    check("every greeting is non-empty",
          all(chat.greeting(lang.locale) for lang in languages.LANGUAGES))

    chat.llm_chat = original

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        for name in FAILED:
            print(f"  FAILED: {name}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
