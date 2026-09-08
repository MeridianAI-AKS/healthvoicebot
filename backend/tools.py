"""Tools the agent can call.

Catalogue search is real — it runs against the scraped corpus. Everything
operational (bookings, reports, slots, serviceability) is backed by
data/mock_operations.json, because Hindustan Wellness's real systems are not
wired up. Every mock result carries "source": "mock" so the UI can badge it and
nobody mistakes a demo answer for live data.

Bookings created during a demo are held in memory only and vanish on restart.
That is deliberate: writing invented customer records to disk in a health
context is not something a prototype should start doing.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from llm import embed_one
from retrieval import get_retriever

MOCK_PATH = Path(__file__).parent / "data" / "mock_operations.json"

# Bookings made during a session. In-memory by design — see module docstring.
_session_bookings: list[dict] = []


@lru_cache(maxsize=1)
def _mock() -> dict:
    with MOCK_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _normalise_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits


def _find_bookings(phone: str = "", booking_id: str = "") -> list[dict]:
    phone = _normalise_phone(phone)
    booking_id = (booking_id or "").strip().upper()
    rows = _mock()["bookings"] + _session_bookings
    return [
        b
        for b in rows
        if (phone and _normalise_phone(b["phone"]) == phone)
        or (booking_id and b["booking_id"].upper() == booking_id)
    ]


# ── tool implementations ─────────────────────────────────────────────

def search_catalogue(query: str, max_results: int = 5) -> dict:
    retriever = get_retriever()
    hits = retriever.search(query, limit=max_results, query_vector=embed_one(query))
    return {
        "source": "catalogue",
        "mode": retriever.mode,
        "query": query,
        "results": [
            {"title": hit.document.title, "detail": hit.document.answer_text}
            for hit in hits
        ],
    }


def get_package_details(package_name: str) -> dict:
    document = get_retriever().by_slug_or_title(package_name)
    if not document:
        return {
            "source": "catalogue",
            "found": False,
            "message": f"No package named '{package_name}' in the catalogue.",
        }
    return {
        "source": "catalogue",
        "found": True,
        "title": document.title,
        "detail": document.answer_text,
        "url": document.meta.get("url"),
    }


def check_pincode(pincode: str) -> dict:
    pincode = re.sub(r"\D", "", pincode or "")
    areas = _mock()["serviceable_pincodes"]
    if pincode in areas:
        return {
            "source": "mock",
            "serviceable": True,
            "pincode": pincode,
            "area": areas[pincode],
            "note": "Free home sample collection is available here.",
        }
    return {
        "source": "mock",
        "serviceable": False,
        "pincode": pincode,
        "note": (
            "Not in the demo coverage list. In production this checks the client's "
            "real serviceability API. Offer to have the team confirm by phone."
        ),
    }


def get_available_slots(pincode: str, collection_date: str = "") -> dict:
    check = check_pincode(pincode)
    if not check["serviceable"]:
        return {"source": "mock", "available": False, **check}

    if collection_date:
        try:
            datetime.strptime(collection_date, "%Y-%m-%d")
        except ValueError:
            collection_date = ""
    if not collection_date:
        collection_date = (date.today() + timedelta(days=1)).isoformat()

    return {
        "source": "mock",
        "available": True,
        "pincode": pincode,
        "area": check["area"],
        "date": collection_date,
        "slots": _mock()["collection_slots"],
        "note": "Home collection is free. Fasting packages are best in a morning slot.",
    }


def lookup_booking(phone: str = "", booking_id: str = "") -> dict:
    if not phone and not booking_id:
        return {
            "source": "mock",
            "found": False,
            "message": "Ask the customer for their registered mobile number first.",
        }
    matches = _find_bookings(phone, booking_id)
    if not matches:
        return {
            "source": "mock",
            "found": False,
            "message": (
                "No booking found for those details in the demo data. Offer to connect "
                "a human agent."
            ),
        }
    return {"source": "mock", "found": True, "bookings": matches}


def get_report_status(phone: str = "", booking_id: str = "") -> dict:
    result = lookup_booking(phone, booking_id)
    if not result.get("found"):
        return result
    reports = [
        {
            "booking_id": b["booking_id"],
            "package": b["package"],
            "report_status": b.get("report_status"),
            "expected": b.get("report_eta"),
            "delivered_by": b.get("report_channels"),
            "collection_date": b.get("collection_date"),
        }
        for b in result["bookings"]
    ]
    return {
        "source": "mock",
        "found": True,
        "reports": reports,
        "note": (
            "Reports go out by SMS, email and WhatsApp, and are in the app. A free "
            "doctor consultation follows every report."
        ),
    }


def create_booking(
    phone: str,
    package_name: str,
    pincode: str,
    collection_date: str = "",
    collection_slot: str = "",
) -> dict:
    phone = _normalise_phone(phone)
    if not re.fullmatch(r"[6-9]\d{9}", phone):
        return {
            "source": "mock",
            "created": False,
            "message": "That does not look like a valid 10-digit Indian mobile number.",
        }

    package = get_retriever().by_slug_or_title(package_name)
    if not package:
        return {
            "source": "mock",
            "created": False,
            "message": f"No package named '{package_name}'. Search the catalogue first.",
        }

    coverage = check_pincode(pincode)
    if not coverage["serviceable"]:
        return {"source": "mock", "created": False, **coverage}

    slots = _mock()["collection_slots"]
    if collection_slot and collection_slot not in slots:
        return {
            "source": "mock",
            "created": False,
            "message": f"Slot not available. Offer one of: {', '.join(slots)}",
        }

    booking = {
        "booking_id": f"HWDEMO{len(_session_bookings) + 1:04d}",
        "phone": phone,
        "customer_name": "Demo booking",
        "package": package.title,
        "pincode": pincode,
        "collection_date": collection_date or (date.today() + timedelta(days=1)).isoformat(),
        "collection_slot": collection_slot or slots[1],
        "status": "confirmed",
        "amount": package.meta.get("price"),
        "payment": "pay at collection",
        "report_status": "pending",
        "report_eta": package.meta.get("report_time"),
    }
    _session_bookings.append(booking)
    return {
        "source": "mock",
        "created": True,
        "booking": booking,
        "note": "Demo booking only — nothing was sent to Hindustan Wellness.",
    }


def escalate_to_human(reason: str, phone: str = "") -> dict:
    contact = "9810981073"
    return {
        "source": "mock",
        "escalated": True,
        "reason": reason,
        "callback_number": _normalise_phone(phone) or None,
        "message": (
            f"A human agent will be connected. Customers can also call or WhatsApp "
            f"{contact} directly, 5 AM to 12 PM Mon-Sat."
        ),
    }


# ── schemas ──────────────────────────────────────────────────────────

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_catalogue",
            "description": (
                "Search Hindustan Wellness health packages, tests, prices, preparation "
                "rules, company policies and the symptom-to-test mapping. ALWAYS use "
                "this before stating any price, test count, turnaround or policy. Pass "
                "the query in ENGLISH even when the customer wrote another language."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "English search query"},
                    "max_results": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_package_details",
            "description": "Full detail for one package by its exact name.",
            "parameters": {
                "type": "object",
                "properties": {"package_name": {"type": "string"}},
                "required": ["package_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_pincode",
            "description": "Check whether home sample collection covers a pincode.",
            "parameters": {
                "type": "object",
                "properties": {"pincode": {"type": "string"}},
                "required": ["pincode"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_available_slots",
            "description": "Home collection slots for a pincode and optional date (YYYY-MM-DD).",
            "parameters": {
                "type": "object",
                "properties": {
                    "pincode": {"type": "string"},
                    "collection_date": {"type": "string"},
                },
                "required": ["pincode"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_booking",
            "description": (
                "Look up an existing booking by registered mobile number or booking id. "
                "Ask for the number before calling this."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {"type": "string"},
                    "booking_id": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_report_status",
            "description": "Whether a report is ready, and when it is expected.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {"type": "string"},
                    "booking_id": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_booking",
            "description": (
                "Book a home collection. Only call after the customer has confirmed the "
                "package, pincode, date and slot."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {"type": "string"},
                    "package_name": {"type": "string"},
                    "pincode": {"type": "string"},
                    "collection_date": {"type": "string"},
                    "collection_slot": {"type": "string"},
                },
                "required": ["phone", "package_name", "pincode"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": (
                "Hand off to a human agent — on request, on complaint, or when the "
                "answer is not in the catalogue."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string"},
                    "phone": {"type": "string"},
                },
                "required": ["reason"],
            },
        },
    },
]

REGISTRY: dict[str, Callable[..., dict]] = {
    "search_catalogue": search_catalogue,
    "get_package_details": get_package_details,
    "check_pincode": check_pincode,
    "get_available_slots": get_available_slots,
    "lookup_booking": lookup_booking,
    "get_report_status": get_report_status,
    "create_booking": create_booking,
    "escalate_to_human": escalate_to_human,
}


def run_tool(name: str, arguments: dict[str, Any]) -> dict:
    function = REGISTRY.get(name)
    if not function:
        return {"error": f"Unknown tool '{name}'"}
    try:
        return function(**arguments)
    except TypeError as exc:
        return {"error": f"Bad arguments for {name}: {exc}"}
    except Exception as exc:  # a tool failure must not kill the turn
        return {"error": f"{name} failed: {exc}"}
