import java.net.URI
import java.security.MessageDigest
import java.io.File

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
}

// Public Google model: pinned download at build time; no model weights or private images in Git.
val handModelAssets = layout.buildDirectory.dir("generated/hand-model-assets")
val prepareHandModel = tasks.register("prepareHandModel") {
    val modelUrl = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
    val expectedSha = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"
    inputs.property("modelUrl", modelUrl)
    inputs.property("modelSha256", expectedSha)
    val modelFile = handModelAssets.map { it.file("hand_landmarker.task") }
    outputs.file(modelFile)
    doLast {
        fun sha(file: File) = MessageDigest.getInstance("SHA-256").digest(file.readBytes())
            .joinToString("") { "%02x".format(it) }
        val target = modelFile.get().asFile
        if (!target.isFile || sha(target) != expectedSha) {
            target.parentFile.mkdirs()
            val temporary = File(target.parentFile, "hand_landmarker.task.download")
            try {
                val connection = URI(modelUrl).toURL().openConnection().apply {
                    connectTimeout = 30_000; readTimeout = 60_000
                }
                connection.getInputStream().use { input -> temporary.outputStream().use { input.copyTo(it) } }
                check(sha(temporary) == expectedSha) { "Hand model SHA256 mismatch" }
                temporary.copyTo(target, overwrite = true)
            } finally { temporary.delete() }
        }
    }
}
tasks.named("preBuild") { dependsOn(prepareHandModel) }

android {
    namespace = "com.blurfing.app"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.blurfing.app"
        minSdk = 26
        targetSdk = 36
        versionCode = 4
        versionName = "1.0.3"

        val revision = providers.gradleProperty("blurfingRevision").orElse("unrecorded").get()
        require(revision.matches(Regex("[0-9a-f]{7,40}|unrecorded")))
        buildConfigField("String", "SOURCE_REVISION", "\"$revision\"")

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        vectorDrawables {
            useSupportLibrary = true
        }
    }

    val uploadStorePath = providers.environmentVariable("BLURFING_KEYSTORE_PATH").orNull
    if (uploadStorePath != null) {
        signingConfigs {
            create("upload") {
                storeFile = file(uploadStorePath)
                storePassword = providers.environmentVariable("BLURFING_KEYSTORE_PASSWORD").get()
                keyAlias = providers.environmentVariable("BLURFING_KEY_ALIAS").get()
                keyPassword = providers.environmentVariable("BLURFING_KEY_PASSWORD").get()
            }
        }
    }

    buildTypes {
        release {
            if (uploadStorePath != null) {
                signingConfig = signingConfigs.getByName("upload")
            }
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_21
        targetCompatibility = JavaVersion.VERSION_21
    }
    kotlinOptions {
        jvmTarget = "21"
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    testOptions {
        unitTests.isIncludeAndroidResources = true
    }
    sourceSets.getByName("androidTest").assets.srcDir("src/test/resources")
    sourceSets.getByName("main").assets.srcDir(handModelAssets)
    androidResources { noCompress += "task" }
    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.activity:activity-compose:1.9.3")

    val composeBom = platform("androidx.compose:compose-bom:2024.10.01")
    implementation(composeBom)
    androidTestImplementation(composeBom)

    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")

    implementation("io.coil-kt:coil-compose:2.7.0")
    implementation("androidx.exifinterface:exifinterface:1.3.7")

    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.google.mediapipe:tasks-vision:1.1.1")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.robolectric:robolectric:4.14.1")
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
    testImplementation("com.squareup.okhttp3:okhttp-tls:4.12.0")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.9.0")
    testImplementation("org.json:json:20240303")
    androidTestImplementation("androidx.test.ext:junit:1.3.0")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.7.0")
    androidTestImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    debugImplementation("androidx.compose.ui:ui-tooling")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
}
