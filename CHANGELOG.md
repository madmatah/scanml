# Changelog

The notable changes of each release of ScanMyLib. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). A release's section is drafted from its commits by
`scripts/release.py` and edited in its release pull request: nothing is written under [Unreleased] in between.

## [Unreleased]

## [0.7.0] - 2026-10-25

### Added

- App: give each page to send a number of its own
- App: suggest a number for a page to send
- App: reach a page's actions from its menu in the review
- App: delete the pages to send from the review's menu
- Web UI: show the app's mark as the web UI's icon
- Web UI: draw the mark in the page in the theme's accent
- OCR: check that the engine's environment imports its libraries
- Scripts: check the engine's environment at the first installation

### Changed

- **Breaking:** Scripts: deploy a published release without testing it again. `scripts/deploy.sh` no longer accepts
  `--skip-tests` and stops with its usage: drop the option from the command. A release is tested before it is
  published, and the deploy checks the installation instead: the api's health and version, the sandbox's isolation, and
  the engine's environment in the new `ocr` container. The `scanmylib-api:test` image that earlier deploys built is no
  longer used: `docker rmi scanmylib-api:test` removes it.

### Fixed

- Scripts: stop a sandbox that fails isolation at the first installation
- OCR: escape the sandbox's output in the ocr container's log

## [0.6.0] - 2026-10-24

### Added

- App: the pages to send get a screen of their own, which never blocks their document: large thumbnails, the first
  page number, Add pages, Delete these pages and Send; the document shows a banner with "Review" instead of opening
  a dialog by itself
- App: copying scanned pages or imported photos goes on when you leave the screen; pages from the scanner join at
  once, even while photos are being imported
- App: a removed page can be put back for 10 seconds
- App: look at a page to send full screen, with zoom up to 2.5×

### Fixed

- Web UI and app: the same words for the same things on both, in English and in French: page states, pages not
  scanned yet, curved-page flattening, kinds, pairing and the access token; "OCR" stays only in the engine's badge

## [0.5.0] - 2026-10-22

### Added

- App: its own mark, an open book in scan corners, as its launcher icon and on the empty library; the dev app's icon
  is cream on orange, with a "dev" tag in its themed icon (Android 13 and later)
- App: banners for what needs the user, in ocher or red, each with one action: try the PC again, open the settings,
  or send the document again
- App: page states as badges that grow with the text, and pages shown as paper with their number, so that no state is
  cut at a larger text size
- App: icons for the PC, the phone and uploads in place of clouds, since nothing goes to a cloud
- App: TalkBack names every switch, and jumps between the headings of the settings, the library and the document
- App: the document's summary in the same colors as the library's cards, whatever the theme

### Security

- App: text from the PC shows on one line, without the characters a reader cannot see, and cut to a set length, so
  that a long or garbled title cannot fill a screen or hide what it shows

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

[unreleased]: https://github.com/madmatah/scanml/compare/v0.7.0...HEAD
[0.7.0]: https://github.com/madmatah/scanml/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/madmatah/scanml/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/madmatah/scanml/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/madmatah/scanml/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/madmatah/scanml/compare/v0.2.3...v0.3.0
[0.2.3]: https://github.com/madmatah/scanml/tree/v0.2.3
