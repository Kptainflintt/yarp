# Durcissement production — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** rendre `yarp apply` sûr : firewall non-transactionnel remplacé par un commit atomique `iptables-restore` avec snapshot/rollback, orchestrateur avec capture pré-apply + rollback + résumé structuré, DHCP WAN supervisé avec backoff, et `yarp status` affichant le dernier résumé d'apply.

**Architecture :** `firewall.py` génère le ruleset complet en mémoire et le commite via `iptables-restore`/`ip6tables-restore` (snapshot avant, restauration sur échec). `yarp-apply.sh` capture l'état pré-apply dans `/var/lib/yarp/`, piège ERR/INT/TERM, exécute un rollback best-effort (firewall d'abord) et écrit un résumé JSON d'une ligne dans `/var/log/yarp/apply.log`. `network.py` + `yarp-dhcp-watch.sh` supervisent `udhcpc` via `supervise-daemon` (fallback `nohup`) avec backoff exponentiel.

**Tech Stack :** Python 3 (stdlib), Bash, iptables-iptables-restore, busybox udhcpc, OpenRC `supervise-daemon`, unittest + harness bash.

**Spec :** `docs/superpowers/specs/2026-11-21-production-hardening-design.md` (autorité ; en conflit, la spec gagne).

## Global Constraints

- Aucun `iptables -F` direct hors du chemin transactionnel (spec §1) : `clear_firewall_rules` passe obligatoirement par `iptables-restore`.
- Conserver le commentaire `YARP-FW-*` sur chaque règle générée (nom de règle YAML normalisé) (spec §1).
- Snapshot pré-apply firewall : `/var/lib/yarp/firewall-before.rules` (v4) et `firewall-before-v6.rules` (v6) (spec §1/§2).
- Sur échec du restore : restaurer le snapshot, remonter l'erreur avec index (1-based dans `firewall.rules:` du YAML) + nom de la règle fautive (spec §1).
- Rôles des étapes de l'orchestrateur : exactement `system`, `dns`, `network`, `routing`, `nat`, `firewall` (spec §2).
- Statuts du résumé : `applied`, `skipped`, `rolled_back`, `failed` (spec §4).
- Résumé JSON : **une seule ligne** dans `/var/log/yarp/apply.log`, clé `"type":"apply_summary"` ; sortie non nule + résumé lisible sur stderr en cas d'échec (spec §2/§4).
- Backoff DHCP exponentiel : 30 s → 300 s max (5 min), reset sur bail valide (spec §3).
- `yarp apply` ne doit PAS échouer parce que le WAN n'a pas de bail : interfaces LAN/follow-ups appliqués, état WAN en warning + **code de sortie dédié 3** (documenté) (spec §3).
- Scripts exécutables avec shebang bash ; `set -e` conservé dans `yarp-apply.sh` (les traps ERR le complètent).
- **Testabilité sans root** : tous les chemins/binaires utilisés par le code modifié sont surchargeables par variables d'environnement : `YARP_DIR` (/opt/yarp), `YARP_STATE_DIR` (/var/lib/yarp), `YARP_CONFIG_FILE` (/etc/yarp/config.yaml), `YARP_APPLY_LOG` (/var/log/yarp/apply.log), `YARP_BIN_DIR` (recherche iptables-restore, iptables-save, ip…). Aucune valeur codée en dur dans les fonctions.
- Limites d'exécution : l'implémenteur travaille sur ≤ 2 fichiers par tâche.
- `make test` doit passer (tests phase 1 + nouveaux tests) (spec critère 5).

## Review Focus

1. **Flush non-transactionnel résiduel** : toute invocation `iptables -F` qui subsisterait en dehors d'un restore (y compris via `clear` CLI). Attendu : zéro occurrence, commit par `iptables-restore` uniquement. Test : `test_transactional_firewall.py::test_no_direct_flush` (grep du module) + revue du diff.
2. **SIGINT pendant un apply** : interrupt à n'importe quelle étape ne doit jamais laisser un état firewall sans restauration. Attendu : trap INT/TERM → rollback (restore snapshot) → exit non nul. Test : `test-hardening.sh::test_sigint_triggers_rollback` (kill -INT du process simulé, vérifie le restore).
3. **Règle firewall YAML invalide en milieu de liste** : la config précédente doit rester intacte et l'erreur doit porter index + nom de règle fautive. Test : `test_transactional_firewall.py::test_commit_failure_restores_snapshot_and_reports_rule`.
4. **WAN sans bail DHCP** : apply continue, LAN + firewall appliqués, exit 3, warning explicite. Test : `test-hardening.sh::test_wan_dhcp_failure_does_not_stop_apply`.
5. **Résumé d'apply** : une ligne JSON valide par apply, statuts exacts du set {applied, skipped, rolled_back, failed} ; `yarp status` la lit et la présente. Test : `test-hardening.sh::test_apply_summary_json_valid`.

---

### Task 1: Firewall — génération du ruleset en mémoire

**Files:**
- Modify: `src/modules/firewall.py`
- Create: `test/test_transactional_firewall.py`

**Interfaces:**
- Consumes : rien de nouveau (module existant : `_build_match_args`, `_normalize_rule_name`, `_validate_ip_or_cidr`, `_validate_interface_name`, `self.firewall`).
- Produces (utilisés par Task 2) :
  - `class RuleBuildError(Exception)` avec attributs `rule_index: int` (1-based dans `firewall.rules:`), `rule_name: str`, `message: str`.
  - `FirewallManager.build_v4_ruleset() -> tuple[list[str], list[dict]]` — retourne `(lines, meta)` : `lines` est le payload iptables-restore complet (liste de lignes : `*filter`, `:INPUT <P> [0:0]`, `:FORWARD <P> [0:0]`, `:OUTPUT <P> [0:0]`, règles `-A CHAIN ... -m comment --comment="YARP-FW-*" -j TARGET`, `COMMIT`) ; `meta[i]` = `{"kind": "policy"|"stateful"|"user", "rule_index": int|None, "rule_name": str|None}` aligné sur `lines` (mêmes index).
  - `FirewallManager.build_v6_ruleset() -> tuple[list[str], list[dict]]` — même format ; contient uniquement politiques + stateful + loopback (voir Ruling).
  - `FirewallManager._user_rule_args(rule, rule_index) -> list[str]` : fragment args d'une règle utilisateur SANS le préfixe `iptables -A chain` : `["-A", CHAIN, *match_args, "-p", proto, *port_args, "-m", "comment", f"--comment={comment}", "-j", target]` (et `--reject-with icmp-port-unreachable` si action reject). Retourne `None` si la règle est invalide (comportement de validation actuel conservé) — mais en génération transactionnelle, une règle invalide lève `RuleBuildError` (Fail-fast, voir Ruling).
  - Constante de classe/module : `SNAPSHOT_V4 = "firewall-before.rules"`, `SNAPSHOT_V6 = "firewall-before-v6.rules"` ; helpers `_state_dir()` (env `YARP_STATE_DIR`, défaut `/var/lib/yarp`) et `_which(bin)` (env `YARP_BIN_DIR` prioritaire, sinon shutil.which/résolution PATH).

**Rulings (décisions qui lient l'implémenteur) :**
- Fail-fast en génération : en mode transactionnel, une règle invalide n'est ni ignorée ni partiellement appliquée → `RuleBuildError` avec index + nom ; c'est ce qui porte "une exécution ne peut pas laisser un état pire" (spec Objectif).
- ip6tables : le module n'a jamais généré de règles utilisateur IPv6. Le ruleset v6 contient politiques + stateful + loopback (édition pentes identiques au v4, sans littéraux IPv4). Les règles utilisateur restent IPv4-only — cohérent avec l'existant ; ne pas inventer un filtrage v6 qui n'existe pas dans la config.
- Les logs d'application règle-par-règle (logger.info "Règle 'Name' [chain]: ...") sont émis à la **génération** (dans `_user_rule_args`), pas au commit — le commit est atomique.

- [ ] **Step 1: Écrire les tests de génération** (`test/test_transactional_firewall.py`, unittest, stub de config + logger vers tempdir) :

```python
# Extrait attendu — à adapter aux imports (modules dir à ajouter à sys.path, pas /opt/yarp)
class StubConfig:
    logging_cfg = {"logging": {"level": "DEBUG", "files": {...tmpdir...}, "formats": {"file": "json"}}}
    def get_firewall(self): return FIXTURE_FIREWALL   # clone de config/yarp.yaml.example
    def get_interfaces(self): return {}
    def get_logging(self): return self.logging_cfg

class TestBuildV4Ruleset(unittest.TestCase):
    def test_policies_in_ruleset(self):     # :INPUT DROP / :FORWARD DROP / :OUTPUT ACCEPT
    def test_stateful_and_user_rules_in_order(self)  # stateful d'abord, règles utilisateur ensuite, commentaires YARP-FW-RULE-*
    def test_line_meta_aligned(self)        # len(meta)==len(lines) ; meta[k]["rule_name"]=="Allow_SSH" pour sa ligne
    def test_reject_no_valid_match_raises(self)  # règle sans match valide -> RuleBuildError(rule_index=..., rule_name=...)
    def test_reject_comment_preserved(self) # reject -> "--reject-with icmp-port-unreachable" présent
class TestBuildV6Ruleset(unittest.TestCase):
    def test_no_user_v4_literals_in_v6(self)  # aucun "-s 192.168." dans le payload v6
```

- [ ] **Step 2: Vérifier l'échec** — `python3 -m unittest test.test_transactional_firewall -v` → AttributeError (méthode inexistante).
- [ ] **Step 3: Implémenter `build_v4_ruleset`/`build_v6_ruleset`/`_user_rule_args`/`RuleBuildError`** dans `src/modules/firewall.py` (journaux : régénérer depuis les méthodes existantes, pas de duplication — `_build_match_args` reste la source de vérité du matching).
- [ ] **Step 4: Vérifier le vert** — `python3 -m unittest test.test_transactional_firewall -v` → OK.
- [ ] **Step 5: Commit** — `git commit -m "feat(firewall): generation des rulesets transactionnels v4/v6 en memoire"`

### Task 2: Firewall — snapshot, commit atomique, rollback sur échec

**Files:**
- Modify: `src/modules/firewall.py`
- Modify: `test/test_transactional_firewall.py`

**Interfaces:**
- Consumes : Task 1 (`build_v4_ruleset`, `build_v6_ruleset`, meta, `RuleBuildError`, SNAPSHOT_V4/V6, `_state_dir`, `_which`).
- Produces :
  - `FirewallManager.snapshot_current_rules() -> bool` : `iptables-save` → `<state>/firewall-before.rules`, `ip6tables-save` → `firewall-before-v6.rules` (échec ip6 non bloquant pour v4 mais loggué warning).
  - `FirewallManager.commit_ruleset(lines, meta, restore_bin="iptables-restore") -> tuple[bool, str]` : écrit le payload dans `<state>/yarp-rules-<pid>.v4` / `.v6` ; run `iptables-restore` (stdin = payload, `check=False`) **puis** `ip6tables-restore` de même ; si succès → `(True, "")` ; si échec v4 → parse `"line (\d+)"` du stderr → meta lookup → restaure snapshot (`iptables-restore < firewall-before.rules`) → retourne `(False, "Ligne N (règle YAML 'Name', index K) : <stderr>")` ; même logique v6 côté v6.
  - `apply_all()` réécrivé : `snapshot_current_rules()` puis `build_v4_ruleset()`/`build_v6_ruleset()` puis `commit_ruleset(...)` ; plus **aucun** appel à flush ; sur échec → `logger.error(msg)` + `return False`.
  - `clear_firewall_rules()` réécrite : transactionnelle (snapshot → commit d'un payload "politiques seules") ; le CLI `clear` garde sa signature.
- Garde-fou : `test_no_direct_flush` grepne `firewall.py` et **échoue** si la sous-chaîne `iptables -F` apparaît (cette règle est un Global Constraint ; l'implémenteur doit faire échouer le test avant de retirer le flush).

**Tests** (fakes dans tempdir avec `YARP_BIN_DIR` ; scripts fake POSIX) :
```bash
#!/bin/sh
# fake-iptables-restore: échoue si le payload contient "FAIL_MARKER", sinon OK ;
# reçoit le payload sur stdin, le copie dans $FAKE_LOG/$1.<n> pour assertion.
# fake-iptables-save: dump d'un ruleset "état précédent" fixe.
```
- `test_snapshot_written` (2 fichiers présents, contenu attendu)
- `test_commit_success_stdin_full_ruleset` (le fake reçoit `*filter…COMMIT`)
- `test_commit_failure_restores_snapshot_and_reports_rule` : règles YAML avec `FAIL_MARKER` au nom de règle 2 (ex. `name: "FAIL_MARKER ku"`) → `(False, msg)` contient `index` et le nom normalisé fautive ; le fake a bien reçu le snapshot en seconde commande.
- `test_clear_is_transactional` (clear → snapshot + restore appelés, pas de -F).
- `test_no_direct_flush` (grep du module : zéro `"iptables", "-F"` / `iptables -F`).

- [ ] **Step 1: les tests fake-bin** → Step 2 échec vert certifié → Step 3 implémentation (`snapshot_current_rules`, `commit_ruleset`, réécriture `apply_all`, `clear_firewall_rules` transactionnelle, suppression du flush et de `apply_default_policies`/`apply_stateful_rules` en tant que writers directs — leur logique migre dans les builders hérités de Task 1) → Step 4 vert → Step 5 `git commit -m "feat(firewall): commit atomique iptables-restore avec snapshot et rollback"`

### Task 3: Orchestrateur — capture pré-apply, traps, rollback, résumé

**Files:**
- Modify: `src/core/yarp-apply.sh`
- Create: `test/test-hardening.sh`
- Modify: `Makefile` (cible `test` : `test-phase1.sh` + `test-hardening.sh` + `python3 -m unittest discover -s test -p 'test_*.py' -v`)

**Interfaces:**
- Consumes : Task 2 — les snapshots firewall s'appellent via `iptables-restore` ; l'orchestrateur fait sa propre capture AUSSI (indépendance : `yarp apply` appelle les modules subprocess, pas leur API interne).
- Produces :
  - Vars d'env surchargeables en tête : `YARP_DIR`, `YARP_STATE_DIR`, `YARP_CONFIG_FILE`, `YARP_APPLY_LOG` (défauts inchangés).
  - `capture_pre_state()` : remplace `save_state` ; appelé **avant** toute étape ; écrit `interfaces.json`, `routes.json`, `iptables.rules`, `ip6tables.rules` dans `<YARP_STATE_DIR>`.
  - Traps : `trap on_interrupt INT TERM` et `trap on_step_failure ERR` ; `on_step_failure` et `on_interrupt` appellent `rollback()` puis `write_summary()` puis exit non nul (1).
  - `run_step <name> <command...>` : wrapper qui chronomètre (`date +%s%3N`), enregistre dans `STEPS_APPLIED`/`STEPS_ROLLED_BACK` (variable d'array), logge ; status "failed" si exit non nul.
  - `rollback()` : **toujours** en premier : `iptables-restore < iptables.rules` + `ip6tables-restore < ip6tables.rules` depuis le snapshot pré-apply (les deux avec check, message d'erreur explicite) ; puis best-effort routes/addr non re-appliquées (conservative, aucune commande réseau destructrice) — la spec ne demande que le retour au dernier état connu ; firewall = priorité absolue (accès SSH).
  - `write_summary <result> <exit_code>` : une ligne JSON via `printf '%s\n'` vers `YARP_APPLY_LOG` (append), contenu :
    `{"type":"apply_summary","timestamp":"<iso8601>","result":"<success|rolled_back|failed>","exit_code":N,"steps":{"system":{"status":"<applied|skipped|failed|rolled_back>","duration_ms":N},...}}` — clés d'étapes = les 6 canoniques, toujours présentes.
  - Flux `main()` : validate_config (hors steps : échec → résumé avec 6 existants "skipped" + exit 1), `capture_pre_state`, backup_backups+disable_alpine placés logiquement sous l'étape "system", puis `run_step system ...`, `run_step dns ...`, `run_step network ...`, `run_step routing ...`, `run_step nat ...`, `run_step firewall ...`, `write_summary success 0`.
  - **Code 3 (warning WAN)** : le step `network` qui retourne exit code **3** (Le Task 5 introduira ce code dans network.py) n'arrête PAS l'apply : log warning "DHCP WAN indisponible", step marqué `applied` + note, continue ; à la fin, si au moins un warning WAN → `result="partial_warning"`, exit 3 ; sinon exit 0. (Described for Task 5 completion — orchestrateur doit déjà accepter le code 3.)

**Tests** (`test/test-hardening.sh`, même style que phase1 : helpers `test_pass`/`test_fail`) :
- Sandbox : `YARP_DIR=$tmpdir`, `CONFIG_FILE/YARP_CONFIG_FILE=$tmpdir/config.yaml`, `YARP_STATE_DIR=$tmpdir/state`, `YARP_APPLY_LOG=$tmpdir/apply.log`, `PATH=$tmpdir/fakebin:$PATH` avec fakes `iptables-restore`, `iptables-save`, `python3` (stub qui logge le module demandé et échoue sur routing pour simuler).
- `test_trap_err_declared` : grep `trap .*ERR` et `trap .*INT` dans yarp-apply.sh.
- `test_rollback_restores_firewall_snapshot` : routing stub échoue → dans le journal du fake, `iptables-restore` a reçu le snapshot.
- `test_summary_json_valid` : `python3 -c "json.load(lone_line)"` du dernier apply.log → `result=="rolled_back"`, `"firewall" in steps`.
- `test_sigint_triggers_rollback` : le process d'apply lancé en bac à sable reçoit `kill -INT` au milieu d'un step (stub python3 qui dort) → le handler exécute le restore snapshot + summary `rolled_back` + exit non nul.
- `test_wan_dhcp_failure_does_not_stop_apply` : run_step network exit 3 → nat/firewall quand même exécutés.
- Ruling : le rollback ne restaure que firewall (snapshot) + rapporte routes/interfaces comme restaurés via fiches JSON (pas de reapplication réseau inventée : c'est le choix conservateur raisonnable, la spec subordonne tout au restore du firewall).

- [ ] **Step 1: test-hardening.sh squelette + les 4 tests en mode "spéc"** → Step 2 échec certifié (`bash -n` ok mais fakes non appelés) → Step 3 réécriture `yarp-apply.sh` (en conservant `validate_config`, `backup_alpine_config`, `disable_alpine_networking`) → Step 4 Makefile → Step 5 `make test` vert → Step 6 `git commit -m "feat(orchestrator): capture pre-apply, rollback firewall, traps ERR/INT et resume JSON"`

### Task 4: `yarp status` — affichage du résumé du dernier apply

**Files:**
- Modify: `src/core/yarp`

**Interfaces:**
- Consumes : Task 3 — la clé `"type":"apply_summary"` et les statuts.
- Produces : `cmd_status` : après les sections réseau, section "=== Dernier apply YARP ===" : dernière ligne de `$YARP_APPLY_LOG` (env, défaut `/var/log/yarp/apply.log`) contenant `"type":"apply_summary"` ; `python3 -m json.tool` pour jolir + mapping statuts vers l'human-readable (`applied`→✓, `failed`→✗, `rolled_back`→⟲, `skipped`→–) ; absence → "Aucun résumé d'apply disponible".

- [ ] **Step 1: test** (append `test_status_reads_summary` à test-hardening.sh ; stub de yarp CLI source en subshell avec YARP_APPLY_LOG factice + assert sortie contient "Dernier apply") → Step 2 échec → Step 3 implémenter `cmd_status` → Step 4 `make test` vert → Step 5 `git commit -m "feat(cli): yarp status affiche le resume du dernier apply"`

### Task 5: DHCP supervisé (network.py + watchdog)

**Files:**
- Create: `src/core/yarp-dhcp-watch.sh`
- Modify: `src/modules/network.py`

**Interfaces:**
- Produces :
  - `src/core/yarp-dhcp-watch.sh <iface> `<max_backoff_s=300>` : watchdog : boucle — si `udhcpc` actif pour `<iface>` → sleep 5 ; sinon → relance (`supervise-daemon --start "udhcpc-<iface>" --background --command udhcpc -- -i <iface> -t 3 -T 10 -f -q -s /etc/yarp/dhcp-hook.sh` si `command -v supervise-daemon`, sinon `nohup udhcpc ... &`) — le flag `-s /etc/yarp/dhcp-hook.sh` n'est ajouté QUE si le hook est exécutable (il n'existera qu'à partir de la Task 6 ; tolérance à son absence) ; backoff : `delay=30` doublant à chaque nouvelle tentative, capé à 300, **reset à 30** dès que `<iface>` a une adresse non-link-local OU que `udhcpc` tient > 120 s ; log à chaque relance (fichier `<YARP_STATE_DIR>/dhcp-watch-<iface>.log`).
  - `network.py` : `YARP_DIR = os.environ.get("YARP_DIR", "/opt/yarp")` (testabilité) ; `enable_dhcp(iface)` réécrite : tue les clients datés, démarre le watchdog en arrière-plan (`nohup ... dhcp-watch.sh <iface> &` + `disown`), attend le bail jusqu'à `WAN_DHCP_TIMEOUT_S=${YARP_DHCP_TIMEOUT_S:-30}` (présence d'adresse) ; retourne bool.
  - Exit code 3 : `apply_all()` collecte `dhcp_failed_ifaces` ; à la fin, `main()` : 0 si aucun, **3** si au moins un DHCP a échoué mais le reste de la config (concurrent LAN) est OK, 1 en cas de vrai échec de config d'interface non-DHCP. Le message d'erreur de chaque interface DHCP passera de "return False → stop" à "warning + collecte".
  - Helper : `DhcpState` (fct imbriquée ou module) `read_lease_state(iface) -> dict|None` lit `<YARP_STATE_DIR>/dhcp-<iface>.json` ; à l'apply, si bail présent, `logger.info("Bail DHCP WAN acquis", **{"context": {"ip": ..., "lease": ..., "server": ...}})` (champ contexte JSON, spec §3).

**Ruling :** les interfaces LAN en DHCP bénéficient du même traitement (spéc ne distingue pas réseau) ; le code 3 n'est émis que si une interface DHCP n'a pas de bail, quel que soit son rôle.

- [ ] **Step 1: tests** (append `test-hardening.sh` : `test_watch_script_exists_and_syntax` (`bash -n`), `test_network_exit_3_on_dhcp_failure` — network.py lancé avec stub de `udhcpc` inexistant dans PATH fakes + config YAML avec 1 LAN statique + 1 WAN dhcp → exit code 3, interfaces LAN logguées) → Step 2 échec certifié → Step 3 implémentation (2 fichiers) → Step 4 `make test` vert → Step 5 `git commit -m "feat(dhcp): supervision udhcpc avec backoff et code de sortie wan 3"`

### Task 6: Persistance du bail DHCP + installation

**Files:**
- Create: `src/core/yarp-dhcp-hook.sh`
- Modify: `install.sh` (installer `yarp-dhcp-watch.sh` → `$BINDIR/yarp-dhcp-watch`, `yarp-dhcp-hook.sh` → `/etc/yarp/dhcp-hook.sh`)

**Interfaces:**
- Consumes : Task 5 (watch script référence `/etc/yarp/dhcp-hook.sh`), state dir.
- Produces : hook `udhcp -s` : `#!/bin/sh` POSIX ; `YARP_IFACE` (exporté par feature retry) ; action `$1` ∈ {deconfig, bound, renew} ; **chaîne vers le default.script d'Alpine** (`/usr/share/udhcpc/default.script "$@"`) pour ne pas casser la config IP ; sur `bound|renew` : écrit `<YARP_STATE_DIR>/dhcp-<iface>.json` = `{"ifname":"eth0","ip":$ip,"prefix":(dérivé de $subnet via ipcalc? POSIX: non — utiliser `busybox ipcalc` si dispo, sinon default 24)","router":$router,"server":"$siaddr","lease":$lease,"ts":"<iso8601>"}` ; sur `deconfig` : `{"ifname":...,"state":"lost"}` ; conserve un lock léger (`flock` wrap pv? — Non : écriture atomique via `mv` de tmp).
- `install.sh` : les 2 lignes d'install + `chmod 755`.

- [ ] **Step 1: les tests** (`test-hardening.sh` : `test_dhcp_hook_syntax`, `test_dhcp_hook_writes_lease_json` — appel du hook avec env YARP_IFACE=eth0 + `bound` + vars udhcpc simulées → jq/json.load valide + champs attendus ; `test_dhcp_hook_chains_default_script` — stub default.script dans PATH fakes) ; Step 2 échec certifié → Step 3 implémentation 2 fichiers → Step 4 `make test` → Step 5 `git commit -m "feat(dhcp): persistance du bail udhcpc dans /var/lib/yarp"`

### Task 7: Documentation (@docs)

**Files:**
- Modify: `README.md` (pipeline apply : ordre steps, code de sortie 3 — warning WAN DHCP —, snapshot/rollback firewall)
- Modify: `TESTING.md` (nouveaux tests + comment lancer `make test` / unittest)

- [ ] **Step 1: rédiger** → **Step 2: vérifier** (`make test` toujours vert) → **Step 3:** `git commit -m "docs: durcissement production (apply transactionnel, rollback, dhcp supervisé)"`

## Rulings transverses (trace intellectuelle du plan)

- `Ruling: commit_ruleset restaure le snapshot AVANT de signaler` — ordre imposé par spec ("restaurer le snapshot ET remonter l'erreur") : si le restore du snapshot échoue lui-même, le code passe en erreur FATALE distincte (exit 2, message explicite) — c'est une situation critique qu'on ne masque pas derrière exit 1. — coût si faux : le restore-last-resort mérite un canal d'alerte distinct.
- `Ruling: ruleset v6 = politiques+stateful uniquement` — le module actuel n'applique aucune règle utilisateur IPv6 ; injecter des `-s 10.x.x.x` dans ip6tables-restore casserait l'atomique. La spec demande ip6tables-restore "en un seul appel atomique" : on respecte ça pour les tables qu'on gère réellement.
- `Ruling: rollback orchestrateur = firewall prioritaire, réseau best-effort` — la spec subordonne tout au "dernier état connu sain" ; réappliquer adresses/routes depuis ip -j serait un nouveau code à risque. Les snapshots JSON fournissent la vérité documentée pour l'opérateur.
- `Ruling: exit 3 = warning WAN DHCP` — spec : "warning + code de sortie dédié documenté" ; 3 ≠ 1 (échec) et n'arrête pas l'apply.
- `Ruling: un bail "dhcp-watch" franchément expiré` — le backoff reset se base sur la présence d'adresse (proxy de bail valide) : jamais DNS/API essentiel, 120 s de stabilité client est le critère de réalité.
