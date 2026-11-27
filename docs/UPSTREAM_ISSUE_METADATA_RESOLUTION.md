# Issue Proposal: Automated Metadata Resolution Fallback (OpenLibrary & Google Books) for Unindexed Books

## Context & Motivation

CiteFact provides excellent deterministic verbatim quote matching and claim extraction against user-provided PDFs. However, citation matching (`citations.matcher.resolve_to_catalog`) requires a pre-existing, curated `.bib` bibliography file.

When users verify manuscripts that cite classic academic monographs, book chapters, or publications without a pre-curated BibTeX catalog (e.g. `(Arendt, 1951)`, `(Foucault, 1977)`, `(Hayek, 1944)`), `resolve_to_catalog()` fails to match the citations to any catalog entry (0% match rate without manual bibliography entry authoring).

## Empirical Benchmark

Tested across a benchmark suite of 10 classic monographs cited without pre-compiled BibTeX entries:
- **Baseline (Without Hydration)**: 0 / 10 (0.0%) citations resolved.
- **With Automated Metadata Cascade (OpenLibrary + Google Books)**: 10 / 10 (100.0%) citations resolved and matched to the catalog with confidence >= 0.80.

## Proposed Solution

1. Add `citefact.citations.resolve`:
   - `openlibrary_search(author, year, title)` querying OpenLibrary's free Search API (`https://openlibrary.org/search.json`).
   - `google_books_search(author, year, title)` querying Google Books Volumes API as secondary fallback.
   - `resolve_cascade(author, year, title)` composing the two providers.
   - `hydrate_catalog_for_citations(citations, catalog)` enriching the local catalog before citation resolution.
2. In `citefact.citations.matcher`:
   - Automatically hydrate catalog entries for unmatched citations when requested or as an opt-in CLI flag `--hydrate-missing`.

## References

- Implementation: `citefact/citations/resolve.py`
- Benchmark: `benchmarks/bench_monograph_resolution.py`
- Unit tests: `tests/test_monograph_resolution_fallback.py`
