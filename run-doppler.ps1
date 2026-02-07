# Run the bot with secrets from Doppler. Requires: doppler login, doppler setup
Set-Location $PSScriptRoot
doppler run -- py run.py
