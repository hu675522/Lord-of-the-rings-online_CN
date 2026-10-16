param(
    [string]$ImageDirectory = "$PSScriptRoot\originals",
    [string]$OutputDirectory = "$PSScriptRoot\ocr",
    [int]$Limit = 0,
    [string]$LanguageTag = 'en-US'
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime] | Out-Null
[Windows.Globalization.Language, Windows.Globalization, ContentType=WindowsRuntime] | Out-Null
[Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType=WindowsRuntime] | Out-Null
$script:asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
function Await($Operation, [Type]$ResultType) {
    $task = $script:asTask.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    $task.Wait()
    return $task.Result
}
$language = New-Object Windows.Globalization.Language($LanguageTag)
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
if ($null -eq $engine) { throw ('Windows OCR language is not available: ' + $LanguageTag) }
[IO.Directory]::CreateDirectory([IO.Path]::GetFullPath($OutputDirectory)) | Out-Null
$images = @(Get-ChildItem -LiteralPath $ImageDirectory -Filter '*.jpg' -File | Sort-Object Name)
if ($Limit -gt 0) { $images = @($images | Select-Object -First $Limit) }
$index = 0
foreach ($image in $images) {
    $destination = Join-Path $OutputDirectory ($image.BaseName + '.json')
    if (Test-Path -LiteralPath $destination) { $index++; continue }
    $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($image.FullName)) ([Windows.Storage.StorageFile])
    $stream = Await ($file.OpenReadAsync()) ([Windows.Storage.Streams.IRandomAccessStreamWithContentType])
    try {
        $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        try {
            $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
            $lines = @($result.Lines | ForEach-Object {
                $line = $_
                $words = @($line.Words | ForEach-Object {
                    @{text=$_.Text; x=$_.BoundingRect.X; y=$_.BoundingRect.Y; width=$_.BoundingRect.Width; height=$_.BoundingRect.Height}
                })
                @{text=$line.Text; words=$words}
            })
            $record = @{resource_id=('0x'+$image.BaseName); image=$image.Name; width=$bitmap.PixelWidth; height=$bitmap.PixelHeight; language=$LanguageTag; text_angle=$result.TextAngle; lines=$lines}
            [IO.File]::WriteAllText($destination, ($record | ConvertTo-Json -Depth 8), (New-Object Text.UTF8Encoding($false)))
        } finally { $bitmap.Dispose() }
    } finally { $stream.Dispose() }
    $index++
    Write-Output ('OCR {0}/{1}: {2}, {3} lines' -f $index,$images.Count,$image.Name,$lines.Count)
}
