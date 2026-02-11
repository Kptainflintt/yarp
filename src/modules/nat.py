#!/usr/bin/env python3
"""
YARP NAT Module
Gestion du NAT et masquerading
"""

import subprocess
import sys
import re
import os
import time
import ipaddress
from pathlib import Path

YARP_DIR = "/opt/yarp"
sys.path.insert(0, os.path.join(YARP_DIR, 'core'))

from yarp_config import YARPConfig
from yarp_logger import get_logger

class NATManager:
    def __init__(self, config):
        self.config = config
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

    def validate_ip_range(self, cidr):
        """Valide qu'une plage IP est valide"""
        try:
            ipaddress.ip_network(cidr, strict=False)
            return True
        except ValueError:
            return False

    def get_nat_interfaces(self):
        """Retourne les interfaces avec masquerading activé"""
        nat_interfaces = {}

        for iface_name, iface_config in self.interfaces.items():
            if iface_config.get('masquerading', False):
                sources = iface_config.get('masquerade_sources', [])

                # Valider toutes les sources
                valid_sources = []
                for source in sources:
                    if self.validate_ip_range(source):
                        valid_sources.append(source)
                        self.logger.debug(f"Source valide pour {iface_name}: {source}")
                    else:
                        self.logger.warning(f"Source invalide ignorée pour {iface_name}: {source}")

                if valid_sources:
                    nat_interfaces[iface_name] = valid_sources
                    self.logger.info(f"Interface NAT: {iface_name} avec {len(valid_sources)} sources")
                else:
                    self.logger.warning(f"Interface {iface_name}: masquerading activé mais aucune source valide")

        return nat_interfaces

    def enable_ip_forwarding(self):
        """Active le forwarding IP dans le kernel"""
        self.logger.info("Activation du forwarding IP")

        # IPv4 forwarding
        success_v4, _, stderr_v4 = self._run_command(
            "sysctl -w net.ipv4.ip_forward=1",
            check=False
        )

        # IPv6 forwarding (optionnel)
        success_v6, _, stderr_v6 = self._run_command(
            "sysctl -w net.ipv6.conf.all.forwarding=1",
            check=False
        )

        if success_v4:
            self.logger.info("Forwarding IPv4 activé")
        else:
            self.logger.error(f"Erreur activation forwarding IPv4: {stderr_v4}")

        if success_v6:
            self.logger.info("Forwarding IPv6 activé")
        else:
            self.logger.warning(f"Forwarding IPv6 non activé: {stderr_v6}")

        return success_v4

    def clear_nat_rules(self):
        """Nettoie les règles NAT existantes de YARP"""
        self.logger.info("Nettoyage des règles NAT existantes")

        # Supprimer les règles YARP dans la table nat
        self._run_command("iptables -t nat -D POSTROUTING -m comment --comment 'YARP-NAT' -j MASQUERADE", check=False)

        # Supprimer les règles YARP dans la table filter
        self._run_command("iptables -D FORWARD -m comment --comment 'YARP-FORWARD' -j ACCEPT", check=False)

        # Flush des chaînes YARP custom si elles existent
        self._run_command("iptables -t nat -F YARP-MASQUERADE", check=False)
        self._run_command("iptables -t nat -X YARP-MASQUERADE", check=False)

    def setup_masquerade_rules(self, nat_interfaces):
        """Configure les règles de masquerading"""
        self.logger.info("Configuration des règles de masquerading")

        for interface, sources in nat_interfaces.items():
            self.logger.info(f"Configuration masquerading sur {interface}")

            for source in sources:
                # Règle MASQUERADE pour chaque source
                cmd = (f"iptables -t nat -A POSTROUTING "
                      f"-s {source} -o {interface} "
                      f"-m comment --comment 'YARP-NAT-{interface}' "
                      f"-j MASQUERADE")

                success, _, stderr = self._run_command(cmd, check=False)

                if success:
                    self.logger.info(f"Masquerading configuré: {source} -> {interface}")
                else:
                    self.logger.error(f"Erreur masquerading {source} -> {interface}: {stderr}")
                    return False

        return True

    def setup_forward_rules(self, nat_interfaces):
        """Configure les règles de forwarding"""
        self.logger.info("Configuration des règles de forwarding")

        for interface, sources in nat_interfaces.items():
            for source in sources:
                # Règle FORWARD sortant (LAN -> WAN)
                cmd_out = (f"iptables -A FORWARD "
                          f"-s {source} -o {interface} "
                          f"-m comment --comment 'YARP-FORWARD-OUT' "
                          f"-j ACCEPT")

                success_out, _, stderr_out = self._run_command(cmd_out, check=False)

                # Règle FORWARD entrant (WAN -> LAN pour connexions établies)
                cmd_in = (f"iptables -A FORWARD "
                         f"-i {interface} -m state --state RELATED,ESTABLISHED "
                         f"-m comment --comment 'YARP-FORWARD-IN' "
                         f"-j ACCEPT")

                success_in, _, stderr_in = self._run_command(cmd_in, check=False)

                if success_out and success_in:
                    self.logger.info(f"Forward configuré: {source} <-> {interface}")
                else:
                    error_msg = f"Erreur forward {source} <-> {interface}"
                    if not success_out:
                        error_msg += f" OUT: {stderr_out}"
                    if not success_in:
                        error_msg += f" IN: {stderr_in}"
                    self.logger.error(error_msg)
                    return False

        return True

    def apply_all(self):
        """Applique toute la configuration NAT"""
        self.logger.info("=== Application de la configuration NAT ===")

        # Obtenir les interfaces NAT
        nat_interfaces = self.get_nat_interfaces()

        if not nat_interfaces:
            self.logger.info("Aucune interface NAT configurée")
            return True

        # Activer le forwarding IP
        if not self.enable_ip_forwarding():
            self.logger.error("Impossible d'activer le forwarding IP")
            return False

        # Nettoyer les règles existantes
        self.clear_nat_rules()

        # Configurer masquerading
        if not self.setup_masquerade_rules(nat_interfaces):
            self.logger.error("Erreur lors de la configuration du masquerading")
            return False

        # Configurer forwarding
        if not self.setup_forward_rules(nat_interfaces):
            self.logger.error("Erreur lors de la configuration du forwarding")
            return False

        total_rules = sum(len(sources) for sources in nat_interfaces.values())
        self.logger.info(f"NAT configuré avec succès: {len(nat_interfaces)} interfaces, {total_rules} règles")

        return True

    def show_nat_status(self):
        """Affiche l'état actuel du NAT"""
        print("\n=== État du NAT ===")

        # Forwarding status
        success, stdout, _ = self._run_command("sysctl net.ipv4.ip_forward", check=False)
        if success:
            forwarding = "ACTIVÉ" if "1" in stdout else "DÉSACTIVÉ"
            print(f"Forwarding IPv4: {forwarding}")

        # Règles NAT
        print("\n--- Règles MASQUERADE ---")
        success, stdout, _ = self._run_command("iptables -t nat -L POSTROUTING -n", check=False)
        if success:
            lines = stdout.split('\n')
            yarp_rules = [line for line in lines if 'YARP' in line]
            if yarp_rules:
                for rule in yarp_rules:
                    print(f"  {rule}")
            else:
                print("  Aucune règle YARP")

        # Règles FORWARD
        print("\n--- Règles FORWARD ---")
        success, stdout, _ = self._run_command("iptables -L FORWARD -n", check=False)
        if success:
            lines = stdout.split('\n')
            yarp_rules = [line for line in lines if 'YARP' in line]
            if yarp_rules:
                for rule in yarp_rules:
                    print(f"  {rule}")
            else:
                print("  Aucune règle YARP")

def main():
    from yarp_config import YARPConfig

    # Gestion des arguments
    if len(sys.argv) < 2:
        print("Usage: nat.py <config_file> [command]")
        print("   ou: nat.py <command>")
        print("Commands:")
        print("  apply      - Appliquer les règles NAT")
        print("  show       - Afficher l'état NAT")
        print("  clear      - Nettoyer les règles NAT")
        sys.exit(1)

    # Cas 1: nat.py apply/show/clear (utilise config par défaut)
    if sys.argv[1] in ["apply", "show", "clear"]:
        config_file = "/etc/yarp/config.yaml"
        command = sys.argv[1]
    # Cas 2: nat.py <config_file> [command]
    else:
        config_file = sys.argv[1]
        command = sys.argv[2] if len(sys.argv) > 2 else "apply"

    config = YARPConfig(config_file)
    if not config.load():
        sys.exit(1)

    manager = NATManager(config)

    if command == "apply":
        if manager.apply_all():
            sys.exit(0)
        else:
            sys.exit(1)
    elif command == "show":
        manager.show_nat_status()
    elif command == "clear":
        manager.clear_nat_rules()
        print("Règles NAT nettoyées")
    else:
        print(f"Commande inconnue: {command}")
        sys.exit(1)

if __name__ == "__main__":
    main()