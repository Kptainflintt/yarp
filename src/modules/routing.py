#!/usr/bin/env python3
"""
YARP Routing Module
Gestion des routes statiques
"""

import subprocess
import sys
import ipaddress

YARP_DIR = "/opt/yarp"
sys.path.insert(0, os.path.join(YARP_DIR, 'core'))

from yarp_config import YARPConfig

class RoutingManager:
    def __init__(self, config):
        self.config = config
        self.routing = config.get_routing()
        self.static_routes = config.get_static_routes()
    
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
    
    def flush_routes(self, table="main"):
        """Supprime toutes les routes d'une table"""
        print(f"Nettoyage de la table de routage {table}")
        # Conserver seulement les routes link-local
        self._run_command(
            f"ip route flush table {table} proto static",
            check=False
        )
    
    def add_route(self, route):
        """Ajoute une route statique"""
        to = route.get('to')
        via = route.get('via')
        interface = route.get('interface')
        metric = route.get('metric')
        
        if not to:
            print("Route sans destination ignorée", file=sys.stderr)
            return False
        
        # Déterminer si c'est IPv4 ou IPv6
        try:
            network = ipaddress.ip_network(to, strict=False)
            ip_cmd = "ip" if network.version == 4 else "ip -6"
        except ValueError:
            print(f"Destination invalide: {to}", file=sys.stderr)
            return False
        
        # Construire la commande
        cmd = f"{ip_cmd} route add {to}"
        
        if via:
            cmd += f" via {via}"
        
        if interface:
            cmd += f" dev {interface}"
        
        if metric:
            cmd += f" metric {metric}"
        
        print(f"Ajout de route: {to} {'via ' + via if via else ''} {'dev ' + interface if interface else ''}")
        
        success, stdout, stderr = self._run_command(cmd, check=False)
        
        if not success and "File exists" not in stderr:
            print(f"Erreur lors de l'ajout de la route: {stderr}", file=sys.stderr)
            return False
        
        return True
    
    def delete_route(self, route):
        """Supprime une route statique"""
        to = route.get('to')
        
        if not to:
            return False
        
        try:
            network = ipaddress.ip_network(to, strict=False)
            ip_cmd = "ip" if network.version == 4 else "ip -6"
        except ValueError:
            return False
        
        cmd = f"{ip_cmd} route del {to}"
        return self._run_command(cmd, check=False)[0]
    
    def show_routes(self, ipv6=False):
        """Affiche les routes"""
        cmd = "ip -6 route" if ipv6 else "ip route"
        success, stdout, _ = self._run_command(cmd)
        if success:
            print(stdout)
        return success
    
    def apply_static_routes(self):
        """Applique toutes les routes statiques"""
        print("\n" + "="*50)
        print("Configuration des routes statiques")
        print("="*50)
        
        if not self.static_routes:
            print("Aucune route statique à configurer")
            return True
        
        success_count = 0
        total_count = len(self.static_routes)
        
        for route in self.static_routes:
            if self.add_route(route):
                success_count += 1
        
        print(f"\n{success_count}/{total_count} routes configurées")
        return success_count == total_count
    
    def apply_all(self):
        """Applique toute la configuration de routage"""
        # Pour l'instant, seulement les routes statiques
        return self.apply_static_routes()

def main():
    from yarp_config import YARPConfig
    
    config = YARPConfig()
    if not config.load() or not config.validate():
        sys.exit(1)
    
    manager = RoutingManager(config)
    
    if len(sys.argv) < 2:
        print("Usage: routing.py <command>")
        print("Commands:")
        print("  apply      - Appliquer les routes")
        print("  show       - Afficher les routes IPv4")
        print("  show6      - Afficher les routes IPv6")
        sys.exit(1)
    
    command = sys.argv[1]
    
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
