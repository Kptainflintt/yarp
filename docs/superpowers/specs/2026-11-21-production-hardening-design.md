# Durcissement production de YARP

**Date:** 2026-11-21
**Statut:** Proposé

## Contexte

Le point d'étape post-écriture Python a confirmé que les fonctionnalités sont
opérationnelles (interfaces, routage, NAT, firewall, DNS) mais que trois
risques bloquent une entrée en production :

1. **Application firewall non transactionnelle** — `yarp-apply.sh` flush les
   chaînes (`iptables -F INPUT/FORWARD/OUTPUT`) avant d'ajouter les règles
   YARP une par une. Un échec à mi-parcours laisse le pare-feu dans un état
   partiel, potentiellement fermé (perte d'accès SSH distant) ou ouvert.
2. **État partiel en cas d'échec** — l'orchestrateur enchaîne système, réseau,
   routage, NAT, firewall avec `set -e` sans rollback : une erreur à l'étape
   routage laisse les étapes précédentes appliquées et les suivantes non.
3. **DHCP non supervisé** — `udhcpc` est lancé en avant-plan avec timeout,
   sans renewal de bail ni reprise après coupure WAN.

Le socle Python (modules + `yarp_config.py`) étant sain, le pivot langage est
écarté : ces actions durcissent l'orchestration existante.

## Objectif

Rendre `yarp apply` sûr par défaut : aucune exécution ne peut laisser la
machine dans un état pire qu'avant l'appel, et tout échec est signalé avec le
périmètre exact appliqué.

## Périmètre

- **Inclus :** transaction firewall (iptables-restore), rollback global de
  l'apply, supervision DHCP, journalisation du périmètre appliqué.
- **Exclus :** migration nftables, interface web, routage dynamique (BGP/OSPF),
  réécriture du CLI Python (spécification 2026-03-17, déjà livrée).

## Spécifications techniques

### 1. Firewall transactionnel

- Construire le jeu de règles complet en mémoire (politiques + stateful +
  règles utilisateur) puis le commiter via `iptables-restore` (et
  `ip6tables-restore`) en un seul appel atomique.
- Avant le commit : `iptables-save` dans un fichier de snapshot
  (`/var/lib/yarp/firewall-before.rules`).
- Sur échec du restore : restaurer le snapshot avec
  `iptables-restore < snapshot` et remonter l'erreur avec le code de la règle
  fautive (index + nom dans le YAML).
- Interdire tout `iptables -F` direct hors du chemin transactionnel.
- Conserver le commentaire `YARP-FW-*` sur chaque règle pour les tags.

### 2. Rollback global de l'orchestrateur

- `yarp-apply.sh` capture l'état pré-apply (interfaces, routes, cartes
  firewall) dans `/var/lib/yarp/` avant toute modification.
- Chaque étape (system, dns, network, routing, nat, firewall) remonte son
  échec ; l'orchestrateur **s'arrête immédiatement**, exécute le rollback et
  affiche la liste explicite des étapes appliquées / annulées / non tentées.
- Le rollback restaure le dernier état connu sain, jamais un état partiel.
- Code de sortie non nul en cas d'échec + résumé lisible sur stderr.

### 3. Supervision DHCP

- Remplacer l'appel avant-plan de `udhcpc` par une invocation supervisée avec
  contract (OpenRC `supervise-daemon`) ou script de surveillance équivalent.
- Persister le bail (IP, lease-time, serveur) dans `/var/lib/yarp/` et le
  consigner dans le log JSON (champ `context`).
- Sur perte de bail : reprise automatique avec backoff exponentiel
  (30 s → 5 min max) plutôt qu'un blocage de l'apply.
- `yarp apply` ne doit pas échouer parce que le WAN n'a pas de bail : la
  configuration des interfaces LAN doit être appliquée et l'état WAN reporté
  explicitement (warning + code de sortie dédié documenté).

### 4. Journalisation du périmètre appliqué

- En fin d'apply, émettre un résumé structuré (JSON, ligne unique dans
  `apply.log`) listant chaque étape avec son statut (`applied`, `skipped`,
  `rolled_back`, `failed`) et sa durée.
- `yarp status` reprend ce résumé du dernier apply.

## Critères d'acceptation

1. Couper volontairement une règle firewall invalide dans le YAML doit
   laisser la configuration firewall précédente intacte (pas de flush
   partiel) et sortir en erreur avec le nom de la règle fautive.
2. Interrompre `yarp apply` (SIGINT) à n'importe quelle étape ne doit jamais
   laisser un flush iptables sans sa restauration.
3. Une machine bootée sans réponse DHCP du WAN doit avoir ses interfaces LAN
   et son firewall opérationnels.
4. `yarp status` affiche le compte-rendu structuré du dernier apply.
5. Tous les tests `make test` passent, y compris les nouveaux tests de
   transaction firewall (snapshot → commit → rollback sur règle invalide).
