plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    id("com.google.devtools.ksp")
    alias(libs.plugins.androidx.room)
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
        versionCode = 6
        versionName = "0.2.3"
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
    }

    lint {
        abortOnError = true
        checkReleaseBuilds = true
        // targetSdk 36 is a project requirement: raising it is a deliberate step, after testing.
        disable += "OldTargetApi"
    }
}

room {
    schemaDirectory("$projectDir/schemas")
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
}
