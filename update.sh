#!/bin/sh
# YARP Update Script
# Met à jour une installation existante après un git pull
# Usage: git pull && ./update.sh
set -e

PREFIX="/opt/yarp"
BINDIR="$PREFIX/bin"
COREDIR="$PREFIX/core"
MODULEDIR="$PREFIX/modules"
YARP_VERSION=$(cat VERSION 2>/dev/null || echo "inconnue")

# Vérification root
if [ "$(id -u)" -ne 0 ]; then
    echo "Erreur: Ce script doit être exécuté en root"
    exit 1
fi

# Vérifier que YARP est déjà installé
if [ ! -d "$BINDIR" ] || [ ! -d "$COREDIR" ] || [ ! -d "$MODULEDIR" ]; then
    echo "Erreur: YARP ne semble pas installé dans $PREFIX"
    echo "Utilisez install.sh pour une première installation"
    exit 1
fi

echo "==================================="
echo "YARP - Mise à jour vers v${YARP_VERSION}"
echo "==================================="

# Mise à jour des fichiers core
echo ""
echo "[1/4] Mise à jour des fichiers core..."
cp -f src/core/yarp "$BINDIR/yarp"
cp -f src/core/yarp-apply.sh "$BINDIR/yarp-apply"
cp -f src/core/yarp-check.sh "$BINDIR/yarp-check"
cp -f src/core/yarp_config.py "$COREDIR/yarp_config.py"
cp -f src/core/yarp_logger.py "$COREDIR/yarp_logger.py"
cp -f VERSION "$PREFIX/VERSION"

# Permissions core
chmod 755 "$BINDIR/yarp" "$BINDIR/yarp-apply" "$BINDIR/yarp-check"
chmod 644 "$COREDIR/yarp_config.py" "$COREDIR/yarp_logger.py"

# Mise à jour des modules
echo "[2/4] Mise à jour des modules..."
for module in src/modules/*.py; do
    cp -f "$module" "$MODULEDIR/$(basename "$module")"
    chmod 644 "$MODULEDIR/$(basename "$module")"
done

# Mise à jour du service OpenRC
echo "[3/4] Mise à jour du service OpenRC..."
cp -f src/init/yarp /etc/init.d/yarp
chmod 755 /etc/init.d/yarp

# Permissions globales
echo "[4/4] Vérification des permissions..."
chown -R root:root "$PREFIX"

echo ""
echo "==================================="
echo "Mise à jour terminée (v${YARP_VERSION})"
echo "==================================="
echo ""
echo "Fichiers mis à jour :"
echo "  Core    : yarp, yarp-apply, yarp-check, yarp_config.py, yarp_logger.py"
echo "  Modules :"
for module in "$MODULEDIR"/*.py; do
    [ "$(basename "$module")" = "__init__.py" ] && continue
    echo "    - $(basename "$module")"
done
echo ""
echo "Note: /etc/yarp/config.yaml n'est PAS modifié par la mise à jour."
echo "  Consultez config/yarp.yaml.example pour les nouvelles options."
echo ""
