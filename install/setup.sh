#!/bin/sh
# YARP Installer - Phase 1
# Installation d'Alpine Linux avec YARP

set -e

YARP_VERSION="0.1.0"
YARP_DIR="/opt/yarp"
CONFIG_DIR="/etc/yarp"

echo "==================================="
echo "YARP Installation - Version $YARP_VERSION"
echo "==================================="

# Fonction de logging
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

error() {
    echo "[ERROR] $1" >&2
    exit 1
}

# Vérification des prérequis
check_prerequisites() {
    log "Vérification des prérequis..."
    
    if [ "$(id -u)" -ne 0 ]; then
        error "Ce script doit être exécuté en root"
    fi
    
    if ! grep -q "Alpine Linux" /etc/os-release 2>/dev/null; then
        error "Ce script nécessite Alpine Linux"
    fi
}

# Installation des paquets de base
install_packages() {
    log "Installation des paquets requis..."
    
    # Mise à jour des dépôts
    apk update
    
    # Installation des paquets essentiels
    # Note: py3-yaml est dans le dépôt community, il faut l'activer
    apk add --no-cache \
        python3 \
        py3-yaml \
        iproute2 \
        iptables \
        ip6tables \
        dhcpcd \
        bash \
        nano \
        curl \
        iputils \
        make
    
    log "Paquets installés avec succès"
}

# Configuration du système de base
configure_system() {
    log "Configuration du système..."
    
    # Activer le forwarding IP
    cat > /etc/sysctl.d/yarp.conf <<EOF
# YARP System Configuration
net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 1
net.ipv4.conf.all.rp_filter = 0
net.ipv4.conf.default.rp_filter = 0
EOF
    
    sysctl -p /etc/sysctl.d/yarp.conf
    
    log "Configuration système appliquée"
}

# Création de la structure de répertoires
create_directories() {
    log "Création des répertoires YARP..."
    
    mkdir -p $YARP_DIR/bin
    mkdir -p $YARP_DIR/core
    mkdir -p $YARP_DIR/modules
    mkdir -p $YARP_DIR/lib
    mkdir -p $CONFIG_DIR
    mkdir -p /var/log/yarp
    mkdir -p /var/run/yarp
    
    log "Répertoires créés"
}

# Installation des fichiers YARP
install_yarp_files() {
    log "Installation des fichiers YARP..."
    
    # Vérifier qu'on est dans le bon répertoire
    if [ ! -f "Makefile" ]; then
        error "Makefile introuvable. Exécutez ce script depuis le répertoire racine du projet"
    fi
    
    # Utiliser Make pour l'installation
    make install
    
    log "Fichiers YARP installés"
}

# Configuration d'exemple
setup_config() {
    log "Configuration d'exemple..."
    
    if [ ! -f "$CONFIG_DIR/config.yaml" ]; then
        if [ -f "config/yarp.yaml.example" ]; then
            cp config/yarp.yaml.example $CONFIG_DIR/config.yaml
            log "Configuration d'exemple copiée vers $CONFIG_DIR/config.yaml"
        else
            # Créer une configuration minimale
            cat > $CONFIG_DIR/config.yaml <<EOF
# Configuration YARP par défaut
system:
  hostname: yarp-router
  domain: local
  timezone: UTC

interfaces: {}

routing:
  static: []

firewall:
  default:
    input: accept
    forward: accept
    output: accept
  stateful: false
  rules: []
EOF
            log "Configuration minimale créée"
        fi
    else
        log "Configuration existante conservée"
    fi
}

# Service init.d
install_service() {
    log "Installation du service init..."
    
    cat > /etc/init.d/yarp <<'EOF'
#!/sbin/openrc-run

name="yarp"
description="YARP Network Configuration Service"

depend() {
    need net
    before firewall
}

start() {
    ebegin "Applying YARP configuration"
    /usr/local/bin/yarp-apply
    eend $?
}

stop() {
    ebegin "Stopping YARP"
    # Pour l'instant, pas d'action au stop
    eend 0
}

reload() {
    ebegin "Reloading YARP configuration"
    /usr/local/bin/yarp-apply
    eend $?
}
EOF
    
    chmod +x /etc/init.d/yarp
    
    # Activer le service au démarrage
    rc-update add yarp default 2>/dev/null || true
    
    log "Service installé et activé"
}

# Vérification post-installation
verify_installation() {
    log "Vérification de l'installation..."
    
    # Vérifier les commandes
    if ! command -v yarp >/dev/null 2>&1; then
        error "Commande 'yarp' non trouvée après installation"
    fi
    
    # Vérifier Python et modules
    if ! python3 -c "import yaml" 2>/dev/null; then
        error "Module Python yaml non disponible"
    fi
    
    # Vérifier la configuration
    if [ ! -f "$CONFIG_DIR/config.yaml" ]; then
        error "Fichier de configuration non trouvé"
    fi
    
    log "Vérification OK"
}

# Affichage des informations finales
show_summary() {
    echo ""
    echo "==================================="
    echo "Installation YARP terminée !"
    echo "==================================="
    echo ""
    echo "Configuration : $CONFIG_DIR/config.yaml"
    echo "Logs          : /var/log/yarp/"
    echo ""
    echo "Commandes disponibles :"
    echo "  yarp version         - Afficher la version"
    echo "  yarp show            - Afficher la configuration"
    echo "  yarp validate        - Valider la configuration"
    echo "  yarp status          - État du système"
    echo "  yarp apply           - Appliquer la configuration"
    echo ""
    echo "Service :"
    echo "  rc-service yarp start"
    echo "  rc-service yarp reload"
    echo ""
    echo "Prochaines étapes :"
    echo "  1. Éditer la configuration : nano $CONFIG_DIR/config.yaml"
    echo "  2. Valider : yarp validate"
    echo "  3. Appliquer : yarp apply"
    echo ""
}

# Fonction principale
main() {
    check_prerequisites
    install_packages
    configure_system
    create_directories
    install_yarp_files
    setup_config
    install_service
    verify_installation
    show_summary
}

# Gestion des erreurs
trap 'error "Installation interrompue"' INT TERM

# Exécution
main

exit 0
