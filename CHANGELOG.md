# Changelog

The notable changes of each release of ScanMyLib. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). A release's section is drafted from its commits by
`scripts/release.py` and edited in its release pull request: nothing is written under [Unreleased] in between.

## [Unreleased]

## [0.4.0] - 2026-10-19

### Added

- Scripts: describe the release pull request with its notes
- Skills: publish the screenshots of a visible change
- App: its own colors, "Paper & Ink", in a light and a dark theme, with medium- and high-contrast variants that follow
  the phone's contrast setting (Android 14 and later)
- App: Settings › Appearance: the theme (same as the phone, light or dark) and the wallpaper's colors (Android 12 and
  later)

### Fixed

- Scripts: keep the tests' git away from the repository of their caller
- Scripts: refuse to install production over changes git status hides
- Scripts: refuse release notes with an entry before any subsection
- OCR: report no versions when the sandbox manifest is not a json object

### Security

- Server: the api's image installs its Python packages from wheels only, so that no build step runs code the lock does
  not check

## [0.3.0] - 2026-10-17

### Added

- App: scan straight from the default camera, or import photos, in one tap
- App: import photos shared from another app
- App: scan from the library card
- App: create a document and scan or import it in one step
- App: share the crash report, and keep it until it is deleted
- App: check for updates and install them from the app, from the APK the PC publishes with `scripts/deploy.sh --apk`
  (`/api/health` says which). Phones install 0.3.0 itself once by hand, from the Pairing tab of the web UI
- Releases published on GitHub, with their notes from this changelog

### Changed

- **Breaking:** Scripts: deploy only published releases. Fetch and check out a release (`git fetch --tags origin`, then
  `git checkout vX.Y.Z`) before `scripts/deploy.sh`, which no longer tags, and refuses a release older than the running
  one unless `--allow-downgrade`. `scripts/setup.sh` and `scripts/prod.sh compose up` need a release too
- Development builds are versioned from git (`0.3.1-dev.N+g…`), and each build of the dev app installs over the
  previous one

### Fixed

- App: delete only the photos of the camera's own visit
- App: clearer feedback in the camera and after an import
- App: one vocabulary in English and French

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

[unreleased]: https://github.com/madmatah/scanml/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/madmatah/scanml/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/madmatah/scanml/compare/v0.2.3...v0.3.0
[0.2.3]: https://github.com/madmatah/scanml/tree/v0.2.3
