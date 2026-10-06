param([Parameter(ValueFromRemainingArguments=$true)][string[]]$CliArgs)
$env:PATH = 'C:\Users\Juan\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin;' + $env:PATH
$env:HYPERFRAMES_NO_TELEMETRY = '1'
$env:HYPERFRAMES_NO_UPDATE_CHECK = '1'
$env:HYPERFRAMES_FFMPEG_PATH = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'vendor/ffmpeg.exe'))
$env:HYPERFRAMES_FFPROBE_PATH = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'node_modules/ffprobe-static/bin/win32/x64/ffprobe.exe'))
$env:HYPERFRAMES_RUN_ID = 'ese-auto-hyperframes-20261005'
& 'C:\Users\Juan\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' (Join-Path $PSScriptRoot 'node_modules/hyperframes/bin/hyperframes.mjs') @CliArgs
exit $LASTEXITCODE
