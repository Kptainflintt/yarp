#!/bin/bash
# YARP Apply Script
# Applique la configuration complète

set -e

YARP_DIR="/opt/yarp"
CONFIG_FILE="/etc/yarp/config.yaml"
LOG_FILE="/var/log/yarp/apply.log"

export PYTHONPATH="$YARP_DIR/core:$PYTHONPATH" 

# Logging
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

error() {
    echo "[ERROR] $1" | tee -a "$LOG_FILE" >&2
    exit 1
}

# Vérification des prérequis
check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        error "Ce script doit être exécuté en root"
    fi
}

check_config() {
    if [ ! -f "$CONFIG_FILE" ]; then
        error "Fichier de configuration introuvable: $CONFIG_FILE"
    fi
}

# Validation de la configuration
validate_config() {
    log "Validation de la configuration..."
    if ! python3 "$YARP_DIR/core/yarp_config.py" validate; then
        error "Configuration invalide"
    fi
    log "Configuration valide"
}

# Application de la configuration système
apply_system() {
    log "=== Configuration Système ==="
    
    # Récupérer la config système
    local hostname=$(python3 -c "
import yaml
with open('$CONFIG_FILE') as f:
    config = yaml.safe_load(f)
    print(config.get('system', {}).get('hostname', 'yarp-router'))
")
    
    # Configurer le hostname
    if [ -n "$hostname" ]; then
        log "Configuration hostname: $hostname"
        hostname "$hostname"
        echo "$hostname" > /etc/hostname
    fi
}

# Application de la configuration réseau
apply_network() {
    log "=== Configuration Réseau ==="
    
    cd "$YARP_DIR/modules"
    if ! python3 network.py apply; then
        error "Erreur lors de la configuration réseau"
    fi
}

# Application du routage
apply_routing() {
    log "=== Configuration Routage ==="
    
    cd "$YARP_DIR/modules"
    if ! python3 routing.py apply; then
        error "Erreur lors de la configuration du routage"
    fi
}

# Affichage du résumé
show_summary() {
    log ""
    log "==================================="
    log "Configuration appliquée avec succès"
    log "==================================="
    log ""
    log "État des interfaces:"
    ip -br addr
    log ""
    log "Table de routage IPv4:"
    ip route
    log ""
    log "Table de routage IPv6:"
    ip -6 route
}

# Main
main() {
    log "======================================"
    log "YARP - Application de la configuration"
    log "======================================"
    
    check_root
    check_config
    validate_config
    
    apply_system
    apply_network
    apply_routing
    
    show_summary
    
    log "Terminé"
}

main "$@"
