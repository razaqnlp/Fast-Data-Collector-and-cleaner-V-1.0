# Changelog

## [1.1.0] - 2026-09-22

Version 1.1.0 is a backward-compatible update to the original v1.0 release.

### Added

- Structured YouTube CSV metadata: `id`, `video_id`, `original_text`, and `collection_date`
- Excel-compatible comma-separated output
- Duplicate video ID detection with an inline warning
- Intentional duplicate re-scraping through **I know - scrape again**
- Persistent auto-download for newly scraped CSV files
- Optional custom CSV filenames with collision protection
- Collection loading state and spinner

### Improved

- Generated YouTube CSV files can be imported using `original_text`
- Duplicate detection supports legacy, numbered, and custom-named CSV files
- Repository cleanup removes local environments, sessions, caches, logs, model binaries, and obsolete UI copies
- Documentation and ignore rules now match the active project structure

### Validation

- Python compilation passes
- Existing test suite passes: 3 tests