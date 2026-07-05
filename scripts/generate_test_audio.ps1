param(
  [string]$OutFile = "tests/assets/sample_partial_speech.wav"
)

Add-Type -AssemblyName System.Speech

$absolutePath = Join-Path (Get-Location) $OutFile
$directory = Split-Path -Parent $absolutePath
New-Item -ItemType Directory -Force -Path $directory | Out-Null

$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.Rate = -1
$synth.Volume = 100
$synth.SetOutputToWaveFile($absolutePath)
$synth.Speak("Um hello there. This is a partial speech test. We need a clear and complete transcript from broken speech.")
$synth.Dispose()

