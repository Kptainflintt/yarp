# Guide de Test YARP - Phase 1

## Prérequis

1. Machine Alpine Linux (ou VM)
2. Accès root
3. Connexion Internet (pour apk)

## Étape 1: Préparation

### Sur votre machine de développement

```bash
# Donner les permissions d'exécution
chmod +x src/core/yarp
chmod +x src/core/yarp-apply.sh
chmod +x src/core/yarp_config.py
chmod +x src/modules/network.py
chmod +x src/modules/routing.py
chmod +x install/setup.sh
chmod +x tests/test-phase1.sh

# Lancer les tests de validation
./tests/test-phase1.sh
