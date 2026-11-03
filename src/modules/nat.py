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
import shlex
from pathlib import Path

YARP_DIR = "/opt/yarp"
sys.path.insert(0, os.path.join(YARP_DIR, 'core'))

from yarp_config import YARPConfig
from yarp_logger import get_logger

def _validate_interface_name(name: str) -> bool:
    """Valide qu'un nom d'interface réseau est valide.

    Les noms d'interface doivent contenir uniquement des caractères alphanumériques,
    des traits du soulignement, et des tirets. Ils ne doivent pas commencer par un chiffre.
    """
    if not name or not isinstance(name, str):
        return False
    # Pattern : doit contenir alphanumérique + _ - , ne pas commencer par un chiffre
    pattern = r"^[a-zA-Z][a-zA-Z0-9_-]*$"
    return bool(re.match(pattern, name))


def _validate_ip_or_cidr(value: str) -> bool:
    """Valide qu'une IP ou plage CIDR est valide.

    Retourne True si c'est une IP unique ou un réseau CIDR valide.
    """
    if not value or not isinstance(value, str):
        return False
    try:
        ipaddress.ip_network(value, strict=False)
        return True
    except ValueError:
        return False


def _run_command_list(args: list, logger, check: bool = True):
    """Exécute une commande système avec une liste d'arguments (sécurisé)."""
    start_time = time.time()
    # Reconstituer la chaîne de commande pour le logging
    cmd_str = " ".join(shlex.quote(arg) for arg in args)
    try:
        result = subprocess.run(
            args, shell=False, capture_output=True, text=True, check=check
        )
        duration_ms = int((time.time() - start_time) * 1000)

        # Logger l'exécution commande
        logger.command_execution(cmd_str, result.returncode, duration_ms)

        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.command_execution(cmd_str, e.returncode, duration_ms)
        return False, e.stdout, e.stderr
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(f"Erreur système lors de l'exécution: {e}")
        return False, "", str(e)


class NATManager:
    def __init__(self, config):
        self.config = config
        self.interfaces = config.get_interfaces()

        # Initialiser le logger avec la config YARP
        logging_config = config.get_logging()
        self.logger = get_logger("firewall", {'logging': logging_config})

    def _run_command(self, args, check=True):
        """Exécute une commande système avec logging (liste d'arguments sécurisée)."""
        return _run_command_list(args, self.logger, check)

    def _run_command_silent(self, args):
        """Exécute une commande silencieuse (pour nettoyage, sans logging d'erreur)"""
        try:
            return _run_command_list(args, self.logger, check=False)
        except Exception:
            return False, "", ""

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
            ["sysctl", "-w", "net.ipv4.ip_forward=1"],
            check=False
        )

        # IPv6 forwarding (optionnel)
        success_v6, _, stderr_v6 = self._run_command(
            ["sysctl", "-w", "net.ipv6.conf.all.forwarding=1"],
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

        rules_cleaned = 0

        # Lister les règles POSTROUTING et supprimer celles avec YARP-NAT
        success, stdout, _ = self._run_command_silent([
            "iptables", "-t", "nat", "-L", "POSTROUTING",
            "--line-numbers", "-n"
        ])
        if success and stdout.strip():
            # Supprimer les règles en partant de la fin
            lines = stdout.strip().split('\n')
            line_numbers = []
            for line in lines:
                if 'YARP-NAT' in line:
                    line_num = line.split()[0]
                    if line_num.isdigit():
                        line_numbers.append(int(line_num))

            # Supprimer en ordre décroissant pour éviter les décalages
            for line_num in sorted(line_numbers, reverse=True):
                success, _, _ = self._run_command_silent(["iptables", "-t", "nat", "-D", "POSTROUTING", str(line_num)])
                if success:
                    rules_cleaned += 1

        if rules_cleaned > 0:
            self.logger.info(f"{rules_cleaned} règles YARP-NAT nettoyées")
        else:
            self.logger.debug("Aucune règle YARP-NAT existante à nettoyer (normal au premier lancement)")

    def setup_masquerade_rules(self, nat_interfaces):
        """Configure les règles de masquerading"""
        self.logger.info("Configuration des règles de masquerading")

        for interface, sources in nat_interfaces.items():
            self.logger.info(f"Configuration masquerading sur {interface}")

            for source in sources:
                # Validate source (IP or CIDR)
                if not self.validate_ip_range(source):
                    self.logger.warning(f"Source invalide ignorée pour {interface}: {source}")
                    continue

                # Validate interface name
                if not _validate_interface_name(interface):
                    self.logger.warning(f"Interface invalide ignorée pour {interface}")
                    continue

                # Règle MASQUERADE pour chaque source (command list)
                args = [
                    "iptables", "-t", "nat", "-A", "POSTROUTING",
                    "-s", source, "-o", interface,
                    "-m", "comment", "--comment", f"YARP-NAT-{interface}",
                    "-j", "MASQUERADE"
                ]

                success, _, stderr = self._run_command(args, check=False)

                if success:
                    self.logger.info(f"Masquerading configuré: {source} -> {interface}")
                else:
                    self.logger.error(f"Erreur masquerading {source} -> {interface}: {stderr}")
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

        total_rules = sum(len(sources) for sources in nat_interfaces.values())
        self.logger.info(f"NAT configuré avec succès: {len(nat_interfaces)} interfaces, {total_rules} règles")

        return True

    def show_nat_status(self):
        """Affiche l'état actuel du NAT"""
        print("\n=== État du NAT ===")

        # Forwarding status
        success, stdout, _ = self._run_command(["sysctl", "net.ipv4.ip_forward"], check=False)
        if success:
            forwarding = "ACTIVÉ" if "1" in stdout else "DÉSACTIVÉ"
            print(f"Forwarding IPv4: {forwarding}")

        # Règles NAT
        print("\n--- Règles MASQUERADE ---")
        success, stdout, _ = self._run_command([
                    "iptables", "-t", "nat", "-L", "POSTROUTING", "-n"
                ], check=False)
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