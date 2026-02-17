#!/bin/bash
# YARP - Vérification de l'installation
# Vérifie que YARP est correctement installé et fonctionnel
# Usage: yarp check

set -e

echo "==================================="
echo "YARP - Vérification de l'installation"
echo "==================================="

# Couleurs
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

PASS=0
FAIL=0
WARN=0

test_pass() {
    echo -e "${GREEN}  ✓ $1${NC}"
    PASS=$((PASS + 1))
}

test_fail() {
    echo -e "${RED}  ✗ $1${NC}"
    FAIL=$((FAIL + 1))
}

test_warn() {
    echo -e "${YELLOW}  ! $1${NC}"
    WARN=$((WARN + 1))
}

# Vérification root
if [ "$(id -u)" -ne 0 ]; then
    echo "Note: certains tests nécessitent root. Résultats partiels possibles."
    echo ""
fi

# =============================================
# 1. Structure des fichiers installés
# =============================================
echo ""
echo "1. Fichiers installés"

for file in \
    /opt/yarp/bin/yarp \
    /opt/yarp/bin/yarp-apply \
    /opt/yarp/bin/yarp-check \
    /opt/yarp/core/yarp_config.py \
    /opt/yarp/core/yarp_logger.py \
    /opt/yarp/modules/network.py \
    /opt/yarp/modules/routing.py \
    /opt/yarp/modules/nat.py \
    /opt/yarp/modules/dns.py \
    /opt/yarp/VERSION
do
    if [ -f "$file" ]; then
        test_pass "$file"
    else
        test_fail "$file manquant"
    fi
done

# =============================================
# 2. Liens symboliques
# =============================================
echo ""
echo "2. Liens symboliques"

for link in /usr/local/bin/yarp /usr/local/bin/yarp-apply; do
    if [ -L "$link" ]; then
        target=$(readlink "$link")
        test_pass "$link -> $target"
    elif [ -f "$link" ]; then
        test_warn "$link existe mais n'est pas un lien symbolique"
    else
        test_fail "$link manquant"
    fi
done

# =============================================
# 3. Permissions
# =============================================
echo ""
echo "3. Permissions d'exécution"

for file in /opt/yarp/bin/yarp /opt/yarp/bin/yarp-apply; do
    if [ -x "$file" ]; then
        test_pass "$file est exécutable"
    else
        test_fail "$file n'est pas exécutable"
    fi
done

# =============================================
# 4. Dépendances système
# =============================================
echo ""
echo "4. Dépendances système"

for cmd in python3 ip iptables ip6tables bash; do
    if command -v "$cmd" > /dev/null 2>&1; then
        test_pass "$cmd disponible"
    else
        test_fail "$cmd non trouvé"
    fi
done

# PyYAML
if python3 -c "import yaml" 2>/dev/null; then
    test_pass "python3 yaml (PyYAML) disponible"
else
    test_fail "python3 yaml (PyYAML) non disponible"
fi

# =============================================
# 5. Configuration
# =============================================
echo ""
echo "5. Configuration"

if [ -f /etc/yarp/config.yaml ]; then
    test_pass "/etc/yarp/config.yaml existe"

    # Validation YAML
    if python3 -c "import yaml; yaml.safe_load(open('/etc/yarp/config.yaml'))" 2>/dev/null; then
        test_pass "YAML syntaxiquement valide"
    else
        test_fail "YAML syntaxiquement invalide"
    fi

    # Validation YARP
    if yarp validate > /dev/null 2>&1; then
        test_pass "yarp validate OK"
    else
        test_fail "yarp validate échoue"
    fi
else
    test_fail "/etc/yarp/config.yaml manquant"
    test_warn "Exécuter: cp /chemin/vers/yarp/config/yarp.yaml.example /etc/yarp/config.yaml"
fi

# =============================================
# 6. CLI
# =============================================
echo ""
echo "6. Commandes CLI"

# version
if yarp version > /dev/null 2>&1; then
    version_output=$(yarp version 2>&1)
    test_pass "yarp version -> $version_output"
else
    test_fail "yarp version échoue"
fi

# help
if yarp help > /dev/null 2>&1; then
    test_pass "yarp help OK"
else
    test_fail "yarp help échoue"
fi

# show (nécessite une config valide)
if [ -f /etc/yarp/config.yaml ]; then
    if yarp show > /dev/null 2>&1; then
        test_pass "yarp show OK"
    else
        test_fail "yarp show échoue"
    fi
fi

# =============================================
# 7. Service OpenRC
# =============================================
echo ""
echo "7. Service OpenRC"

if [ -f /etc/init.d/yarp ]; then
    test_pass "/etc/init.d/yarp installé"

    if [ -x /etc/init.d/yarp ]; then
        test_pass "/etc/init.d/yarp exécutable"
    else
        test_fail "/etc/init.d/yarp non exécutable"
    fi

    # Vérifier si dans un runlevel
    if rc-update show 2>/dev/null | grep -q yarp; then
        runlevel=$(rc-update show 2>/dev/null | grep yarp | awk '{print $NF}')
        test_pass "Service dans le runlevel: $runlevel"
    else
        test_warn "Service non activé au démarrage (rc-update add yarp default)"
    fi
else
    test_fail "/etc/init.d/yarp manquant"
fi

# =============================================
# 8. Configuration noyau
# =============================================
echo ""
echo "8. Configuration noyau (IP forwarding)"

if [ -f /etc/sysctl.d/yarp.conf ]; then
    test_pass "/etc/sysctl.d/yarp.conf présent"
else
    test_fail "/etc/sysctl.d/yarp.conf manquant"
fi

ipv4_fwd=$(cat /proc/sys/net/ipv4/ip_forward 2>/dev/null)
if [ "$ipv4_fwd" = "1" ]; then
    test_pass "IPv4 forwarding activé"
else
    test_fail "IPv4 forwarding désactivé"
fi

ipv6_fwd=$(cat /proc/sys/net/ipv6/conf/all/forwarding 2>/dev/null)
if [ "$ipv6_fwd" = "1" ]; then
    test_pass "IPv6 forwarding activé"
elif [ -z "$ipv6_fwd" ]; then
    test_warn "IPv6 forwarding: impossible à vérifier"
else
    test_fail "IPv6 forwarding désactivé"
fi

# =============================================
# 9. Répertoires de travail
# =============================================
echo ""
echo "9. Répertoires de travail"

for dir in /var/log/yarp /var/run/yarp; do
    if [ -d "$dir" ]; then
        test_pass "$dir existe"
    else
        test_fail "$dir manquant"
    fi
done

# =============================================
# Résumé
# =============================================
echo ""
echo "==================================="
TOTAL=$((PASS + FAIL + WARN))
echo -e "Résultats: ${GREEN}${PASS} OK${NC} / ${RED}${FAIL} ERREUR${NC} / ${YELLOW}${WARN} AVERTISSEMENT${NC} (${TOTAL} tests)"
echo "==================================="

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi

exit 0
