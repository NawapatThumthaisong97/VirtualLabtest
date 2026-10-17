# ==============================================================================
# Setup Authentication Secrets in Kubernetes (PowerShell)
# ==============================================================================

param(
  [string]$Namespace = "virtual-lab",
  [string]$JwtSecretKey = "",
  [string]$GoogleClientId = "placeholder-client-id.apps.googleusercontent.com",
  [string]$GoogleClientSecret = "placeholder-client-secret",
  [string]$DatabaseUrl = "postgresql://postgres:password@virtual-lab-db:5432/virtual_lab"
)

Write-Host "==> Ensuring namespace '$Namespace' exists..."
kubectl create namespace "$Namespace" --dry-run=client -o yaml | kubectl apply -f -

if (-not $JwtSecretKey) {
  $bytes = New-Object byte[] 32
  [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  $JwtSecretKey = [System.BitConverter]::ToString($bytes) -replace '-'
}

Write-Host "==> Applying 'jwt-secret'..."
kubectl create secret generic jwt-secret `
  --namespace="$Namespace" `
  --from-literal=secret-key="$JwtSecretKey" `
  --from-literal=algorithm="HS256" `
  --dry-run=client -o yaml | kubectl apply -f -

$cookieBytes = New-Object byte[] 24
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($cookieBytes)
$CookieSecret = [System.Convert]::ToBase64String($cookieBytes)

Write-Host "==> Applying 'oauth2-proxy-secret'..."
kubectl create secret generic oauth2-proxy-secret `
  --namespace="$Namespace" `
  --from-literal=cookie-secret="$CookieSecret" `
  --dry-run=client -o yaml | kubectl apply -f -

Write-Host "==> Applying 'google-oauth-secret'..."
kubectl create secret generic google-oauth-secret `
  --namespace="$Namespace" `
  --from-literal=client-id="$GoogleClientId" `
  --from-literal=client-secret="$GoogleClientSecret" `
  --dry-run=client -o yaml | kubectl apply -f -

Write-Host "==> Applying 'database-secret'..."
kubectl create secret generic database-secret `
  --namespace="$Namespace" `
  --from-literal=database-url="$DatabaseUrl" `
  --dry-run=client -o yaml | kubectl apply -f -

Write-Host "==> All authentication secrets successfully provisioned in namespace '$Namespace'."

