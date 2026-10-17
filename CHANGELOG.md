# Changelog

The notable changes of each release of ScanMyLib. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). A release's section is drafted from its commits by
`scripts/release.py` and edited in its release pull request: nothing is written under [Unreleased] in between.

## [Unreleased]

## [0.2.3] - 2026-10-15

### Added

- Scan books with a phone and OCR them in a network-less sandbox
- Give the api and the app a single version from `VERSION`
- Server: keep the fake OCR off live sockets and out of production
- Scripts: name each Docker stack from `.env` and isolate it
- Scripts: add a development stack and app for worktrees
- Scripts: deploy production only through guarded scripts
- Scripts: write the PC's time zone into `.env` at installation
- Run the test suites on GitHub Actions
- License the project under MIT

### Fixed

- OCR: read the whole request body before refusing a request

[unreleased]: https://github.com/madmatah/scanml/compare/v0.2.3...HEAD
[0.2.3]: https://github.com/madmatah/scanml/tree/v0.2.3
