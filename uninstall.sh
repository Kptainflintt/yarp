#!/bin/sh
# YARP Uninstallation Script
set -e

PREFIX="/opt/yarp"
CONFIGDIR="/etc/yarp"

# Vérification root
if [ "$(id -u)" -ne 0 ]; then
    echo "Erreur: Ce script doit être exécuté en root"
    exit 1
fi

echo "==================================="
echo "Désinstallation de YARP"
echo "==================================="

# Confirmation
printf "\nCette opération va supprimer YARP et sa configuration.\n"
printf "Continuer ? [y/N] "
read -r confirm
case "$confirm" in
    [yYoO]) ;;
    *)
        echo "Désinstallation annulée."
        exit 0
        ;;
esac

# Arrêt du service OpenRC
echo ""
echo "[1/7] Arrêt du service..."
if rc-service yarp status > /dev/null 2>&1; then
    rc-service yarp stop 2>/dev/null || true
fi
rc-update del yarp default 2>/dev/null || true

# Suppression du service OpenRC
echo "[2/7] Suppression du service OpenRC..."
rm -f /etc/init.d/yarp

# Suppression des liens symboliques
echo "[3/7] Suppression des liens symboliques..."
rm -f /usr/local/bin/yarp
rm -f /usr/local/bin/yarp-apply

# Suppression de la configuration sysctl
echo "[4/7] Suppression de la configuration sysctl..."
rm -f /etc/sysctl.d/yarp.conf
# Recharger sysctl sans la conf YARP (le forwarding sera désactivé)
sysctl --system > /dev/null 2>&1 || true

# Restauration de /etc/network/interfaces si backup existe
echo "[5/7] Restauration de la configuration réseau Alpine..."
if [ -f /etc/network/interfaces.yarp-backup ]; then
    cp /etc/network/interfaces.yarp-backup /etc/network/interfaces
    rm -f /etc/network/interfaces.yarp-backup
    echo "  Configuration réseau Alpine restaurée depuis le backup"
fi

# Suppression des fichiers YARP
echo "[6/7] Suppression des fichiers YARP..."
rm -rf "$PREFIX"
rm -rf /var/log/yarp
rm -rf /var/run/yarp
rm -rf /var/lib/yarp

# Suppression de la configuration
echo "[7/7] Suppression de la configuration..."
rm -rf "$CONFIGDIR"

echo ""
echo "==================================="
echo "Désinstallation terminée."
echo "==================================="
echo ""
echo "Note: les paquets installés par YARP (python3, iproute2,"
echo "iptables, etc.) n'ont pas été supprimés."
echo "Pour les supprimer manuellement :"
echo "  apk del python3 py3-yaml iproute2 iptables ip6tables curl"
echo ""
