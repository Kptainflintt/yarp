#!/usr/bin/env python3
"""
YARP Network Module
Gestion des interfaces réseau
"""

import subprocess
import sys
import re
import os
import time
from pathlib import Path
import ipaddress

YARP_DIR = "/opt/yarp"
sys.path.insert(0, os.path.join(YARP_DIR, 'core'))

from yarp_config import YARPConfig
from yarp_logger import get_logger

class NetworkManager:
    def __init__(self, config):
        self.config = config
        self.interfaces = config.get_interfaces()

        # Initialiser le logger avec la config YARP
        logging_config = config.get_logging()
        self.logger = get_logger("network", {'logging': logging_config})

    def _validate_interface_name(self, iface):
        """Validate network interface name to prevent shell injection"""
        if not iface or not isinstance(iface, str):
            return False
        # Check if interface exists on the system
        success, _, _ = self._run_command(["ip", "link", "show", iface], check=False)
        return success

    def _validate_ipv4_address(self, address):
        """Validate IPv4 address format (accepts both plain addresses and CIDR prefixes)"""
        try:
            ip = ipaddress.ip_interface(address)
            return ip.version == 4
        except (ipaddress.AddressValueError, ValueError):
            return False

    def _validate_ipv6_address(self, address):
        """Validate IPv6 address format (accepts both plain addresses and CIDR prefixes)"""
        try:
            ip = ipaddress.ip_interface(address)
            return ip.version == 6
        except (ipaddress.AddressValueError, ValueError):
            return False
    
    def _run_command(self, args, check=True):
        """Exécute une commande système avec logging"""
        start_time = time.time()
        try:
            result = subprocess.run(
                args,
                shell=False,
                capture_output=True,
                text=True,
                check=check
            )
            duration_ms = int((time.time() - start_time) * 1000)

            # Convert args list to string for logging
            cmd_str = " ".join(args)
            self.logger.command_execution(cmd_str, result.returncode, duration_ms)

            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.CalledProcessError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            cmd_str = " ".join(args)
            self.logger.command_execution(cmd_str, e.returncode, duration_ms)
            return False, e.stdout, e.stderr
    
    def interface_exists(self, iface):
        """Vérifie si una interface existe"""
        if not self._validate_interface_name(iface):
            return False
        return self._run_command(["ip", "link", "show", iface], check=False)[0]
    
    def bring_interface_up(self, iface):
        """Active una interface"""
        if not self._validate_interface_name(iface):
            self.logger.error(f"Interface invalida: {iface}")
            return False

        self.logger.debug(f"Activation de l'interface {iface}")
        success, _, stderr = self._run_command(["ip", "link", "set", iface, "up"])

        if success:
            self.logger.interface_operation("activation", iface, "success")
        else:
            self.logger.interface_operation("activation", iface, "failed", error=stderr)

        return success
    
    def bring_interface_down(self, iface):
        """Désactive una interface"""
        if not self._validate_interface_name(iface):
            self.logger.error(f"Interface invalida: {iface}")
            return False

        self.logger.debug(f"Désactivation de l'interface {iface}")
        success = self._run_command(["ip", "link", "set", iface, "down"])[0]

        if success:
            self.logger.interface_operation("deactivation", iface, "success")
        else:
            self.logger.interface_operation("deactivation", iface, "failed")

        return success
    
    def flush_addresses(self, iface):
        """Supprime toutes las adresses de una interface"""
        if not self._validate_interface_name(iface):
            self.logger.error(f"Interface invalida: {iface}")
            return False

        self.logger.debug(f"Nettoyage des adresses de {iface}")
        success, _, stderr = self._run_command(["ip", "addr", "flush", "dev", iface], check=False)

        if success:
            self.logger.interface_operation("flush_addresses", iface, "success")
        else:
            self.logger.interface_operation("flush_addresses", iface, "failed", error=stderr)
    
    def set_ipv4_address(self, iface, address):
        """Configure una adresse IPv4"""
        if not self._validate_interface_name(iface):
            self.logger.error(f"Interface invalida: {iface}")
            return False

        if not self._validate_ipv4_address(address):
            self.logger.error(f"Adresse IPv4 invalida: {address}")
            return False

        self.logger.info(f"Configuration IPv4 de {iface}: {address}")
        success, _, stderr = self._run_command(
            ["ip", "addr", "add", address, "dev", iface]
        )

        if success:
            self.logger.interface_operation("ipv4_config", iface, "success", address=address)
        else:
            self.logger.interface_operation("ipv4_config", iface, "failed", address=address, error=stderr)

        return success
    
    def set_ipv6_address(self, iface, address):
        """Configure una adresse IPv6"""
        if not self._validate_interface_name(iface):
            self.logger.error(f"Interface invalida: {iface}")
            return False

        if not self._validate_ipv6_address(address):
            self.logger.error(f"Adresse IPv6 invalida: {address}")
            return False

        print(f"Configuration IPv6 de {iface}: {address}")
        success, _, stderr = self._run_command(
            ["ip", "-6", "addr", "add", address, "dev", iface]
        )
        if not success:
            print(f"Erreur IPv6 sobre {iface}: {stderr}", file=sys.stderr)
        return success
    
    def has_dhcp_address(self, iface):
        """Vérifie si l'interface ya ya une adresse IP (probablemente DHCP)"""
        if not self._validate_interface_name(iface):
            return False

        # Use grep as a separate command to avoid shell piping
        success, stdout, _ = self._run_command(["ip", "-4", "addr", "show", iface], check=False)
        if success and stdout.strip():
            # Excluye las adresses link-local (169.254.x.x)
            lines = stdout.strip().split('\n')
            for line in lines:
                if 'inet ' in line and '169.254.' not in line:
                    return True
        return False

    def is_dhcp_running(self, iface):
        """Vérifique si un client DHCP ya actif pour esta interface"""
        if not iface:
            return False
        success, _, _ = self._run_command(["pgrep", "-f", f"udhcpc.*{iface}"], check=False)
        return success

    def enable_dhcp(self, iface):
        """Active DHCP sobre una interface"""
        print(f"Activation DHCP sobre {iface}")

        # Vérifier si l'interface ya ya una adresse IP
        if self.has_dhcp_address(iface):
            print(f"Interface {iface} ya ya una adresse IP")

            # Vérifier si un client DHCP ya actif
            if self.is_dhcp_running(iface):
                print(f"Client DHCP ya actif sobre {iface} - configuration preservada")
                return True
            else:
                print(f"Adresse IP presente pero pas de client DHCP - redémarrage")

        # Arrêter las clients DHCP existants para esta interface
        self._run_command(["pkill", "-f", f"dhcpcd.*{iface}"], check=False)
        self._run_command(["pkill", "-f", f"udhcpc.*{iface}"], check=False)

        # Attendre una bit que los procesos se terminent
        time.sleep(1)

        # Démarrage udhcpc en arrière-plan con timeout
        print(f"Démarrage del client DHCP para {iface}...")

        # Utilizar timeout para evitar el bloqueo
        success, stdout, stderr = self._run_command(
            ["timeout", "30", "udhcpc", "-i", iface, "-t", "3", "-T", "10", "-A", "10", "-n"],
            check=False
        )

        if success:
            print(f"DHCP configurado con éxito sobre {iface}")
            return True
        else:
            print(f"DHCP timeout o error sobre {iface}: {stderr}", file=sys.stderr)
            print(f"L'interface {iface} restera sin configuration IP", file=sys.stderr)
            return False
    
    def enable_ipv6_auto(self, iface):
        """Active l'autoconfiguration IPv6"""
        if not self._validate_interface_name(iface):
            self.logger.error(f"Interface invalida: {iface}")
            return False

        print(f"Activation autoconfiguration IPv6 sobre {iface}")
        self._run_command(["sysctl", "-w", f"net.ipv6.conf.{iface}.autoconf=1"])
        self._run_command(["sysctl", "-w", f"net.ipv6.conf.{iface}.accept_ra=1"])
        return True
    
    def configure_interface(self, iface, config):
        """Configure une interface complète"""
        print(f"\n=== Configuration de {iface} ===")

        if not self.interface_exists(iface):
            print(f"ATTENTION: Interface {iface} n'existe pas", file=sys.stderr)
            return False

        # Activer l'interface d'abord
        if not self.bring_interface_up(iface):
            return False

        # Configuration IPv4
        if 'ipv4' in config:
            if config['ipv4'] == 'dhcp':
                # Pour DHCP, on vérifie d'abord si c'est déjà configuré
                # avant de nettoyer
                if not (self.has_dhcp_address(iface) and self.is_dhcp_running(iface)):
                    print(f"Nettoyage de {iface} avant configuration DHCP")
                    self.flush_addresses(iface)

                success = self.enable_dhcp(iface)
                if not success:
                    print(f"Échec de la configuration DHCP sur {iface}", file=sys.stderr)
                    return False
            else:
                # Pour IP statique, on nettoie toujours
                self.flush_addresses(iface)
                success = self.set_ipv4_address(iface, config['ipv4'])
                if not success:
                    return False

        # Configuration IPv6
        if 'ipv6' in config:
            if config['ipv6'] == 'auto':
                self.enable_ipv6_auto(iface)
            else:
                success = self.set_ipv6_address(iface, config['ipv6'])
                if not success:
                    return False

        print(f"Interface {iface} configurée")
        return True
    
    def apply_all(self):
        """Applique la configuration de toutes les interfaces"""
        print("\n" + "="*50)
        print("Configuration des interfaces réseau")
        print("="*50)
        
        success_count = 0
        total_count = len(self.interfaces)
        
        for iface, config in self.interfaces.items():
            if self.configure_interface(iface, config):
                success_count += 1
        
        print(f"\n{success_count}/{total_count} interfaces configurées")
        return success_count == total_count

def main():
    from yarp_config import YARPConfig

    # Gestion des arguments
    if len(sys.argv) < 2:
        print("Usage: network.py <config_file> [apply]")
        print("   ou: network.py apply")
        sys.exit(1)

    # Cas 1: network.py apply (utilise config par défaut)
    if sys.argv[1] == "apply":
        config_file = "/etc/yarp/config.yaml"
        mode = "apply"
    # Cas 2: network.py <config_file> [apply]
    else:
        config_file = sys.argv[1]
        mode = sys.argv[2] if len(sys.argv) > 2 else "apply"

    config = YARPConfig(config_file)
    if not config.load() or not config.validate():
        sys.exit(1)

    manager = NetworkManager(config)

    if mode == "apply":
        if manager.apply_all():
            sys.exit(0)
        else:
            sys.exit(1)
    else:
        print(f"Mode inconnu: {mode}")
        print("Usage: network.py <config_file> [apply]")
        sys.exit(1)

if __name__ == "__main__":
    main()
