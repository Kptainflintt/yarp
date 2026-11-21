#!/usr/bin/env python3
"""
Tests pour la génération transactionnelle des rulesets firewall.
Task 1: Firewall — génération du ruleset en mémoire
"""

import unittest
import tempfile
import sys
import os

# Ajouter les chemins nécessaires pour les imports
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(repo_root, 'src', 'core'))
sys.path.insert(0, os.path.join(repo_root, 'src', 'modules'))

from yarp_logger import get_logger


# Fixture de configuration firewall (extrait de config/yarp.yaml.example)
FIXTURE_FIREWALL = {
    "default": {
        "input": "drop",
        "forward": "drop",
        "output": "accept"
    },
    "stateful": True,
    "rules": [
        {
            "name": "Allow_SSH",
            "chain": "input",
            "source": "any",
            "in_interface": "eth1",
            "protocols": {
                "tcp": 22
            },
            "action": "accept"
        },
        {
            "name": "Allow_Internet",
            "chain": "forward",
            "source": "192.168.1.0/24",
            "out_interface": "eth0",
            "protocols": {
                "tcp": [80, 443],
                "udp": 53
            },
            "action": "accept"
        },
        {
            "name": "Allow_HTTP_from_WAN",
            "chain": "forward",
            "in_interface": "eth0",
            "destination": "192.168.1.100",
            "protocols": {
                "tcp": 80
            },
            "action": "accept"
        },
        {
            "name": "Allow_Ping_out",
            "chain": "forward",
            "in_interface": "eth1",
            "out_interface": "eth0",
            "protocols": {
                "icmp": True
            },
            "action": "accept"
        },
        {
            "name": "Allow_app_ports",
            "chain": "forward",
            "source": "192.168.1.0/24",
            "out_interface": "eth0",
            "protocols": {
                "tcp": "8000:8100"
            },
            "action": "accept"
        },
        {
            "name": "Block_WAN_to_LAN",
            "chain": "forward",
            "in_interface": "eth0",
            "out_interface": "eth1",
            "protocols": "any",
            "action": "drop"
        }
    ]
}


class StubConfig:
    """Stub de configuration pour les tests."""
    
    def __init__(self, tmpdir=None):
        self.tmpdir = tmpdir
        self.logging_cfg = {
            "logging": {
                "level": "DEBUG",
                "files": {
                    "application": os.path.join(tmpdir, "apply.log") if tmpdir else "/tmp/yarp-apply.log",
                    "debug": os.path.join(tmpdir, "debug.log") if tmpdir else "/tmp/yarp-debug.log",
                    "error": os.path.join(tmpdir, "error.log") if tmpdir else "/tmp/yarp-error.log"
                },
                "formats": {
                    "file": "json",
                    "console": "simple"
                }
            }
        }
    
    def get_firewall(self):
        return FIXTURE_FIREWALL
    
    def get_interfaces(self):
        return {}
    
    def get_logging(self):
        return self.logging_cfg


# Import des classes nécessaires (sera fait après la définition de StubConfig)
try:
    from firewall import FirewallManager, RuleBuildError
    HAS_FIREWALL_IMPLEMENTATION = True
except ImportError:
    HAS_FIREWALL_IMPLEMENTATION = False
    FirewallManager = None
    RuleBuildError = None


class TestBuildV4Ruleset(unittest.TestCase):
    """Tests pour la génération du ruleset IPv4."""
    
    @classmethod
    def setUpClass(cls):
        """Import des dépendances une fois pour tous les tests."""
        global FirewallManager, RuleBuildError, HAS_FIREWALL_IMPLEMENTATION
        if not HAS_FIREWALL_IMPLEMENTATION:
            try:
                from firewall import FirewallManager, RuleBuildError
                cls.FirewallManager = FirewallManager
                cls.RuleBuildError = RuleBuildError
                cls.HAS_IMPLEMENTATION = True
            except ImportError:
                cls.HAS_IMPLEMENTATION = False
        else:
            cls.FirewallManager = FirewallManager
            cls.RuleBuildError = RuleBuildError
            cls.HAS_IMPLEMENTATION = True
    
    def setUp(self):
        """Configuration avant chaque test."""
        self.tmpdir = tempfile.mkdtemp()
        self.config = StubConfig(self.tmpdir)
        if self.HAS_IMPLEMENTATION:
            self.manager = self.FirewallManager(self.config)
    
    def tearDown(self):
        """Nettoyage après chaque test."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
    
    def test_policies_in_ruleset(self):
        """Test que les politiques par défaut sont présentes dans le ruleset."""
        if not self.HAS_IMPLEMENTATION:
            self.skipTest("Implémentation non disponible")
        
        lines, meta = self.manager.build_v4_ruleset()
        
        # Vérifier la présence des politiques
        policy_lines = [line for line in lines if line.startswith(":")]
        self.assertEqual(len(policy_lines), 3)
        
        # Vérifier les politiques spécifiques
        input_policy = [line for line in policy_lines if "INPUT" in line]
        forward_policy = [line for line in policy_lines if "FORWARD" in line]
        output_policy = [line for line in policy_lines if "OUTPUT" in line]
        
        self.assertEqual(len(input_policy), 1)
        self.assertEqual(len(forward_policy), 1)
        self.assertEqual(len(output_policy), 1)
        
        # Vérifier que INPUT et FORWARD sont en DROP, OUTPUT en ACCEPT
        self.assertIn("DROP", input_policy[0])
        self.assertIn("DROP", forward_policy[0])
        self.assertIn("ACCEPT", output_policy[0])
    
    def test_stateful_and_user_rules_in_order(self):
        """Test que les règles stateful viennent avant les règles utilisateur."""
        if not self.HAS_IMPLEMENTATION:
            self.skipTest("Implémentation non disponible")
        
        lines, meta = self.manager.build_v4_ruleset()
        
        # Trouver les positions des règles stateful et utilisateur
        stateful_positions = []
        user_rule_positions = []
        
        for i, line in enumerate(lines):
            if "YARP-FW-STATEFUL" in line:
                stateful_positions.append(i)
            elif "YARP-FW-RULE-" in line:
                user_rule_positions.append(i)
        
        # Vérifier que toutes les règles stateful viennent avant les règles utilisateur
        if stateful_positions and user_rule_positions:
            self.assertLess(max(stateful_positions), min(user_rule_positions))
        
        # Vérifier la présence des règles stateful
        self.assertTrue(any("YARP-FW-STATEFUL-INPUT" in line for line in lines))
        self.assertTrue(any("YARP-FW-STATEFUL-FORWARD" in line for line in lines))
        self.assertTrue(any("YARP-FW-LOOPBACK" in line for line in lines))
        
        # Vérifier la présence des règles utilisateur
        self.assertTrue(any("YARP-FW-RULE-Allow_SSH" in line for line in lines))
        self.assertTrue(any("YARP-FW-RULE-Allow_Internet" in line for line in lines))
    
    def test_line_meta_aligned(self):
        """Test que la liste meta est alignée avec les lignes."""
        if not self.HAS_IMPLEMENTATION:
            self.skipTest("Implémentation non disponible")
        
        lines, meta = self.manager.build_v4_ruleset()
        
        # Vérifier que les longueurs sont identiques
        self.assertEqual(len(lines), len(meta))
        
        # Vérifier que chaque élément meta a les bonnes clés
        for meta_item in meta:
            self.assertIn("kind", meta_item)
            self.assertIn("rule_index", meta_item)
            self.assertIn("rule_name", meta_item)
        
        # Trouver la ligne avec Allow_SSH et vérifier son meta
        for i, line in enumerate(lines):
            if "YARP-FW-RULE-Allow_SSH" in line:
                self.assertEqual(meta[i]["rule_name"], "Allow_SSH")
                self.assertEqual(meta[i]["kind"], "user")
                self.assertEqual(meta[i]["rule_index"], 1)  # 1-based index
                break
        else:
            self.fail("Règle Allow_SSH non trouvée")
    
    def test_reject_no_valid_match_raises(self):
        """Test qu'une règle sans match valide lève RuleBuildError."""
        if not self.HAS_IMPLEMENTATION:
            self.skipTest("Implémentation non disponible")
        
        # Créer une configuration avec une règle invalide
        invalid_firewall = {
            "default": {
                "input": "drop",
                "forward": "drop",
                "output": "accept"
            },
            "stateful": True,
            "rules": [
                {
                    "name": "Valid_Rule",
                    "chain": "input",
                    "source": "any",
                    "protocols": "any",
                    "action": "accept"
                },
                {
                    "name": "Invalid_Rule",
                    "chain": "input",
                    "source": "invalid_ip_address",  # IP invalide
                    "protocols": "any",
                    "action": "accept"
                }
            ]
        }
        
        config = StubConfig(self.tmpdir)
        config.get_firewall = lambda: invalid_firewall
        manager = self.FirewallManager(config)
        
        # Vérifier que RuleBuildError est levé
        with self.assertRaises(self.RuleBuildError) as context:
            manager.build_v4_ruleset()
        
        # Vérifier les attributs de l'erreur
        error = context.exception
        self.assertEqual(error.rule_index, 2)  # Deuxième règle (1-based)
        self.assertEqual(error.rule_name, "Invalid_Rule")
    
    def test_reject_comment_preserved(self):
        """Test que le commentaire reject est préservé avec --reject-with."""
        if not self.HAS_IMPLEMENTATION:
            self.skipTest("Implémentation non disponible")
        
        # Ajouter une règle avec reject
        firewall_with_reject = {
            "default": {
                "input": "drop",
                "forward": "drop",
                "output": "accept"
            },
            "stateful": True,
            "rules": [
                {
                    "name": "Reject_Bad_Traffic",
                    "chain": "input",
                    "source": "192.168.1.200",
                    "protocols": "any",
                    "action": "reject"
                }
            ]
        }
        
        config = StubConfig(self.tmpdir)
        config.get_firewall = lambda: firewall_with_reject
        manager = self.FirewallManager(config)
        
        lines, meta = manager.build_v4_ruleset()
        
        # Trouver la ligne avec la règle reject
        reject_lines = [line for line in lines if "Reject_Bad_Traffic" in line]
        self.assertEqual(len(reject_lines), 1)
        
        # Vérifier la présence de --reject-with
        self.assertIn("--reject-with", reject_lines[0])
        self.assertIn("icmp-port-unreachable", reject_lines[0])


class TestBuildV6Ruleset(unittest.TestCase):
    """Tests pour la génération du ruleset IPv6."""
    
    @classmethod
    def setUpClass(cls):
        """Import des dépendances une fois pour tous les tests."""
        global FirewallManager, RuleBuildError, HAS_FIREWALL_IMPLEMENTATION
        if not HAS_FIREWALL_IMPLEMENTATION:
            try:
                from firewall import FirewallManager, RuleBuildError
                cls.FirewallManager = FirewallManager
                cls.RuleBuildError = RuleBuildError
                cls.HAS_IMPLEMENTATION = True
            except ImportError:
                cls.HAS_IMPLEMENTATION = False
        else:
            cls.FirewallManager = FirewallManager
            cls.RuleBuildError = RuleBuildError
            cls.HAS_IMPLEMENTATION = True
    
    def setUp(self):
        """Configuration avant chaque test."""
        self.tmpdir = tempfile.mkdtemp()
        self.config = StubConfig(self.tmpdir)
        if self.HAS_IMPLEMENTATION:
            self.manager = self.FirewallManager(self.config)
    
    def tearDown(self):
        """Nettoyage après chaque test."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
    
    def test_no_user_v4_literals_in_v6(self):
        """Test qu'il n'y a pas de littéraux IPv4 dans le ruleset v6."""
        if not self.HAS_IMPLEMENTATION:
            self.skipTest("Implémentation non disponible")
        
        lines, meta = self.manager.build_v6_ruleset()
        
        # Vérifier qu'il n'y a pas de références IPv4
        for line in lines:
            self.assertNotIn("192.168.", line)
            self.assertNotIn("10.0.0.", line)
        
        # Vérifier que le ruleset contient les politiques
        policy_lines = [line for line in lines if line.startswith(":")]
        self.assertEqual(len(policy_lines), 3)
        
        # Vérifier la présence des règles stateful
        self.assertTrue(any("YARP-FW-STATEFUL-INPUT" in line for line in lines))
        self.assertTrue(any("YARP-FW-STATEFUL-FORWARD" in line for line in lines))
        self.assertTrue(any("YARP-FW-LOOPBACK" in line for line in lines))


class TestUserRuleArgs(unittest.TestCase):
    """Tests pour la méthode _user_rule_args."""
    
    @classmethod
    def setUpClass(cls):
        """Import des dépendances une fois pour tous les tests."""
        global FirewallManager, RuleBuildError, HAS_FIREWALL_IMPLEMENTATION
        if not HAS_FIREWALL_IMPLEMENTATION:
            try:
                from firewall import FirewallManager, RuleBuildError
                cls.FirewallManager = FirewallManager
                cls.RuleBuildError = RuleBuildError
                cls.HAS_IMPLEMENTATION = True
            except ImportError:
                cls.HAS_IMPLEMENTATION = False
        else:
            cls.FirewallManager = FirewallManager
            cls.RuleBuildError = RuleBuildError
            cls.HAS_IMPLEMENTATION = True
    
    def setUp(self):
        """Configuration avant chaque test."""
        self.tmpdir = tempfile.mkdtemp()
        self.config = StubConfig(self.tmpdir)
        if self.HAS_IMPLEMENTATION:
            self.manager = self.FirewallManager(self.config)
    
    def tearDown(self):
        """Nettoyage après chaque test."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
    
    def test_user_rule_args_valid_rule(self):
        """Test _user_rule_args avec une règle valide."""
        if not self.HAS_IMPLEMENTATION:
            self.skipTest("Implémentation non disponible")
        
        rule = {
            "name": "Test_Rule",
            "chain": "input",
            "source": "192.168.1.0/24",
            "in_interface": "eth0",
            "protocols": {
                "tcp": 80
            },
            "action": "accept"
        }
        
        args = self.manager._user_rule_args(rule, 1)
        
        # Vérifier que le résultat est une liste
        self.assertIsInstance(args, list)
        
        # Vérifier la présence des éléments attendus
        self.assertIn("-A", args)
        self.assertIn("INPUT", args)
        self.assertIn("-s", args)
        self.assertIn("192.168.1.0/24", args)
        self.assertIn("-i", args)
        self.assertIn("eth0", args)
        self.assertIn("-p", args)
        self.assertIn("tcp", args)
        self.assertIn("--dport", args)
        self.assertIn("80", args)
        self.assertIn("-m", args)
        self.assertIn("comment", args)
        self.assertIn("--comment=YARP-FW-RULE-Test_Rule", args)
        self.assertIn("-j", args)
        self.assertIn("ACCEPT", args)
    
    def test_user_rule_args_invalid_rule(self):
        """Test _user_rule_args avec une règle invalide."""
        if not self.HAS_IMPLEMENTATION:
            self.skipTest("Implémentation non disponible")
        
        rule = {
            "name": "Invalid_Rule",
            "chain": "input",
            "source": "invalid_ip",  # IP invalide
            "protocols": "any",
            "action": "accept"
        }
        
        args = self.manager._user_rule_args(rule, 1)
        
        # Doit retourner None pour une règle invalide
        self.assertIsNone(args)
    
    def test_user_rule_args_reject(self):
        """Test _user_rule_args avec action reject."""
        if not self.HAS_IMPLEMENTATION:
            self.skipTest("Implémentation non disponible")
        
        rule = {
            "name": "Reject_Rule",
            "chain": "input",
            "source": "any",
            "protocols": "any",
            "action": "reject"
        }
        
        args = self.manager._user_rule_args(rule, 1)
        
        # Vérifier la présence de --reject-with
        self.assertIn("--reject-with", args)
        self.assertIn("icmp-port-unreachable", args)
        self.assertIn("-j", args)
        self.assertIn("REJECT", args)


if __name__ == "__main__":
    unittest.main()
