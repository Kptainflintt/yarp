# YARP - YAML Alpine Router Project

![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)
![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)
![Platform](https://img.shields.io/badge/platform-Alpine%20Linux-orange.svg)

**YARP** est un framework moderne de configuration de routeurs basé sur Alpine Linux, permettant la configuration complète d'un routeur via des fichiers YAML déclaratifs.

## **Pourquoi YARP ?**

Et pourquoi pas ?

Travaillant dans un environnement éducatif, je remarque que dans certains cas, perdre du temps à configurer un routeur n'est aps l'objectif premier du TP ou de la manipulation demandée. 
J'ai donc eu l'idée de ce projet, pour passer moins de temps à la configuration et plus aux manipulations importantes.

Bien entendu, son utilisation ne dispense en aucun cas de savoir faire les manipulation à la main, comprendre ce que cela fait et pourquoi...

**ATTENTION** : il n'est pas recommandé d'utiliser YARP en production, ce projet n'as pas été fait pour cela. J'ai largement utilisé l'IA, il n'est donc surement pas adapté.
Toutefois, si des personnes plus calées en dev python veulent s'emparer du sujet, welcome !

## **Fonctionnalités Principales**

### **Implémentées**
- **Configuration réseau déclarative** - Interfaces, DHCP, IPs statiques via YAML
- **Routage statique avancé** - Routes IPv4/IPv6 avec métriques
- **NAT/Masquerading intelligent** - Configuration par interface avec sources contrôlées
- **Système de logs professionnel** - Logs JSON structurés + console utilisateur
- **Validation robuste** - Vérification CIDR, cohérence de configuration
- **CLI moderne** - Interface en ligne de commande avec sous-commandes
- **Installation automatisée** - Scripts d'installation Alpine Linux + OpenRC
- **Tests intégrés** - Validation syntaxe et structure

### **En Développement**
- **Module Firewall** - Règles iptables déclaratives (structure prête)
- **Langage Runtime** - Commandes pour modifications à la volée
- **Builder ISO** - Création d'ISO Alpine personnalisé avec YARP

### **Roadmap Future**
- Interface Web de gestion (optionnel)
- Support routage dynamique (BGP, OSPF)
- Monitoring et alertes intégrés
- Templates de configuration prédéfinis (utile ?)

---

## 🚀 **Installation**

### **Prérequis**
- **Alpine Linux** (version 3.18+)
- **Accès root** pour l'installation
- **Python 3** et **iptables** (installés automatiquement)

### **Installation Rapide**

```bash
# 1. Cloner le projet
git clone https://github.com/Kptainflintt/yarp
cd yarp

# 2. Installer YARP
sudo make install

# 3. Vérifier l'installation
yarp version
yarp validate

# 4. Configurer (éditer selon vos besoins)
sudo cp config/yarp.yaml.example /etc/yarp/config.yaml
sudo nano /etc/yarp/config.yaml

# 5. Appliquer la configuration
sudo yarp apply
```

### **Installation Manuelle**

```bash
# Installer les dépendances
sudo apk update
sudo apk add python3 py3-yaml iproute2 iptables

# Installer YARP
sudo ./install.sh

# Activer le service OpenRC
sudo rc-update add yarp default
sudo rc-service yarp start
```

---

## 🛠 **Configuration**

### **Fichier de Configuration Principal**
`/etc/yarp/config.yaml`

```yaml
# Configuration système
system:
  hostname: my-router
  domain: lan.local
  timezone: Europe/Paris

# Configuration des logs
logging:
  level: INFO
  debug: false
  formats:
    console: "simple"
    file: "json"

# Interfaces réseau
interfaces:
  eth0:
    description: "Interface WAN"
    ipv4: dhcp
    zone: WAN
    # NAT/Masquerading
    masquerading: true
    masquerade_sources:
      - "192.168.1.0/24"

  eth1:
    description: "Interface LAN"
    ipv4: 192.168.1.1/24
    ipv6: fd00:1::1/64
    zone: LAN

# Routage statique
routing:
  static:
    - to: 0.0.0.0/0
      via: 192.168.100.1
      interface: eth0

# Firewall (structure prête)
firewall:
  default:
    input: drop
    forward: drop
    output: accept
  stateful: true
  rules: []
```

---

## 📋 **Commandes Utiles**

### **Commandes Principales**

```bash
# Application de configuration
sudo yarp apply              # Appliquer la configuration complète
sudo yarp reload             # Recharger la configuration

# Validation et debug
yarp validate                # Valider la syntaxe YAML
yarp show                    # Afficher la configuration
yarp status                  # État des interfaces et routes

# Informations
yarp version                 # Version de YARP
yarp --help                  # Aide générale
```

### **Modules Spécialisés**

```bash
# Module réseau
sudo python3 /opt/yarp/modules/network.py apply
sudo python3 /opt/yarp/modules/network.py <config.yaml>

# Module routage
sudo python3 /opt/yarp/modules/routing.py apply
sudo python3 /opt/yarp/modules/routing.py show

# Module NAT
sudo python3 /opt/yarp/modules/nat.py apply
sudo python3 /opt/yarp/modules/nat.py show
sudo python3 /opt/yarp/modules/nat.py clear
```

### **Diagnostic et Logs**

```bash
# Logs en temps réel
sudo tail -f /var/log/yarp/apply.log

# Logs debug (si activé)
sudo tail -f /var/log/yarp/debug.log | jq .

# Logs erreurs uniquement
sudo tail -f /var/log/yarp/error.log

# État iptables
sudo iptables -L -n -v
sudo iptables -t nat -L -n -v

# État réseau
ip addr show
ip route show
cat /proc/sys/net/ipv4/ip_forward
```

### **Gestion du Service**

```bash
# Service OpenRC
sudo rc-service yarp start
sudo rc-service yarp stop
sudo rc-service yarp restart
sudo rc-service yarp status

# Logs service
sudo rc-service yarp start --verbose
```

### **Tests et Développement**

```bash
# Tests de validation
make test

# Nettoyage
make clean

# Désinstallation
sudo make uninstall  # Attention : supprime toute la config YARP
```

---

## **Structure du Projet**

```
yarp/
├── src/                    # Code source
│   ├── core/              # Scripts principaux
│   │   ├── yarp           # CLI principal
│   │   ├── yarp-apply.sh  # Orchestrateur d'application
│   │   ├── yarp_config.py # Parser YAML + validation
│   │   └── yarp_logger.py # Système de logs
│   ├── modules/           # Modules fonctionnels
│   │   ├── network.py     # Gestion interfaces
│   │   ├── routing.py     # Routage statique
│   │   └── nat.py         # NAT/Masquerading
│   └── init/              # Service OpenRC
├── config/                # Exemples de configuration
├── install/               # Scripts d'installation
├── tests/                 # Tests de validation
└── build/                 # Builder ISO (futur)
```

---

## **Développement**

### **Contribuer**

```bash
# Fork et clone
git clone https://github.com/your-username/yarp.git
cd yarp

# Tests avant commit
make test

# Structure d'un nouveau module
cp src/modules/network.py src/modules/mon_module.py
# Modifier install.sh pour inclure le nouveau module
# Ajouter aux tests dans test/test-phase1.sh
```

### **Standards de Code**

- **Python 3** avec type hints recommandés
- **Logging structuré** via le module `yarp_logger`
- **Validation robuste** des entrées utilisateur
- **Comments en français** (orienté utilisateurs francophones)
- **Gestion d'erreurs** et codes retour appropriés

---

## **Licence**

Ce projet est sous licence **Apache 2.0**. Voir le fichier [LICENSE](LICENSE) pour les détails.

---

## **Support**

- **Issues :** [GitHub Issues](https://github.com/your-org/yarp/issues)
- **Documentation :** [Wiki du projet](https://github.com/your-org/yarp/wiki)
- **Logs :** Consultez `/var/log/yarp/` pour le debugging
