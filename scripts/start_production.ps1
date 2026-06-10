# Production server (gunicorn). Requires: pip install gunicorn
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:FLASK_ENV = "production"
gunicorn -w 2 -b 0.0.0.0:8000 --timeout 120 "run:app"
