# Weekly discovery cron for Windows Task Scheduler.
# Set DISCOVERY_CRON_SECRET and APP_URL in your environment or edit below.
$AppUrl = $env:APP_URL
if (-not $AppUrl) { $AppUrl = "http://127.0.0.1:8000" }
$Secret = $env:DISCOVERY_CRON_SECRET
if (-not $Secret) {
    Write-Error "DISCOVERY_CRON_SECRET is not set."
    exit 1
}
Invoke-WebRequest -Method POST -Uri "$AppUrl/admin/ingest" -Headers @{ "X-Cron-Secret" = $Secret } -UseBasicParsing
