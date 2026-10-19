plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    id("com.google.devtools.ksp")
    alias(libs.plugins.androidx.room)
}

// A release has a single version, the repository's VERSION file (MAJOR.MINOR.PATCH), which the
// api reports too. The versionCode is derived from it, major * 10000 + minor * 100 + patch
// (0.2.3 -> 203), so that every release installs over the previous one; minor and patch stay
// below 100. scripts/build-apk.sh mounts the file at /VERSION, next to the project (/workspace).
// The dev app is a development build: its version and versionCode come from the environment (see
// the dev build type below).
val projectVersion: String = providers
    .fileContents(rootProject.layout.projectDirectory.file("../VERSION"))
    .asText.get().trim()
val projectVersionCode: Int = run {
    val parts = Regex("""(\d{1,3})\.(\d{1,2})\.(\d{1,2})""").matchEntire(projectVersion)?.destructured
        ?: error("VERSION must be MAJOR.MINOR.PATCH with minor and patch below 100, not '$projectVersion'")
    val (major, minor, patch) = parts
    major.toInt() * 10000 + minor.toInt() * 100 + patch.toInt()
}

android {
    namespace = "fr.scanmylib"
    // The current AndroidX, OkHttp and Coil releases require compiling against API 37. Only the
    // compile-time API changes: runtime behavior follows targetSdk, which stays at 36.
    compileSdk = 37

    defaultConfig {
        applicationId = "fr.scanmylib"
        minSdk = 26
        targetSdk = 36
        versionCode = projectVersionCode
        versionName = projectVersion
    }

    buildTypes {
        // Left unsigned: scripts/build-apk.sh signs it in a container without network access,
        // with a key kept outside the repository, so the build itself never sees the key.
        release {
            // No R8: shrinking saves a few MB on a sideloaded app, but breaks code that
            // Google Play services and the libraries reach by reflection.
            isMinifyEnabled = false
            isShrinkResources = false
        }
        // The development app (APP_VARIANT=dev, scripts/dev-env.sh): the release build under its own
        // application id and name ("ScanMyLib (dev)", src/dev/res), so that it installs next to the
        // production app and talks to the development stack. Same signing key. Its version is set
        // below (androidComponents).
        create("dev") {
            initWith(getByName("release"))
            applicationIdSuffix = ".dev"
        }
    }

    androidResources {
        // The app is in English (values/) with a French translation (values-fr/): drop the other
        // translations shipped by the libraries.
        localeFilters += listOf("en", "fr")
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        buildConfig = true
        compose = true
    }

    testOptions {
        // Framework calls (android.util.Log...) do nothing in JVM unit tests instead of throwing,
        // so that view models can be tested.
        unitTests.isReturnDefaultValues = true
        // The screenshot tests draw the screens with the app's resources: strings, drawables and themes.
        unitTests.isIncludeAndroidResources = true
    }

    lint {
        abortOnError = true
        checkReleaseBuilds = true
        // targetSdk 36 is a project requirement: raising it is a deliberate step, after testing.
        disable += "OldTargetApi"
    }
}

// The dev app's version and versionCode, from scripts/build-apk.sh (scripts/lib/version.py): the
// development build's version, derived from git, and the time of the build, so that each build
// installs over the previous one. Without them (a build outside the script), VERSION's with "-dev".
androidComponents {
    onVariants(selector().withBuildType("dev")) { variant ->
        val versionName = providers.environmentVariable("SCANMYLIB_DEV_VERSION_NAME")
            .orElse("$projectVersion-dev")
        val versionCode = providers.environmentVariable("SCANMYLIB_DEV_VERSION_CODE")
            .map { it.toInt() }
            .orElse(projectVersionCode)
        variant.outputs.forEach { output ->
            output.versionName.set(versionName)
            output.versionCode.set(versionCode)
        }
    }
}

room {
    schemaDirectory("$projectDir/schemas")
}

val ktlint: Configuration = configurations.create("ktlint")

// The image of Android that Robolectric runs the screenshot tests on, resolved and verified by Gradle like
// any other dependency: Robolectric runs offline and reads it from robolectricDependencyDir, never
// downloading it itself.
val robolectricAndroidAll: Configuration = configurations.create("robolectricAndroidAll")
val robolectricDependencyDir = layout.buildDirectory.dir("robolectric")
val syncRobolectricAndroidAll = tasks.register<Sync>("syncRobolectricAndroidAll") {
    from(robolectricAndroidAll)
    into(robolectricDependencyDir)
}

val screenshotsDir = layout.buildDirectory.dir("outputs/roborazzi")

// The screenshot tests run with the debug variant's unit tests (src/testDebug).
tasks.withType<Test>().named { it == "testDebugUnitTest" }.configureEach {
    inputs.files(syncRobolectricAndroidAll)
        .withPropertyName("robolectricAndroidAll")
        .withNormalizer(ClasspathNormalizer::class)
    // Declared, so that a run taken from the build cache brings back the pictures of its inputs, and cleared first, so
    // that no picture of an earlier revision stays among them.
    val screenshots = screenshotsDir
    outputs.dir(screenshots).withPropertyName("screenshots")
    doFirst { screenshots.get().asFile.deleteRecursively() }
    systemProperty("robolectric.offline", "true")
    systemProperty("robolectric.dependency.dir", robolectricDependencyDir.get().asFile.absolutePath)
    // Android 16 reads raw file descriptors through the JDK's jdk.internal.access, which Java 21 exports to no unnamed
    // module: without it, Robolectric fails to set up every test.
    jvmArgs("--add-exports=java.base/jdk.internal.access=ALL-UNNAMED")
    // The pictures are never committed, so there are no references to compare them with: every run records them.
    systemProperty("roborazzi.test.record", "true")
}

dependencies {
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.camera.camera2)
    implementation(libs.androidx.camera.core)
    implementation(libs.androidx.camera.lifecycle)
    implementation(libs.androidx.camera.view)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.datastore.preferences)
    implementation(libs.androidx.exifinterface)
    implementation(libs.androidx.lifecycle.process)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.room.runtime)
    implementation(libs.androidx.work.runtime)
    implementation(libs.coil.compose)
    implementation(libs.coil.network.okhttp)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.okhttp)
    implementation(libs.play.services.code.scanner)
    implementation(libs.play.services.mlkit.document.scanner)
    ksp(libs.androidx.room.compiler)

    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
    testImplementation(libs.okhttp.mockwebserver)
    // The screenshot tests (src/testDebug) run on the debug variant, whose manifest declares the activity
    // that the Compose test rule starts (ui-test-manifest).
    testDebugImplementation(libs.androidx.compose.ui.test.junit4)
    testDebugImplementation(libs.robolectric)
    testDebugImplementation(libs.roborazzi)
    debugImplementation(libs.androidx.compose.ui.test.manifest)
    robolectricAndroidAll(libs.robolectric.android.all)

    ktlint(libs.ktlint.cli) {
        attributes {
            // Its libraries as artifacts of their own, which dependency verification lists, rather than one shaded jar.
            attribute(Bundling.BUNDLING_ATTRIBUTE, objects.named(Bundling.EXTERNAL))
        }
    }
}

val ktlintSources = listOf("app/src/**/*.kt", "*.kts", "app/*.kts")

tasks.register<JavaExec>("ktlintCheck") {
    group = "verification"
    classpath = ktlint
    mainClass.set("com.pinterest.ktlint.Main")
    workingDir = rootDir
    args = listOf("--relative") + ktlintSources
}

tasks.register<JavaExec>("ktlintFormat") {
    group = "formatting"
    classpath = ktlint
    mainClass.set("com.pinterest.ktlint.Main")
    workingDir = rootDir
    args = listOf("--format", "--relative") + ktlintSources
}
