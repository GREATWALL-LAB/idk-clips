<#
.SYNOPSIS
  Creates a legally clean sample video for testing IDK Clips.

.DESCRIPTION
  The script below is original text written for this project. It is spoken by
  the text-to-speech voices built into Windows (System.Speech) and combined
  with an animated waveform by FFmpeg. No third-party video or audio is used.

  Output: data\samples\curious-minds-sample.mp4 (about 4 minutes, 1280x720, ignored by git).
#>
[CmdletBinding()]
param([string]$Output)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Output) { $Output = Join-Path $root 'data\samples\curious-minds-sample.mp4' }
$ffmpeg = Join-Path $root 'tools\ffmpeg\bin\ffmpeg.exe'
if (-not (Test-Path -LiteralPath $ffmpeg)) {
    $cmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if (-not $cmd) { throw 'FFmpeg not found. Run scripts\windows\install-ffmpeg.cmd first.' }
    $ffmpeg = $cmd.Source
}

Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voices = @($synth.GetInstalledVoices() | Where-Object { $_.Enabled } | ForEach-Object { $_.VoiceInfo.Name })
if ($voices.Count -eq 0) { throw 'No text-to-speech voices are installed.' }
$hostA = if ($voices -contains 'Microsoft Zira Desktop') { 'Microsoft Zira Desktop' } else { $voices[0] }
$hostB = if ($voices -contains 'Microsoft David Desktop') { 'Microsoft David Desktop' } else { $voices[-1] }

# Original script (A = first host, B = second host).
$lines = @(
    @('A', "Welcome back to Curious Minds, the show where we take one big question and pull it apart. I'm Zira."),
    @('B', "And I'm David. Today's question sounds simple. Why do we forget almost everything we read?"),
    @('A', "Here is the uncomfortable truth. Within a day, most people forget more than half of what they just learned. That idea goes back to 1885, when a German psychologist named Hermann Ebbinghaus tested his own memory with lists of nonsense syllables."),
    @('B', "Nonsense syllables? Like dax and bok?"),
    @('A', "Exactly. He wanted material with no meaning, so he could measure pure memory. And he discovered what we now call the forgetting curve. Memory drops fast at first, and then it levels off."),
    @('B', "Okay, so that is the bad news. What is the good news?"),
    @('A', "The good news is that every time you review something at the right moment, the curve gets flatter. This is called spaced repetition. You review after one day, then after three days, then after a week, and the memory gets stronger each time."),
    @('B', "I have to tell you a story about this. In university, I crammed for a biology exam the night before. I drank four cups of coffee, read the entire textbook, and walked in feeling like a genius."),
    @('A', "How did it go?"),
    @('B', "I passed. Barely. But here is the funny part. Two weeks later, a friend asked me a basic question about cells, and I could not answer it. I had paid for a whole semester and kept the knowledge for about forty eight hours."),
    @('A', "That is the classic cramming trap. It feels productive, but it builds short term memory, not long term understanding."),
    @('B', "So what should people actually do? Give me something practical."),
    @('A', "Three things. First, test yourself instead of rereading. Close the book and try to explain the idea out loud. Second, space it out. Ten minutes a day beats three hours once a week. Third, connect new ideas to things you already know, because memories are stored as networks, not as isolated facts."),
    @('B', "Testing yourself sounds uncomfortable."),
    @('A', "It is uncomfortable, and that is the point. Researchers call it desirable difficulty. When recall feels hard, your brain is doing the work that makes the memory last."),
    @('B', "Here is a fact that surprised me while preparing for this episode. An octopus has three hearts, and about two thirds of its neurons are in its arms, not in its head."),
    @('A', "Wait, so an octopus partly thinks with its arms?"),
    @('B', "In a way, yes. Each arm can react to touch and taste on its own. Which makes me feel a little better about forgetting where I left my keys."),
    @('A', "Ha! That is a terrible excuse, David."),
    @('B', "It is the best excuse I have. Okay, before we wrap up, what is the one habit you would recommend to every listener?"),
    @('A', "Write one sentence at the end of every day about something you learned. Then read last week's sentences every Sunday. It takes two minutes, and it turns forgetting into review."),
    @('B', "One sentence a day. I can do that. Thanks for listening to Curious Minds. If this episode helped you, share it with one friend who is studying for an exam."),
    @('A', "See you next time.")
)

$builder = New-Object System.Speech.Synthesis.PromptBuilder
$builder.AppendBreak([TimeSpan]::FromMilliseconds(600))
foreach ($line in $lines) {
    $voice = if ($line[0] -eq 'A') { $hostA } else { $hostB }
    $builder.StartVoice($voice)
    $builder.AppendText($line[1])
    $builder.EndVoice()
    $builder.AppendBreak([TimeSpan]::FromMilliseconds(450))
}

$outDir = Split-Path -Parent $Output
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$wav = Join-Path $outDir 'curious-minds-speech.wav'
$synth.SetOutputToWaveFile($wav)
$synth.Speak($builder)
$synth.SetOutputToNull()
$synth.Dispose()
Write-Host "Speech synthesized: $wav"

$filter = '[1:a]aformat=channel_layouts=mono,showwaves=s=1280x260:mode=cline:rate=30:colors=0x8b5cf6[w];' +
          '[0:v][w]overlay=0:230:shortest=1,format=yuv420p[v]'
& $ffmpeg -hide_banner -loglevel error -y `
    -f lavfi -i 'color=c=0x14141f:s=1280x720:r=30' -i $wav `
    -filter_complex $filter -map '[v]' -map '1:a' `
    -c:v libx264 -preset veryfast -crf 23 -c:a aac -b:a 128k -shortest $Output
if ($LASTEXITCODE -ne 0) { throw "FFmpeg failed with exit code $LASTEXITCODE" }
Remove-Item -LiteralPath $wav
Write-Host "Sample video created: $Output"
