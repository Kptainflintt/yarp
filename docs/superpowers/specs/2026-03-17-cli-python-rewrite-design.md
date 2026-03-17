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
        # Note: retourne returncode (int) et non success (bool) car les
        # commandes cmd_* doivent propager le code de sortie exact vers
        # sys.exit(). Ceci déroge volontairement au pattern (success, stdout,
        # stderr) utilisé dans les autres modules YARP.

    def cmd_apply(self):     # → YARP_DIR/bin/yarp-apply
    def cmd_validate(self):  # → YARP_DIR/core/yarp_config.py validate
    def cmd_show(self):      # → YARP_DIR/core/yarp_config.py show
    def cmd_status(self):    # → ip -br addr, ip route, ip -6 route
    def cmd_check(self):     # → YARP_DIR/bin/yarp-check
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
| `apply` | Propage le code retour de `YARP_DIR/bin/yarp-apply` |
| `validate`, `show` | Propage le code retour de `YARP_DIR/core/yarp_config.py` |
| `check` | Propage le code retour de `YARP_DIR/bin/yarp-check` |
| `status` | Exécute 3 commandes `ip` séquentiellement avec en-têtes entre chaque. Propage le code retour de la dernière commande (`ip -6 route`), comme le fait la version Bash actuelle. |
| `reload` | Vérifie `/etc/init.d/yarp` avec `os.path.isfile()`. Si présent, l'appelle. Sinon, fallback vers `cmd_apply()`. |
| `version` | Print pur, retourne toujours 0. |

Pas d'exceptions propagées au caller. Toutes les erreurs sont gérées
en interne avec messages français et codes de sortie appropriés.

Toutes les commandes appellent les scripts/outils externes via
`subprocess.run()` (pas d'import direct de `YARPConfig` ou autres modules).
Ceci maintient le CLI comme un dispatcher pur, identique en comportement
à la version Bash.

### Déploiement

Le entrypoint installé est un wrapper shell minimal à `/usr/local/bin/yarp` :

```bash
#!/bin/sh
exec python3 /opt/yarp/core/yarp.py "$@"
```

Modifications dans `install.sh` :
- **Ligne 48** : remplacer `install -m 755 src/core/yarp "$BINDIR/yarp"` par
  `install -m 644 src/core/yarp.py "$COREDIR/yarp.py"` (le .py va dans core/,
  pas dans bin/). L'ancien `$BINDIR/yarp` n'est plus créé. Sur une mise à jour,
  ajouter `rm -f "$BINDIR/yarp"` pour nettoyer l'ancienne version Bash.
- **Ligne 85** : remplacer `ln -sf "$BINDIR/yarp" /usr/local/bin/yarp` par la
  création du wrapper shell :
  ```bash
  cat > /usr/local/bin/yarp << 'WRAPPER'
  #!/bin/sh
  exec python3 /opt/yarp/core/yarp.py "$@"
  WRAPPER
  chmod +x /usr/local/bin/yarp
  ```
- **Ligne 86** : `ln -sf "$BINDIR/yarp-apply" /usr/local/bin/yarp-apply`
  reste inchangé.
- **Ligne 113** : `chmod 755 "$BINDIR"/*` reste inchangé (yarp-apply et
  yarp-check sont toujours dans bin/)
- Le script OpenRC (`src/init/yarp`) appelle `/usr/local/bin/yarp` qui est le
  wrapper — transparent, aucune modification nécessaire.

### Tests

- `python3 -m py_compile src/core/yarp.py` pour la validation syntaxique
- Ajouter `yarp.py` à la liste de vérification Python dans `test/test-phase1.sh`
- Supprimer l'ancien `src/core/yarp` (Bash) une fois la réécriture vérifiée

## Contraintes

- Python 3 standard library uniquement (pas de dépendances tierces)
- Tous les messages, commentaires, docstrings en français
- Pattern `sys.argv` manuel (pas d'argparse), conforme aux conventions YARP
- Compatible Alpine Linux 3.18+
