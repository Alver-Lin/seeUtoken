$ErrorActionPreference = 'Stop'
$Client = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
$Keys = @(
    "HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$Client",
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\$Client",
    "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$Client"
)
foreach ($Key in $Keys) {
    $Version = (Get-ItemProperty -Path $Key -Name pv -ErrorAction SilentlyContinue).pv
    if ($Version -and $Version -ne '0.0.0.0') { Write-Host "WebView2 $Version is installed."; exit 0 }
}
$Installer = Join-Path $env:TEMP 'MicrosoftEdgeWebview2Setup.exe'
Invoke-WebRequest 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -OutFile $Installer
$Signature = Get-AuthenticodeSignature $Installer
if ($Signature.Status -ne 'Valid' -or $Signature.SignerCertificate.Subject -notmatch 'Microsoft Corporation') {
    throw 'Invalid Microsoft WebView2 installer signature.'
}
$Process = Start-Process $Installer -ArgumentList '/silent', '/install' -PassThru -Wait
if ($Process.ExitCode -ne 0) { throw "WebView2 installer exited with $($Process.ExitCode)" }
