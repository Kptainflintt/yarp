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

## Pourquoi Alpine Linux ?

Alpine Linux a été choisi pour YARP pour sa légèreté (±130 MB installé), 
sa sécurité (musl libc, PaX/grsecurity), et sa philosophie minimaliste 
parfaitement adaptée aux appliances réseau. Son gestionnaire de paquets 
APK et son système d'init OpenRC offrent rapidité et simplicité.


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

## **Installation**

### **Prérequis**
- **Alpine Linux** (version 3.18+)
- **Accès root** (par défaut sur Alpine Linux - pas de `sudo` nécessaire)
- **Connexion internet** pour télécharger les dépendances


### **Installation Simple**

```bash
# 1. Cloner le projet
git clone https://github.com/Kptainflintt/yarp
cd yarp

# 2. Installer YARP (installe automatiquement toutes les dépendances)
./install.sh

# 3. Vérifier l'installation
yarp version
yarp validate

# 4. Copier et éditer la configuration
cp config/yarp.yaml.example /etc/yarp/config.yaml
nano /etc/yarp/config.yaml

# 5. Appliquer la configuration
yarp apply
```

### **Alternative avec Make**

```bash
# Installation via Makefile
make install

# Tests de validation
make test
```

### **Activation du Service OpenRC (optionnel)**

```bash
# Activer le service au démarrage
rc-update add yarp default

# Démarrer le service
rc-service yarp start
```

**Note :** `install.sh` installe automatiquement toutes les dépendances nécessaires :
- `python3` et `py3-yaml` pour l'exécution
- `iproute2` pour la gestion réseau (`ip` command)
- `iptables` et `ip6tables` pour les règles firewall/NAT

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
yarp apply                   # Appliquer la configuration complète
yarp reload                  # Recharger la configuration

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
python3 /opt/yarp/modules/network.py apply
python3 /opt/yarp/modules/network.py <config.yaml>

# Module routage
python3 /opt/yarp/modules/routing.py apply
python3 /opt/yarp/modules/routing.py show

# Module NAT
python3 /opt/yarp/modules/nat.py apply
python3 /opt/yarp/modules/nat.py show
python3 /opt/yarp/modules/nat.py clear
```

### **Diagnostic et Logs**

```bash
# Logs en temps réel
tail -f /var/log/yarp/apply.log

# Logs debug (si activé)
tail -f /var/log/yarp/debug.log | jq .

# Logs erreurs uniquement
tail -f /var/log/yarp/error.log

# État iptables
iptables -L -n -v
iptables -t nat -L -n -v

# État réseau
ip addr show
ip route show
cat /proc/sys/net/ipv4/ip_forward
```

### **Gestion du Service**

```bash
# Service OpenRC
rc-service yarp start
rc-service yarp stop
rc-service yarp restart
rc-service yarp status

# Logs service
rc-service yarp start --verbose
```

### **Tests et Développement**

```bash
# Tests de validation
make test

# Nettoyage
make clean

# Désinstallation
make uninstall  # Attention : supprime toute la config YARP
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

# Installation pour tests
./install.sh

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
