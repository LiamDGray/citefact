"""Online metadata cascade resolution for monographs and unindexed citations.

Provides fallback metadata hydration (OpenLibrary + Google Books cascade)
when a citation cannot be resolved against the local catalog.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Any, Callable, Iterable

from .base import Citation
from .matcher import _first_author_surname, _citation_surname, _year_matches


def _default_fetcher(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "CiteFact/0.2.0 (citation-resolution; https://github.com/LiamDGray/citefact)"},
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _format_author_name(name: str) -> str:
    """Format 'Firstname [Middle] Lastname' into 'Lastname, Firstname' for catalog indexing."""
    name = name.strip()
    if "," in name:
        return name
    parts = name.split()
    if len(parts) > 1:
        return f"{parts[-1]}, {' '.join(parts[:-1])}"
    return name


def _format_authors(authors: list[str] | str) -> str:
    if isinstance(authors, str):
        if "," in authors:
            return authors
        return _format_author_name(authors)
    return ", ".join(_format_author_name(a) for a in authors if a)


def openlibrary_search(
    author: str,
    year: int | str | None = None,
    title: str | None = None,
    *,
    fetcher: Callable[[str], dict] | None = None,
) -> dict[str, Any] | None:
    """Query OpenLibrary search API for matching books."""
    fetch = fetcher or _default_fetcher
    query_parts = []
    if author:
        query_parts.append(f"author={urllib.parse.quote_plus(str(author))}")
    if title:
        query_parts.append(f"title={urllib.parse.quote_plus(str(title))}")
    if not query_parts:
        return None

    url = f"https://openlibrary.org/search.json?{'&'.join(query_parts)}&limit=5"
    try:
        data = fetch(url)
    except Exception:
        return None

    docs = data.get("docs") or []
    if not docs:
        return None

    # Filter by year if supplied
    for doc in docs:
        doc_year = doc.get("first_publish_year")
        if year is not None and doc_year is not None:
            if not _year_matches(year, doc_year):
                continue
        author_names = doc.get("author_name") or []
        author_str = _format_authors(author_names) if author_names else _format_author_name(author)
        return {
            "id": doc.get("key", "").replace("/works/", "ol_"),
            "title": doc.get("title", ""),
            "authors": author_str,
            "year": int(doc_year) if doc_year else year,
            "source": "openlibrary",
        }

    # If year didn't match exactly, accept the top hit
    top = docs[0]
    top_year = top.get("first_publish_year") or year
    author_names = top.get("author_name") or []
    return {
        "id": top.get("key", "").replace("/works/", "ol_"),
        "title": top.get("title", ""),
        "authors": _format_authors(author_names) if author_names else _format_author_name(author),
        "year": int(top_year) if top_year else year,
        "source": "openlibrary",
    }


def google_books_search(
    author: str,
    year: int | str | None = None,
    title: str | None = None,
    *,
    fetcher: Callable[[str], dict] | None = None,
) -> dict[str, Any] | None:
    """Query Google Books Volumes API for matching books."""
    fetch = fetcher or _default_fetcher
    q_terms = []
    if author:
        q_terms.append(f"inauthor:{author}")
    if title:
        q_terms.append(f"intitle:{title}")
    if not q_terms:
        return None

    query = urllib.parse.quote_plus(" ".join(q_terms))
    url = f"https://www.googleapis.com/books/v1/volumes?q={query}&maxResults=5"
    try:
        data = fetch(url)
    except Exception:
        return None

    items = data.get("items") or []
    if not items:
        return None

    for item in items:
        info = item.get("volumeInfo") or {}
        pub_date = str(info.get("publishedDate") or "")
        match_year = re.search(r"\b(19|20)\d{2}\b", pub_date)
        item_year = int(match_year.group(0)) if match_year else None

        if year is not None and item_year is not None:
            if not _year_matches(year, item_year):
                continue

        authors = info.get("authors") or []
        return {
            "id": item.get("id", f"gb_{item_year}"),
            "title": info.get("title", ""),
            "authors": _format_authors(authors) if authors else _format_author_name(author),
            "year": item_year or year,
            "source": "google_books",
        }

    top = items[0]
    info = top.get("volumeInfo") or {}
    pub_date = str(info.get("publishedDate") or "")
    match_year = re.search(r"\b(19|20)\d{2}\b", pub_date)
    item_year = int(match_year.group(0)) if match_year else year
    authors = info.get("authors") or []
    return {
        "id": top.get("id", f"gb_{item_year}"),
        "title": info.get("title", ""),
        "authors": _format_authors(authors) if authors else _format_author_name(author),
        "year": item_year or year,
        "source": "google_books",
    }


def resolve_cascade(
    author: str,
    year: int | str | None = None,
    title: str | None = None,
    *,
    fetcher: Callable[[str], dict] | None = None,
) -> dict[str, Any] | None:
    """Cascade resolution: OpenLibrary -> Google Books."""
    res = openlibrary_search(author, year, title, fetcher=fetcher)
    if res is not None:
        return res
    return google_books_search(author, year, title, fetcher=fetcher)


def hydrate_catalog_for_citations(
    citations: Iterable[Citation],
    catalog: dict[str, dict[str, Any]],
    *,
    resolver: Callable[..., dict[str, Any] | None] | None = None,
) -> dict[str, dict[str, Any]]:
    """Enrich catalog by querying external monograph APIs for unmatched citations."""
    resolve_fn = resolver or resolve_cascade
    updated = dict(catalog)

    for cite in citations:
        surname = _citation_surname(cite.author_string)
        if not surname:
            continue

        # Check if already in catalog
        already_matched = False
        for paper in updated.values():
            cand_surname = _first_author_surname(paper.get("authors", ""))
            if cand_surname and cand_surname.lower() == surname.lower():
                if _year_matches(cite.year, paper.get("year")):
                    already_matched = True
                    break

        if not already_matched:
            resolved = resolve_fn(cite.author_string, cite.year)
            if resolved:
                updated[resolved["id"]] = {
                    "title": resolved["title"],
                    "authors": resolved["authors"],
                    "year": resolved["year"],
                    "_source": resolved.get("source", "online"),
                }

    return updated
