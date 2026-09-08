"""Turn hw_knowledge.json into flat retrieval documents.

The corpus is ~3.2 MB, so it cannot be stuffed into a system prompt the way the
FixFeels reference does. Each package, FAQ and company fact becomes one small
document with searchable text and a compact `answer_text` the model is given
when the document is retrieved.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

KNOWLEDGE_PATH = Path(__file__).parent / "data" / "hw_knowledge.json"


@dataclass
class Document:
    doc_id: str
    kind: str            # package | faq | company | policy
    title: str
    search_text: str     # what the index matches against
    answer_text: str     # what the model reads
    meta: dict[str, Any] = field(default_factory=dict)


def _rupees(value: Any) -> str:
    return f"Rs.{value:,}" if isinstance(value, (int, float)) else "price on request"


def _package_documents(knowledge: dict) -> list[Document]:
    docs: list[Document] = []
    for package in knowledge.get("packages", []):
        title = package.get("title") or ""
        if not title:
            continue

        tests = package.get("all_tests") or []
        groups = [g.get("group") for g in package.get("test_groups") or [] if g.get("group")]
        tags = package.get("taxonomy_tags") or []
        categories = package.get("categories") or []

        # Search text is deliberately keyword-rich: package name, what it covers,
        # who it is for, the body systems, the symptoms it is tagged to, and a
        # sample of the individual test names.
        search_parts = [
            title,
            package.get("description") or "",
            package.get("recommended_for") or "",
            " ".join(categories),
            " ".join(groups),
            " ".join(tags),
            " ".join(tests[:60]),
        ]

        fasting = package.get("fasting_required")
        fasting_text = (
            "Fasting required" if fasting is True
            else "No fasting required" if fasting is False
            else "Fasting requirement not listed"
        )

        answer_lines = [
            f"PACKAGE: {title}",
            f"Price: {_rupees(package.get('price'))}"
            + (
                f" (MRP {_rupees(package.get('mrp'))}, {package['discount_percent']}% off)"
                if package.get("discount_percent")
                else ""
            ),
            f"Tests included: {package.get('test_count')}",
            f"Report: {package.get('report_time')}",
            f"{fasting_text}. Samples: {', '.join(package.get('samples') or []) or 'not listed'}.",
            f"Age group: {package.get('age_group') or 'not listed'}",
        ]
        if package.get("description"):
            answer_lines.append(f"About: {package['description']}")
        if package.get("recommended_for"):
            answer_lines.append(f"Recommended for: {package['recommended_for']}")
        if groups:
            counts = ", ".join(
                f"{g['group']} ({g.get('test_count')})" for g in package["test_groups"]
            )
            answer_lines.append(f"Covers: {counts}")
        if package.get("preparation_instructions"):
            answer_lines.append(
                "Preparation: " + " ".join(package["preparation_instructions"][:4])
            )
        if tags:
            answer_lines.append(f"Relevant to: {', '.join(tags[:8])}")
        answer_lines.append(f"Page: {package.get('url')}")

        docs.append(
            Document(
                doc_id=f"pkg:{package['id']}",
                kind="package",
                title=title,
                search_text=" ".join(p for p in search_parts if p),
                answer_text="\n".join(answer_lines),
                meta={
                    "package_id": package["id"],
                    "price": package.get("price"),
                    "mrp": package.get("mrp"),
                    "test_count": package.get("test_count"),
                    "report_time": package.get("report_time"),
                    "fasting_required": fasting,
                    "url": package.get("url"),
                    "slug": package.get("slug"),
                },
            )
        )

        # Package FAQs are separate documents — they answer different questions
        # from the package summary and should be retrievable on their own.
        for index, faq in enumerate(package.get("faqs") or []):
            question = faq.get("question")
            answer = faq.get("answer")
            if not question or not answer:
                continue
            docs.append(
                Document(
                    doc_id=f"pkgfaq:{package['id']}:{index}",
                    kind="faq",
                    title=f"{title} — {question}",
                    search_text=f"{title} {question} {answer}",
                    answer_text=f"Q ({title}): {question}\nA: {answer}",
                    meta={"package_id": package["id"], "url": package.get("url")},
                )
            )
    return docs


def _company_documents(knowledge: dict) -> list[Document]:
    site = knowledge.get("site", {})
    docs: list[Document] = []

    contact = site.get("contact", {})
    offices = site.get("offices", [])
    docs.append(
        Document(
            doc_id="company:contact",
            kind="company",
            title="Contact and support hours",
            search_text=(
                "contact phone number email whatsapp support hours timing office address "
                "customer care helpline call centre reach us open closed"
                + " ".join(o.get("city", "") for o in offices)
            ),
            answer_text="\n".join(
                [
                    "CONTACT",
                    f"Phone: {contact.get('phone_primary')} (also {contact.get('phone_alternate')})",
                    f"WhatsApp: same number, {contact.get('whatsapp')}",
                    f"Email: {contact.get('email')}",
                    f"Support hours: {contact.get('support_hours')}",
                    "Offices: "
                    + "; ".join(f"{o['city']} — {o['address']}" for o in offices),
                ]
            ),
        )
    )

    docs.append(
        Document(
            doc_id="company:booking-process",
            kind="company",
            title="How booking and reports work",
            search_text=(
                "how to book booking process order test appointment slot home collection "
                "sample collection report delivery when will I get my report how do I get "
                "my report report kab aayega turnaround time 24 hours sms email whatsapp "
                "download report doctor consultation dietician free health manager "
                "modify change package cancel reschedule booking status"
            ),
            answer_text="\n".join(
                [
                    "HOW IT WORKS",
                    "Booking channels: " + ", ".join(site.get("booking_channels", [])),
                    "Steps: pick a package, book it, give contact details, choose the "
                    "sample collection date and time at checkout. Home sample collection "
                    "is free.",
                    "Reports are delivered by " + ", ".join(site.get("report_delivery", [])) + ".",
                    "After the report a doctor calls to discuss it; video consultation is "
                    "available in the Hindustan Wellness app. Dietician and health manager "
                    "consultations are free.",
                    "Every customer is assigned a health manager.",
                    "A package can be modified before sample pickup by calling or "
                    "WhatsApping the support number, or by telling the collection officer "
                    "at pickup.",
                ]
            ),
        )
    )

    docs.append(
        Document(
            doc_id="company:collection-and-charges",
            kind="company",
            title="Home collection, fasting and charges",
            search_text=(
                "home collection free charge fee cost extra visit charges phlebotomist "
                "sample collection at home is it free do you come home "
                "fasting empty stomach khali pet how many hours fasting before test "
                "water allowed morning slot timing preparation before test "
                "payment pay online cash on collection prepay postpay cancel reschedule"
            ),
            answer_text="\n".join(
                [
                    "HOME COLLECTION, FASTING AND PAYMENT",
                    "Home sample collection is FREE — there is no extra visit charge.",
                    "Fasting depends on the package: many full-body and diabetes "
                    "packages require it, others do not. Always check the specific "
                    "package before telling a customer — the package record says "
                    "whether fasting is required.",
                    "Where fasting is required, a morning collection slot is easiest.",
                    "Standard preparation: do not take the morning dose of any tablets "
                    "before collection, and avoid alcohol or nicotine for 24 hours.",
                    "Payment can be prepaid online or paid at the time of collection.",
                    "A package can be changed before sample pickup by calling or "
                    "WhatsApping the support number, or by telling the collection "
                    "officer at pickup.",
                ]
            ),
        )
    )

    about = site.get("about", {})
    stats = site.get("stats", {})
    docs.append(
        Document(
            doc_id="company:about",
            kind="company",
            title="About Hindustan Wellness",
            search_text=(
                "about company who are you what do you do lab quality accreditation "
                "cities coverage experience trust reviews rating doctors team founded"
            ),
            answer_text="\n".join(
                [
                    "ABOUT HINDUSTAN WELLNESS",
                    site.get("company", {}).get("summary", ""),
                    f"Founded {about.get('founded')}. {about.get('lab', '')}",
                    f"Reach: {about.get('reach')}.",
                    "Lab: " + "; ".join(site.get("lab_credentials", [])),
                    f"Scale: {stats.get('tests_performed')} tests, {stats.get('customers')} "
                    f"customers, Google rating {stats.get('google_rating')} from "
                    f"{stats.get('google_reviews')} reviews.",
                    "Doctors on panel: "
                    + "; ".join(
                        f"{d['name']} ({d['credentials']})" for d in site.get("doctors", [])[:6]
                    ),
                ]
            ),
        )
    )

    apps = site.get("apps", {})
    docs.append(
        Document(
            doc_id="company:app",
            kind="company",
            title="Mobile app",
            search_text=(
                "app mobile application download android ios play store app store "
                "digital report view report health trends family diet plan prescription"
            ),
            answer_text="\n".join(
                [
                    "MOBILE APP",
                    "Features: " + ", ".join(apps.get("features", [])),
                    f"Android: {apps.get('android')}",
                    f"iOS: {apps.get('ios')}",
                ]
            ),
        )
    )

    for index, faq in enumerate(site.get("faqs", [])):
        docs.append(
            Document(
                doc_id=f"sitefaq:{index}",
                kind="faq",
                title=faq["question"],
                search_text=f"{faq['question']} {faq['answer']}",
                answer_text=f"Q: {faq['question']}\nA: {faq['answer']}",
            )
        )

    return docs


def _taxonomy_documents(knowledge: dict) -> list[Document]:
    """One document per symptom/condition, listing the tests it maps to.

    Answers "I have hair loss, which test?" from Hindustan Wellness's own
    mapping instead of letting the model improvise clinical advice.
    """
    by_id = {p["id"]: p for p in knowledge.get("packages", [])}
    docs: list[Document] = []
    for group in knowledge.get("taxonomies", []):
        group_name = group.get("group", "")
        for item in group.get("items", []):
            package_ids = item.get("package_ids") or []
            if not package_ids:
                continue
            names = [by_id[pid]["title"] for pid in package_ids if pid in by_id]
            if not names:
                continue
            title = item.get("title", "")
            docs.append(
                Document(
                    doc_id=f"tax:{item['item_id']}",
                    kind="company",
                    title=f"{group_name}: {title}",
                    search_text=f"{title} {group_name} " + " ".join(names),
                    answer_text=(
                        f"TESTS LISTED FOR {title.upper()} ({group_name}):\n"
                        + "\n".join(f"- {n}" for n in names[:12])
                        + "\nThis is the mapping published by Hindustan Wellness, not a "
                        "diagnosis. A doctor should confirm what is appropriate."
                    ),
                    meta={"taxonomy": group_name, "item": title},
                )
            )
    return docs


@lru_cache(maxsize=1)
def load_knowledge(path: str | None = None) -> dict:
    target = Path(path) if path else KNOWLEDGE_PATH
    if not target.exists():
        raise FileNotFoundError(
            f"{target} not found. Run: python scrape_hw_knowledge.py"
        )
    with target.open(encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def build_documents() -> list[Document]:
    knowledge = load_knowledge()
    return (
        _package_documents(knowledge)
        + _company_documents(knowledge)
        + _taxonomy_documents(knowledge)
    )
