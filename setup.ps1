$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
python (Join-Path $Root "setup") @args
exit $LASTEXITCODE
