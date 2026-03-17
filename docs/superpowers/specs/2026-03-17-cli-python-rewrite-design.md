# Réécriture du CLI YARP en Python

**Date:** 2026-03-17
**Statut:** Approuvé

## Contexte

Le CLI actuel (`src/core/yarp`) est un script Bash de 108 lignes qui dispatche
vers des modules Python pour 5 de ses 7 commandes. Le mélange Bash/Python dans
la couche core crée une ambiguïté de maintenance signalée lors de la revue de
code. Les blocs `python3 -c` inline dans `yarp-apply.sh` ont déjà été éliminés
(remplacés par des sous-commandes `get` dans `yarp_config.py`). Le CLI est le
dernier point de friction Bash/Python dans core/.

## Objectif

Réécrire `src/core/yarp` en Python pour éliminer la frontière Bash/Python dans
la couche core. Même ensemble de commandes, même comportement, même interface
utilisateur.

## Périmètre

- **Inclus :** Réécriture du CLI entrypoint (`src/core/yarp` → `src/core/yarp.py`)
- **Exclus :** Réécriture de `yarp-apply.sh` (reste en Bash), ajout de nouvelles commandes

## Architecture

### Fichier : `src/core/yarp.py`

Structure conforme au pattern existant des modules YARP :

```
#!/usr/bin/env python3
"""YARP CLI - Interface en ligne de commande"""

Shebang → docstring française → imports → constantes → classe → main() → guard
```

### Classe : `YARPCli`

```python
class YARPCli:
    def __init__(self):
        # Lit VERSION, construit le dict de commandes

    def _run_command(self, cmd):
        # subprocess.run() wrapper, retourne (returncode, stdout, stderr)

    def cmd_apply(self):     # → yarp-apply.sh
    def cmd_validate(self):  # → yarp_config.py validate
    def cmd_show(self):      # → yarp_config.py show
    def cmd_status(self):    # → ip -br addr, ip route, ip -6 route
    def cmd_check(self):     # → yarp-check
    def cmd_reload(self):    # → /etc/init.d/yarp reload ou fallback apply
    def cmd_version(self):   # → print version

    def show_help(self):     # → texte d'aide en français
    def run(self, args):     # → dispatch args[0] vers le dict de commandes
```

### Dispatch des commandes

Dict `str → method` :
```python
self.commands = {
    "apply": self.cmd_apply,
    "validate": self.cmd_validate,
    "show": self.cmd_show,
    "status": self.cmd_status,
    "check": self.cmd_check,
    "reload": self.cmd_reload,
    "version": self.cmd_version,
}
```

`help`, `--help`, `-h` → `show_help()`.
Commande inconnue → message d'erreur français sur stderr, `sys.exit(1)`.
Aucun argument → `show_help()`, `sys.exit(0)`.

### Gestion des erreurs et codes de sortie

| Commande | Comportement |
|----------|-------------|
| `apply` | Propage le code retour de `yarp-apply.sh` |
| `validate`, `show` | Propage le code retour de `yarp_config.py` |
| `check` | Propage le code retour de `yarp-check` |
| `status` | Exécute 3 commandes `ip` séquentiellement avec en-têtes. Continue si une échoue. Retourne 0 sauf si toutes échouent. |
| `reload` | Vérifie `/etc/init.d/yarp` avec `os.path.isfile()`. Si présent, l'appelle. Sinon, fallback vers `cmd_apply()`. |
| `version` | Print pur, retourne toujours 0. |

Pas d'exceptions propagées au caller. Toutes les erreurs sont gérées
en interne avec messages français et codes de sortie appropriés.

### Déploiement

Le entrypoint installé est un wrapper shell minimal à `/usr/local/bin/yarp` :

```bash
#!/bin/sh
exec python3 /opt/yarp/core/yarp.py "$@"
```

Modifications dans `install.sh` / `setup.sh` :
- Copier `yarp.py` vers `/opt/yarp/core/`
- Créer le wrapper `/usr/local/bin/yarp`
- `chmod +x` sur les deux fichiers

### Tests

- `python3 -m py_compile src/core/yarp.py` pour la validation syntaxique
- Ajouter `yarp.py` à la liste de vérification Python dans `test/test-phase1.sh`
- Supprimer l'ancien `src/core/yarp` (Bash) une fois la réécriture vérifiée

## Contraintes

- Python 3 standard library uniquement (pas de dépendances tierces)
- Tous les messages, commentaires, docstrings en français
- Pattern `sys.argv` manuel (pas d'argparse), conforme aux conventions YARP
- Compatible Alpine Linux 3.18+
