#!/usr/bin/env python3
"""
YARP Configuration Parser
Parse et valide le fichier de configuration YAML
"""

import yaml
import sys
import os
import ipaddress
from pathlib import Path

class YARPConfig:
    def __init__(self, config_file="/etc/yarp/config.yaml"):
        self.config_file = config_file
        self.config = None
        
    def load(self):
        """Charge le fichier de configuration"""
        try:
            with open(self.config_file, 'r') as f:
                self.config = yaml.safe_load(f)
            return True
        except FileNotFoundError:
            print(f"Erreur: Fichier {self.config_file} introuvable", file=sys.stderr)
            return False
        except yaml.YAMLError as e:
            print(f"Erreur de parsing YAML: {e}", file=sys.stderr)
            return False
    
    def validate(self):
        """Valide la configuration"""
        if not self.config:
            return False
        
        errors = []
        
        # Validation système
        if 'system' in self.config:
            if 'hostname' not in self.config['system']:
                errors.append("system.hostname est requis")
        
        # Validation interfaces
        if 'interfaces' in self.config:
            for iface, config in self.config['interfaces'].items():
                if 'ipv4' in config and config['ipv4'] != 'dhcp':
                    try:
                        ipaddress.ip_network(config['ipv4'], strict=False)
                    except ValueError:
                        errors.append(f"IPv4 invalide pour {iface}: {config['ipv4']}")
                
                if 'ipv6' in config and config['ipv6'] != 'auto':
                    try:
                        ipaddress.ip_network(config['ipv6'], strict=False)
                    except ValueError:
                        errors.append(f"IPv6 invalide pour {iface}: {config['ipv6']}")
        
        # Validation routes
        if 'routing' in self.config and 'static' in self.config['routing']:
            for idx, route in enumerate(self.config['routing']['static']):
                if 'to' not in route:
                    errors.append(f"Route {idx}: destination 'to' manquante")
                if 'via' not in route and 'interface' not in route:
                    errors.append(f"Route {idx}: 'via' ou 'interface' requis")
        
        if errors:
            print("Erreurs de validation:", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
            return False
        
        return True
    
    def get_system(self):
        """Retourne la configuration système"""
        return self.config.get('system', {})
    
    def get_interfaces(self):
        """Retourne la configuration des interfaces"""
        return self.config.get('interfaces', {})
    
    def get_routing(self):
        """Retourne la configuration du routage"""
        return self.config.get('routing', {})
    
    def get_static_routes(self):
        """Retourne les routes statiques"""
        routing = self.get_routing()
        return routing.get('static', [])

    def get_logging(self):
        """Retourne la configuration de logging avec valeurs par défaut"""
        default_logging = {
            'level': 'INFO',
            'debug': False,
            'files': {
                'application': '/var/log/yarp/apply.log',
                'debug': '/var/log/yarp/debug.log',
                'error': '/var/log/yarp/error.log'
            },
            'formats': {
                'console': 'simple',
                'file': 'json'
            },
            'modules': {
                'network': 'INFO',
                'routing': 'INFO',
                'firewall': 'WARNING'
            }
        }

        # Fusionner avec la config existante
        user_logging = self.config.get('logging', {})

        # Merge récursif des dictionnaires
        def merge_dict(default, user):
            result = default.copy()
            for key, value in user.items():
                if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = merge_dict(result[key], value)
                else:
                    result[key] = value
            return result

        return merge_dict(default_logging, user_logging)
    
    def dump_json(self):
        """Exporte la config en JSON pour les scripts shell"""
        import json
        return json.dumps(self.config, indent=2)

def main():
    if len(sys.argv) < 2:
        print("Usage: yarp_config.py <command> [args]")
        print("Commands:")
        print("  validate           - Valider la configuration")
        print("  show              - Afficher la configuration")
        print("  get <section>     - Obtenir une section")
        print("  dump-json         - Exporter en JSON")
        sys.exit(1)
    
    config = YARPConfig()
    
    if not config.load():
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "validate":
        if config.validate():
            print("Configuration valide")
            sys.exit(0)
        else:
            sys.exit(1)
    
    elif command == "show":
        print(yaml.dump(config.config, default_flow_style=False))
    
    elif command == "get":
        if len(sys.argv) < 3:
            print("Usage: yarp_config.py get <section>")
            sys.exit(1)
        
        section = sys.argv[2]
        if section == "system":
            print(yaml.dump(config.get_system()))
        elif section == "interfaces":
            print(yaml.dump(config.get_interfaces()))
        elif section == "routing":
            print(yaml.dump(config.get_routing()))
        elif section == "static-routes":
            print(yaml.dump(config.get_static_routes()))
    
    elif command == "dump-json":
        print(config.dump_json())
    
    else:
        print(f"Commande inconnue: {command}")
        sys.exit(1)

if __name__ == "__main__":
    main()
