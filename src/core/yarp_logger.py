#!/usr/bin/env python3
"""
YARP Logger Module
Système de logs avancé et configurable pour YARP
"""

import json
import logging
import logging.handlers
import sys
from datetime import datetime
from typing import Optional, Dict, Any

class YARPLogger:
    def __init__(self, name: str = "yarp", config: Optional[Dict] = None):
        self.name = name
        self.logger = logging.getLogger(name)
        self.config = config or {}
        self._setup_logger()

    def _setup_logger(self):
        """Configure le logger selon la configuration"""
        # Nettoyer les handlers existants
        self.logger.handlers.clear()

        # Niveau global
        level = self._get_log_level()
        self.logger.setLevel(level)

        # Console handler (pour l'utilisateur)
        self._setup_console_handler()

        # File handlers (pour les logs détaillés)
        self._setup_file_handlers()

        # Éviter la propagation des logs vers le root logger
        self.logger.propagate = False

    def _get_log_level(self) -> int:
        """Détermine le niveau de log effectif"""
        logging_config = self.config.get('logging', {})

        # Niveau spécifique au module si configuré
        modules_config = logging_config.get('modules', {})
        if self.name in modules_config:
            level_str = modules_config[self.name]
        else:
            # Niveau global
            level_str = logging_config.get('level', 'INFO')

        # Mode debug force le niveau DEBUG
        if logging_config.get('debug', False):
            level_str = 'DEBUG'

        return getattr(logging, level_str.upper(), logging.INFO)

    def _setup_console_handler(self):
        """Configure l'handler console"""
        console_handler = logging.StreamHandler(sys.stdout)

        logging_config = self.config.get('logging', {})
        console_format = logging_config.get('formats', {}).get('console', 'simple')

        if console_format == 'minimal':
            formatter = logging.Formatter('%(message)s')
        elif console_format == 'detailed':
            formatter = logging.Formatter(
                '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
                datefmt='%H:%M:%S'
            )
        else:  # simple (default)
            formatter = logging.Formatter('[%(levelname)s] %(message)s')

        console_handler.setFormatter(formatter)

        # Console seulement pour INFO et WARNING (pas DEBUG ni ERROR en double)
        console_handler.addFilter(lambda record: record.levelno in [logging.INFO, logging.WARNING])

        self.logger.addHandler(console_handler)

    def _setup_file_handlers(self):
        """Configure les handlers de fichiers"""
        logging_config = self.config.get('logging', {})
        files_config = logging_config.get('files', {})

        # Handler application (tous les logs)
        if 'application' in files_config:
            self._add_file_handler(
                files_config['application'],
                logging.INFO,
                "application"
            )

        # Handler debug (si mode debug activé)
        if logging_config.get('debug', False) and 'debug' in files_config:
            self._add_file_handler(
                files_config['debug'],
                logging.DEBUG,
                "debug"
            )

        # Handler erreur (erreurs uniquement)
        if 'error' in files_config:
            self._add_file_handler(
                files_config['error'],
                logging.ERROR,
                "error"
            )

    def _add_file_handler(self, filepath: str, level: int, handler_type: str):
        """Ajoute un handler de fichier avec rotation"""
        try:
            # Créer le répertoire si nécessaire
            import os
            os.makedirs(os.path.dirname(filepath), exist_ok=True)

            # Handler avec rotation (5MB max, 5 fichiers)
            handler = logging.handlers.RotatingFileHandler(
                filepath, maxBytes=5*1024*1024, backupCount=5
            )
            handler.setLevel(level)

            # Format selon config
            logging_config = self.config.get('logging', {})
            file_format = logging_config.get('formats', {}).get('file', 'json')

            if file_format == 'json':
                formatter = JSONFormatter()
            elif file_format == 'detailed':
                formatter = logging.Formatter(
                    '[%(asctime)s] [%(name)s] [%(levelname)s] [%(funcName)s:%(lineno)d] %(message)s'
                )
            else:  # text
                formatter = logging.Formatter(
                    '[%(asctime)s] [%(levelname)s] %(message)s'
                )

            handler.setFormatter(formatter)

            # Filtrer selon le type de handler
            if handler_type == "error":
                handler.addFilter(lambda record: record.levelno >= logging.ERROR)
            elif handler_type == "debug":
                # Debug handler prend tout
                pass
            else:
                # Application handler exclut le DEBUG (sauf si mode debug)
                min_level = logging.DEBUG if logging_config.get('debug', False) else logging.INFO
                handler.addFilter(lambda record: record.levelno >= min_level)

            self.logger.addHandler(handler)

        except Exception as e:
            # Si impossible de créer le fichier, au moins logger vers console
            print(f"Impossible de créer le fichier de log {filepath}: {e}", file=sys.stderr)

    # Méthodes de logging avec contexte
    def debug(self, message: str, **context):
        """Log debug avec contexte optionnel"""
        self._log_with_context(logging.DEBUG, message, context)

    def info(self, message: str, **context):
        """Log info avec contexte optionnel"""
        self._log_with_context(logging.INFO, message, context)

    def warning(self, message: str, **context):
        """Log warning avec contexte optionnel"""
        self._log_with_context(logging.WARNING, message, context)

    def error(self, message: str, **context):
        """Log error avec contexte optionnel"""
        self._log_with_context(logging.ERROR, message, context)

    def _log_with_context(self, level: int, message: str, context: Dict[str, Any]):
        """Log avec contexte métadata"""
        if context:
            # Pour les formats JSON, inclure le contexte
            extra = {'context': context}
            self.logger.log(level, message, extra=extra)
        else:
            self.logger.log(level, message)

    # Méthodes de convenance pour les opérations réseau
    def interface_operation(self, operation: str, interface: str, status: str, **details):
        """Log spécialisé pour les opérations sur interfaces"""
        context = {
            'operation': operation,
            'interface': interface,
            'status': status,
            **details
        }
        if status == 'success':
            self.info(f"{operation} réussi sur {interface}", **context)
        elif status == 'failed':
            self.error(f"{operation} échoué sur {interface}", **context)
        else:
            self.debug(f"{operation} sur {interface}: {status}", **context)

    def command_execution(self, command: str, return_code: int, duration_ms: int = None):
        """Log spécialisé pour l'exécution de commandes"""
        context = {
            'command': command,
            'return_code': return_code,
            'duration_ms': duration_ms
        }
        if return_code == 0:
            self.debug(f"Commande réussie: {command}", **context)
        else:
            self.warning(f"Commande échouée (code {return_code}): {command}", **context)


class JSONFormatter(logging.Formatter):
    """Formatter JSON pour logs structurés"""

    def format(self, record):
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'module': record.name,
            'function': record.funcName,
            'line': record.lineno,
            'message': record.getMessage()
        }

        # Ajouter le contexte si présent
        if hasattr(record, 'context'):
            log_entry['context'] = record.context

        # Ajouter l'exception si présente
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)


# Factory function pour créer des loggers facilement
def get_logger(name: str = "yarp", config: Optional[Dict] = None) -> YARPLogger:
    """Créé un logger YARP configuré"""
    return YARPLogger(name, config)


# Logger par défaut pour compatibilité
default_logger = None

def setup_default_logger(config: Optional[Dict] = None):
    """Configure le logger par défaut"""
    global default_logger
    default_logger = get_logger("yarp", config)

def debug(message: str, **context):
    if default_logger:
        default_logger.debug(message, **context)

def info(message: str, **context):
    if default_logger:
        default_logger.info(message, **context)

def warning(message: str, **context):
    if default_logger:
        default_logger.warning(message, **context)

def error(message: str, **context):
    if default_logger:
        default_logger.error(message, **context)