#!/usr/bin/env bash
# Vendors KaTeX (MIT) into the web UI, used to display LaTeX formulas in previews.
#
# The npm tarball is checked against the SHA-512 integrity published by the npm
# registry (pinned below), and only the browser files are extracted: the minified
# script and stylesheet, the WOFF2 fonts and the license. No CDN is ever used:
# the PC serves these files itself.
#
# Usage: scripts/vendor-katex.sh
set -euo pipefail

VERSION=0.19.0
TARBALL_URL="https://registry.npmjs.org/katex/-/katex-${VERSION}.tgz"
INTEGRITY="sha512-v6Tznz3zJ7u3niRCoDTsumM2+HA2XXcCu+WAacCeHD2z3p9A9Ks987o5FzfTGBN0e8A0vjEgIDvLbICrXpdw/Q=="

cd "$(dirname "$0")/.."
DEST=server/scanmylib/web/static/vendor/katex
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

curl -fsSL "$TARBALL_URL" -o "$WORK/katex.tgz"
actual="sha512-$(openssl dgst -sha512 -binary "$WORK/katex.tgz" | base64 -w0)"
if [[ "$actual" != "$INTEGRITY" ]]; then
  echo "KaTeX tarball integrity mismatch: $actual" >&2
  exit 1
fi

mkdir "$WORK/x"
tar -xzf "$WORK/katex.tgz" -C "$WORK/x" --no-same-owner --no-same-permissions \
  package/LICENSE package/dist/katex.min.js package/dist/katex.min.css \
  --wildcards 'package/dist/fonts/*.woff2'

rm -rf "$DEST"
mkdir -p "$DEST/fonts"
cp "$WORK/x/package/LICENSE" "$WORK/x/package/dist/katex.min.js" "$WORK/x/package/dist/katex.min.css" "$DEST/"
cp "$WORK/x/package/dist/fonts/"*.woff2 "$DEST/fonts/"
echo "KaTeX ${VERSION} (${INTEGRITY})" > "$DEST/VERSION"
echo "KaTeX ${VERSION} vendored into $DEST ($(du -sh "$DEST" | cut -f1))"
