#!/usr/bin/env python3
"""
YARP Network Module
Gestion des interfaces réseau
"""

import subprocess
import sys
import re
from pathlib import Path

class NetworkManager:
    def __init__(self, config):
        self.config = config
        self.interfaces = config.get_interfaces()
    
    def _run_command(self, cmd, check=True):
        """Exécute une commande système"""
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                check=check
            )
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.CalledProcessError as e:
            return False, e.stdout, e.stderr
    
    def interface_exists(self, iface):
        """Vérifie si une interface existe"""
        success, stdout, _ = self._run_command(f"ip link show {iface}", check=False)
        return success
    
    def bring_interface_up(self, iface):
        """Active une interface"""
        print(f"Activation de l'interface {iface}")
        success, _, stderr = self._run_command(f"ip link set {iface} up")
        if not success:
            print(f"Erreur lors de l'activation de {iface}: {stderr}", file=sys.stderr)
        return success
    
    def bring_interface_down(self, iface):
        """Désactive une interface"""
        print(f"Désactivation de l'interface {iface}")
        return self._run_command(f"ip link set {iface} down")[0]
    
    def flush_addresses(self, iface):
        """Supprime toutes les adresses d'une interface"""
        print(f"Nettoyage des adresses de {iface}")
        self._run_command(f"ip addr flush dev {iface}", check=False)
    
    def set_ipv4_address(self, iface, address):
        """Configure une adresse IPv4"""
        print(f"Configuration IPv4 de {iface}: {address}")
        success, _, stderr = self._run_command(
            f"ip addr add {address} dev {iface}"
        )
        if not success:
            print(f"Erreur IPv4 sur {iface}: {stderr}", file=sys.stderr)
        return success
    
    def set_ipv6_address(self, iface, address):
        """Configure une adresse IPv6"""
        print(f"Configuration IPv6 de {iface}: {address}")
        success, _, stderr = self._run_command(
            f"ip -6 addr add {address} dev {iface}"
        )
        if not success:
            print(f"Erreur IPv6 sur {iface}: {stderr}", file=sys.stderr)
        return success
    
    def enable_dhcp(self, iface):
        """Active DHCP sur une interface"""
        print(f"Activation DHCP sur {iface}")
        # Arrêter dhcpcd existant pour cette interface
        self._run_command(f"pkill -f 'dhcpcd.*{iface}'", check=False)
        # Démarrer dhcpcd
        success, _, stderr = self._run_command(f"dhcpcd {iface}")
        if not success:
            print(f"Erreur DHCP sur {iface}: {stderr}", file=sys.stderr)
        return success
    
    def enable_ipv6_auto(self, iface):
        """Active l'autoconfiguration IPv6"""
        print(f"Activation autoconfiguration IPv6 sur {iface}")
        self._run_command(f"sysctl -w net.ipv6.conf.{iface}.autoconf=1")
        self._run_command(f"sysctl -w net.ipv6.conf.{iface}.accept_ra=1")
        return True
    
    def configure_interface(self, iface, config):
        """Configure une interface complète"""
        print(f"\n=== Configuration de {iface} ===")
        
        if not self.interface_exists(iface):
            print(f"ATTENTION: Interface {iface} n'existe pas", file=sys.stderr)
            return False
        
        # Nettoyer l'interface
        self.flush_addresses(iface)
        
        # Activer l'interface
        if not self.bring_interface_up(iface):
            return False
        
        # Configuration IPv4
        if 'ipv4' in config:
            if config['ipv4'] == 'dhcp':
                self.enable_dhcp(iface)
            else:
                self.set_ipv4_address(iface, config['ipv4'])
        
        # Configuration IPv6
        if 'ipv6' in config:
            if config['ipv6'] == 'auto':
                self.enable_ipv6_auto(iface)
            else:
                self.set_ipv6_address(iface, config['ipv6'])
        
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
    
    config = YARPConfig()
    if not config.load() or not config.validate():
        sys.exit(1)
    
    manager = NetworkManager(config)
    
    if len(sys.argv) > 1 and sys.argv[1] == "apply":
        if manager.apply_all():
            sys.exit(0)
        else:
            sys.exit(1)
    else:
        print("Usage: network.py apply")
        sys.exit(1)

if __name__ == "__main__":
    main()
