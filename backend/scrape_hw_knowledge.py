"""Build the Hindustan Wellness knowledge base from the site's catalogue APIs.

Writes data/hw_knowledge.json — the retrieval corpus the help-desk agent
answers from.

    python scrape_hw_knowledge.py                 # full crawl (~700 packages)
    python scrape_hw_knowledge.py --limit 40      # quick sample for dev
    python scrape_hw_knowledge.py --no-details    # listings only, no per-package calls

Structure of the output:
    site            company facts (hours, contact, labs, doctors) — see site_facts.py
    taxonomies      tests grouped by condition / habit / symptom
    categories      health package categories and their members
    packages        the catalogue, one entry per package, with detail merged in
    stats           counts + crawl metadata
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hw_api import HWClient, HWApiError
from site_facts import SITE_FACTS

DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "hw_knowledge.json"

PAGE_SIZE = 20


# ── normalisation ────────────────────────────────────────────────────

def package_slug(title: str) -> str:
    """'Young India: Full Body Checkup' -> 'Young-India-Full-Body-Checkup'.

    Matches the site's own /package/<slug> routes.
    """
    cleaned = re.sub(r"[^0-9A-Za-z]+", " ", title or "").strip()
    return "-".join(cleaned.split())


def parse_details(details: str) -> dict[str, Any]:
    """Split 'Age Group: 0 - 100 yrs|Blood Sample|Urine Sample|Fasting Required: yes'."""
    out: dict[str, Any] = {"age_group": None, "samples": [], "fasting_required": None}
    for part in (details or "").split("|"):
        part = part.strip()
        if not part:
            continue
        low = part.lower()
        if low.startswith("age group"):
            out["age_group"] = part.split(":", 1)[-1].strip()
        elif low.startswith("fasting required"):
            value = part.split(":", 1)[-1].strip().lower()
            out["fasting_required"] = value.startswith("y")
        elif "sample" in low:
            out["samples"].append(part)
    return out


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def instruction_lines(raw: str | None) -> list[str]:
    """'General Instructions:\n\nDo not...\nDo not...' -> a list of instructions."""
    lines = []
    for line in clean_text(raw).split("\n"):
        line = line.strip()
        if not line or line.rstrip(":").lower() in {
            "general instructions",
            "preparation & general instructions",
        }:
            continue
        lines.append(line)
    return lines


def normalise_listing(item: dict) -> dict:
    """One row from a catalogue listing -> our package shape."""
    details = parse_details(item.get("details") or item.get("sampleType") or "")
    price = item.get("price")
    discount_price = item.get("discountPrice")

    discount_pct = None
    if isinstance(price, (int, float)) and isinstance(discount_price, (int, float)):
        if price > 0 and discount_price < price:
            discount_pct = round((price - discount_price) / price * 100)

    title = clean_text(item.get("title"))
    return {
        "id": item.get("id"),
        "title": title,
        "slug": package_slug(title),
        "url": SITE_FACTS["package_url_template"].format(slug=package_slug(title)),
        "type": item.get("type"),
        "description": clean_text(item.get("description")),
        "recommended_for": clean_text(item.get("recommendedFor")),
        "report_time": clean_text(item.get("reportTime")),
        "mrp": price,
        "price": discount_price,
        "discount_percent": discount_pct,
        "test_count": item.get("testCount"),
        "age_group": details["age_group"],
        "samples": details["samples"],
        "fasting_required": details["fasting_required"],
        "categories": [],
    }


def merge_detail(package: dict, detail: dict) -> dict:
    """Fold getAllCatalogueDetails into a listing row."""
    body_parts = []
    for part in detail.get("bodyPartDetails") or []:
        tests = [clean_text(t) for t in (part.get("catalogueTest") or []) if clean_text(t)]
        body_parts.append(
            {
                "group": clean_text(part.get("bodyPartName")),
                "test_count": part.get("totalPartData"),
                "tests": tests,
            }
        )

    faqs = []
    for faq in detail.get("faqDataList") or []:
        question = clean_text(faq.get("question") or faq.get("faqQuestion"))
        answer = clean_text(faq.get("answer") or faq.get("faqAnswer"))
        if question:
            faqs.append({"question": question, "answer": answer})

    package.update(
        {
            "what_test": clean_text(detail.get("whatTest")),
            "why_test": clean_text(detail.get("whyTest")),
            "how_test": clean_text(detail.get("howTest")),
            "fasting_time": clean_text(detail.get("fastingTime")),
            "sample_required": clean_text(detail.get("sampleRequired")),
            "preparation_instructions": instruction_lines(detail.get("generalInstructions")),
            "mandatory_requirements": clean_text(detail.get("mandatoryRequirements")),
            "test_groups": body_parts,
            "all_tests": [t for group in body_parts for t in group["tests"]],
            "faqs": faqs,
        }
    )
    if not package.get("age_group") and detail.get("ageGroup"):
        package["age_group"] = clean_text(detail.get("ageGroup"))
    return package


# ── crawl steps ──────────────────────────────────────────────────────

def crawl_taxonomies(client: HWClient) -> list[dict]:
    payload = client.taxonomies()
    groups = []
    for group in payload.get("catagory") or []:  # sic — the API spells it this way
        groups.append(
            {
                "group": clean_text(group.get("groupTitle")),
                "group_id": group.get("groupTitleId"),
                "items": [
                    {"title": clean_text(i.get("title")), "item_id": i.get("itemId")}
                    for i in group.get("items") or []
                ],
            }
        )
    return groups


def crawl_categories(client: HWClient) -> tuple[list[dict], dict[str, list[str]]]:
    """Health categories plus a package-id -> category-names index."""
    payload = client.health_categories()
    categories = []
    membership: dict[str, list[str]] = {}

    for category in payload.get("healthCategoryList") or []:
        category_id = category.get("healthCategoryPackageId")
        name = clean_text(category.get("healthCategoryName"))
        try:
            listing = client.packages_in_category(category_id)
        except HWApiError as exc:
            print(f"  ! category '{name}' failed: {exc}", file=sys.stderr)
            continue

        member_ids = []
        for item in listing.get("catalogueResponses") or []:
            pid = item.get("id")
            if not pid:
                continue
            member_ids.append(pid)
            membership.setdefault(pid, []).append(name)

        categories.append(
            {"name": name, "category_id": category_id, "package_ids": member_ids}
        )
        print(f"  category '{name}': {len(member_ids)} packages")

    return categories, membership


def crawl_catalogue(client: HWClient, limit: int | None) -> list[dict]:
    """Page through the whole catalogue."""
    packages: dict[str, dict] = {}
    page = 1
    total = None

    while True:
        payload = client.catalogue_page(page)
        rows = payload.get("catalogueList") or []
        if total is None:
            total = payload.get("totalDataInCatalogues")
            print(f"  catalogue reports {total} items")
        if not rows:
            break

        for row in rows:
            package = normalise_listing(row)
            if package["id"]:
                packages.setdefault(package["id"], package)

        print(f"  page {page}: +{len(rows)} (have {len(packages)})")

        if limit and len(packages) >= limit:
            break
        if total and len(packages) >= total:
            break
        if len(rows) < PAGE_SIZE:
            break
        page += 1

    result = list(packages.values())
    return result[:limit] if limit else result


def crawl_taxonomy_packages(client: HWClient, taxonomies: list[dict]) -> dict[str, list[str]]:
    """Map each condition/habit/symptom to its packages.

    This is what lets the agent answer "I have back pain, which test should I
    take?" — the site's own symptom -> package mapping rather than a guess.
    Annotates `taxonomies` in place and returns package-id -> tag list.
    """
    tags: dict[str, list[str]] = {}
    for group in taxonomies:
        group_label = group["group"]
        for item in group["items"]:
            try:
                payload = client.packages_for_group(item["item_id"])
            except HWApiError as exc:
                print(f"  ! {group_label}/{item['title']} failed: {exc}", file=sys.stderr)
                item["package_ids"] = []
                continue

            ids = [row.get("id") for row in (payload.get("data") or []) if row.get("id")]
            item["package_ids"] = ids
            for pid in ids:
                tags.setdefault(pid, []).append(f"{group_label}: {item['title']}")
        covered = sum(len(i.get("package_ids") or []) for i in group["items"])
        print(f"  {group_label}: {len(group['items'])} items, {covered} package links")
    return tags


def normalise_report_time(packages: list[dict]) -> None:
    """'Within 24 hours' and 'Within 24 Hours' are the same promise."""
    for package in packages:
        raw = (package.get("report_time") or "").strip()
        package["report_time"] = re.sub(r"\s+", " ", raw)
        package["report_time_key"] = package["report_time"].lower()


def crawl_details(client: HWClient, packages: list[dict]) -> int:
    failures = 0
    for index, package in enumerate(packages, start=1):
        try:
            detail = client.package_details(package["id"])
            merge_detail(package, detail)
        except HWApiError as exc:
            failures += 1
            package["detail_error"] = str(exc)
            print(f"  ! detail failed for {package['title']}: {exc}", file=sys.stderr)
        if index % 25 == 0 or index == len(packages):
            print(f"  details {index}/{len(packages)}")
    return failures


# ── entry point ──────────────────────────────────────────────────────

def build(limit: int | None, with_details: bool) -> dict:
    client = HWClient()
    started = datetime.now(timezone.utc)

    print("Taxonomies (conditions / habits / symptoms)...")
    taxonomies = crawl_taxonomies(client)
    print(f"  {len(taxonomies)} groups")

    print("Health categories...")
    categories, membership = crawl_categories(client)

    print("Catalogue...")
    packages = crawl_catalogue(client, limit)
    print(f"  {len(packages)} packages")

    for package in packages:
        package["categories"] = membership.get(package["id"], [])

    print("Taxonomy -> package mapping...")
    tags = crawl_taxonomy_packages(client, taxonomies)
    for package in packages:
        package["taxonomy_tags"] = tags.get(package["id"], [])

    detail_failures = 0
    if with_details:
        print(f"Package details ({len(packages)} calls)...")
        detail_failures = crawl_details(client, packages)

    normalise_report_time(packages)

    priced = [p for p in packages if isinstance(p.get("price"), (int, float))]
    return {
        "generated_at": started.isoformat(),
        "source": "hindustanwellness.com catalogue API",
        "site": SITE_FACTS,
        "taxonomies": taxonomies,
        "categories": categories,
        "packages": packages,
        "stats": {
            "package_count": len(packages),
            "packages_with_details": sum(1 for p in packages if p.get("test_groups")),
            "detail_failures": detail_failures,
            "taxonomy_groups": len(taxonomies),
            "tagged_packages": sum(1 for p in packages if p.get("taxonomy_tags")),
            "category_count": len(categories),
            "requests_made": client.request_count,
            "price_min": min((p["price"] for p in priced), default=None),
            "price_max": max((p["price"] for p in priced), default=None),
            "crawl_seconds": round(
                (datetime.now(timezone.utc) - started).total_seconds(), 1
            ),
        },
    }


def enrich(path: Path) -> dict:
    """Add taxonomy tags to an existing corpus without re-fetching 700 details."""
    with path.open(encoding="utf-8") as f:
        knowledge = json.load(f)

    client = HWClient()
    taxonomies = crawl_taxonomies(client)
    print("Taxonomy -> package mapping...")
    tags = crawl_taxonomy_packages(client, taxonomies)

    packages = knowledge["packages"]
    for package in packages:
        package["taxonomy_tags"] = tags.get(package["id"], [])
    normalise_report_time(packages)

    knowledge["taxonomies"] = taxonomies
    knowledge["stats"]["tagged_packages"] = sum(
        1 for p in packages if p.get("taxonomy_tags")
    )
    knowledge["stats"]["requests_made"] += client.request_count
    knowledge["enriched_at"] = datetime.now(timezone.utc).isoformat()
    return knowledge


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="cap packages (dev)")
    parser.add_argument(
        "--no-details",
        dest="details",
        action="store_false",
        help="skip per-package detail calls",
    )
    parser.add_argument(
        "--enrich",
        action="store_true",
        help="add taxonomy tags to an existing corpus instead of re-crawling",
    )
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args()

    knowledge = enrich(args.out) if args.enrich else build(args.limit, args.details)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        json.dump(knowledge, f, indent=2, ensure_ascii=False)

    stats = knowledge["stats"]
    print(f"\nWrote {args.out} ({args.out.stat().st_size / 1024:.0f} KB)")
    print(
        f"  {stats['package_count']} packages, "
        f"{stats['packages_with_details']} with test breakdown, "
        f"{stats['detail_failures']} detail failures"
    )
    print(
        f"  {stats['requests_made']} requests in {stats['crawl_seconds']}s; "
        f"prices Rs.{stats['price_min']} - Rs.{stats['price_max']}"
    )


if __name__ == "__main__":
    main()
