#!/usr/bin/env bash
#
# Builds the ScanMyLib Android app in throwaway containers: nothing is installed on the host.
#
# Usage: scripts/build-apk.sh [gradle arguments...]      (default: test assembleRelease lint)
#
# The containers are named <prefix>-build-<pid> and <prefix>-sign-<pid>, with the prefix
# "scanmylib-android" unless SCANMYLIB_CONTAINER_PREFIX says otherwise.
#
# Gradle checks every dependency against android/gradle/verification-metadata.xml (SHA-256).
# After changing dependencies, record the new checksums with:
#   scripts/build-apk.sh --write-verification-metadata sha256 test assembleRelease lint
#
# 1. Build: the official eclipse-temurin:21-jdk image runs Gradle as your uid, with network
#    access (SDK, Gradle and Maven downloads) and only these bind mounts:
#      android/                      -> /workspace          sources; the Gradle wrapper is generated here once
#      $DATA_DIR/android/sdk         -> /opt/android-sdk    Android SDK (command-line tools, platform, build-tools)
#      $DATA_DIR/android/gradle      -> /gradle             GRADLE_USER_HOME (distribution, dependency caches)
#      $DATA_DIR/android/user-home   -> /android-user-home  ANDROID_USER_HOME, i.e. what would be ~/.android
#    Gradle produces an unsigned release APK and never sees the signing key.
# 2. Sign (when the APK was assembled): the same image, without any network, creates the release
#    key once in $DATA_DIR/android/keystore (never in the repository), signs the APK with
#    apksigner and publishes it as $DATA_DIR/app/scanmylib.apk.
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
readonly DEFAULT_GRADLE_ARGS=(test assembleRelease lint)
readonly UNSIGNED_APK_DIR=app/build/outputs/apk/release
# Release key, under $DATA_DIR/android/keystore.
readonly KEYSTORE_FILE=scanmylib-release.p12
readonly KEY_PASSWORD_FILE=password

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
    local keystore=/keystore/$KEYSTORE_FILE password_file=/keystore/$KEY_PASSWORD_FILE
    local build_tools=$ANDROID_HOME/build-tools/$BUILD_TOOLS_VERSION
    ensure_release_key "$keystore" "$password_file"
    log "Signing the release APK"
    "$build_tools/zipalign" -P 16 -f 4 /apk/app-release-unsigned.apk /tmp/aligned.apk
    "$build_tools/apksigner" sign --ks "$keystore" --ks-key-alias scanmylib \
        --ks-pass "file:$password_file" --out /tmp/scanmylib.apk /tmp/aligned.apk
    "$build_tools/apksigner" verify --verbose --print-certs /tmp/scanmylib.apk \
        | grep -E '^(Verified using v[0-9]+ scheme|Signer #1 certificate (DN|SHA-256 digest))'
    cp /tmp/scanmylib.apk /out/.scanmylib.apk.partial
    mv /out/.scanmylib.apk.partial /out/scanmylib.apk
    log "Published DATA_DIR/app/scanmylib.apk"
    sha256sum /out/scanmylib.apk | cut -d ' ' -f 1 | sed 's/^/sha256: /'
    stat -c 'size:   %s bytes' /out/scanmylib.apk
}

ensure_release_key() {
    local keystore=$1 password_file=$2
    [[ -f $keystore && -f $password_file ]] && return
    [[ -e $keystore || -e $password_file ]] \
        && die "incomplete DATA_DIR/android/keystore: refusing to replace an existing signing key"
    log "Creating the release signing key (once) in DATA_DIR/android/keystore"
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

# Reads KEY=value from the project's .env without evaluating it as shell code.
env_file_value() {
    local key=$1 file=$2
    [[ -f $file ]] || return 0
    sed -n "s/^$key=//p" "$file" | tail -n 1 | sed -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'$/\1/"
}

# Whether the Gradle arguments produce the release APK.
assembles_release() {
    local arg
    for arg in "$@"; do
        [[ $arg =~ ^(:app:)?(assembleRelease|assemble|build)$ ]] && return 0
    done
    return 1
}

main() {
    local project_dir data_dir
    project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
    data_dir=${DATA_DIR:-$(env_file_value DATA_DIR "$project_dir/.env")}
    [[ $data_dir == /* ]] || die "DATA_DIR must be an absolute path (see .env)"
    local android_data=$data_dir/android
    mkdir -p "$android_data"/{sdk,gradle,user-home,keystore} "$data_dir/app"
    chmod 700 "$android_data/keystore"

    local gradle_args=("$@")
    ((${#gradle_args[@]})) || gradle_args=("${DEFAULT_GRADLE_ARGS[@]}")

    local prefix=${SCANMYLIB_CONTAINER_PREFIX:-scanmylib-android}
    [[ $prefix =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]] || die "invalid SCANMYLIB_CONTAINER_PREFIX: '$prefix'"
    local build_container=$prefix-build-$$ sign_container=$prefix-sign-$$
    # shellcheck disable=SC2064  # expand the names now
    trap "docker rm --force $build_container $sign_container > /dev/null 2>&1 || true" EXIT

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
        --volume "$project_dir/android:/workspace" \
        --volume "$android_data/sdk:/opt/android-sdk" \
        --volume "$android_data/gradle:/gradle" \
        --volume "$android_data/user-home:/android-user-home" \
        --workdir /workspace \
        "$BUILDER_IMAGE" \
        bash -c "$(declare -f build_main log die sdk_archive_info install_command_line_tools \
            install_sdk_packages ensure_gradle_wrapper verify_gradle_wrapper); build_main \"\$@\"" \
        build_main "${gradle_args[@]}"

    assembles_release "${gradle_args[@]}" || return 0

    # The key is only written the first time; afterwards the signing container just reads it.
    local keystore_mode=rw
    [[ -f $android_data/keystore/$KEYSTORE_FILE && -f $android_data/keystore/$KEY_PASSWORD_FILE ]] \
        && keystore_mode=ro
    docker run "${common[@]}" --name "$sign_container" \
        --network none \
        --env KEYSTORE_FILE="$KEYSTORE_FILE" \
        --env KEY_PASSWORD_FILE="$KEY_PASSWORD_FILE" \
        --volume "$project_dir/android/$UNSIGNED_APK_DIR:/apk:ro" \
        --volume "$android_data/sdk:/opt/android-sdk:ro" \
        --volume "$android_data/keystore:/keystore:$keystore_mode" \
        --volume "$data_dir/app:/out" \
        "$BUILDER_IMAGE" \
        bash -c "$(declare -f sign_main ensure_release_key log die); sign_main"
}

main "$@"
