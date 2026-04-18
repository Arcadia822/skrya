param(
    [Parameter(Mandatory = $true)]
    [string]$Topic,
    [string]$CodexPath
)

$Root = (Resolve-Path (Split-Path -Parent $PSScriptRoot)).Path
$TopicPath = Join-Path $Root "topics\\$Topic"
$SkillPath = Join-Path $Root "skills\\digest\\SKILL.md"

if (-not (Test-Path -LiteralPath $TopicPath)) {
    throw "Topic '$Topic' not found under $TopicPath"
}

if (-not $CodexPath) {
    $CodexPath = (Get-Command codex.exe -ErrorAction Stop).Source
}

$Prompt = @"
Start a new agent session for this workspace.
Use `$digest at $SkillPath to collect the latest digest for topic `$Topic.
Read and use the topic files under $TopicPath.
Use real data by default, not sample-only reasoning.
Return the digest in Chinese as a single-paragraph numbered digest.
"@

$PromptFile = Join-Path ([System.IO.Path]::GetTempPath()) ("digest-session-" + [System.Guid]::NewGuid().ToString() + ".txt")
Set-Content -LiteralPath $PromptFile -Value $Prompt -Encoding UTF8

$LaunchCommand = "& '$CodexPath' exec (Get-Content -LiteralPath '$PromptFile' -Raw)"
$EncodedCommand = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($LaunchCommand))

Start-Process powershell -WorkingDirectory $Root -ArgumentList "-NoExit", "-EncodedCommand", $EncodedCommand
