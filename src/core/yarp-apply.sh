#!/bin/bash
# YARP Apply Script

set -e

YARP_DIR="/opt/yarp"
CONFIG_FILE="/etc/yarp/config.yaml"
LOG_FILE="/var/log/yarp/apply.log"
ALPINE_INTERFACES="/etc/network/interfaces"
ALPINE_BACKUP="/etc/network/interfaces.yarp-backup"

export PYTHONPATH="$YARP_DIR/core:$PYTHONPATH"

# Logging
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

error() {
    echo "[ERROR] $1" | tee -a "$LOG_FILE" >&2
    exit 1
}

# Validation de la configuration
validate_config() {
    log "Validation de la configuration..."
    if ! python3 "$YARP_DIR/core/yarp_config.py" validate; then
        error "Configuration invalide"
    fi
    log "Configuration valide"
}

# Backup de la configuration Alpine
backup_alpine_config() {
    if [ ! -f "$ALPINE_BACKUP" ]; then
        log "Sauvegarde de la configuration Alpine originale..."
        cp "$ALPINE_INTERFACES" "$ALPINE_BACKUP"
    fi
}

# Désactiver la gestion Alpine pour les interfaces YARP
disable_alpine_networking() {
    log "Désactivation de la gestion Alpine pour les interfaces YARP..."
    
    # Lire les interfaces depuis la config YAML
    local interfaces=$(python3 -c "
import sys
import yaml
sys.path.insert(0, '$YARP_DIR/core')

with open('$CONFIG_FILE', 'r') as f:
    config = yaml.safe_load(f)
    
if 'interfaces' in config:
    for iface in config['interfaces'].keys():
        print(iface)
")
    
    # Créer un nouveau fichier interfaces sans les interfaces YARP
    cat > "$ALPINE_INTERFACES" << 'EOF'
# Configuration réseau Alpine - Géré par YARP
# Les interfaces suivantes sont gérées par YARP:
EOF
    
    for iface in $interfaces; do
        echo "# - $iface (géré par YARP)" >> "$ALPINE_INTERFACES"
    done
    
    echo "" >> "$ALPINE_INTERFACES"
    echo "auto lo" >> "$ALPINE_INTERFACES"
    echo "iface lo inet loopback" >> "$ALPINE_INTERFACES"
    
    log "Configuration Alpine mise à jour"
}

# Configuration du système
configure_system() {
    log "=== Configuration Système ==="
    
    # Extraire hostname, domain et timezone depuis la config YAML
    local system_values=$(python3 -c "
import sys, yaml
sys.path.insert(0, '$YARP_DIR/core')
with open('$CONFIG_FILE') as f:
    system = yaml.safe_load(f).get('system', {})
print(system.get('hostname', ''))
print(system.get('domain', ''))
print(system.get('timezone', ''))
")
    
    local hostname=$(echo "$system_values" | sed -n '1p')
    local domain=$(echo "$system_values" | sed -n '2p')
    local timezone=$(echo "$system_values" | sed -n '3p')
    
    # Hostname
    if [ -n "$hostname" ]; then
        log "Configuration hostname: $hostname"
        hostname "$hostname"
        echo "$hostname" > /etc/hostname
        
        # Construire l'entrée /etc/hosts avec FQDN si domain est défini
        if [ -n "$domain" ]; then
            local fqdn="${hostname}.${domain}"
            sed -i "/127.0.0.1.*localhost/c\127.0.0.1\tlocalhost ${fqdn} ${hostname}" /etc/hosts
        else
            sed -i "/127.0.0.1.*localhost/c\127.0.0.1\tlocalhost $hostname" /etc/hosts
        fi
    fi
    
    # Domain
    if [ -n "$domain" ]; then
        log "Configuration domain: $domain"
        
        # Mettre à jour /etc/resolv.conf : ajouter/remplacer la directive domain
        if grep -q "^domain " /etc/resolv.conf 2>/dev/null; then
            sed -i "s/^domain .*/domain ${domain}/" /etc/resolv.conf
        else
            # Insérer 'domain' en première ligne du fichier
            sed -i "1i domain ${domain}" /etc/resolv.conf
        fi
        
        # Ajouter/remplacer la directive search si absente
        if ! grep -q "^search " /etc/resolv.conf 2>/dev/null; then
            sed -i "/^domain /a search ${domain}" /etc/resolv.conf
        else
            # Vérifier que le domain est dans la liste search
            if ! grep -q "^search.*${domain}" /etc/resolv.conf 2>/dev/null; then
                sed -i "s/^search .*/& ${domain}/" /etc/resolv.conf
            fi
        fi
        
        log "Domain configuré dans /etc/resolv.conf"
    fi
    
    # Timezone
    if [ -n "$timezone" ]; then
        log "Configuration timezone: $timezone"
        
        local zoneinfo="/usr/share/zoneinfo/${timezone}"
        if [ -f "$zoneinfo" ]; then
            # Installer le paquet tzdata si le fichier zoneinfo n'existe pas encore
            ln -sf "$zoneinfo" /etc/localtime
            echo "$timezone" > /etc/timezone
            log "Timezone configuré: $timezone"
        else
            # Tenter d'installer tzdata si absent
            if command -v apk > /dev/null 2>&1; then
                log "Installation de tzdata pour $timezone..."
                apk add --no-cache tzdata > /dev/null 2>&1 || true
            fi
            
            if [ -f "$zoneinfo" ]; then
                ln -sf "$zoneinfo" /etc/localtime
                echo "$timezone" > /etc/timezone
                log "Timezone configuré: $timezone"
            else
                log "ATTENTION: Timezone invalide ou tzdata non disponible: $timezone"
            fi
        fi
    fi
}

# Configuration réseau
configure_network() {
    log "=== Configuration Réseau ==="
    
    if ! python3 "$YARP_DIR/modules/network.py" "$CONFIG_FILE"; then
        error "Erreur lors de la configuration réseau"
    fi
    
    log "Configuration réseau appliquée"
}

# Configuration du routage
configure_routing() {
    log "=== Configuration Routage ==="

    if ! python3 "$YARP_DIR/modules/routing.py" "$CONFIG_FILE"; then
        error "Erreur lors de la configuration du routage"
    fi

    log "Configuration routage appliquée"
}

# Configuration NAT/firewall
configure_nat() {
    log "=== Configuration NAT/Firewall ==="

    if ! python3 "$YARP_DIR/modules/nat.py" "$CONFIG_FILE"; then
        error "Erreur lors de la configuration NAT"
    fi

    log "Configuration NAT appliquée"
}

# Sauvegarder l'état actuel
save_state() {
    log "Sauvegarde de l'état..."
    
    mkdir -p /var/lib/yarp
    
    # Sauvegarder les interfaces
    ip -j addr show > /var/lib/yarp/interfaces.json
    ip -j route show > /var/lib/yarp/routes.json
    
    # Sauvegarder les règles firewall
    iptables-save > /var/lib/yarp/iptables.rules 2>/dev/null || true
    ip6tables-save > /var/lib/yarp/ip6tables.rules 2>/dev/null || true
    
    log "État sauvegardé"
}

# Main
main() {
    log "======================================"
    log "YARP - Application de la configuration"
    log "======================================"

    validate_config
    backup_alpine_config
    disable_alpine_networking
    configure_system
    configure_network
    configure_routing
    configure_nat
    save_state

    log "======================================"
    log "✓ Configuration appliquée avec succès"
    log "======================================"
}

main
