param(
    [Parameter(Mandatory=$true)][string]$JavaHome,
    [Parameter(Mandatory=$true)][string]$ExpectedUploadSha256,
    [string]$SigningDirectory = (Join-Path $env:USERPROFILE '.blurfing\signing'),
    [string]$SourceRevision
)

$ErrorActionPreference = 'Stop'
$projectDirectory = Split-Path $PSScriptRoot -Parent
$repositoryDirectory = Split-Path $projectDirectory -Parent
$javaTool = Join-Path $JavaHome 'bin\keytool.exe'
if (!(Test-Path -LiteralPath $javaTool) -or
    !(Select-String -LiteralPath (Join-Path $JavaHome 'release') -Pattern '^JAVA_VERSION="21[\."]' -Quiet)) {
    throw 'JDK 21을 지정하세요.'
}
$expected = $ExpectedUploadSha256.Replace(':','').ToLowerInvariant()
if ($expected -notmatch '^[0-9a-f]{64}$') { throw '등록된 업로드 인증서의 SHA256을 지정하세요.' }
$SigningDirectory = [IO.Path]::GetFullPath($SigningDirectory)
if ($SigningDirectory.StartsWith($repositoryDirectory + [IO.Path]::DirectorySeparatorChar,
    [StringComparison]::OrdinalIgnoreCase) -or $SigningDirectory -eq $repositoryDirectory) {
    throw '서명 자료는 Git 저장소 밖에 보관하세요.'
}
$keyStorePath = Join-Path $SigningDirectory 'blurfing-upload.jks'
$protectedPasswordPath = Join-Path $SigningDirectory 'upload-password.dpapi'
if (!(Test-Path -LiteralPath $keyStorePath) -or !(Test-Path -LiteralPath $protectedPasswordPath)) {
    throw '기존 업로드 키와 DPAPI 암호 파일이 필요합니다. 새 키를 자동 생성하지 않습니다.'
}
if (!$SourceRevision) {
    $SourceRevision = (& git -C $repositoryDirectory rev-parse --short=12 HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw '소스 커밋을 확인하지 못했습니다.' }
}
if ($SourceRevision -notmatch '^[0-9a-f]{7,40}$') { throw '실제 소스 커밋 해시를 지정하세요.' }

function Read-CertificateFingerprint([string[]]$ToolArguments) {
    $publicInfo = & $javaTool '-J-Duser.language=en' '-J-Duser.country=US' @ToolArguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw '인증서를 읽지 못했습니다.' }
    $matched = [regex]::Match(($publicInfo -join "`n"), 'SHA256:\s*([0-9A-Fa-f:]+)')
    if (!$matched.Success) { throw '인증서 SHA256을 확인하지 못했습니다.' }
    return $matched.Groups[1].Value.Replace(':','').ToLowerInvariant()
}

$names = @('JAVA_HOME','BLURFING_KEYSTORE_PATH','BLURFING_KEYSTORE_PASSWORD','BLURFING_KEY_ALIAS','BLURFING_KEY_PASSWORD')
$previous = @{}
foreach ($name in $names) { $previous[$name] = [Environment]::GetEnvironmentVariable($name,'Process') }
try {
    $securePassword = (Get-Content -LiteralPath $protectedPasswordPath -Raw).Trim() | ConvertTo-SecureString
    $uploadPassword = [Net.NetworkCredential]::new('', $securePassword).Password
    $env:JAVA_HOME = $JavaHome
    $env:BLURFING_KEYSTORE_PATH = $keyStorePath
    $env:BLURFING_KEYSTORE_PASSWORD = $uploadPassword
    $env:BLURFING_KEY_ALIAS = 'blurfing-upload'
    $env:BLURFING_KEY_PASSWORD = $uploadPassword
    $keyFingerprint = Read-CertificateFingerprint @('-list','-v','-keystore',$keyStorePath,
        '-storepass:env','BLURFING_KEYSTORE_PASSWORD','-alias',$env:BLURFING_KEY_ALIAS)
    if ($keyFingerprint -ne $expected) { throw '기존 업로드 인증서와 키가 다릅니다. 빌드를 중단합니다.' }
    Push-Location -LiteralPath $projectDirectory
    try {
        & '.\gradlew.bat' testDebugUnitTest testReleaseUnitTest lintRelease bundleRelease assembleDebug assembleDebugAndroidTest `
            "-PblurfingRevision=$SourceRevision" --max-workers=2 --console=plain --no-daemon
        if ($LASTEXITCODE -ne 0) { throw '릴리스 검사 또는 빌드가 실패했습니다.' }
    } finally { Pop-Location }
    $bundle = Join-Path $projectDirectory 'app\build\outputs\bundle\release\app-release.aab'
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($bundle)
    try {
        if (!($zip.Entries | Where-Object FullName -Match '^META-INF/[^/]+\.SF$') -or
            !($zip.Entries | Where-Object FullName -Match '^META-INF/[^/]+\.(RSA|EC|DSA)$')) {
            throw 'AAB 업로드 서명이 없습니다.'
        }
    } finally { $zip.Dispose() }
    $bundleFingerprint = Read-CertificateFingerprint @('-printcert','-jarfile',$bundle)
    if ($bundleFingerprint -ne $expected) { throw 'AAB 인증서가 등록된 업로드 키와 다릅니다.' }
    $verification = & (Join-Path $JavaHome 'bin\jarsigner.exe') '-J-Duser.language=en' -verify $bundle 2>&1
    if ($LASTEXITCODE -ne 0 -or ($verification -join "`n") -notmatch 'jar verified\.') {
        throw 'AAB 서명 검증에 실패했습니다.'
    }
    $verification | Set-Content -LiteralPath (Join-Path (Split-Path $bundle -Parent) 'signature-verification.txt') -Encoding UTF8
    Write-Output '기존 업로드 키의 인증서와 AAB 서명을 확인했습니다. Play 게시 완료는 아닙니다.'
    Write-Output "AAB: $bundle"
} finally {
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name,$previous[$name],'Process') }
    $uploadPassword = $null
    $securePassword = $null
}
