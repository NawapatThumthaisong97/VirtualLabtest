#!/bin/bash
# ตรวจสอบการติดตั้ง SkyPilot Node

echo "========================================="
echo "  SkyPilot Node Installation Check"
echo "========================================="
echo ""

# ตรวจสอบ Nodes
echo "📦 K3s Nodes:"
kubectl get nodes -o wide
echo ""

# ตรวจสอบ Nginx Ingress Service
echo "🔷 Nginx Ingress Service:"
NGINX_SVC=$(kubectl get svc -n skypilot-ingress -l app.kubernetes.io/component=controller -o jsonpath='{.items[0].metadata.name}')
kubectl get svc -n skypilot-ingress -l app.kubernetes.io/component=controller
echo ""
echo "   Service Name: $NGINX_SVC"
echo "   ⚠️  Use this for Cloudflare: ${NGINX_SVC}.skypilot-ingress.svc.cluster.local:80"
echo ""

# ตรวจสอบ Nginx Ingress Pods
echo "🔷 Nginx Ingress Pods:"
kubectl get pods -n skypilot-ingress -l app.kubernetes.io/component=controller -o wide
echo ""

# ตรวจสอบ Cloudflare Tunnel
echo "☁️  Cloudflare Tunnel:"
kubectl get pods -n skypilot-ingress -l app=cloudflare-tunnel -o wide
echo ""

# ตรวจสอบ SkyPilot Service
echo "🚀 SkyPilot Service:"
SKYPILOT_SVC=$(kubectl get svc -n skypilot -o jsonpath='{.items[0].metadata.name}')
kubectl get svc -n skypilot
echo ""
echo "   Service Name: $SKYPILOT_SVC"
echo ""

# ตรวจสอบ SkyPilot Pods
echo "🚀 SkyPilot Pods:"
kubectl get pods -n skypilot -o wide
echo ""

# ตรวจสอบ Ingress Configuration
echo "🌐 Ingress Configuration:"
kubectl get ingress -n skypilot
echo ""
echo "   Ingress Details:"
kubectl describe ingress -n skypilot | grep -E "Name:|Host:|Path:|Backend:"
echo ""

# สรุป
NGINX_READY=$(kubectl get pods -n skypilot-ingress -l app.kubernetes.io/component=controller --no-headers 2>/dev/null | grep -c Running)
TUNNEL_READY=$(kubectl get pods -n skypilot-ingress -l app=cloudflare-tunnel --no-headers 2>/dev/null | grep -c Running)
SKYPILOT_READY=$(kubectl get pods -n skypilot --no-headers 2>/dev/null | grep -c Running)

echo "========================================="
echo "  Summary"
echo "========================================="
echo "Nginx Ingress: $NGINX_READY running"
echo "Cloudflare Tunnel: $TUNNEL_READY running"
echo "SkyPilot API: $SKYPILOT_READY running"
echo ""

if [ "$NGINX_READY" -gt 0 ] && [ "$TUNNEL_READY" -gt 0 ] && [ "$SKYPILOT_READY" -gt 0 ]; then
  echo "✅ All components running!"
  echo ""
  echo "========================================="
  echo "  ⚠️  NEXT STEP REQUIRED"
  echo "========================================="
  echo ""
  echo "Configure Cloudflare Tunnel Dashboard:"
  echo ""
  echo "1. Go to: https://one.dash.cloudflare.com/"
  echo "2. Networks -> Tunnels -> Configure tunnel"
  echo "3. Public Hostname -> Add:"
  echo "   - Subdomain: skypilot"
  echo "   - Domain: bell-lab.space"
  echo "   - Type: HTTP"
  echo "   - URL: ${NGINX_SVC}.skypilot-ingress.svc.cluster.local:80"
  echo ""
  echo "4. Wait 1-2 minutes, then access:"
  echo "   🌐 https://skypilot.bell-lab.space"
  echo ""
else
  echo "⚠️  Some components not ready"
  echo ""
  echo "Check logs:"
  echo "  kubectl logs -n skypilot-ingress deployment/cloudflare-tunnel"
  echo "  kubectl logs -n skypilot <pod-name>"
fi
echo ""
