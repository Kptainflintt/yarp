#!/bin/sh
# YARP Installation Script
set -e

PREFIX="/opt/yarp"
BINDIR="$PREFIX/bin"
COREDIR="$PREFIX/core"
MODULEDIR="$PREFIX/modules"
CONFIGDIR="/etc/yarp"
YARP_VERSION=$(cat VERSION 2>/dev/null || echo "inconnue")

# Vérification root
if [ "$(id -u)" -ne 0 ]; then
    echo "Erreur: Ce script doit être exécuté en root"
    exit 1
fi

echo "==================================="
echo "Installation de YARP v${YARP_VERSION}"
echo "==================================="

# Installation des dépendances
echo ""
echo "[1/7] Installation des dépendances..."
apk update
apk add --no-cache \
    python3 \
    py3-yaml \
    iproute2 \
    iptables \
    ip6tables \
    bash \
    curl

# Création des répertoires
echo ""
echo "[2/7] Création de la structure..."
mkdir -p "$BINDIR"
mkdir -p "$COREDIR"
mkdir -p "$MODULEDIR"
mkdir -p "$CONFIGDIR"
mkdir -p /var/log/yarp
mkdir -p /var/run/yarp

# Copie des fichiers core
echo ""
echo "[3/7] Installation des fichiers core..."
install -m 755 src/core/yarp "$BINDIR/yarp"
install -m 755 src/core/yarp-apply.sh "$BINDIR/yarp-apply"
install -m 755 src/core/yarp-check.sh "$BINDIR/yarp-check"
install -m 644 src/core/yarp_config.py "$COREDIR/yarp_config.py"
install -m 644 src/core/yarp_logger.py "$COREDIR/yarp_logger.py"
install -m 644 VERSION "$PREFIX/VERSION"

# Copie des modules
echo ""
echo "[4/7] Installation des modules..."
install -m 644 src/modules/network.py "$MODULEDIR/network.py"
install -m 644 src/modules/routing.py "$MODULEDIR/routing.py"
install -m 644 src/modules/nat.py "$MODULEDIR/nat.py"
install -m 644 src/modules/dns.py "$MODULEDIR/dns.py"

# Création des __init__.py pour Python
touch "$COREDIR/__init__.py"
touch "$MODULEDIR/__init__.py"

echo ""
echo "[5/7] Installation du service OpenRC..."
install -m 755 src/init/yarp /etc/init.d/yarp
echo ""

# Liens symboliques
echo ""
echo "[6/7] Création des liens symboliques..."
ln -sf "$BINDIR/yarp" /usr/local/bin/yarp
ln -sf "$BINDIR/yarp-apply" /usr/local/bin/yarp-apply

# Configuration système
echo ""
echo "[7/7] Configuration système..."

# Activer le forwarding
cat > /etc/sysctl.d/yarp.conf << 'EOF'
# YARP System Configuration
net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 1
net.ipv4.conf.all.rp_filter = 0
net.ipv4.conf.default.rp_filter = 0
EOF

sysctl -p /etc/sysctl.d/yarp.conf > /dev/null 2>&1

# Configuration exemple
if [ ! -f "$CONFIGDIR/config.yaml" ]; then
    if [ -f config/yarp.yaml.example ]; then
        cp config/yarp.yaml.example "$CONFIGDIR/config.yaml"
        echo "Configuration d'exemple installée"
    fi
fi

# Permissions
chown -R root:root "$PREFIX"
chmod 755 "$BINDIR"/*

echo ""
echo "==================================="
echo "✓ Installation terminée avec succès !"
echo "==================================="
echo ""
echo "Emplacement: $PREFIX"
echo "Configuration: $CONFIGDIR/config.yaml"
echo ""
echo "Commandes disponibles:"
echo "  yarp version      - Version de YARP"
echo "  yarp validate     - Valider la config"
echo "  yarp show         - Afficher la config"
echo "  yarp apply        - Appliquer la config"
echo ""
echo "Prochaine étape:"
echo "  1. Éditer: $CONFIGDIR/config.yaml"
echo "  2. Valider: yarp validate"
echo "  3. Appliquer: yarp apply"
echo ""
