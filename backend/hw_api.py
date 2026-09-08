"""Thin client for the public Hindustan Wellness catalogue APIs.

The website (hindustanwellness.com) is an Angular SPA that renders nothing
server-side, so HTML scraping returns an empty <app-root>. These are the same
unauthenticated JSON endpoints the public site calls to draw its own catalogue
pages; endpoint names and payload shapes were read out of the site bundle
(main.*.js).

Only catalogue//reference data is read here. Account, booking, prescription,
wishlist and payment endpoints exist on the same hosts and are deliberately
NOT touched — they carry customer PII.
"""

from __future__ import annotations

import time
from typing import Any

import requests

CATALOGUE_URL = "https://search-filter.stetho.hindustanlab.com/"
SERVICE_URL = "https://web-api.stetho.hindustanlab.com/"
HOME_SERVICES_URL = "https://home-services.stetho.hindustanlab.com/"

USER_AGENT = "HindustanWellnessKB/1.0 (prototype knowledge-base build)"

# Be a good citizen: the site is the customer's own, but pace the crawl anyway.
REQUEST_DELAY_SECONDS = 0.25
TIMEOUT_SECONDS = 30
MAX_RETRIES = 3


class HWApiError(RuntimeError):
    """A catalogue endpoint failed after retries."""


class HWClient:
    def __init__(self, *, delay: float = REQUEST_DELAY_SECONDS) -> None:
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update(
            {"Content-Type": "application/json", "User-Agent": USER_AGENT}
        )
        self.request_count = 0

    def _post(self, url: str, payload: Any | None) -> dict:
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.post(url, json=payload, timeout=TIMEOUT_SECONDS)
                resp.raise_for_status()
                self.request_count += 1
                time.sleep(self.delay)
                return resp.json()
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                time.sleep(1.5 * (attempt + 1))
        raise HWApiError(f"{url} failed after {MAX_RETRIES} attempts: {last_error}")

    # ── catalogue endpoints ──────────────────────────────────────────

    def taxonomies(self) -> dict:
        """Tests grouped by Condition / Habit / Symptom (drives the site's nav)."""
        return self._post(f"{CATALOGUE_URL}sectionWebDetails", None)

    def health_categories(self) -> dict:
        """Top-level package categories (Popular, Diabetes, Thyroid, ...)."""
        return self._post(f"{CATALOGUE_URL}getHealthCategoryPackage", None)

    def packages_in_category(self, health_category_id: str) -> dict:
        return self._post(
            f"{CATALOGUE_URL}getHealthCatalogueData",
            {"healthCategoryPackageId": health_category_id},
        )

    def catalogue_page(self, page_no: int, catalogue_type: str = "all") -> dict:
        """One page of the full catalogue (20 items per page)."""
        return self._post(
            f"{CATALOGUE_URL}getSortingOrderData"
            f"?pageNo={page_no}&catalogueType={catalogue_type}",
            None,
        )

    def package_details(self, catalogue_id: str) -> dict:
        """Full detail: prep instructions, fasting, test breakdown, FAQs."""
        return self._post(
            f"{CATALOGUE_URL}getAllCatalogueDetails", {"catalogueId": catalogue_id}
        )

    def packages_for_group(self, group_id: str) -> dict:
        """Packages tagged to a condition/habit/symptom item id."""
        return self._post(f"{CATALOGUE_URL}getPackageTests", {"groupId": group_id})
