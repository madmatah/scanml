---
paths:
  - "VERSION"
  - "CHANGELOG.md"
  - "scripts/release.py"
  - "scripts/lib/version.py"
  - "scripts/deploy.sh"
  - "scripts/setup.sh"
  - "scripts/prod.sh"
  - "scripts/build-apk.sh"
  - ".github/workflows/release.yml"
  - "android/app/build.gradle.kts"
---

# Releases

A release is a version of the api and of the app together, published on GitHub, which each installation deploys when it
chooses.

- **`VERSION` is the last release,** `MAJOR.MINOR.PATCH`: the version of an api deployed from it, which `/api/health`
  reports, and of its release app, whose versionCode is major × 10000 + minor × 100 + patch. Minor and patch stay below
  100, so that every release installs over the previous one.
- **Pull requests never change `VERSION`.** Only a release pull request does, `chore(release): X.Y.Z`, whose one commit
  `scripts/release.py --commit` makes: `VERSION`, and the release's section of `CHANGELOG.md`, in the Keep a Changelog
  format.
- **Nothing else is merged while a release pull request is open,** since a feature, a fix or a breaking change merged in
  between is missing from its notes, and the release workflow then publishes nothing.
- **A release is tested before its pull request opens:** CI passes on the commit of `main` it releases, and so do the
  OCR sandbox's unit tests that need an engine's environment, which CI does not have, in the sandbox's image with the
  machine's sandbox, read-only and without network.
- **Tags and GitHub releases come only from `.github/workflows/release.yml`,** once the release pull request is merged.
  No script and no session tags.
- **Production runs published releases only, from a clean checkout:** `scripts/deploy.sh`, `scripts/setup.sh` and the
  release build of `scripts/build-apk.sh` refuse a HEAD that is not the commit of the tag `vVERSION` on `origin`, and
  the `up` of `scripts/prod.sh` a HEAD that is not the commit of the tag `vVERSION` among the checkout's own tags, which
  a deployment checked on `origin`. All of them refuse uncommitted or untracked files, and files marked assume-unchanged
  or skip-worktree, whose changes `git status` hides. The release app's versionCode comes from `VERSION`, so an app
  built from a later commit of `main` would have the same one, and phones would not install it.
- **Development builds are versioned from git,** as a pre-release of the next patch (`scripts/lib/version.py`), and the
  dev app's versionCode is the time of its build, so that each build installs over the previous one.
