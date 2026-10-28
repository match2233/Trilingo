param(
    [string]$SdkRoot = "",
    [string]$JdkHome = "",
    [switch]$Install,
    [switch]$EmbedKey,
    [string]$Adb = "D:\Program Files\Netease\MuMu\nx_device\12.0\shell\adb.exe",
    [string]$Device = "emulator-5554"
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$appRoot = Join-Path $scriptDir "app\src\main"
$assetsDir = Join-Path $appRoot "assets"
$resDir = Join-Path $appRoot "res"
$buildDir = Join-Path $scriptDir "build"
$distDir = Join-Path $scriptDir "dist"
$genDir = Join-Path $buildDir "gen"
$classesDir = Join-Path $buildDir "classes"
$dexDir = Join-Path $buildDir "dex"
$keystoreDir = Join-Path $scriptDir "keystore"
$keystore = Join-Path $keystoreDir "bodyexercise.jks"
$keystorePass = "bodyexercise-local"
$keyAlias = "bodyexercise"
$versionName = "1.1.0"
$versionCode = 2

function Find-Jdk([string]$preferred) {
    $candidates = @()
    if ($preferred) { $candidates += $preferred }
    if ($env:JAVA_HOME) { $candidates += $env:JAVA_HOME }
    $candidates += @(
        "C:\Program Files\JetBrains\PyCharm 2024.3.1.1\jbr",
        "C:\Program Files\Android\Android Studio\jbr",
        "C:\Program Files\Java\jdk-21",
        "C:\Program Files\Java\jdk-17"
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path (Join-Path $candidate "bin\javac.exe"))) {
            return $candidate
        }
    }
    throw "未找到 JDK。请安装 JDK 17/21，或用 -JdkHome 指定路径。"
}

if (-not $SdkRoot) {
    if ($env:ANDROID_HOME) { $SdkRoot = $env:ANDROID_HOME }
    elseif ($env:ANDROID_SDK_ROOT) { $SdkRoot = $env:ANDROID_SDK_ROOT }
    else { $SdkRoot = Join-Path $env:LOCALAPPDATA "Android\Sdk" }
}
$JdkHome = Find-Jdk $JdkHome
$env:JAVA_HOME = $JdkHome
$env:PATH = (Join-Path $JdkHome "bin") + ";" + $env:PATH

$buildTools = Get-ChildItem (Join-Path $SdkRoot "build-tools") -Directory -ErrorAction Stop |
    Sort-Object { [version]($_.Name -replace "[^0-9.]", "") } -Descending |
    Select-Object -First 1
if (-not $buildTools) { throw "未找到 Android build-tools。" }
$platformDir = Join-Path $SdkRoot "platforms\android-35"
if (-not (Test-Path $platformDir)) {
    $platformDir = Get-ChildItem (Join-Path $SdkRoot "platforms") -Directory |
        Sort-Object Name -Descending | Select-Object -First 1 -ExpandProperty FullName
}
$androidJar = Join-Path $platformDir "android.jar"
$aapt2 = Join-Path $buildTools.FullName "aapt2.exe"
$d8 = Join-Path $buildTools.FullName "d8.bat"
$zipalign = Join-Path $buildTools.FullName "zipalign.exe"
$apksigner = Join-Path $buildTools.FullName "apksigner.bat"
$javac = Join-Path $JdkHome "bin\javac.exe"
$keytool = Join-Path $JdkHome "bin\keytool.exe"

foreach ($tool in @($aapt2, $d8, $zipalign, $apksigner, $javac, $keytool, $androidJar)) {
    if (-not (Test-Path $tool)) { throw "缺少构建工具：$tool" }
}

Write-Host "清理构建目录..."
if (Test-Path $buildDir) { Remove-Item -Recurse -Force $buildDir }
if (Test-Path $distDir) { Remove-Item -Recurse -Force $distDir }
New-Item -ItemType Directory -Force -Path $buildDir, $distDir, $genDir, $classesDir, $dexDir, $keystoreDir | Out-Null

# API Key 从 data/llm.json 读取，只在本地生成 config.js；不要提交或打印。
$llmPath = Join-Path $repoRoot "data\llm.json"
if (-not (Test-Path $llmPath)) { throw "找不到 data\llm.json。" }
$llm = Get-Content $llmPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $llm.api_key) { throw "data\llm.json 缺少 api_key。" }
if (-not $EmbedKey) {
    Write-Host "未加 -EmbedKey：config.js 不写入 API Key（在 App 的 AI 设置里填）。"
    $llm.api_key = ""
}
if (-not $llm.base_url) { throw "data\llm.json 缺少 base_url。" }
if (-not $llm.model) { throw "data\llm.json 缺少 model。" }
$configObject = [ordered]@{
    apiKey = [string]$llm.api_key
    baseUrl = [string]$llm.base_url
    model = [string]$llm.model
}
$configText = "/* 本地生成：数据只随 APK 安装，不参与同步。 */`r`nwindow.APP_CONFIG = " +
    ($configObject | ConvertTo-Json -Depth 3) + ";`r`n"
$configPath = Join-Path $assetsDir "config.js"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($configPath, $configText, $utf8NoBom)
Write-Host "已生成本地 config.js（API Key 不显示）。"

$moveSlugs = @(
    "incline-press", "bench-press", "shoulder-press", "lateral-raise", "triceps-ext",
    "rdl", "bent-row", "single-row", "reverse-fly", "face-pull", "bicep-curl",
    "goblet-squat", "crunch", "hip-thrust"
)
$imgSource = Join-Path $repoRoot "assets\fitness"
$staleImgDir = Join-Path $assetsDir "img"
if (Test-Path $staleImgDir) { Remove-Item -Recurse -Force $staleImgDir }
Get-ChildItem $assetsDir -Filter "*.png" -File -ErrorAction SilentlyContinue | Remove-Item -Force
foreach ($slug in $moveSlugs) {
    $source = Join-Path $imgSource "$slug.png"
    if (-not (Test-Path $source)) { throw "缺少动作图片：$source" }
    Copy-Item $source (Join-Path $assetsDir "$slug.png") -Force
}
Write-Host "已复制 $($moveSlugs.Count) 张动作图片到 assets 根目录。"

Write-Host "编译资源..."
$compiled = Join-Path $buildDir "compiled.zip"
& $aapt2 compile --dir $resDir -o $compiled
if ($LASTEXITCODE -ne 0) { throw "aapt2 compile 失败。" }

$unsignedApk = Join-Path $buildDir "unsigned.apk"
& $aapt2 link `
    -o $unsignedApk `
    -I $androidJar `
    --manifest (Join-Path $appRoot "AndroidManifest.xml") `
    -A $assetsDir `
    --java $genDir `
    --min-sdk-version 23 `
    --target-sdk-version 35 `
    --version-code $versionCode `
    --version-name $versionName `
    --auto-add-overlay `
    $compiled
if ($LASTEXITCODE -ne 0) { throw "aapt2 link 失败。" }

Write-Host "编译 Java..."
$javaFiles = @()
$javaFiles += Get-ChildItem (Join-Path $appRoot "java") -Recurse -Filter "*.java" | ForEach-Object { $_.FullName }
$javaFiles += Get-ChildItem $genDir -Recurse -Filter "*.java" | ForEach-Object { $_.FullName }
& $javac -encoding UTF-8 --release 8 -nowarn -classpath $androidJar -d $classesDir @javaFiles
if ($LASTEXITCODE -ne 0) { throw "javac 失败。" }

Write-Host "生成 dex..."
$classFiles = Get-ChildItem $classesDir -Recurse -Filter "*.class" | ForEach-Object { $_.FullName }
& $d8 --release --min-api 23 --lib $androidJar --output $dexDir @classFiles
if ($LASTEXITCODE -ne 0) { throw "d8 失败。" }
$dexFile = Join-Path $dexDir "classes.dex"
if (-not (Test-Path $dexFile)) { throw "d8 没有生成 classes.dex。" }

Write-Host "写入 classes.dex..."
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::Open($unsignedApk, "Update")
try {
    [void][System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
        $zip, $dexFile, "classes.dex", [System.IO.Compression.CompressionLevel]::Optimal)
} finally {
    $zip.Dispose()
}

$alignedApk = Join-Path $buildDir "aligned.apk"
& $zipalign -f 4 $unsignedApk $alignedApk
if ($LASTEXITCODE -ne 0) { throw "zipalign 失败。" }

if (-not (Test-Path $keystore)) {
    Write-Host "生成本地签名证书..."
    & $keytool -genkeypair `
        -keystore $keystore `
        -storetype JKS `
        -alias $keyAlias `
        -keyalg RSA `
        -keysize 2048 `
        -validity 10000 `
        -storepass $keystorePass `
        -keypass $keystorePass `
        -dname "CN=Body Exercise, OU=Personal, O=Local, L=Local, ST=Local, C=CN" `
        -noprompt | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "keytool 失败。" }
}

$finalApk = Join-Path $distDir "BodyExercise-$versionName.apk"
Write-Host "签名 APK..."
& $apksigner sign `
    --ks $keystore `
    --ks-key-alias $keyAlias `
    --ks-pass "pass:$keystorePass" `
    --key-pass "pass:$keystorePass" `
    --min-sdk-version 23 `
    --out $finalApk `
    $alignedApk
if ($LASTEXITCODE -ne 0) { throw "apksigner 失败。" }

& $apksigner verify --print-certs $finalApk | Out-Host
if ($LASTEXITCODE -ne 0) { throw "APK 签名校验失败。" }

$apk = Get-Item $finalApk
Write-Host ""
Write-Host "构建完成：$($apk.FullName)"
Write-Host ("APK 大小：{0:N1} MB" -f ($apk.Length / 1MB))

if ($Install) {
    if (-not (Test-Path $Adb)) { throw "找不到 adb：$Adb" }
    Write-Host "安装到 $Device ..."
    & $Adb -s $Device install -r $finalApk
    if ($LASTEXITCODE -ne 0) { throw "adb install 失败。" }
    Write-Host "安装完成。"
}

exit 0
