"""Turn handling: safety gate -> tool loop -> answer.

This inverts the FixFeels control flow. There, a script drove the call and the
knowledge base was the detour. Here the customer drives, and every factual claim
has to come back from a tool.

Streaming note: the model answers in the same call that stops requesting tools,
so the reply is emitted as one delta rather than token-by-token. The NDJSON
envelope (meta -> delta -> done) is kept because the reference frontend's speech
queue already waits for `done` before speaking — nothing is lost, and real token
streaming can be dropped in later without touching the client.
"""

from __future__ import annotations

import json
from typing import Any, Generator

import config
import languages
import safety
import tools
from llm import LLMError, chat as llm_chat
from session import Session

AGENT_NAME = "Asha"

BASE_PROMPT = (
    f"You are {AGENT_NAME}, a customer help desk agent for Hindustan Wellness, an "
    "Indian diagnostics company offering blood tests and health checkup packages with "
    "free home sample collection.\n\n"
    "HOW TO ANSWER\n"
    "- Be warm, brief and practical, like a good call-centre agent. Two or three short "
    "sentences. This may be spoken aloud, so no markdown, no bullet points, no emoji.\n"
    "- NEVER state a price, test count, turnaround time, coverage area, policy or "
    "booking status from memory. Call a tool and use what it returns. If a tool "
    "returns nothing useful, say you do not have it and offer a human agent.\n"
    "- Quote prices as rupees with the discounted price first.\n"
    "- Ask for one piece of information at a time. Do not interrogate.\n"
    "- Anything a tool marked \"source\": \"mock\" is demo data; still answer naturally, "
    "but never invent extra detail around it.\n\n"
    "LANGUAGE\n"
    "- Reply in the SAME language and script the customer used. If they wrote Hindi in "
    "Roman letters, reply the same way. If they mixed Hindi and English, mix it back "
    "the same way — that is normal Indian speech, not an error to correct.\n"
    "- Keep package names, test names and pincodes in their original form; do not "
    "translate or transliterate them.\n\n"
)


def _system_prompt(session: Session, locale: str) -> str:
    language = languages.get(locale)
    lines = [
        BASE_PROMPT,
        safety.SAFETY_RULES,
        f"\nThe customer's language appears to be {language.name} ({language.locale}). "
        "Mirror their actual message rather than this label if the two disagree.",
    ]
    if session.known:
        facts = "; ".join(f"{k}: {v}" for k, v in session.known.items())
        lines.append(f"\nAlready provided by this customer (do not ask again): {facts}")
    return "\n".join(lines)


def _emit(event_type: str, **fields: Any) -> str:
    return json.dumps({"type": event_type, **fields}, ensure_ascii=False) + "\n"


def _remember_from_tool(session: Session, name: str, arguments: dict) -> None:
    """Carry identifiers across turns so the agent stops re-asking."""
    if arguments.get("phone"):
        session.remember(phone=str(arguments["phone"]))
    if arguments.get("pincode"):
        session.remember(pincode=str(arguments["pincode"]))
    if name == "escalate_to_human":
        session.escalated = True


def process_turn(
    session: Session,
    user_text: str,
    locale_hint: str | None = None,
) -> Generator[str, None, None]:
    """Yield NDJSON lines for one customer turn."""
    user_text = (user_text or "").strip()
    if not user_text:
        yield _emit("error", detail="Empty message")
        return

    locale = languages.detect_locale(user_text, hint=locale_hint or session.locale)
    session.locale = locale

    # 1. Emergency gate — before the model, and not dependent on it.
    if safety.is_emergency(user_text):
        reply = safety.emergency_reply(locale)
        session.append("user", user_text)
        session.append("assistant", reply)
        yield _emit(
            "meta",
            locale=locale,
            speakable=languages.can_speak(locale),
            guardrail="emergency",
            tools_used=[],
        )
        yield _emit("delta", text=reply)
        yield _emit("done", reply=reply, locale=locale, guardrail="emergency")
        return

    if not config.llm_configured():
        detail = (
            "The assistant is not connected to Azure OpenAI. Set AZURE_OPENAI_ENDPOINT "
            "and AZURE_OPENAI_KEY in backend/.env."
        )
        yield _emit("error", detail=detail)
        return

    # 2. Build the prompt.
    messages: list[dict] = [{"role": "system", "content": _system_prompt(session, locale)}]
    messages.extend(session.turns)
    if safety.wants_interpretation(user_text):
        messages.append({"role": "system", "content": safety.interpretation_nudge()})
    messages.append({"role": "user", "content": user_text})

    yield _emit(
        "meta",
        locale=locale,
        speakable=languages.can_speak(locale),
        guardrail="interpretation" if safety.wants_interpretation(user_text) else None,
    )

    # 3. Tool loop.
    used: list[str] = []
    reply = ""
    try:
        for _ in range(config.MAX_TOOL_ROUNDS):
            message = llm_chat(messages, tools=tools.TOOL_SCHEMAS)
            calls = message.get("tool_calls") or []

            if not calls:
                reply = (message.get("content") or "").strip()
                break

            messages.append(message)
            for call in calls:
                name = call["function"]["name"]
                try:
                    arguments = json.loads(call["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    arguments = {}

                yield _emit("tool", name=name, arguments=arguments)
                result = tools.run_tool(name, arguments)
                _remember_from_tool(session, name, arguments)
                used.append(name)

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
        else:
            # Ran out of rounds — ask for a plain answer with no further tools.
            messages.append(
                {
                    "role": "system",
                    "content": "Answer now from what the tools returned. Do not call more tools.",
                }
            )
            reply = (llm_chat(messages).get("content") or "").strip()
    except LLMError as exc:
        yield _emit("error", detail=str(exc))
        return

    if not reply:
        reply = (
            "Sorry, I could not put that together. Let me connect you to an agent — "
            "you can also call or WhatsApp 9810981073."
        )

    session.append("user", user_text)
    session.append("assistant", reply)

    yield _emit("delta", text=reply)
    yield _emit(
        "done",
        reply=reply,
        locale=locale,
        speakable=languages.can_speak(locale),
        tools_used=used,
        escalated=session.escalated,
    )


def greeting(locale: str) -> str:
    """Opening line. Static per language — no model round-trip on page load."""
    return {
        "en-IN": (
            "Namaste! I am Asha from Hindustan Wellness. I can help with health "
            "packages, prices, home sample collection, bookings and reports. How may I "
            "help you?"
        ),
        "hi-IN": (
            "नमस्ते! मैं हिंदुस्तान वेलनेस से आशा बोल रही हूँ। हेल्थ पैकेज, कीमत, घर से "
            "सैंपल कलेक्शन, बुकिंग और रिपोर्ट — किसी भी चीज़ में मदद कर सकती हूँ। बताइए?"
        ),
        "mr-IN": (
            "नमस्कार! मी हिंदुस्तान वेलनेसमधून आशा बोलत आहे. हेल्थ पॅकेज, किंमत, घरून "
            "सॅम्पल कलेक्शन, बुकिंग आणि रिपोर्टमध्ये मदत करू शकते. काय मदत करू?"
        ),
        "bn-IN": (
            "নমস্কার! আমি হিন্দুস্তান ওয়েলনেস থেকে আশা বলছি। হেলথ প্যাকেজ, দাম, বাড়ি "
            "থেকে স্যাম্পল কালেকশন, বুকিং ও রিপোর্ট নিয়ে সাহায্য করতে পারি। বলুন?"
        ),
        "ta-IN": (
            "வணக்கம்! நான் ஹிந்துஸ்தான் வெல்னஸ்ஸில் இருந்து ஆஷா. ஹெல்த் பேக்கேஜ், விலை, "
            "வீட்டிலிருந்து சாம்பிள் சேகரிப்பு, புக்கிங், ரிப்போர்ட் — உதவ முடியும். "
            "சொல்லுங்கள்?"
        ),
        "te-IN": (
            "నమస్కారం! నేను హిందుస్తాన్ వెల్‌నెస్ నుండి ఆశ. హెల్త్ ప్యాకేజీలు, ధరలు, "
            "ఇంటి వద్ద శాంపిల్ కలెక్షన్, బుకింగ్, రిపోర్ట్‌లలో సహాయం చేయగలను. చెప్పండి?"
        ),
    }.get(locale, "Namaste! I am Asha from Hindustan Wellness. How may I help you?")
