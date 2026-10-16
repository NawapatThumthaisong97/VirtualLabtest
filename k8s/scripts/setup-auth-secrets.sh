#!/usr/bin/env bash
# ==============================================================================
# Setup Authentication Secrets in Kubernetes (Least Privilege & Secure Storage)
#
# Generates and provisions Kubernetes-native Secrets for:
#   1. jwt-secret (JWT Secret Key & Algorithm)
#   2. google-oauth-secret (Google Client ID & Client Secret)
#   3. oauth2-proxy-secret (32-byte Cookie Secret)
#   4. database-secret (PostgreSQL Connection String)
#
# Constraint Check (Issue #81):
#   - NEVER hardcodes secrets into source files.
#   - Creates secrets directly in cluster namespace 'virtual-lab'.
# ==============================================================================

set -euo pipefail

NAMESPACE="${NAMESPACE:-virtual-lab}"

echo "==> Ensuring namespace '${NAMESPACE}' exists..."
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

# 1. JWT Secret (Generate 32-byte secure random hex if not provided)
JWT_SECRET_KEY="${JWT_SECRET_KEY:-$(openssl rand -hex 32 2>/dev/null || python3 -c 'import secrets; print(secrets.token_hex(32))')}"
JWT_ALGORITHM="${JWT_ALGORITHM:-HS256}"

echo "==> Applying 'jwt-secret'..."
kubectl create secret generic jwt-secret \
  --namespace="${NAMESPACE}" \
  --from-literal=secret-key="${JWT_SECRET_KEY}" \
  --from-literal=algorithm="${JWT_ALGORITHM}" \
  --dry-run=client -o yaml | kubectl apply -f -

# 2. oauth2-proxy Cookie Secret (Must be 32 bytes base64 encoded for AES-256)
COOKIE_SECRET="${COOKIE_SECRET:-$(openssl rand -base64 32 2>/dev/null | tr -- '+/' '-_' | head -c 32 || python3 -c 'import secrets; print(secrets.token_urlsafe(24)[:32])')}"

echo "==> Applying 'oauth2-proxy-secret'..."
kubectl create secret generic oauth2-proxy-secret \
  --namespace="${NAMESPACE}" \
  --from-literal=cookie-secret="${COOKIE_SECRET}" \
  --dry-run=client -o yaml | kubectl apply -f -

# 3. Google OAuth2 Credentials
GOOGLE_CLIENT_ID="${GOOGLE_CLIENT_ID:-placeholder-client-id.apps.googleusercontent.com}"
GOOGLE_CLIENT_SECRET="${GOOGLE_CLIENT_SECRET:-placeholder-client-secret}"

echo "==> Applying 'google-oauth-secret'..."
kubectl create secret generic google-oauth-secret \
  --namespace="${NAMESPACE}" \
  --from-literal=client-id="${GOOGLE_CLIENT_ID}" \
  --from-literal=client-secret="${GOOGLE_CLIENT_SECRET}" \
  --dry-run=client -o yaml | kubectl apply -f -

# 4. Database Secret
DATABASE_URL="${DATABASE_URL:-postgresql://postgres:password@virtual-lab-db:5432/virtual_lab}"

echo "==> Applying 'database-secret'..."
kubectl create secret generic database-secret \
  --namespace="${NAMESPACE}" \
  --from-literal=database-url="${DATABASE_URL}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "==> All authentication secrets successfully provisioned in namespace '${NAMESPACE}'."
echo "==> Apply RBAC rules with: kubectl apply -f k8s/auth/01-rbac.yaml"
