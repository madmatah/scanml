// AGP 9 compiles Kotlin itself ("built-in Kotlin") and defaults to KGP 2.2.10. Putting newer
// KGP and KSP versions on the build classpath is the documented way to upgrade them.
buildscript {
    dependencies {
        classpath(libs.kotlin.gradle.plugin)
        classpath(libs.ksp.gradle.plugin)
    }
}

plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.androidx.room) apply false
    alias(libs.plugins.kotlin.compose) apply false
    alias(libs.plugins.kotlin.serialization) apply false
}
