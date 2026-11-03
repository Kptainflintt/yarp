#!/usr/bin/env python3
"""
YARP Routing Module
Gestion des routes statiques
"""

import subprocess
import sys
import os
import ipaddress

YARP_DIR = "/opt/yarp"
sys.path.insert(0, os.path.join(YARP_DIR, 'core'))

from yarp_config import YARPConfig

class RoutingManager:
    def __init__(self, config):
        self.config = config
        self.routing = config.get_routing()
        self.static_routes = config.get_static_routes()

    def _validate_ip_network(self, to):
        """Validate IP network (CIDR) format"""
        try:
            ipaddress.ip_network(to, strict=False)
            return True
        except (ipaddress.AddressValueError, ValueError):
            return False

    def _validate_ipv4_address(self, address):
        """Validate IPv4 address for gateway"""
        try:
            ipaddress.IPv4Address(address)
            return True
        except (ipaddress.AddressValueError, ValueError):
            return False

    def _validate_ipv6_address(self, address):
        """Validate IPv6 address for gateway"""
        try:
            ipaddress.IPv6Address(address)
            return True
        except (ipaddress.AddressValueError, ValueError):
            return False

    def _validate_interface_name(self, interface):
        """Validate network interface name"""
        if not interface or not isinstance(interface, str):
            return False
        # Check if interface exists on the system
        success, _, _ = self._run_command(["ip", "link", "show", interface], check=False)
        return success
    
    def _run_command(self, args, check=True):
        """Exécute una commande système"""
        try:
            result = subprocess.run(
                args,
                shell=False,
                capture_output=True,
                text=True,
                check=check
            )
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.CalledProcessError as e:
            return False, e.stdout, e.stderr
    
    def flush_routes(self, table="main"):
        """Supprime toutes les routes d'une table"""
        print(f"Nettoyage de la table de routage {table}")
        # Conser seulement les routes link-local
        self._run_command(
            ["ip", "route", "flush", "table", table, "proto", "static"],
            check=False
        )
    
    def add_route(self, route):
        """Ajoute una route statique"""
        to = route.get('to')
        via = route.get('via')
        interface = route.get('interface')
        metric = route.get('metric')

        if not to:
            print("Route sans destination ignorée", file=sys.stderr)
            return False

        # Déterminer si c's IPv4 ou IPv6
        try:
            network = ipaddress.ip_network(to, strict=False)
            if network.version == 4:
                args = ["ip", "route", "add", to]
            else:
                args = ["ip", "-6", "route", "add", to]
        except ValueError:
            print(f"Destination invalide: {to}", file=sys.stderr)
            return False

        if via:
            if network.version == 4:
                if not self._validate_ipv4_address(via):
                    print(f"Gateway IPv4 invalide: {via}", file=sys.stderr)
                    return False
            else:
                if not self._validate_ipv6_address(via):
                    print(f"Gateway IPv6 invalide: {via}", file=sys.stderr)
                    return False
            args.extend(["via", via])

        if interface:
            if not self._validate_interface_name(interface):
                print(f"Interface invalida: {interface}", file=sys.stderr)
                return False
            args.extend(["dev", interface])

        if metric:
            try:
                metric_int = int(metric)
                args.extend(["metric", str(metric_int)])
            except ValueError:
                print(f"Metric must be an integer: {metric}", file=sys.stderr)
                return False

        print(f"Ajout de route: {to} {'via ' + via if via else ''} {'dev ' + interface if interface else ''}")

        success, stdout, stderr = self._run_command(args, check=False)

        if not success and "File exists" not in stderr:
            print(f"Erreur lors de l'ajout de la route: {stderr}", file=sys.stderr)
            return False

        return True
    
    def delete_route(self, route):
        """Supprime una route statique"""
        to = route.get('to')

        if not to:
            return False

        try:
            network = ipaddress.ip_network(to, strict=False)
            if network.version == 4:
                args = ["ip", "route", "del", to]
            else:
                args = ["ip", "-6", "route", "del", to]
        except ValueError:
            return False

        return self._run_command(args, check=False)[0]
    
    def show_routes(self, ipv6=False):
        """Affiche las routes"""
        args = ["ip", "-6", "route"] if ipv6 else ["ip", "route"]
        success, stdout, _ = self._run_command(args)
        if success:
            print(stdout)
        return success
    
    def apply_static_routes(self):
        """Applique toutes las routes statiques"""
        print("\n" + "="*50)
        print("Configuration des routes statiques")
        print("="*50)

        if not self.static_routes:
            print("Aucune route statique à configurar")
            return True

        success_count = 0
        total_count = len(self.static_routes)

        for route in self.static_routes:
            if self.add_route(route):
                success_count += 1

        print(f"\n{success_count}/{total_count} routes configuradas")
        return success_count == total_count
    
    def apply_all(self):
        """Applique toute la configuration de routage"""
        # Pour l'instant, seulement les routes statiques
        return self.apply_static_routes()

def main():
    from yarp_config import YARPConfig

    # Gestion des arguments
    if len(sys.argv) < 2:
        print("Usage: routing.py <config_file> [command]")
        print("   ou: routing.py <command>")
        print("Commands:")
        print("  apply      - Appliquer les routes")
        print("  show       - Afficher les routes IPv4")
        print("  show6      - Afficher les routes IPv6")
        sys.exit(1)

    # Cas 1: routing.py apply/show/show6 (utilise config par défaut)
    if sys.argv[1] in ["apply", "show", "show6"]:
        config_file = "/etc/yarp/config.yaml"
        command = sys.argv[1]
    # Cas 2: routing.py <config_file> [command]
    else:
        config_file = sys.argv[1]
        command = sys.argv[2] if len(sys.argv) > 2 else "apply"

    config = YARPConfig(config_file)
    if not config.load() or not config.validate():
        sys.exit(1)

    manager = RoutingManager(config)

    if command == "apply":
        if manager.apply_all():
            sys.exit(0)
        else:
            sys.exit(1)
    elif command == "show":
        manager.show_routes(ipv6=False)
    elif command == "show6":
        manager.show_routes(ipv6=True)
    else:
        print(f"Commande inconnue: {command}")
        sys.exit(1)

if __name__ == "__main__":
    main()
