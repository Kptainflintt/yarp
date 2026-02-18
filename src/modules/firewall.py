#!/usr/bin/env python3
"""
YARP Firewall Module
Gestion des règles de filtrage iptables
"""

import subprocess
import sys
import os
import time
import ipaddress

YARP_DIR = "/opt/yarp"
sys.path.insert(0, os.path.join(YARP_DIR, 'core'))

from yarp_config import YARPConfig
from yarp_logger import get_logger


class FirewallManager:
    def __init__(self, config):
        self.config = config
        self.firewall = config.get_firewall()
        self.interfaces = config.get_interfaces()

        # Initialiser le logger avec la config YARP
        logging_config = config.get_logging()
        self.logger = get_logger("firewall", {'logging': logging_config})

    def _run_command(self, cmd, check=True):
        """Exécute une commande système avec logging"""
        start_time = time.time()
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                check=check
            )
            duration_ms = int((time.time() - start_time) * 1000)

            # Logger l'exécution commande
            self.logger.command_execution(cmd, result.returncode, duration_ms)

            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.CalledProcessError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self.logger.command_execution(cmd, e.returncode, duration_ms)
            return False, e.stdout, e.stderr

    def _run_command_silent(self, cmd):
        """Exécute une commande silencieuse (pour nettoyage, sans logging d'erreur)"""
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                check=False
            )
            return result.returncode == 0, result.stdout, result.stderr
        except Exception:
            return False, "", ""

    # ------------------------------------------------------------------ #
    #  Résolution des ports                                                #
    # ------------------------------------------------------------------ #

    def _normalize_ports(self, value):
        """Normalise une valeur de ports en liste de chaînes iptables.

        Entrées acceptées :
          - int ou str  : port unique           → ["80"]
          - list         : liste de ports        → ["80", "443"]
          - str range    : "8000:8100"           → ["8000:8100"]
        Retourne une liste de chaînes utilisables avec --dport / --match multiport.
        """
        if isinstance(value, int):
            return [str(value)]

        if isinstance(value, str):
            # Range "8000:8100" ou port unique en str
            return [value]

        if isinstance(value, list):
            return [str(p) for p in value]

        return []

    def _build_port_args(self, ports):
        """Construit le fragment iptables pour les ports.

        - 1 port   → --dport 80
        - N ports  → -m multiport --dports 80,443
        - range    → --dport 8000:8100
        """
        if len(ports) == 1:
            return f"--dport {ports[0]}"
        else:
            return f"-m multiport --dports {','.join(ports)}"

    # ------------------------------------------------------------------ #
    #  Politiques par défaut                                               #
    # ------------------------------------------------------------------ #

    def apply_default_policies(self):
        """Applique les politiques par défaut (INPUT, FORWARD, OUTPUT)"""
        defaults = self.firewall.get('default', {})

        policy_map = {
            'accept': 'ACCEPT',
            'drop': 'DROP',
            'reject': 'REJECT',
        }

        chains = {
            'input': 'INPUT',
            'forward': 'FORWARD',
            'output': 'OUTPUT',
        }

        for key, chain in chains.items():
            policy = defaults.get(key, 'accept')
            iptables_policy = policy_map.get(policy.lower(), 'ACCEPT')

            # REJECT n'est pas supporté comme policy par iptables, on utilise DROP
            if iptables_policy == 'REJECT':
                self.logger.warning(
                    f"La policy REJECT n'est pas supportée par iptables pour {chain}, "
                    f"utilisation de DROP"
                )
                iptables_policy = 'DROP'

            success, _, stderr = self._run_command(
                f"iptables -P {chain} {iptables_policy}", check=False
            )
            if success:
                self.logger.info(f"Policy {chain} → {iptables_policy}")
            else:
                self.logger.error(f"Erreur policy {chain}: {stderr}")
                return False

        return True

    # ------------------------------------------------------------------ #
    #  Règles stateful                                                     #
    # ------------------------------------------------------------------ #

    def apply_stateful_rules(self):
        """Ajoute les règles de suivi de connexion (conntrack) si stateful: true"""
        if not self.firewall.get('stateful', False):
            self.logger.info("Mode stateful désactivé")
            return True

        self.logger.info("Application des règles stateful (conntrack)")

        stateful_cmds = [
            # Accepter les connexions déjà établies / liées sur INPUT et FORWARD
            ("iptables -A INPUT -m state --state ESTABLISHED,RELATED "
             "-m comment --comment 'YARP-FW-STATEFUL-INPUT' -j ACCEPT"),
            ("iptables -A FORWARD -m state --state ESTABLISHED,RELATED "
             "-m comment --comment 'YARP-FW-STATEFUL-FORWARD' -j ACCEPT"),
            # Accepter le loopback
            ("iptables -A INPUT -i lo "
             "-m comment --comment 'YARP-FW-LOOPBACK' -j ACCEPT"),
        ]

        for cmd in stateful_cmds:
            success, _, stderr = self._run_command(cmd, check=False)
            if not success:
                self.logger.error(f"Erreur règle stateful: {stderr}")
                return False

        self.logger.info("Règles stateful appliquées")
        return True

    # ------------------------------------------------------------------ #
    #  Nettoyage des règles YARP existantes                                #
    # ------------------------------------------------------------------ #

    def clear_firewall_rules(self):
        """Nettoie les règles firewall existantes taggées YARP-FW-*"""
        self.logger.info("Nettoyage des règles firewall YARP existantes")
        rules_cleaned = 0

        for chain in ['INPUT', 'FORWARD', 'OUTPUT']:
            success, stdout, _ = self._run_command_silent(
                f"iptables -L {chain} --line-numbers -n | grep 'YARP-FW-'"
            )
            if success and stdout.strip():
                lines = stdout.strip().split('\n')
                line_numbers = []
                for line in lines:
                    if 'YARP-FW-' in line:
                        parts = line.split()
                        if parts and parts[0].isdigit():
                            line_numbers.append(int(parts[0]))

                # Supprimer en ordre décroissant pour éviter les décalages
                for line_num in sorted(line_numbers, reverse=True):
                    success, _, _ = self._run_command_silent(
                        f"iptables -D {chain} {line_num}"
                    )
                    if success:
                        rules_cleaned += 1

        if rules_cleaned > 0:
            self.logger.info(f"{rules_cleaned} règles YARP-FW nettoyées")
        else:
            self.logger.debug(
                "Aucune règle YARP-FW existante à nettoyer "
                "(normal au premier lancement)"
            )

    # ------------------------------------------------------------------ #
    #  Application d'une règle utilisateur                                 #
    # ------------------------------------------------------------------ #

    def _apply_rule(self, rule):
        """Applique une règle firewall unique.

        Paramètres attendus dans le dict `rule` :
          - name       : str  (obligatoire) — nom descriptif
          - from       : str  (obligatoire) — interface source
          - to         : str  (obligatoire) — interface destination
          - protocols  : dict | "any" — { tcp: ..., udp: ..., icmp: true } ou "any"
          - action     : str  (obligatoire) — accept / drop / reject
        """
        name = rule.get('name', 'unnamed')
        iface_in = rule.get('from', '')
        iface_out = rule.get('to', '')
        protocols = rule.get('protocols', 'any')
        action = rule.get('action', 'accept').upper()

        if action == 'REJECT':
            target = 'REJECT --reject-with icmp-port-unreachable'
        else:
            target = action  # ACCEPT ou DROP

        comment = f"YARP-FW-RULE-{name}"
        base_args = f"-i {iface_in} -o {iface_out}" if iface_in and iface_out else ""

        # --- Cas "any" : tout le trafic, pas de filtre protocole ---
        if protocols == 'any':
            cmd = (
                f"iptables -A FORWARD {base_args} "
                f"-m comment --comment '{comment}' "
                f"-j {target}"
            )
            success, _, stderr = self._run_command(cmd, check=False)
            if not success:
                self.logger.error(f"Erreur règle '{name}': {stderr}")
                return False
            self.logger.info(f"Règle '{name}': {iface_in} → {iface_out} any → {action}")
            return True

        # --- Cas dict de protocoles ---
        if not isinstance(protocols, dict):
            self.logger.error(
                f"Règle '{name}': protocols doit être un dict ou 'any', "
                f"reçu {type(protocols).__name__}"
            )
            return False

        for proto, port_value in protocols.items():
            proto = proto.lower()

            # ICMP : pas de notion de port
            if proto == 'icmp':
                cmd = (
                    f"iptables -A FORWARD {base_args} -p icmp "
                    f"-m comment --comment '{comment}' "
                    f"-j {target}"
                )
                success, _, stderr = self._run_command(cmd, check=False)
                if not success:
                    self.logger.error(f"Erreur règle '{name}' icmp: {stderr}")
                    return False
                self.logger.info(
                    f"Règle '{name}': {iface_in} → {iface_out} icmp → {action}"
                )
                continue

            # TCP / UDP avec ports
            if proto not in ('tcp', 'udp'):
                self.logger.warning(f"Règle '{name}': protocole '{proto}' non supporté, ignoré")
                continue

            ports = self._normalize_ports(port_value)
            if not ports:
                self.logger.warning(
                    f"Règle '{name}': aucun port valide pour {proto}, ignoré"
                )
                continue

            port_args = self._build_port_args(ports)

            cmd = (
                f"iptables -A FORWARD {base_args} -p {proto} "
                f"{port_args} "
                f"-m comment --comment '{comment}' "
                f"-j {target}"
            )

            success, _, stderr = self._run_command(cmd, check=False)
            if not success:
                self.logger.error(f"Erreur règle '{name}' {proto}: {stderr}")
                return False

            self.logger.info(
                f"Règle '{name}': {iface_in} → {iface_out} "
                f"{proto}/{','.join(ports)} → {action}"
            )

        return True

    # ------------------------------------------------------------------ #
    #  Application complète                                                #
    # ------------------------------------------------------------------ #

    def apply_all(self):
        """Applique toute la configuration firewall"""
        self.logger.info("=== Application de la configuration Firewall ===")

        # S'il n'y a pas de section firewall, ne rien faire
        if not self.firewall:
            self.logger.info("Aucune configuration firewall définie")
            return True

        # 1. Nettoyer les règles YARP-FW existantes
        self.clear_firewall_rules()

        # 2. Appliquer les politiques par défaut
        if not self.apply_default_policies():
            self.logger.error("Erreur lors de l'application des politiques par défaut")
            return False

        # 3. Appliquer les règles stateful (avant les règles utilisateur)
        if not self.apply_stateful_rules():
            self.logger.error("Erreur lors de l'application des règles stateful")
            return False

        # 4. Appliquer les règles utilisateur
        rules = self.firewall.get('rules', [])
        if not rules:
            self.logger.info("Aucune règle firewall à appliquer")
            return True

        success_count = 0
        total_count = len(rules)

        for rule in rules:
            if self._apply_rule(rule):
                success_count += 1

        self.logger.info(
            f"Firewall configuré: {success_count}/{total_count} règles appliquées"
        )

        return success_count == total_count

    # ------------------------------------------------------------------ #
    #  Affichage de l'état                                                 #
    # ------------------------------------------------------------------ #

    def show_firewall_status(self):
        """Affiche l'état actuel du firewall"""
        print("\n=== État du Firewall ===")

        # Politiques par défaut
        print("\n--- Politiques par défaut ---")
        for chain in ['INPUT', 'FORWARD', 'OUTPUT']:
            success, stdout, _ = self._run_command(
                f"iptables -L {chain} -n | head -1", check=False
            )
            if success:
                print(f"  {stdout.strip()}")

        # Règles YARP-FW
        print("\n--- Règles YARP Firewall ---")
        success, stdout, _ = self._run_command(
            "iptables -L FORWARD -n --line-numbers", check=False
        )
        if success:
            lines = stdout.split('\n')
            yarp_rules = [line for line in lines if 'YARP-FW' in line]
            if yarp_rules:
                for rule in yarp_rules:
                    print(f"  {rule}")
            else:
                print("  Aucune règle YARP-FW")

        # Règles stateful
        print("\n--- Règles Stateful ---")
        success, stdout, _ = self._run_command(
            "iptables -L INPUT -n --line-numbers", check=False
        )
        if success:
            lines = stdout.split('\n')
            stateful_rules = [line for line in lines if 'YARP-FW-STATEFUL' in line or 'YARP-FW-LOOPBACK' in line]
            if stateful_rules:
                for rule in stateful_rules:
                    print(f"  {rule}")
            else:
                print("  Aucune règle stateful YARP")


def main():
    from yarp_config import YARPConfig

    # Gestion des arguments
    if len(sys.argv) < 2:
        print("Usage: firewall.py <config_file> [command]")
        print("   ou: firewall.py <command>")
        print("Commands:")
        print("  apply      - Appliquer les règles firewall")
        print("  show       - Afficher l'état du firewall")
        print("  clear      - Nettoyer les règles firewall YARP")
        sys.exit(1)

    # Cas 1: firewall.py apply/show/clear (utilise config par défaut)
    if sys.argv[1] in ["apply", "show", "clear"]:
        config_file = "/etc/yarp/config.yaml"
        command = sys.argv[1]
    # Cas 2: firewall.py <config_file> [command]
    else:
        config_file = sys.argv[1]
        command = sys.argv[2] if len(sys.argv) > 2 else "apply"

    config = YARPConfig(config_file)
    if not config.load():
        sys.exit(1)

    manager = FirewallManager(config)

    if command == "apply":
        if manager.apply_all():
            sys.exit(0)
        else:
            sys.exit(1)
    elif command == "show":
        manager.show_firewall_status()
    elif command == "clear":
        manager.clear_firewall_rules()
        print("Règles firewall YARP nettoyées")
    else:
        print(f"Commande inconnue: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
