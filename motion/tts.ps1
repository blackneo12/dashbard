# Generates narration clips (assets\v<i>.wav) and word timings (assets\words.tsv)
# from assets\lines.txt using the built-in Windows Korean voice (Microsoft Heami).
param([int]$Rate = 2)
$d = Join-Path $PSScriptRoot "assets"
Add-Type -AssemblyName System.Speech
$lines = Get-Content -Encoding UTF8 (Join-Path $d "lines.txt") | Where-Object { $_.Trim() -ne "" }
$out = New-Object System.Collections.Generic.List[string]
Get-ChildItem (Join-Path $d "v*.wav") -ErrorAction SilentlyContinue | Remove-Item
for ($i = 0; $i -lt $lines.Count; $i++) {
    $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $s.SelectVoice("Microsoft Heami Desktop")
    $s.Rate = $Rate
    $fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(24000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
    $s.SetOutputToWaveFile((Join-Path $d "v$i.wav"), $fmt)
    $idx = $i
    $s.add_SpeakProgress({ param($sender, $e) $out.Add("$idx`t$($e.CharacterPosition)`t$($e.AudioPosition.TotalMilliseconds)`t$($e.Text)") })
    $s.Speak($lines[$i])
    $s.Dispose()
}
[System.IO.File]::WriteAllLines((Join-Path $d "words.tsv"), $out, (New-Object System.Text.UTF8Encoding $false))
"clips: $($lines.Count), words: $($out.Count)"
