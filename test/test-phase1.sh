#!/bin/bash
# Script de test Phase 1

set -e

echo "==================================="
echo "YARP Phase 1 - Tests"
echo "==================================="

# Couleurs pour l'affichage
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

test_pass() {
    echo -e "${GREEN}✓ $1${NC}"
}

test_fail() {
    echo -e "${RED}✗ $1${NC}"
    exit 1
}

# Test 1: Vérifier la structure des fichiers
echo ""
echo "Test 1: Structure des fichiers"
for file in \
    "src/core/yarp" \
    "src/core/yarp-apply.sh" \
    "src/core/yarp_config.py" \
    "src/core/yarp_logger.py" \
    "src/modules/network.py" \
    "src/modules/routing.py" \
    "src/modules/nat.py" \
    "src/modules/dns.py" \
    "src/modules/firewall.py" \
    "src/init/yarp-motd.sh" \
    "install/setup.sh"
do
    if [ -f "$file" ]; then
        test_pass "$file existe"
    else
        test_fail "$file manquant"
    fi
done

# Test 2: Vérifier les permissions exécutables
echo ""
echo "Test 2: Permissions exécutables"
for file in \
    "src/core/yarp" \
    "src/core/yarp-apply.sh" \
    "install/setup.sh"
do
    if [ -x "$file" ]; then
        test_pass "$file est exécutable"
    else
        test_fail "$file n'est pas exécutable"
    fi
done

# Test 3: Vérifier la syntaxe Python
echo ""
echo "Test 3: Syntaxe Python"
for file in \
    "src/core/yarp_config.py" \
    "src/core/yarp_logger.py" \
    "src/modules/network.py" \
    "src/modules/routing.py" \
    "src/modules/nat.py" \
    "src/modules/dns.py" \
    "src/modules/firewall.py"
do
    if python3 -m py_compile "$file" 2>/dev/null; then
        test_pass "Syntaxe Python valide: $file"
    else
        test_fail "Erreur syntaxe Python: $file"
    fi
done

# Test 4: Vérifier la syntaxe Bash
echo ""
echo "Test 4: Syntaxe Bash"
for file in \
    "src/core/yarp" \
    "src/core/yarp-apply.sh" \
    "install/setup.sh" \
    "src/init/yarp-motd.sh"
do
    if bash -n "$file" 2>/dev/null; then
        test_pass "Syntaxe Bash valide: $file"
    else
        test_fail "Erreur syntaxe Bash: $file"
    fi
done

# Test 5: Validation YAML
echo ""
echo "Test 5: Configuration YAML"
if [ -f "config/yarp.yaml.example" ]; then
    if python3 -c "import yaml; yaml.safe_load(open('config/yarp.yaml.example'))" 2>/dev/null; then
        test_pass "YAML exemple valide"
    else
        test_fail "YAML exemple invalide"
    fi
else
    test_fail "Fichier config/yarp.yaml.example manquant"
fi

echo ""
echo "==================================="
echo "Tous les tests sont passés !"
echo "==================================="
