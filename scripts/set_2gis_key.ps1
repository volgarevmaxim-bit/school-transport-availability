# set_2gis_key.ps1 — ввод ключа 2ГИС вслепую, запись в User-окружение (реестр)
# Запуск: powershell -ExecutionPolicy Bypass -File C:\Users\volga\school-transport\scripts\set_2gis_key.ps1
# После запуска набери/вставь ключ и Enter. На экран выведется только префикс ключа.
$sec = Read-Host "2GIS API key" -AsSecureString
$key = [System.Net.NetworkCredential]::new("", $sec).Password
[Environment]::SetEnvironmentVariable("2GIS_API_KEY", $key, "User")
$env:2GIS_API_KEY = $key   # для текущего окна
$key = $null
$sec = $null
$env:2GIS_API_KEY.Substring(0,6) + "..."
