#!/usr/bin/env bash
#
# Builds the ScanMyLib Android app in throwaway containers: nothing is installed on the host.
#
# Usage: scripts/build-apk.sh [--create-signing-key] [gradle arguments...]
#        (default gradle arguments: test assemble<Variant> lint)
#
# Settings come from the checkout's .env, in the strict format of scripts/lib/stack.py; when a
# .env exists, the environment is ignored:
#   APP_VARIANT   release: the production app, fr.scanmylib, built only in production's checkout
#                 (scripts/lib/stack.py: the project directory of production's containers), with
#                 production's .env (COMPOSE_PROJECT_NAME=scanmylib), on a clean main equal to
#                 main on origin (git ls-remote), without assume-unchanged or skip-worktree files:
#                 normally by scripts/deploy.sh --apk
#                 dev: the development app, fr.scanmylib.dev, "ScanMyLib (dev)", the only one a
#                 worktree builds, once its .env passes the isolation check of scripts/dev.sh
#                 (default: release with production's .env, else dev)
#   DATA_DIR      the APK is published as $DATA_DIR/app/scanmylib.apk
#   ANDROID_DIR   Android SDK, Gradle caches and Android home (default: $DATA_DIR/android); the
#                 development stack has its own (scripts/dev-env.sh), so that its builds never
#                 write to the toolchain that builds and signs the production app
#   ANDROID_KEYSTORE_DIR  the signing key (default: $ANDROID_DIR/keystore); the development stack
#                 uses production's, which only the signing container mounts, read-only
# Without .env, only in CI (CI=true or GITHUB_ACTIONS=true), the environment gives DATA_DIR
# (ANDROID_DIR and APP_VARIANT optional), which must share nothing with production's paths and
# stay outside your home directory (on GitHub Actions, GITHUB_ACTIONS=true, inside RUNNER_TEMP
# is allowed: the runner keeps it in its home directory), and the app is built and checked but
# never signed nor published:
#   CI=true DATA_DIR=... scripts/build-apk.sh test lint
# The version is the repository's VERSION file (see android/app/build.gradle.kts).
#
# --create-signing-key creates the release key in ANDROID_KEYSTORE_DIR if there is none yet
# (scripts/setup.sh, first installation of production); otherwise a missing key is an error.
#
# One build at a time per ANDROID_DIR (a lock on that directory). The containers are named
# <prefix>-build-<pid>, <prefix>-key-<pid> and <prefix>-sign-<pid>, with the prefix
# "scanmylib-android" unless SCANMYLIB_CONTAINER_PREFIX says otherwise.
#
# Gradle checks every dependency against android/gradle/verification-metadata.xml (SHA-256),
# including metadata files (POM, .module), but those only when it downloads them: a Gradle home
# that already holds them hides missing entries, which then break the next build with an empty
# home (CI, a new ANDROID_DIR). After changing dependencies, record the new checksums in a
# worktree whose .env points ANDROID_DIR to a new directory (the "app:" task paths keep the
# script from signing anything):
#   scripts/build-apk.sh --write-verification-metadata sha256 test app:assembleDev app:assembleRelease lint
# then check every added checksum (Maven Central and Google Maven publish a .sha1 per file)
# before committing.
#
# 1. Build: the official eclipse-temurin:21-jdk image runs Gradle as your uid, with network
#    access (SDK, Gradle and Maven downloads) and only these bind mounts:
#      android/                      -> /workspace          sources; the Gradle wrapper is generated here once
#      VERSION                       -> /VERSION            read-only: the version of the app
#      $ANDROID_DIR/sdk              -> /opt/android-sdk    Android SDK (command-line tools, platform, build-tools)
#      $ANDROID_DIR/gradle           -> /gradle             GRADLE_USER_HOME (distribution, dependency caches)
#      $ANDROID_DIR/user-home        -> /android-user-home  ANDROID_USER_HOME, i.e. what would be ~/.android
#    Gradle produces an unsigned APK of the variant and never sees the signing key.
# 2. Sign (when the APK was assembled, with a .env): the same image, without any network, with
#    the key directory mounted read-only. It copies zipalign, apksigner.jar and their libc++ from
#    build-tools to its own tmpfs, checks the copies against the SHA-256 sums pinned below, and
#    only runs these: whatever a build (which writes to the SDK) left there never runs next to the
#    key. Before signing, it reads the package name and versionCode of the unsigned APK (with the
#    checked apksigner.jar's own manifest parser) and refuses anything but the variant's app,
#    fr.scanmylib.dev (dev) or fr.scanmylib (release), with the versionCode of VERSION: a change
#    that drops the ".dev" suffix never gets the production app signed in a worktree. It signs
#    the APK and publishes it as $DATA_DIR/app/scanmylib.apk. Both variants are signed with the
#    same key. With --create-signing-key and no key yet, a first container without network
#    creates it (read-write mount, the only one).
#
# Downloads are verified: the Android command-line tools against the SHA-1 and size published in
# Google's SDK repository XML, the Gradle distribution and wrapper jar against the SHA-256 sums
# published on services.gradle.org, SDK packages by the Android CLI itself. The Android CLI (the
# replacement of the deprecated sdkmanager) is always run with --no-metrics: it would otherwise
# send usage data to Google.

set -euo pipefail

readonly BUILDER_IMAGE=eclipse-temurin:21-jdk
readonly GRADLE_VERSION=9.8.1
readonly SDK_REPOSITORY_URL=https://dl.google.com/android/repository/repository2-4.xml
# The platform matching compileSdk, and the default build-tools of AGP 9.4 (Android CLI paths).
readonly BUILD_TOOLS_VERSION=36.0.0
readonly SDK_PACKAGES="platforms/android-37.0 build-tools/$BUILD_TOOLS_VERSION"
# Release key, in ANDROID_KEYSTORE_DIR ($ANDROID_DIR/keystore by default).
readonly KEYSTORE_FILE=scanmylib-release.p12
readonly KEY_PASSWORD_FILE=password
# The application id of the release app (android/app/build.gradle.kts); the dev app adds ".dev".
readonly APPLICATION_ID=fr.scanmylib
# SHA-256 of the files of build-tools $BUILD_TOOLS_VERSION that the signing container runs, as the
# Android CLI installs them from Google's repository (checksum-verified download). After changing
# BUILD_TOOLS_VERSION, record them from a fresh SDK: a new ANDROID_DIR, "scripts/build-apk.sh
# help", then sha256sum of these files under $ANDROID_DIR/sdk/build-tools/<version>/.
readonly SIGNING_TOOLS_SHA256="\
c5f559e946de5a9e7d58792181db20383b228877812136bc469d97ae00a43b0a  zipalign
3716d9311e55d2b0918a2fd9d54ba9e406c5f6abeea700b287f11259bc163dec  lib/apksigner.jar
96a19cd2154a4423a61f8444e5d3148a608fa3033bc1a22285d19855a950d05a  lib64/libc++.so"

# --- Build container steps (serialized into the container with `declare -f`) -----------------

build_main() {
    set -euo pipefail
    # HOME is on the tmpfs; only ~/.android persists (AGP and the Android CLI keep state there).
    mkdir -p "$HOME"
    ln -sfn "$ANDROID_USER_HOME" "$HOME/.android"
    install_command_line_tools
    install_sdk_packages
    ensure_gradle_wrapper
    verify_gradle_wrapper
    log "Running ./gradlew $*"
    ./gradlew --no-daemon --console=plain "$@"
}

log() { printf '\n>> %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

# Prints "<file name> <sha1> <size>" of the Linux archive of an SDK package, read from Google's
# repository XML with the JDK's own XML parser (the image has no Python or xmllint).
sdk_archive_info() {
    local repository_xml=$1 package=$2 tool=/tmp/SdkArchive.java
    cat > "$tool" <<'JAVA'
import java.io.File;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.xpath.XPath;
import javax.xml.xpath.XPathConstants;
import javax.xml.xpath.XPathFactory;
import org.w3c.dom.Node;

public class SdkArchive {
    public static void main(String[] args) throws Exception {
        var factory = DocumentBuilderFactory.newInstance();
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        var repository = factory.newDocumentBuilder().parse(new File(args[0]));
        XPath xpath = XPathFactory.newInstance().newXPath();
        var archive = (Node) xpath.evaluate(
                "//remotePackage[@path='" + args[1] + "']/archives/archive[host-os='linux']/complete",
                repository, XPathConstants.NODE);
        if (archive == null) {
            System.err.println("no Linux archive for " + args[1]);
            System.exit(1);
        }
        System.out.println(String.join(" ",
                xpath.evaluate("url", archive),
                xpath.evaluate("checksum[@type='sha1']", archive),
                xpath.evaluate("size", archive)));
    }
}
JAVA
    java "$tool" "$repository_xml" "$package"
}

install_command_line_tools() {
    [[ -x $ANDROID_HOME/cmdline-tools/latest/bin/android ]] && return
    log "Installing the Android command-line tools"
    local work=/tmp/cmdline-tools name sha1 size
    mkdir -p "$work"
    curl -fsSL --proto '=https' -o "$work/repository.xml" "$SDK_REPOSITORY_URL"
    read -r name sha1 size < <(sdk_archive_info "$work/repository.xml" 'cmdline-tools;latest')
    [[ $name =~ ^[A-Za-z0-9._-]+\.zip$ && $sha1 =~ ^[0-9a-f]{40}$ && $size =~ ^[0-9]+$ ]] \
        || die "unexpected repository entry for cmdline-tools: '$name' '$sha1' '$size'"
    curl -fsSL --proto '=https' -o "$work/$name" "https://dl.google.com/android/repository/$name"
    [[ $(stat -c %s "$work/$name") == "$size" ]] || die "$name: size differs from the repository XML"
    echo "$sha1  $work/$name" | sha1sum --check --strict --quiet - || die "$name: SHA-1 mismatch"
    echo "$name: size and SHA-1 match Google's repository XML"
    (cd "$work" && jar xf "$name")  # the image has no unzip; jar drops the exec bits
    chmod +x "$work"/cmdline-tools/bin/*
    mkdir -p "$ANDROID_HOME/cmdline-tools"
    rm -rf "$ANDROID_HOME/cmdline-tools/latest"
    mv "$work/cmdline-tools" "$ANDROID_HOME/cmdline-tools/latest"
    rm -rf "$work"
}

# Installs the missing SDK packages with the Android CLI, which accepts the SDK license
# (https://developer.android.com/studio/terms) and verifies each download's checksum.
install_sdk_packages() {
    local package packages missing=()
    read -ra packages <<< "$SDK_PACKAGES"
    for package in "${packages[@]}"; do
        [[ -f $ANDROID_HOME/$package/package.xml ]] || missing+=("$package")
    done
    ((${#missing[@]})) || return 0
    log "Installing SDK packages: ${missing[*]}"
    "$ANDROID_HOME/cmdline-tools/latest/bin/android" --no-metrics --sdk="$ANDROID_HOME" \
        sdk install "${missing[@]}"
}

ensure_gradle_wrapper() {
    local properties=gradle/wrapper/gradle-wrapper.properties
    if [[ -x gradlew ]] && grep -qF "/gradle-$GRADLE_VERSION-bin.zip" "$properties" 2> /dev/null; then
        return
    fi
    log "Generating the Gradle $GRADLE_VERSION wrapper"
    local work=/tmp/gradle-bootstrap dist=gradle-$GRADLE_VERSION-bin.zip sha256
    mkdir -p "$work/empty-project"
    sha256=$(curl -fsSL --proto '=https' "https://services.gradle.org/distributions/$dist.sha256")
    [[ $sha256 =~ ^[0-9a-f]{64}$ ]] || die "unexpected checksum for $dist: '$sha256'"
    curl -fsSL --proto '=https' -o "$work/$dist" "https://services.gradle.org/distributions/$dist"
    echo "$sha256  $work/$dist" | sha256sum --check --strict --quiet - || die "$dist: SHA-256 mismatch"
    echo "$dist: SHA-256 matches services.gradle.org"
    (cd "$work" && jar xf "$dist")
    # Generate the wrapper in an empty project so that the bootstrap Gradle never configures the
    # real build; the wrapper pins the distribution checksum for every later download.
    touch "$work/empty-project/settings.gradle.kts"
    sh "$work/gradle-$GRADLE_VERSION/bin/gradle" --no-daemon --quiet --project-dir "$work/empty-project" \
        wrapper --gradle-version "$GRADLE_VERSION" --distribution-type bin \
        --gradle-distribution-sha256-sum "$sha256"
    mkdir -p gradle/wrapper
    cp "$work/empty-project/gradlew" "$work/empty-project/gradlew.bat" .
    cp "$work/empty-project/gradle/wrapper/gradle-wrapper.jar" \
        "$work/empty-project/$properties" gradle/wrapper/
    rm -rf "$work"
}

# Checks the committed wrapper on every build: the jar must be the official one for the pinned
# version, and the distribution must be pinned by checksum.
verify_gradle_wrapper() {
    local properties=gradle/wrapper/gradle-wrapper.properties version expected
    grep -q '^distributionSha256Sum=[0-9a-f]\{64\}$' "$properties" \
        || die "$properties does not pin the distribution checksum"
    version=$(sed -n 's#^distributionUrl=.*/gradle-\(.*\)-bin\.zip$#\1#p' "$properties")
    [[ -n $version ]] || die "cannot read the Gradle version from $properties"
    expected=$(curl -fsSL --proto '=https' \
        "https://services.gradle.org/distributions/gradle-$version-wrapper.jar.sha256")
    [[ $expected =~ ^[0-9a-f]{64}$ ]] || die "unexpected wrapper checksum: '$expected'"
    echo "$expected  gradle/wrapper/gradle-wrapper.jar" | sha256sum --check --strict --quiet - \
        || die "gradle-wrapper.jar is not the official Gradle $version wrapper"
    echo "gradle-wrapper.jar is the official Gradle $version wrapper"
}

# --- Signing container steps (no network) -----------------------------------------------------

sign_main() {
    set -euo pipefail
    local keystore=/keystore/$KEYSTORE_FILE password_file=/keystore/$KEY_PASSWORD_FILE tools=/tmp/signing-tools
    # Copies of the signing tools, checked: the SDK directory is written by builds, with network.
    mkdir -p "$tools/lib" "$tools/lib64"
    cp /build-tools/zipalign "$tools/zipalign"
    cp /build-tools/lib/apksigner.jar "$tools/lib/apksigner.jar"
    cp /build-tools/lib64/libc++.so "$tools/lib64/libc++.so"
    (cd "$tools" && printf '%s\n' "$SIGNING_TOOLS_SHA256" | sha256sum --check --strict --quiet -) \
        || die "the signing tools of build-tools $BUILD_TOOLS_VERSION differ from the pinned SHA-256 sums: not signing"
    chmod 755 "$tools/zipalign"
    # The app this key signs: only the variant's, never another application id.
    local apk=/apk/app-$APP_VARIANT-unsigned.apk identity
    identity=$(apk_identity "$tools/lib/apksigner.jar" "$apk") \
        || die "cannot read the package name and versionCode of $(basename "$apk"): not signing"
    [[ $identity == "$EXPECTED_PACKAGE $EXPECTED_VERSION_CODE" ]] \
        || die "the $APP_VARIANT APK is the app '$identity' (package versionCode), not '$EXPECTED_PACKAGE \
$EXPECTED_VERSION_CODE': not signing"
    log "Signing the $APP_VARIANT APK, $EXPECTED_PACKAGE versionCode $EXPECTED_VERSION_CODE (zipalign and apksigner \
checked against their pinned SHA-256)"
    "$tools/zipalign" -P 16 -f 4 "$apk" /tmp/aligned.apk
    java -Xmx1024M -jar "$tools/lib/apksigner.jar" sign --ks "$keystore" --ks-key-alias scanmylib \
        --ks-pass "file:$password_file" --out /tmp/scanmylib.apk /tmp/aligned.apk
    java -Xmx1024M -jar "$tools/lib/apksigner.jar" verify --verbose --print-certs /tmp/scanmylib.apk \
        | grep -E '^(Verified using v[0-9]+ scheme|Signer #1 certificate (DN|SHA-256 digest))'
    cp /tmp/scanmylib.apk /out/.scanmylib.apk.partial
    mv /out/.scanmylib.apk.partial /out/scanmylib.apk
    log "Published $PUBLISHED_PATH ($APP_VARIANT)"
    sha256sum /out/scanmylib.apk | cut -d ' ' -f 1 | sed 's/^/sha256: /'
    stat -c 'size:   %s bytes' /out/scanmylib.apk
}

# Prints "<package name> <versionCode>" of an APK, read from its binary AndroidManifest.xml by the
# manifest parser of apksigner.jar (com.android.apksig, the one apksigner itself uses).
apk_identity() {  # apk_identity APKSIGNER_JAR APK
    local tool=/tmp/ApkIdentity.java
    cat > "$tool" <<'JAVA'
import com.android.apksig.apk.ApkUtils;
import com.android.apksig.util.DataSources;
import java.io.RandomAccessFile;

public class ApkIdentity {
    public static void main(String[] args) throws Exception {
        try (var file = new RandomAccessFile(args[0], "r")) {
            var manifest = ApkUtils.getAndroidManifest(DataSources.asDataSource(file));
            System.out.println(ApkUtils.getPackageNameFromBinaryAndroidManifest(manifest.duplicate()) + " "
                    + ApkUtils.getLongVersionCodeFromBinaryAndroidManifest(manifest.duplicate()));
        }
    }
}
JAVA
    java -Xmx256M --class-path "$1" "$tool" "$2"
}

# Creates the release key (--create-signing-key, when there is none): the only container that
# mounts the key directory read-write.
key_main() {
    set -euo pipefail
    local keystore=/keystore/$KEYSTORE_FILE password_file=/keystore/$KEY_PASSWORD_FILE
    [[ ! -e $keystore && ! -e $password_file ]] || die "refusing to replace an existing signing key"
    log "Creating the release signing key in ANDROID_KEYSTORE_DIR"
    (
        umask 077
        head -c 30 /dev/urandom | base64 | tr '+/' '-_' > "$password_file"
        SCANMYLIB_KEYSTORE_PASSWORD=$(< "$password_file") \
            keytool -genkeypair -keystore "$keystore" -storetype PKCS12 \
            -storepass:env SCANMYLIB_KEYSTORE_PASSWORD -alias scanmylib \
            -keyalg RSA -keysize 4096 -validity 10000 -dname "CN=ScanMyLib, O=ScanMyLib local build"
    )
}

# --- Host side ----------------------------------------------------------------------------------

# Whether the Gradle arguments produce the APK of the variant (release or dev).
assembles_variant() {
    local variant=$1 arg
    shift
    for arg in "$@"; do
        [[ $arg =~ ^(:app:)?(assemble${variant^}|assemble|build)$ ]] && return 0
    done
    return 1
}

# The release app is production's: production's checkout and .env, main as on origin, clean.
assert_production_release() {  # assert_production_release PROJECT
    local checkout branch stray hidden head remote
    checkout=$(production_checkout) || die "cannot tell production's checkout (see above)"
    is_production_checkout "$ROOT" "$checkout" || die "the release app is only built in production's checkout \
($checkout), by scripts/deploy.sh --apk; a worktree builds the dev app (APP_VARIANT=dev, scripts/dev-env.sh)"
    [[ $1 == "$PRODUCTION_PROJECT" ]] \
        || die "APP_VARIANT=release needs production's .env (COMPOSE_PROJECT_NAME=$PRODUCTION_PROJECT), not '$1'"
    branch=$(git -C "$ROOT" symbolic-ref --quiet --short HEAD || true)
    [[ $branch == main ]] || die "the release app is built from main only, not from '${branch:-a detached HEAD}'"
    [[ -z $(git -C "$ROOT" status --porcelain --untracked-files=all) ]] \
        || die "the release app is built from a clean checkout only (git status)"
    hidden=$(hidden_changes "$ROOT")
    [[ -z $hidden ]] || die "files marked assume-unchanged or skip-worktree could hide changes: \
$(tr '\n' ' ' <<< "$hidden")(git update-index --no-assume-unchanged --no-skip-worktree FILE)"
    stray=$(android_stray_files "$ROOT")
    [[ -z $stray ]] || die "ignored files under android/ could end up in the release app: $(tr '\n' ' ' <<< "$stray")"
    head=$(git -C "$ROOT" rev-parse HEAD)
    remote=$(git -C "$ROOT" ls-remote origin refs/heads/main | cut -f 1) || remote=
    [[ -n $remote ]] || die "cannot read main on origin (git ls-remote origin refs/heads/main)"
    [[ $remote == "$head" ]] || die "HEAD ${head:0:12} differs from main on origin (${remote:0:12}): pull or push first"
}

# The versionCode of VERSION (MAJOR.MINOR.PATCH): major * 10000 + minor * 100 + patch, as
# android/app/build.gradle.kts computes it.
version_code() {  # version_code VERSION_FILE
    local version
    version=$(tr -d '[:space:]' < "$1")
    [[ $version =~ ^([0-9]{1,3})\.([0-9]{1,2})\.([0-9]{1,2})$ ]] \
        || die "VERSION must be MAJOR.MINOR.PATCH (minor and patch below 100), not '$version'"
    echo $((10#${BASH_REMATCH[1]} * 10000 + 10#${BASH_REMATCH[2]} * 100 + 10#${BASH_REMATCH[3]}))
}

main() {
    local create_key=0
    if [[ ${1:-} == --create-signing-key ]]; then
        create_key=1
        shift
    fi
    local env_file=$ROOT/.env data_dir android_dir keystore_dir variant project containers signs=1
    if [[ -f $env_file ]]; then
        load_env "$env_file" STACK
        project=${STACK[COMPOSE_PROJECT_NAME]:-}
        data_dir=${STACK[DATA_DIR]:-}
        [[ $data_dir == /* ]] || die "DATA_DIR in $env_file must be an absolute path"
        android_dir=${STACK[ANDROID_DIR]:-$data_dir/android}
        keystore_dir=${STACK[ANDROID_KEYSTORE_DIR]:-$android_dir/keystore}
        variant=${STACK[APP_VARIANT]:-}
        if [[ -z $variant ]]; then
            variant=dev
            [[ $project == "$PRODUCTION_PROJECT" ]] && variant=release
        fi
        case $variant in
            release) assert_production_release "$project" ;;
            dev)
                [[ $project != "$PRODUCTION_PROJECT" ]] \
                    || die "APP_VARIANT=dev in production's .env: production publishes the release app"
                ((!create_key)) || die "--create-signing-key: only production creates the signing key"
                assert_isolated_from_production "$env_file"
                ;;
            *) die "APP_VARIANT must be release or dev, not '$variant'" ;;
        esac
    else
        # CI: no stack, settings from the environment (read before common.sh cleared it).
        [[ ${CI:-} == true || ${GITHUB_ACTIONS:-} == true ]] \
            || die "no $env_file: run scripts/dev-env.sh (without .env, only CI builds: CI=true, never signed)"
        signs=0
        data_dir=$CI_DATA_DIR
        [[ $data_dir == /* ]] || die "no $env_file: set DATA_DIR to an absolute path (CI), or run scripts/dev-env.sh"
        android_dir=${CI_ANDROID_DIR:-$data_dir/android}
        variant=${CI_APP_VARIANT:-dev}
        [[ $variant == release || $variant == dev ]] || die "APP_VARIANT must be release or dev, not '$variant'"
        ((!create_key)) || die "--create-signing-key needs production's .env"
        # The build runs with network access and writes there: never production's directories,
        # nor your home directory but GitHub's RUNNER_TEMP.
        local runner_temp=()
        [[ ${GITHUB_ACTIONS:-} == true && -n ${RUNNER_TEMP:-} ]] && runner_temp=(--runner-temp "$RUNNER_TEMP")
        containers=$(production_containers) || die "cannot list production's containers: is Docker running?"
        python3 "$SCRIPTS_LIB/stack.py" check-paths "${runner_temp[@]}" "DATA_DIR=$data_dir" "ANDROID_DIR=$android_dir" \
            <<< "$containers" || die "DATA_DIR and ANDROID_DIR must share nothing with production nor be in your home directory (see above)"
    fi
    [[ $android_dir == /* ]] || die "ANDROID_DIR must be an absolute path"
    [[ -f $ROOT/VERSION ]] || die "missing $ROOT/VERSION"
    local expected_package=$APPLICATION_ID expected_version_code
    [[ $variant == dev ]] && expected_package=$APPLICATION_ID.dev
    expected_version_code=$(version_code "$ROOT/VERSION")

    local gradle_args=("$@")
    ((${#gradle_args[@]})) || gradle_args=(test "assemble${variant^}" lint)
    local assembles=0 publication="not published (no assemble${variant^})"
    assembles_variant "$variant" "${gradle_args[@]}" && assembles=1
    if ((assembles && !signs)); then
        publication="built unsigned, never published (no .env: CI)"
    elif ((assembles)); then
        publication="published as $data_dir/app/scanmylib.apk"
        [[ $keystore_dir == /* ]] || die "ANDROID_KEYSTORE_DIR must be an absolute path"
        if [[ ! -f $keystore_dir/$KEYSTORE_FILE || ! -f $keystore_dir/$KEY_PASSWORD_FILE ]]; then
            [[ ! -e $keystore_dir/$KEYSTORE_FILE && ! -e $keystore_dir/$KEY_PASSWORD_FILE ]] \
                || die "incomplete $keystore_dir: refusing to replace an existing signing key"
            ((create_key)) || die "no signing key in $keystore_dir: production creates it once, \
with scripts/build-apk.sh --create-signing-key in production's checkout (scripts/setup.sh does)"
        else
            create_key=0
        fi
    fi
    echo "App variant $variant, $publication"
    echo "Android toolchain: $android_dir"
    ((assembles && signs)) && echo "Signing key: $keystore_dir (read-only$( ((create_key)) && echo ', created first'))"

    # One build at a time per toolchain directory.
    mkdir -p "$android_dir"/{sdk,gradle,user-home}
    exec 8< "$android_dir"
    if ! flock --nonblock 8; then
        echo "Waiting for another build that uses $android_dir..."
        flock 8
    fi

    local prefix=${SCANMYLIB_CONTAINER_PREFIX:-scanmylib-android}
    [[ $prefix =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]] || die "invalid SCANMYLIB_CONTAINER_PREFIX: '$prefix'"
    local build_container=$prefix-build-$$ key_container=$prefix-key-$$ sign_container=$prefix-sign-$$
    # shellcheck disable=SC2064  # expand the names now
    trap "docker rm --force $build_container $key_container $sign_container > /dev/null 2>&1 || true" EXIT

    local common=(
        --rm --init
        --user "$(id -u):$(id -g)"
        --cap-drop ALL --security-opt no-new-privileges:true
        --read-only --tmpfs /tmp:rw,exec,nosuid,nodev,size=6g
        --memory 10g --pids-limit 4096
        --env HOME=/tmp/home
        # Java takes user.home from /etc/passwd, not from HOME.
        --env JAVA_TOOL_OPTIONS=-Duser.home=/tmp/home
        --env ANDROID_HOME=/opt/android-sdk
        --env BUILD_TOOLS_VERSION="$BUILD_TOOLS_VERSION"
    )

    docker run "${common[@]}" --name "$build_container" \
        --env GRADLE_USER_HOME=/gradle \
        --env ANDROID_USER_HOME=/android-user-home \
        --env GRADLE_VERSION="$GRADLE_VERSION" \
        --env SDK_PACKAGES="$SDK_PACKAGES" \
        --env SDK_REPOSITORY_URL="$SDK_REPOSITORY_URL" \
        --volume "$ROOT/android:/workspace" \
        --mount "type=bind,source=$ROOT/VERSION,target=/VERSION,readonly" \
        --volume "$android_dir/sdk:/opt/android-sdk" \
        --volume "$android_dir/gradle:/gradle" \
        --volume "$android_dir/user-home:/android-user-home" \
        --workdir /workspace \
        "$BUILDER_IMAGE" \
        bash -c "$(declare -f build_main log die sdk_archive_info install_command_line_tools \
            install_sdk_packages ensure_gradle_wrapper verify_gradle_wrapper); build_main \"\$@\"" \
        build_main "${gradle_args[@]}"

    ((assembles && signs)) || return 0
    mkdir -p "$data_dir/app"

    if ((create_key)); then
        [[ -d $keystore_dir ]] || mkdir -p -m 700 "$keystore_dir"
        docker run "${common[@]}" --name "$key_container" \
            --network none \
            --env KEYSTORE_FILE="$KEYSTORE_FILE" \
            --env KEY_PASSWORD_FILE="$KEY_PASSWORD_FILE" \
            --volume "$keystore_dir:/keystore" \
            "$BUILDER_IMAGE" \
            bash -c "$(declare -f key_main log die); key_main"
    fi

    docker run "${common[@]}" --name "$sign_container" \
        --network none \
        --env KEYSTORE_FILE="$KEYSTORE_FILE" \
        --env KEY_PASSWORD_FILE="$KEY_PASSWORD_FILE" \
        --env SIGNING_TOOLS_SHA256="$SIGNING_TOOLS_SHA256" \
        --env APP_VARIANT="$variant" \
        --env EXPECTED_PACKAGE="$expected_package" \
        --env EXPECTED_VERSION_CODE="$expected_version_code" \
        --env PUBLISHED_PATH="$data_dir/app/scanmylib.apk" \
        --volume "$ROOT/android/app/build/outputs/apk/$variant:/apk:ro" \
        --volume "$android_dir/sdk/build-tools/$BUILD_TOOLS_VERSION:/build-tools:ro" \
        --volume "$keystore_dir:/keystore:ro" \
        --volume "$data_dir/app:/out" \
        "$BUILDER_IMAGE" \
        bash -c "$(declare -f sign_main apk_identity log die); sign_main"
}

# Without .env (CI only), the settings come from the environment, which common.sh clears.
readonly CI_DATA_DIR=${DATA_DIR:-} CI_ANDROID_DIR=${ANDROID_DIR:-} CI_APP_VARIANT=${APP_VARIANT:-}
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=lib/common.sh
source "$ROOT/scripts/lib/common.sh"

main "$@"
