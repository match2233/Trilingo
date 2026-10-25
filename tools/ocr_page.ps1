# OCR 一页 PNG -> 文本 (Windows.Media.Ocr, 日文)
# 用法: pwsh -File ocr_page.ps1 -ImagePath x.png [-Lang ja]
param(
  [Parameter(Mandatory=$true)][string]$ImagePath,
  [string]$Lang = "ja"
)

Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType=WindowsRuntime]

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
  $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]

function Await($op, $type) {
  $task = $asTaskGeneric.MakeGenericMethod($type).Invoke($null, @($op))
  $task.Wait(-1) | Out-Null
  $task.Result
}

$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($ImagePath)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])

$language = [Windows.Globalization.Language]::new($Lang)
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
if ($null -eq $engine) { Write-Error "没有 $Lang 的 OCR 引擎"; exit 1 }

$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])

# 按行输出, 行内各词用空格连接 (保持行列结构, 便于后续按位置还原版面)
foreach ($line in $result.Lines) {
  Write-Output $line.Text
}
