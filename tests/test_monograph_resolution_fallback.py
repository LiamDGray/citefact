"""Unit tests for automated monograph metadata cascade resolution."""

import pytest
from citefact.citations.base import Citation
from citefact.citations.matcher import resolve_to_catalog
from citefact.citations.resolve import (
    openlibrary_search,
    google_books_search,
    resolve_cascade,
    hydrate_catalog_for_citations,
)


def test_openlibrary_search_parser():
    mock_payload = {
        "docs": [
            {
                "title": "The Origins of Totalitarianism",
                "author_name": ["Hannah Arendt"],
                "first_publish_year": 1951,
                "key": "/works/OL12345W",
            }
        ]
    }
    res = openlibrary_search("Hannah Arendt", 1951, fetcher=lambda url: mock_payload)
    assert res is not None
    assert res["title"] == "The Origins of Totalitarianism"
    assert res["authors"] == "Arendt, Hannah"
    assert res["year"] == 1951
    assert res["source"] == "openlibrary"


def test_google_books_search_parser():
    mock_payload = {
        "items": [
            {
                "id": "gb_arendt_1951",
                "volumeInfo": {
                    "title": "The Origins of Totalitarianism",
                    "authors": ["Hannah Arendt"],
                    "publishedDate": "1951-03-15",
                },
            }
        ]
    }
    res = google_books_search("Hannah Arendt", 1951, fetcher=lambda url: mock_payload)
    assert res is not None
    assert res["title"] == "The Origins of Totalitarianism"
    assert res["authors"] == "Arendt, Hannah"
    assert res["year"] == 1951
    assert res["source"] == "google_books"


def test_resolve_cascade_fallback_to_google_books():
    # OpenLibrary returns empty, Google Books succeeds
    def mock_fetcher(url: str):
        if "openlibrary.org" in url:
            return {"docs": []}
        return {
            "items": [
                {
                    "id": "gb_eyal_2019",
                    "volumeInfo": {
                        "title": "The Crisis of Expertise",
                        "authors": ["Gil Eyal"],
                        "publishedDate": "2019-10-01",
                    },
                }
            ]
        }

    res = resolve_cascade("Gil Eyal", 2019, fetcher=mock_fetcher)
    assert res is not None
    assert res["title"] == "The Crisis of Expertise"
    assert res["authors"] == "Eyal, Gil"
    assert res["source"] == "google_books"


def test_resolve_to_catalog_with_auto_hydration():
    catalog = {}  # Empty local catalog
    citations = [
        Citation(raw="(Arendt, 1951)", author_string="Arendt", year=1951, start=0, end=14),
    ]

    def mock_cascade(author, year, title=None):
        if "Arendt" in author and year == 1951:
            return {
                "id": "ol_arendt_1951",
                "title": "The Origins of Totalitarianism",
                "authors": "Arendt, Hannah",
                "year": 1951,
                "source": "openlibrary",
            }
        return None

    # Before hydration: unmatched
    matched = resolve_to_catalog(citations, catalog)
    assert matched[0].paper_id is None

    # Hydrate catalog
    hydrated_catalog = hydrate_catalog_for_citations(citations, catalog, resolver=mock_cascade)
    assert "ol_arendt_1951" in hydrated_catalog

    # After hydration: matched
    matched_hydrated = resolve_to_catalog(citations, hydrated_catalog)
    assert matched_hydrated[0].paper_id == "ol_arendt_1951"
    assert matched_hydrated[0].confidence >= 0.8
