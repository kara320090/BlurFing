param(
    [Parameter(Mandatory=$true)][string]$JdkHome,
    [string]$SdkHome = "$env:LOCALAPPDATA\Android\Sdk",
    [string[]]$Tasks = @('testDebugUnitTest','assembleDebug','assembleDebugAndroidTest')
)
$ErrorActionPreference = 'Stop'
$javaPath = Join-Path $JdkHome 'bin\java.exe'
if (!(Test-Path -LiteralPath $javaPath)) { throw 'JDK 경로의 bin/java.exe를 찾을 수 없습니다.' }
$releasePath = Join-Path $JdkHome 'release'
if (!(Test-Path -LiteralPath $releasePath) -or !(Select-String -LiteralPath $releasePath -Pattern '^JAVA_VERSION="21[\."]' -Quiet)) {
    throw '이 프로젝트는 JDK 21로 빌드합니다. Android Studio의 JDK 25 경로 대신 JDK 21을 지정하세요.'
}
if (!(Test-Path -LiteralPath (Join-Path $SdkHome 'platforms\android-35\android.jar'))) { throw 'Android SDK 35를 설치하고 SdkHome 경로를 확인하세요.' }
$androidDirectory = Split-Path -Parent $PSScriptRoot
$previousJava = $env:JAVA_HOME
$previousAndroid = $env:ANDROID_HOME
try {
    $env:JAVA_HOME = (Resolve-Path -LiteralPath $JdkHome).Path
    $env:ANDROID_HOME = (Resolve-Path -LiteralPath $SdkHome).Path
    Push-Location -LiteralPath $androidDirectory
    try {
        & (Join-Path $androidDirectory 'gradlew.bat') @Tasks --max-workers=4 --console=plain
        if ($LASTEXITCODE -ne 0) { throw "Gradle이 종료 코드 $LASTEXITCODE 로 중단됐습니다." }
    } finally { Pop-Location }
} finally {
    $env:JAVA_HOME = $previousJava
    $env:ANDROID_HOME = $previousAndroid
}
