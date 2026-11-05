# YARP - YAML Alpine Router Project

<!-- Mettre à jour le badge ci-dessous en même temps que le fichier VERSION -->
![Version](https://img.shields.io/badge/version-0.1.1-blue.svg)
![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)
![Platform](https://img.shields.io/badge/platform-Alpine%20Linux-orange.svg)

**YARP** est un framework moderne de configuration de routeurs basé sur Alpine Linux, permettant la configuration complète d'un routeur via des fichiers YAML déclaratifs.

## **Pourquoi YARP ?**

Et pourquoi pas ?

Travaillant dans un environnement éducatif, je remarque que dans certains cas, perdre du temps à configurer un routeur n'est pas l'objectif premier du TP ou de la manipulation demandée. 
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
- **Firewall déclaratif** - Règles iptables via YAML avec politiques par défaut, conntrack et filtrage par protocole/port
- **Système de logs professionnel** - Logs JSON structurés + console utilisateur
- **Validation robuste** - Vérification CIDR, cohérence de configuration
- **CLI moderne** - Interface en ligne de commande avec sous-commandes
- **Installation automatisée** - Scripts d'installation Alpine Linux + OpenRC
- **Tests intégrés** - Validation syntaxe et structure

### **En Développement**
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

# 4. Copier et éditer la configuration
cp config/yarp.yaml.example /etc/yarp/config.yaml
nano /etc/yarp/config.yaml

# 5. Vérifier le fichier de configuration
yarp validate

# 6. Appliquer la configuration
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

### **Mise à jour**

Après un `git pull`, utilisez `update.sh` pour mettre à jour les fichiers installés sans réinstaller les dépendances ni toucher à votre configuration :

```bash
git pull
./update.sh
```

> **Note :** `update.sh` ne modifie pas `/etc/yarp/config.yaml`. Consultez `config/yarp.yaml.example` pour les nouvelles options disponibles.

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
  domain: lan.local          # Appliqué dans /etc/resolv.conf et /etc/hosts (FQDN)
  timezone: Europe/Paris     # Appliqué via /etc/localtime et /etc/timezone
  dns_servers:               # Serveurs DNS dans /etc/resolv.conf
    - 1.1.1.1
    - 8.8.8.8

# Configuration des logs (voir section dédiée ci-dessous)
logging:
  level: INFO
  debug: false
  files:
    application: "/var/log/yarp/apply.log"
    debug: "/var/log/yarp/debug.log"
    error: "/var/log/yarp/error.log"
  formats:
    console: "simple"
    file: "json"
  modules:
    network: INFO
    routing: INFO
    dns: INFO
    firewall: WARNING

# Interfaces réseau
interfaces:
  eth0:
    description: "Interface WAN"
    ipv4: dhcp
    # NAT/Masquerading
    masquerading: true
    masquerade_sources:
      - "192.168.1.0/24"

  eth1:
    description: "Interface LAN"
    ipv4: 192.168.1.1/24
    ipv6: fd00:1::1/64

# Routage statique
routing:
  static:
    - to: 0.0.0.0/0
      via: 192.168.100.1
      interface: eth0

# Firewall
firewall:
  default:
    input: drop
    forward: drop
    output: accept
  stateful: true
  rules:
    - name: "Allow_Internet"
      chain: forward
      source: 192.168.1.0/24
      out_interface: eth0
      protocols:
        tcp: [80, 443]
        udp: 53
      action: accept

    - name: "Block_WAN_to_LAN"
      chain: forward
      in_interface: eth0
      out_interface: eth1
      protocols: any
      action: drop
```

### **Système de Logs**

YARP intègre un système de logging structuré avec catégorisation par module, permettant un contrôle fin de la verbosité et du format des logs.

#### Niveau global et mode debug

```yaml
logging:
  # Niveau global appliqué à tous les modules par défaut
  # Valeurs possibles : DEBUG, INFO, WARNING, ERROR
  level: INFO

  # Mode debug : force le niveau DEBUG sur tous les modules
  # et active le fichier de log debug
  debug: false
```

#### Catégorisation par module

Chaque module fonctionnel possède son propre logger avec un niveau configurable indépendamment. Cela permet par exemple de passer le firewall en WARNING tout en gardant le réseau en DEBUG :

```yaml
logging:
  modules:
    network: INFO       # Logs du module réseau (interfaces, DHCP, adresses IP)
    routing: INFO       # Logs du module routage (routes statiques IPv4/IPv6)
    dns: INFO           # Logs du module DNS (resolv.conf, nameservers)
    firewall: WARNING   # Logs du module NAT/firewall (masquerading, iptables)
```

Les niveaux disponibles sont `DEBUG`, `INFO`, `WARNING`, `ERROR`. Un module configuré en `WARNING` ne produira que les avertissements et erreurs, ce qui est utile pour les modules stables.

#### Fichiers de log

Trois fichiers de log distincts avec rotation automatique (5 Mo max, 5 fichiers conservés) :

```yaml
logging:
  files:
    # Log principal : toutes les opérations (niveau INFO et supérieur)
    application: "/var/log/yarp/apply.log"

    # Log debug : toutes les opérations y compris DEBUG
    # Actif uniquement si debug: true
    debug: "/var/log/yarp/debug.log"

    # Log erreurs : uniquement les erreurs (niveau ERROR)
    error: "/var/log/yarp/error.log"
```

#### Formats de sortie

```yaml
logging:
  formats:
    # Format console (ce que voit l'utilisateur)
    #   simple   -> [INFO] message
    #   detailed -> [12:30:45] [network] [INFO] message
    #   minimal  -> message (sans préfixe)
    console: "simple"

    # Format fichier (logs persistants)
    #   json     -> {"timestamp": "...", "level": "INFO", "module": "network", ...}
    #   detailed -> [2025-01-15 12:30:45] [network] [INFO] [apply:42] message
    #   text     -> [2025-01-15 12:30:45] [INFO] message
    file: "json"
```

Le format `json` est recommandé pour les fichiers : chaque ligne est un objet JSON contenant le timestamp, le niveau, le module source, la fonction, le numéro de ligne, le message et un éventuel contexte métadata (interface, commande exécutée, code retour, durée, etc.).

Exemple de sortie JSON :
```json
{
  "timestamp": "2025-01-15T12:30:45.123456",
  "level": "INFO",
  "module": "network",
  "function": "apply",
  "line": 42,
  "message": "Configuration IPv4 réussie sur eth0",
  "context": {
    "operation": "set_ipv4",
    "interface": "eth0",
    "status": "success"
  }
}
```

### **Firewall**

Le module firewall permet de définir des règles de filtrage iptables de manière déclarative. Les règles sont appliquées dans l'ordre du fichier YAML, après le NAT.

#### Politiques par défaut et mode stateful

```yaml
firewall:
  # Politiques par défaut pour chaque chaîne (accept, drop, reject)
  default:
    input: drop       # Trafic entrant vers le routeur
    forward: drop     # Trafic traversant le routeur
    output: accept    # Trafic sortant du routeur

  # Active le suivi de connexion (conntrack)
  # Accepte automatiquement les connexions ESTABLISHED/RELATED
  # et le trafic loopback
  stateful: true
```

Avec `stateful: true`, il n'est pas nécessaire de créer des règles pour le trafic retour. Seules les connexions initiales doivent être autorisées.

#### Règles de filtrage

Chaque règle contient :

| Champ | Requis | Description |
|---|---|---|
| `name` | oui | Nom descriptif (utilisé comme tag iptables `YARP-FW-RULE-<name>` ; les espaces et caractères non alphanumériques sont automatiquement normalisés, ex: `Allow SSH` → `Allow_SSH`) |
| `chain` | oui | Chaîne iptables : `input`, `forward` ou `output` |
| `source` | non | IP, CIDR source ou `any` (ex: `192.168.1.0/24`, `10.0.0.1`, `any`) |
| `destination` | non | IP, CIDR destination ou `any` |
| `in_interface` | non | Interface d'entrée (incompatible avec `chain: output`) |
| `out_interface` | non | Interface de sortie (incompatible avec `chain: input`) |
| `protocols` | non | Protocoles et ports à filtrer, ou `any` pour tout le trafic |
| `action` | oui | `accept`, `drop` ou `reject` |

Les chaînes correspondent à :
- **`input`** — trafic destiné au routeur lui-même (ex: SSH, SNMP, ping vers le routeur)
- **`forward`** — trafic traversant le routeur d'une interface à une autre
- **`output`** — trafic émis par le routeur (ex: requêtes DNS du routeur)

> **Note :** Au moins un critère de matching (`source`, `destination`, `in_interface`, `out_interface`) est requis par règle.

#### Protocoles supportés

Le champ `protocols` accepte un dictionnaire de protocoles ou la valeur `any` :

**Protocoles L4 (avec ports)** : `tcp`, `udp`, `sctp`

```yaml
# Port unique
protocols:
  tcp: 80

# Liste de ports
protocols:
  tcp: [80, 443, 8080]

# Range de ports
protocols:
  tcp: "8000:8100"

# Plusieurs protocoles combinés
protocols:
  tcp: [80, 443]
  udp: 53
```

**Protocoles L3 (sans ports)** : `icmp`, `gre`, `esp`, `ah`, `ipip`, `ospf`, `vrrp`

```yaml
# ICMP (ping)
protocols:
  icmp: true

# Tunnel GRE
protocols:
  gre: true

# IPsec (ESP + AH)
protocols:
  esp: true
  ah: true

# Combinaison L3 + L4
protocols:
  tcp: [80, 443]
  icmp: true
```

**Tout le trafic** (pas de filtrage par protocole) :

```yaml
protocols: any
```

#### Exemple complet

```yaml
firewall:
  default:
    input: drop
    forward: drop
    output: accept
  stateful: true
  rules:
    # Autoriser le SSH vers le routeur (INPUT)
    - name: "Allow_SSH"
      chain: input
      source: any
      in_interface: eth1
      protocols:
        tcp: 22
      action: accept

    # Autoriser HTTP/HTTPS et DNS du LAN vers le WAN (FORWARD)
    - name: "Allow_Internet"
      chain: forward
      source: 192.168.1.0/24
      out_interface: eth0
      protocols:
        tcp: [80, 443]
        udp: 53
      action: accept

    # Autoriser un serveur web accessible depuis le WAN
    - name: "Allow_HTTP_from_WAN"
      chain: forward
      in_interface: eth0
      destination: 192.168.1.100
      protocols:
        tcp: 80
      action: accept

    # Autoriser le ping sortant
    - name: "Allow_Ping_out"
      chain: forward
      in_interface: eth1
      out_interface: eth0
      protocols:
        icmp: true
      action: accept

    # Autoriser un range de ports applicatif
    - name: "Allow_app_ports"
      chain: forward
      source: 192.168.1.0/24
      out_interface: eth0
      protocols:
        tcp: "8000:8100"
      action: accept

    # Autoriser les tunnels GRE vers le routeur (INPUT)
    - name: "Allow_GRE_tunnels"
      chain: input
      in_interface: eth0
      destination: 192.168.1.1
      protocols:
        gre: true
      action: accept

    # Bloquer tout le reste du WAN vers le LAN
    - name: "Block_WAN_to_LAN"
      chain: forward
      in_interface: eth0
      out_interface: eth1
      protocols: any
      action: drop
```

#### Ordre d'application

Le pipeline firewall s'exécute dans cet ordre lors de `yarp apply` :

1. Flush des chaînes iptables (`iptables -F INPUT/FORWARD/OUTPUT`)
2. Application des politiques par défaut (`iptables -P`)
3. Règles stateful (conntrack + loopback) si `stateful: true`
4. Règles utilisateur dans l'ordre du YAML

> **Note :** les règles sont évaluées dans l'ordre. Placez les règles les plus spécifiques en premier et les règles catch-all (`protocols: any`) en dernier.

#### Validation

La validation (`yarp validate`) vérifie :
- Les politiques par défaut (`accept`, `drop`, `reject`)
- Les champs obligatoires de chaque règle (`name`, `chain`, `action`)
- Que `chain` est valide (`input`, `forward`, `output`)
- La cohérence chaîne/interface (`out_interface` incompatible avec `input`, `in_interface` incompatible avec `output`)
- Qu'au moins un critère de matching est présent (`source`, `destination`, `in_interface`, `out_interface`)
- Que les `in_interface`/`out_interface` existent dans la section `interfaces`
- Que les `source`/`destination` sont des IP, CIDR valides ou `any`
- Les protocoles L4 supportés (`tcp`, `udp`, `sctp`) avec validation des ports (1-65535, listes, ranges)
- Les protocoles L3 supportés (`icmp`, `gre`, `esp`, `ah`, `ipip`, `ospf`, `vrrp`)

---

## **Commandes Utiles**

### **Commandes Principales**

```bash
# Application de configuration
yarp apply                   # Appliquer la configuration complète
yarp reload                  # Recharger la configuration

# Validation et debug
yarp validate                # Valider la syntaxe YAML
yarp show                    # Afficher la configuration
yarp status                  # État des interfaces et routes
yarp check                   # Vérifier l'installation

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

# Module DNS
python3 /opt/yarp/modules/dns.py apply
python3 /opt/yarp/modules/dns.py show

# Module Firewall
python3 /opt/yarp/modules/firewall.py apply
python3 /opt/yarp/modules/firewall.py show
python3 /opt/yarp/modules/firewall.py clear
```

### **Diagnostic et Logs**

```bash
# Logs en temps réel
tail -f /var/log/yarp/apply.log

# Logs debug JSON (si debug: true dans la config)
tail -f /var/log/yarp/debug.log | jq .

# Logs erreurs uniquement
tail -f /var/log/yarp/error.log

# Filtrer les logs JSON par module (nécessite jq)
cat /var/log/yarp/apply.log | jq 'select(.module == "network")'
cat /var/log/yarp/apply.log | jq 'select(.module == "firewall")'
cat /var/log/yarp/apply.log | jq 'select(.module == "routing")'
cat /var/log/yarp/apply.log | jq 'select(.module == "dns")'

# Filtrer par niveau
cat /var/log/yarp/apply.log | jq 'select(.level == "ERROR")'

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
│   │   ├── nat.py         # NAT/Masquerading
│   │   ├── dns.py         # Résolution DNS
│   │   └── firewall.py    # Règles de filtrage
│   └── init/              # Service et scripts système
│       ├── yarp           # Service OpenRC
│       └── yarp-motd.sh   # MOTD affiché à la connexion
├── config/                # Exemples de configuration
├── install/               # Scripts d'installation
├── install.sh             # Installation initiale
├── update.sh              # Mise à jour après git pull
├── uninstall.sh           # Désinstallation complète
├── tests/                 # Tests de validation
└── build/                 # Builder ISO (futur)
```

<!---

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
-->

