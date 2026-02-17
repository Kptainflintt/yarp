#!/usr/bin/env python3
"""
YARP DNS Module
Gestion de la résolution DNS (/etc/resolv.conf)
"""

import subprocess
import sys
import os
import time
import ipaddress
import shutil

YARP_DIR = "/opt/yarp"
sys.path.insert(0, os.path.join(YARP_DIR, 'core'))

from yarp_config import YARPConfig
from yarp_logger import get_logger

RESOLV_CONF = "/etc/resolv.conf"
RESOLV_BACKUP = "/etc/resolv.conf.yarp-backup"


class DNSManager:
    def __init__(self, config):
        self.config = config
        self.system = config.get_system()

        # Initialiser le logger
        logging_config = config.get_logging()
        self.logger = get_logger("dns", {'logging': logging_config})

    def _backup_resolv_conf(self):
        """Sauvegarde /etc/resolv.conf si pas déjà fait"""
        if not os.path.exists(RESOLV_BACKUP) and os.path.exists(RESOLV_CONF):
            shutil.copy2(RESOLV_CONF, RESOLV_BACKUP)
            self.logger.info(f"Backup de {RESOLV_CONF} vers {RESOLV_BACKUP}")

    def apply(self):
        """Génère et écrit /etc/resolv.conf depuis la configuration YARP"""
        domain = self.system.get('domain', '')
        dns_servers = self.system.get('dns_servers', [])

        # Rien à faire si ni domain ni dns_servers ne sont définis
        if not domain and not dns_servers:
            self.logger.info("Aucune configuration DNS définie, /etc/resolv.conf inchangé")
            return True

        self._backup_resolv_conf()

        lines = []
        lines.append("# Généré par YARP - ne pas modifier manuellement")
        lines.append(f"# Toute modification sera écrasée par 'yarp apply'")

        # Directive domain
        if domain:
            lines.append(f"domain {domain}")
            lines.append(f"search {domain}")
            self.logger.info(f"Domain configuré: {domain}")

        # Directives nameserver
        for server in dns_servers:
            lines.append(f"nameserver {server}")
            self.logger.info(f"Nameserver ajouté: {server}")

        # Écriture du fichier
        content = "\n".join(lines) + "\n"

        try:
            with open(RESOLV_CONF, 'w') as f:
                f.write(content)
            self.logger.info(f"{RESOLV_CONF} écrit avec succès")
            return True
        except IOError as e:
            self.logger.error(f"Impossible d'écrire {RESOLV_CONF}: {e}")
            return False

    def show(self):
        """Affiche la configuration DNS actuelle"""
        print("=== Configuration DNS ===")

        # Depuis la config YARP
        domain = self.system.get('domain', '')
        dns_servers = self.system.get('dns_servers', [])

        if domain:
            print(f"Domain: {domain}")
        if dns_servers:
            print("Serveurs DNS:")
            for server in dns_servers:
                print(f"  - {server}")

        # Depuis le système
        print(f"\n=== {RESOLV_CONF} actuel ===")
        if os.path.exists(RESOLV_CONF):
            with open(RESOLV_CONF, 'r') as f:
                print(f.read())
        else:
            print("Fichier absent")


def main():
    # Gestion des arguments
    if len(sys.argv) < 2:
        print("Usage: dns.py <config_file|apply|show>")
        sys.exit(1)

    if sys.argv[1] in ("apply", "show"):
        config_file = "/etc/yarp/config.yaml"
        mode = sys.argv[1]
    else:
        config_file = sys.argv[1]
        mode = sys.argv[2] if len(sys.argv) > 2 else "apply"

    config = YARPConfig(config_file)
    if not config.load() or not config.validate():
        sys.exit(1)

    manager = DNSManager(config)

    if mode == "apply":
        if manager.apply():
            sys.exit(0)
        else:
            sys.exit(1)
    elif mode == "show":
        manager.show()
    else:
        print(f"Mode inconnu: {mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
