#!/usr/bin/env python3
"""
YARP Configuration Parser
Parse et valide le fichier de configuration YAML
"""

import yaml
import sys
import os
import re
import ipaddress
from pathlib import Path


def _normalize_rule_name(name: str):
    """Normalise un nom de règle firewall pour le commentaire iptables.

    Doit rester synchronisée avec src/modules/firewall.py : les espaces
    deviennent des traits du soulignement et les caractères non
    alphanumériques (hors `_`, `.`, `-`) sont supprimés.
    Retourne None si le nom est vide ou invalide.
    """
    if not name or not isinstance(name, str):
        return None
    normalized = re.sub(r"\s+", "_", name.strip())
    normalized = re.sub(r"[^a-zA-Z0-9._-]", "", normalized)
    if not normalized:
        return None
    if not normalized[0].isalpha():
        normalized = f"rule-{normalized}"
    return normalized


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
    
    # ------------------------------------------------------------------ #
    #  Constantes de validation                                            #
    # ------------------------------------------------------------------ #

    # Protocoles L4 (avec ports)
    L4_PROTOCOLS = ('tcp', 'udp', 'sctp')
    # Protocoles L3 (sans port)
    L3_PROTOCOLS = ('icmp', 'gre', 'esp', 'ah', 'ipip', 'ospf', 'vrrp')
    VALID_PROTOCOLS = L4_PROTOCOLS + L3_PROTOCOLS
    VALID_ACTIONS = ('accept', 'drop', 'reject')
    VALID_CHAINS = ('input', 'forward', 'output')
    VALID_POLICIES = ('accept', 'drop', 'reject')

    # ------------------------------------------------------------------ #
    #  Validation principale                                               #
    # ------------------------------------------------------------------ #

    def validate(self):
        """Valide la configuration complète.

        Délègue chaque section à une méthode privée dédiée.
        Accumule toutes les erreurs et les affiche en fin de parcours.
        """
        if not self.config:
            return False

        errors = []
        warnings = []

        self._validate_system(errors)
        self._validate_interfaces(errors, warnings)
        self._validate_routes(errors)
        self._validate_firewall(errors, warnings)

        # Afficher les avertissements (non bloquants)
        if warnings:
            print("Avertissements:", file=sys.stderr)
            for warning in warnings:
                print(f"  - {warning}", file=sys.stderr)

        if errors:
            print("Erreurs de validation:", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
            return False

        return True

    # ------------------------------------------------------------------ #
    #  Validation : system                                                 #
    # ------------------------------------------------------------------ #

    def _validate_system(self, errors):
        """Valide la section system (hostname, domain, timezone, dns_servers)."""
        if 'system' not in self.config:
            errors.append("La section 'system' est requise (system.hostname est obligatoire)")
            return

        system = self.config['system']
        if not isinstance(system, dict):
            errors.append("La section 'system' doit être un dictionnaire")
            return

        if 'hostname' not in system:
            errors.append("system.hostname est requis")

        # Validation domain
        if 'domain' in system:
            domain = system['domain']
            if not isinstance(domain, str) or not domain:
                errors.append("system.domain doit être une chaîne non vide")
            elif not re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?)*$', domain):
                errors.append(f"system.domain invalide: {domain} (format attendu: ex. lab.local, example.com)")

        # Validation timezone
        if 'timezone' in system:
            timezone = system['timezone']
            if not isinstance(timezone, str) or not timezone:
                errors.append("system.timezone doit être une chaîne non vide")
            elif not re.match(r'^[a-zA-Z]+(/[a-zA-Z0-9_\-]+)+$', timezone):
                errors.append(f"system.timezone invalide: {timezone} (format attendu: ex. Europe/Paris, America/New_York)")

        # Validation dns_servers
        if 'dns_servers' in system:
            dns_servers = system['dns_servers']
            if not isinstance(dns_servers, list):
                errors.append("system.dns_servers doit être une liste")
            elif len(dns_servers) == 0:
                errors.append("system.dns_servers ne peut pas être vide")
            else:
                for idx, server in enumerate(dns_servers):
                    try:
                        ipaddress.ip_address(str(server))
                    except ValueError:
                        errors.append(f"system.dns_servers[{idx}] invalide: {server} (adresse IP attendue)")

    # ------------------------------------------------------------------ #
    #  Validation : interfaces                                             #
    # ------------------------------------------------------------------ #

    def _validate_interfaces(self, errors, warnings):
        """Valide la section interfaces (IPv4/IPv6, masquerading)."""
        if 'interfaces' not in self.config:
            return

        interfaces = self.config['interfaces']
        if not isinstance(interfaces, dict):
            errors.append("La section 'interfaces' doit être un dictionnaire")
            return

        for iface, iface_config in interfaces.items():
            if not isinstance(iface_config, dict):
                errors.append(f"La configuration de l'interface '{iface}' doit être un dictionnaire")
                continue

            if 'ipv4' in iface_config and iface_config['ipv4'] != 'dhcp':
                try:
                    ipaddress.ip_network(iface_config['ipv4'], strict=False)
                except ValueError:
                    errors.append(f"IPv4 invalide pour {iface}: {iface_config['ipv4']}")

            if 'ipv6' in iface_config and iface_config['ipv6'] != 'auto':
                try:
                    ipaddress.ip_network(iface_config['ipv6'], strict=False)
                except ValueError:
                    errors.append(f"IPv6 invalide pour {iface}: {iface_config['ipv6']}")

            # Validation NAT/masquerading
            if 'masquerading' in iface_config:
                if not isinstance(iface_config['masquerading'], bool):
                    errors.append(f"masquerading pour {iface} doit être true/false")

                # Si masquerading activé, vérifier les sources
                if iface_config['masquerading'] and 'masquerade_sources' in iface_config:
                    sources = iface_config['masquerade_sources']
                    if not isinstance(sources, list):
                        errors.append(f"masquerade_sources pour {iface} doit être une liste")
                    else:
                        for idx, source in enumerate(sources):
                            try:
                                ipaddress.ip_network(source, strict=False)
                            except ValueError:
                                errors.append(f"Source invalide pour {iface}[{idx}]: {source}")

                # Avertir si masquerading sans sources (non bloquant)
                if iface_config['masquerading'] and 'masquerade_sources' not in iface_config:
                    warnings.append(f"masquerading activé sur {iface} mais aucune source spécifiée")

    # ------------------------------------------------------------------ #
    #  Validation : routes                                                 #
    # ------------------------------------------------------------------ #

    def _validate_routes(self, errors):
        """Valide la section routing.static."""
        if 'routing' not in self.config:
            return
        routing = self.config['routing']
        if not isinstance(routing, dict):
            errors.append("La section 'routing' doit être un dictionnaire")
            return
        if 'static' not in routing:
            return

        static = routing['static']
        if not isinstance(static, list):
            errors.append("routing.static doit être une liste")
            return

        for idx, route in enumerate(static):
            if not isinstance(route, dict):
                errors.append(f"Route {idx}: doit être un dictionnaire")
                continue
            if 'to' not in route:
                errors.append(f"Route {idx}: destination 'to' manquante")
            if 'via' not in route and 'interface' not in route:
                errors.append(f"Route {idx}: 'via' ou 'interface' requis")

    # ------------------------------------------------------------------ #
    #  Validation : firewall                                               #
    # ------------------------------------------------------------------ #

    def _validate_firewall(self, errors, warnings):
        """Valide la section firewall (politiques, stateful, règles)."""
        if 'firewall' not in self.config:
            return

        fw = self.config['firewall']
        if not isinstance(fw, dict):
            errors.append("La section 'firewall' doit être un dictionnaire")
            return

        self._validate_firewall_defaults(fw, errors)
        self._validate_firewall_stateful(fw, errors)
        self._validate_firewall_rules(fw, errors, warnings)

    def _validate_firewall_defaults(self, fw, errors):
        """Valide les politiques par défaut du firewall."""
        if 'default' not in fw:
            return
        for chain in self.VALID_CHAINS:
            if chain in fw['default']:
                policy = fw['default'][chain]
                if not isinstance(policy, str) or policy.lower() not in self.VALID_POLICIES:
                    errors.append(
                        f"firewall.default.{chain} invalide: '{policy}' "
                        f"(valeurs acceptées: {', '.join(self.VALID_POLICIES)})"
                    )

    def _validate_firewall_stateful(self, fw, errors):
        """Valide le flag stateful du firewall."""
        if 'stateful' in fw:
            if not isinstance(fw['stateful'], bool):
                errors.append("firewall.stateful doit être true/false")

    def _validate_firewall_rules(self, fw, errors, warnings):
        """Valide la liste des règles firewall."""
        if 'rules' not in fw:
            return
        if not isinstance(fw['rules'], list):
            errors.append("firewall.rules doit être une liste")
            return

        interface_names = list(self.config.get('interfaces', {}).keys())

        for idx, rule in enumerate(fw['rules']):
            prefix = f"firewall.rules[{idx}]"
            if not isinstance(rule, dict):
                errors.append(f"{prefix}: doit être un dictionnaire")
                continue
            self._validate_firewall_rule(rule, prefix, interface_names, errors, warnings)

    def _validate_firewall_rule(self, rule, prefix, interface_names, errors, warnings):
        """Valide une règle firewall individuelle."""
        # Champs obligatoires
        if 'name' not in rule:
            errors.append(f"{prefix}: 'name' est requis")
        elif not isinstance(rule['name'], str) or not rule['name'].strip():
            errors.append(f"{prefix}: 'name' doit être une chaîne non vide")
        else:
            normalized = _normalize_rule_name(rule['name'])
            if normalized is None:
                errors.append(
                    f"{prefix}: 'name' invalide: '{rule['name']}' "
                    f"(aucun caractère alphanumérique)"
                )
            elif normalized != rule['name']:
                warnings.append(
                    f"{prefix}: le nom '{rule['name']}' sera normalisé "
                    f"en '{normalized}' dans le tag iptables"
                )

        if 'action' not in rule:
            errors.append(f"{prefix}: 'action' est requis")
        elif not isinstance(rule['action'], str) or rule['action'].lower() not in self.VALID_ACTIONS:
            errors.append(
                f"{prefix}: action invalide: '{rule.get('action')}' "
                f"(valeurs acceptées: {', '.join(self.VALID_ACTIONS)})"
            )

        # Validation de la chaîne (obligatoire)
        if 'chain' not in rule:
            errors.append(f"{prefix}: 'chain' est requis (input, forward, output)")
        elif not isinstance(rule['chain'], str) or rule['chain'].lower() not in self.VALID_CHAINS:
            errors.append(
                f"{prefix}: chain invalide: '{rule.get('chain')}' "
                f"(valeurs acceptées: {', '.join(self.VALID_CHAINS)})"
            )
        else:
            chain = rule['chain'].lower()
            # Vérifier cohérence interface / chaîne
            if chain == 'input' and 'out_interface' in rule:
                errors.append(
                    f"{prefix}: 'out_interface' n'est pas compatible "
                    f"avec chain: input (le trafic INPUT n'a pas d'interface de sortie)"
                )
            if chain == 'output' and 'in_interface' in rule:
                errors.append(
                    f"{prefix}: 'in_interface' n'est pas compatible "
                    f"avec chain: output (le trafic OUTPUT n'a pas d'interface d'entrée)"
                )

        # Au moins un critère de matching requis
        has_match = any(
            k in rule for k in ('source', 'destination', 'in_interface', 'out_interface')
        )
        if not has_match:
            errors.append(
                f"{prefix}: au moins un critère de matching requis "
                f"(source, destination, in_interface, out_interface)"
            )

        # Validation des interfaces (facultatives)
        self._validate_rule_interfaces(rule, prefix, interface_names, errors)
        # Validation des adresses (facultatives)
        self._validate_rule_addresses(rule, prefix, errors)
        # Validation des protocoles
        self._validate_rule_protocols(rule, prefix, errors)

    def _validate_rule_interfaces(self, rule, prefix, interface_names, errors):
        """Valide les champs in_interface / out_interface d'une règle."""
        for iface_field in ('in_interface', 'out_interface'):
            if iface_field in rule:
                if not isinstance(rule[iface_field], str):
                    errors.append(f"{prefix}: '{iface_field}' doit être une chaîne")
                elif rule[iface_field] not in interface_names:
                    errors.append(
                        f"{prefix}: {iface_field} inconnue: '{rule[iface_field]}' "
                        f"(interfaces disponibles: {', '.join(interface_names)})"
                    )

    def _validate_rule_addresses(self, rule, prefix, errors):
        """Valide les champs source / destination d'une règle."""
        for addr_field in ('source', 'destination'):
            if addr_field in rule:
                addr = rule[addr_field]
                if not isinstance(addr, str):
                    errors.append(f"{prefix}: '{addr_field}' doit être une chaîne")
                elif addr.lower() == 'any':
                    pass
                else:
                    try:
                        ipaddress.ip_network(addr, strict=False)
                    except ValueError:
                        try:
                            ipaddress.ip_address(addr)
                        except ValueError:
                            errors.append(
                                f"{prefix}: {addr_field} invalide: '{addr}' "
                                f"(attendu: IP, CIDR ou 'any', ex: 192.168.1.0/24, 10.0.0.1, any)"
                            )

    def _validate_rule_protocols(self, rule, prefix, errors):
        """Valide le champ protocols d'une règle firewall."""
        if 'protocols' not in rule:
            return

        protocols = rule['protocols']

        if isinstance(protocols, str):
            if protocols.lower() != 'any':
                errors.append(
                    f"{prefix}: protocols en tant que chaîne doit être 'any', "
                    f"reçu: '{protocols}'"
                )
        elif isinstance(protocols, dict):
            for proto, port_value in protocols.items():
                if proto.lower() not in self.VALID_PROTOCOLS:
                    errors.append(
                        f"{prefix}: protocole non supporté: '{proto}' "
                        f"(supportés: {', '.join(self.VALID_PROTOCOLS)})"
                    )
                    continue

                # Protocoles L3 : pas de notion de port
                if proto.lower() in self.L3_PROTOCOLS:
                    continue

                # Protocoles L4 : valider les ports
                self._validate_ports(port_value, proto, prefix, errors)
        else:
            errors.append(
                f"{prefix}: protocols doit être 'any' ou un dict, "
                f"reçu: {type(protocols).__name__}"
            )

    def _validate_ports(self, port_value, proto, prefix, errors):
        """Valide une valeur de ports pour un protocole L4 (tcp, udp, sctp)."""
        if isinstance(port_value, int):
            if port_value < 1 or port_value > 65535:
                errors.append(f"{prefix}: port {proto} hors limites: {port_value}")

        elif isinstance(port_value, str):
            if ':' in port_value:
                # Range "8000:8100"
                parts = port_value.split(':')
                if len(parts) != 2:
                    errors.append(f"{prefix}: range de ports {proto} invalide: '{port_value}'")
                else:
                    valid_parts = True
                    for p in parts:
                        if not p.isdigit() or int(p) < 1 or int(p) > 65535:
                            errors.append(f"{prefix}: port dans le range {proto} invalide: '{p}'")
                            valid_parts = False
                    # Vérifier que le début du range est inférieur à la fin
                    if valid_parts and int(parts[0]) > int(parts[1]):
                        errors.append(
                            f"{prefix}: range de ports {proto} inversé: '{port_value}' "
                            f"(le port de début doit être inférieur au port de fin)"
                        )
            else:
                if not port_value.isdigit() or int(port_value) < 1 or int(port_value) > 65535:
                    errors.append(f"{prefix}: port {proto} invalide: '{port_value}'")

        elif isinstance(port_value, list):
            for pidx, p in enumerate(port_value):
                if isinstance(p, int):
                    if p < 1 or p > 65535:
                        errors.append(f"{prefix}: port {proto}[{pidx}] hors limites: {p}")
                elif isinstance(p, str):
                    if not p.isdigit() or int(p) < 1 or int(p) > 65535:
                        errors.append(f"{prefix}: port {proto}[{pidx}] invalide: '{p}'")
                else:
                    errors.append(f"{prefix}: port {proto}[{pidx}] type non supporté")
        else:
            errors.append(
                f"{prefix}: valeur de ports {proto} invalide "
                f"(attendu: int, str, ou liste)"
            )
    
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

    def get_firewall(self):
        """Retourne la configuration du firewall"""
        return self.config.get('firewall', {})

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
                'dns': 'INFO',
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
        print("  validate              - Valider la configuration")
        print("  show                  - Afficher la configuration")
        print("  get <section>         - Obtenir une section (YAML)")
        print("  get interface-names   - Lister les noms d'interfaces (un par ligne)")
        print("  get system-vars       - Exporter les variables système (KEY=VALUE)")
        print("  dump-json             - Exporter en JSON")
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
        elif section == "interface-names":
            # Affiche un nom d'interface par ligne (pour consommation shell)
            for name in config.get_interfaces().keys():
                print(name)
        elif section == "system-vars":
            # Exporte les variables système au format KEY=VALUE
            # Utilisable en shell via: eval "$(yarp_config.py get system-vars)"
            system = config.get_system()
            print(f"HOSTNAME={system.get('hostname', '')}")
            print(f"DOMAIN={system.get('domain', '')}")
            print(f"TIMEZONE={system.get('timezone', '')}")
        else:
            print(f"Section inconnue: {section}", file=sys.stderr)
            sys.exit(1)

    elif command == "dump-json":
        print(config.dump_json())

    else:
        print(f"Commande inconnue: {command}")
        sys.exit(1)

if __name__ == "__main__":
    main()
