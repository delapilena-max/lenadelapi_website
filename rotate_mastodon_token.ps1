param([string])
# PowerShell helper to rotate Mastodon token into SecretStore
if(-not ){
    Write-Host 'Enter new Mastodon access token (paste then press Enter):'
     = Read-Host -AsSecureString
    Dnd4life! = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR())
} else {
    Dnd4life! = 
}
try{
    Import-Module Microsoft.PowerShell.SecretManagement -ErrorAction SilentlyContinue
    Import-Module Microsoft.PowerShell.SecretStore -ErrorAction SilentlyContinue
    Set-Secret -Name 'MASTODON_ACCESS_TOKEN' -Secret Dnd4life!
    Write-Host 'Token stored in SecretStore.'
} catch {
    Write-Host 'Failed to store token. Run this script from an elevated PowerShell or ensure SecretStore modules are installed.'; exit 1
}
