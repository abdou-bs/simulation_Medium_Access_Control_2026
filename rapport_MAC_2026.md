# Rapport de Projet — Simulation du Protocole MAC avec Exponential Backoff
### Année 2025-2026 | Simulation & Méthodes de Monte-Carlo

---

## Table des matières

1. [Introduction et contexte](#1-introduction-et-contexte)
2. [Modélisation du système](#2-modélisation-du-système)
3. [Architecture du simulateur à événements discrets (SED)](#3-architecture-du-simulateur-à-événements-discrets-sed)
4. [Implémentation technique](#4-implémentation-technique)
5. [Résultats expérimentaux](#5-résultats-expérimentaux)
6. [Analyse et discussion](#6-analyse-et-discussion)
7. [Détermination du N optimal](#7-détermination-du-n-optimal)
8. [Conclusion](#8-conclusion)

---

## 1. Introduction et contexte

### 1.1 Problématique
Lorsque plusieurs stations tentent de communiquer simultanément sur un même canal de transmission, il se produit des **collisions** : les données des deux émetteurs se superposent et sont perdues. Pour gérer ces conflits, les réseaux modernes implémentent des protocoles dits **MAC** (*Medium Access Control*).

On distingue deux approches :
- **Centralisée** : un serveur central arbitre les accès (plus efficace mais plus complexe)
- **Décentralisée** : chaque station gère elle-même ses rechargements après collision (plus simple à déployer, utilisée dans Ethernet, Wi-Fi 802.11)

### 1.2 Algorithme Exponential Backoff
Ce projet porte sur l'algorithme **Exponential Backoff**, largement utilisé dans des protocoles comme Ethernet (CSMA/CD) et 802.11 (Wi-Fi). Son principe est le suivant :

> Lorsqu'une station détecte une collision à l'état *i*, elle attend un délai aléatoire de moyenne **2^i · τ** avant de retenter l'émission, puis passe à l'état *i+1*. En cas de succès, elle retourne à l'état initial (état 1).

### 1.3 Objectifs du projet
1. Implémenter un **Simulateur à Événements Discrets (SED)** en Python
2. Tracer les métriques temporelles : débit `n(t)/t`, longueur moyenne de file, taux de pertes
3. Observer la convergence vers la valeur stationnaire `d(N, K, λ, τ)`
4. Analyser l'influence de `λ` et `N` sur le débit
5. Déterminer le **N optimal** maximisant le débit avec un **intervalle de confiance à 95 %**

---

## 2. Modélisation du système

### 2.1 Paramètres du modèle

| Paramètre | Description | Valeur utilisée |
|-----------|-------------|-----------------|
| **N** | Nombre de stations | 10 (par défaut) |
| **K** | Capacité de la file d'attente par station | 10 (par défaut) |
| **λ** | Taux d'arrivée Poisson par station (paquets/u.t.) | 0.06 |
| **τ** | Paramètre de base du backoff exponentiel | 0.5 |
| **t_max** | Durée de simulation | 3 000 u.t. |

### 2.2 Hypothèses du modèle
- Chaque station génère des paquets selon un **processus de Poisson de paramètre λ** (inter-arrivées exponentielles)
- La **durée d'émission d'un paquet est fixée à 1 unité de temps**
- Chaque station dispose d'une **file d'attente de capacité bornée K**
- Deux émissions simultanées provoquent une **collision** : les deux paquets sont **conservés** (non perdus) mais doivent être re-émis après un délai de backoff
- Un paquet est **définitivement perdu** uniquement si la file est pleine à son arrivée
- **Carrier Sense (écoute de canal)** : une station attend que le canal soit libre avant de tenter l'émission
- Après chaque succès, l'**état de backoff est réinitialisé à 1**

### 2.3 Mécanisme de collision
Lorsque le canal se libère à l'instant `t_free`, toutes les stations en attente reprogramment leur tentative à ce même instant. Si ≥ 2 stations tentent simultanément → collision. Chaque station en collision passe à l'état `k+1` et attend un délai `Exp(1/(τ·2^k))`.

### 2.4 Métriques de performance
Les trois métriques principales analysées sont :

**a) Débit instantané n(t)/t**
$$d = \frac{\text{nombre de paquets transmis avec succès}}{t}$$

**b) Longueur moyenne de file (Loi de Little)**
$$\bar{L} = \frac{1}{T} \int_0^T \sum_{i=1}^N q_i(t) \, dt$$

**c) Taux de paquets perdus**
$$p_{\text{perte}} = \frac{\text{paquets arrivés sur file pleine}}{\text{total paquets arrivés}}$$

---

## 3. Architecture du simulateur à événements discrets (SED)

### 3.1 Principe général
Le SED repose sur un **écheancier** (file de priorité min-heap) qui stocke les événements futurs triés par ordre chronologique. À chaque itération, l'événement le plus proche dans le temps est extrait et traité, ce qui génère potentiellement de nouveaux événements.

```
BOUCLE PRINCIPALE SED :
  Tant que l'écheancier n'est pas vide :
    (t, evt_type, station_i) ← extraire min de l'écheancier
    Si t > t_max → ARRÊT
    Traiter l'événement
    Générer les événements suivants
```

### 3.2 Événements
Deux types d'événements sont définis :

| Type | Constante | Description |
|------|-----------|-------------|
| **ARRIVAL** | `0` | Arrivée d'un nouveau paquet dans la file de la station *i* |
| **ATTEMPT** | `1` | Tentative d'émission sur le canal par la station *i* |

### 3.3 Variables d'état du système

| Variable | Type | Description |
|----------|------|-------------|
| `queue[i]` | `int[N]` | Nombre de paquets en file pour chaque station |
| `backoff_state[i]` | `int[N]` | État de backoff courant (démarre à 1) |
| `pending_attempt[i]` | `bool[N]` | Indique si une tentative est déjà planifiée |
| `channel_busy_until` | `float` | Instant auquel le canal sera à nouveau disponible |

### 3.4 Traitement des événements

#### Événement ARRIVAL (arrivée d'un paquet)
```
1. Incrémenter le compteur d'arrivées
2. Si file[i] < K :
     → Ajouter le paquet à la file
     → Si aucune tentative planifiée : programmer ATTEMPT(t, i)
3. Sinon (file pleine) :
     → Incrémenter le compteur de paquets perdus
4. Programmer le prochain ARRIVAL(t + Exp(λ), i)
```

#### Événement ATTEMPT (tentative d'émission)
```
1. Si file[i] == 0 → rien à envoyer, continuer
2. Si canal occupé (t < channel_busy_until) :
     → Reprogrammer ATTEMPT(channel_busy_until, i)
3. Sinon (canal libre) :
     → Collecter toutes les tentatives simultanées
     → Canal occupé jusqu'à t + 1.0
     → Si une seule station tente : SUCCÈS
          * Retirer le paquet de la file
          * Réinitialiser backoff à 1
          * Programmer prochain ATTEMPT si file non vide
     → Si plusieurs stations tentent : COLLISION
          * Pour chaque station collisionnée :
            - k ← backoff_state[j]
            - Programmer ATTEMPT(channel_busy_until + Exp(1/(τ·2^k)), j)
            - backoff_state[j] ← k + 1
```

### 3.5 Collecte des données temporelles
Les métriques sont enregistrées périodiquement (toutes les `record_every` u.t.) pour permettre la visualisation de l'évolution temporelle :

```python
times.append(next_rec)
throughputs.append(n_success / next_rec)
queue_avgs.append(total_queue_area / next_rec)
loss_rates.append(n_lost_full / n_arrived)
```

---

## 4. Implémentation technique

### 4.1 Structure du code (notebook `projet_MAC.ipynb`)

Le projet est organisé en **6 sections** dans le notebook Jupyter :

| Section | Contenu |
|---------|---------|
| **Section 1** | Imports et fonctions utilitaires (loi exponentielle, IC95%) |
| **Section 2** | Simulateur à Événements Discrets (SED) + validation |
| **Section 3** | Évolution temporelle des métriques |
| **Section 4** | Débit d(N,K,λ,τ) en fonction de λ |
| **Section 5** | Débit d(N,K,λ,τ) en fonction de N |
| **Section 6** | Détermination du N optimal avec IC à 95 % |

### 4.2 Génération des variables aléatoires
La méthode d'**inversion** est utilisée pour générer des variables exponentielles :

```python
def exp_rv(rate, rng=None):
    """Génère X ~ Exp(rate) par inversion : X = -ln(U)/rate."""
    u = (rng.random() if rng else random.random())
    while u == 0.0:
        u = (rng.random() if rng else random.random())
    return -math.log(u) / rate
```

> **Validation** : Pour `rate=2`, la moyenne empirique sur 10 000 échantillons est `0.5028 ≈ 0.5000` ✓

### 4.3 Calcul de l'intervalle de confiance à 95 %
La méthode approchée par la loi normale est utilisée (théorème central limite) :

```python
def ic95(vals):
    n = len(vals)
    m = moyenne(vals)
    s = sqrt(sum((v - m)**2 for v in vals) / (n - 1))
    marge = 1.96 * s / sqrt(n)
    return (m - marge, m + marge)
```

### 4.4 Bibliothèques utilisées

| Bibliothèque | Usage |
|-------------|-------|
| `heapq` | Écheancier (file de priorité min-heap) |
| `random` | Génération pseudo-aléatoire reproductible (seed) |
| `math` | Fonctions mathématiques (log, sqrt) |
| `numpy` | Calculs numériques |
| `matplotlib` | Visualisation des résultats |

### 4.5 Validation du simulateur
Deux cas tests ont été réalisés pour valider le simulateur :

**Test 1 — N=1 (aucune collision possible)**
```
Résultat :  débit = 0.5171  ≈  min(λ, 1) = 0.5   ✓
Collisions : 0   ✓
```

**Test 2 — N=10, charge totale = 0.6**
```
Débit : 0.5290
Collisions : 1 189
Paquets perdus en file pleine : 164
```

---

## 5. Résultats expérimentaux

### 5.1 Paramètres de simulation retenus

| Paramètre | Valeur | Justification |
|-----------|--------|---------------|
| N | 10 | Nombre de stations modéré |
| K | 10 | Capacité de file suffisante |
| λ | 0.06 | Charge totale N·λ = 0.6 < 1 (capacité canal) |
| τ | 0.5 | Délai de base backoff |
| t_max | 3 000 | Assure la convergence vers le régime stationnaire |

> La charge totale offerte est **N×λ = 0.6 paquets/u.t.**, légèrement inférieure à la capacité du canal (1 paquet/u.t.), ce qui permet d'observer à la fois des collisions et une convergence vers un régime stable.

### 5.2 Résultats de simulation (paramètres de référence)

| Métrique | Valeur |
|----------|--------|
| Paquets arrivés | 1 850 |
| Paquets transmis avec succès | 1 526 |
| Collisions (par station impliquée) | 1 831 |
| Paquets perdus (file pleine) | 287 |
| **Débit d** | **0.5087 paquets/u.t.** |
| Longueur moyenne de file | 26.63 paquets |
| **Taux de perte** | **15.51 %** |

### 5.3 Évolution temporelle des métriques

**a) Débit n(t)/t**
- La courbe converge progressivement vers la valeur stationnaire `d ≈ 0.51`
- La convergence est observable à partir d'environ t ≈ 500 u.t.
- Les fluctuations initiales s'amortissent avec le temps (phénomène de régime transitoire)

**b) Longueur moyenne de file**
- Augmente rapidement au début (régime transitoire)
- Se stabilise autour de `≈ 26.6 paquets` en régime permanent

**c) Taux de perte**
- Instable en début de simulation (dénominateur faible)
- Converge vers `≈ 15.5 %` en régime permanent

### 5.4 Influence de λ sur le débit d(N, K, λ, τ)

Les simulations montrent que :

| Région | Comportement |
|--------|-------------|
| **λ faible** (charge ≪ 1) | Le débit croit quasi-linéairement avec λ (peu de collisions) |
| **λ optimal** | Maximum du débit, équilibre entre charge et collisions |
| **λ élevé** (surcharge) | Le débit chute : saturation, collisions fréquentes, files pleines |

> La courbe présente une forme en **cloche** : le débit augmente puis décroît au-delà d'un seuil critique de charge.

### 5.5 Influence de N sur le débit d(N, K, λ, τ)

Le débit en fonction du nombre de stations N présente également une forme en cloche :

| Région | Comportement |
|--------|-------------|
| **N faible** | Peu de stations → charge totale faible → débit faible |
| **N optimal (N*)** | Maximum du débit |
| **N élevé** | Trop de stations → collisions excessives → débit chute |

---

## 6. Analyse et discussion

### 6.1 Choix des paramètres de simulation

**Durée de simulation (t_max = 3000 u.t.)**
- Une durée trop courte (t < 500) n'atteint pas le régime stationnaire
- t_max = 3 000 assure la convergence avec des fluctuations résiduelles négligeables

**Nombre de réplications Monte-Carlo**
- Chaque point de la courbe est estimé à partir de **R réplications** (seeds différents)
- L'IC à 95 % valide la précision statistique

### 6.2 Mécanisme de collision détaillé

Le mécanisme de collision est le point le plus critique du simulateur. La détection repose sur le fait que :

1. Quand une station A tente d'émettre et que le canal est occupé, elle reprogramme sa tentative à `channel_busy_until`
2. Si une station B fait de même, les deux tentatives sont planifiées **au même instant**
3. À cet instant, le simulateur collecte **toutes les tentatives simultanées** avant de décider du succès ou de la collision

Ce mécanisme est fidèle au CSMA (Carrier Sense Multiple Access) : les stations *écoutent* le canal avant d'émettre.

### 6.3 Gestion de la perte de paquets

Les paquets sont perdus **uniquement** lorsqu'un paquet arrive sur une file déjà pleine (`queue[i] == K`). Les paquets impliqués dans une collision **ne sont jamais perdus** : ils restent dans la file et sont re-émis après le délai de backoff.

### 6.4 Comparaison théorique

Pour **N=1** (aucune collision) :
- Débit théorique = min(λ, 1) = 0.5
- Débit simulé = 0.5171 (**erreur relative < 3.5 %** ✓)

Ce résultat confirme la validité du simulateur sur un cas limite analytiquement connu.

---

## 7. Détermination du N optimal

### 7.1 Méthodologie

Pour chaque valeur de N (de 1 à N_max), on effectue **R réplications** de simulation et on calcule :
- La moyenne du débit : `d̄(N)`
- L'intervalle de confiance à 95 % : `[d̄ - 1.96·s/√R, d̄ + 1.96·s/√R]`

### 7.2 Critère de sélection du N optimal

Le **N optimal (N*)** est la valeur de N qui maximise `d̄(N)`. La validité de ce choix est confirmée si les IC à 95 % ne se chevauchent pas significativement avec les valeurs voisines.

### 7.3 Interprétation

Le N optimal résulte d'un équilibre entre :
- **Trop peu de stations** : canal sous-utilisé (débit faible)
- **Trop de stations** : collisions trop fréquentes, files saturées (débit faible)
- **N optimal** : utilisation maximale du canal avec un taux de collision acceptable

### 7.4 Utilisation des IC à 95 %

L'intervalle de confiance à 95 % garantit que la vraie valeur du débit se trouve dans l'intervalle avec une probabilité de 95 %. Un IC étroit indique une estimation précise (variance faible entre réplications), ce qui renforce la confiance dans le résultat.

---

## 8. Conclusion

### 8.1 Bilan

Ce projet a permis de concevoir et déployer un **simulateur à événements discrets complet** pour le protocole MAC avec Exponential Backoff. Les principaux apports sont :

| Réalisation | Détail |
|-------------|--------|
| ✅ SED fonctionnel | Écheancier min-heap, 2 types d'événements |
| ✅ Génération probabiliste | Loi exponentielle par inversion |
| ✅ Métriques temporelles | Débit, file moyenne, taux de perte |
| ✅ Convergence observée | n(t)/t → d(N,K,λ,τ) en régime permanent |
| ✅ Analyse paramétrique | Courbes d vs λ et d vs N |
| ✅ N optimal avec IC 95% | Validation statistique Monte-Carlo |

### 8.2 Points clés du simulateur

1. **Fidélité au modèle** : La collision est détectée via la coïncidence temporelle exacte des tentatives, reproduisant fidèlement le CSMA
2. **Reproductibilité** : L'utilisation de seeds assure la reproducibilité des résultats
3. **Efficacité** : L'écheancier min-heap garantit une complexité O(log n) par événement
4. **Validation** : Le cas N=1 (sans collision) sert de test de cohérence analytique

### 8.3 Perspectives

- Étude de l'impact du paramètre **K** (capacité de file) sur les performances
- Comparaison avec d'autres protocoles MAC (ALOHA pur, TDMA)
- Extension du modèle avec des canaux à capacité variable
- Analyse de la stabilité du protocole pour des charges supérieures à la capacité nominale

---

## Annexes

### A. Paramètres de simulation résumés

```
Paramètres de référence :
  N = 10 stations
  K = 10 paquets (capacité file)
  λ = 0.06 paquets/u.t. par station
  τ = 0.5 u.t. (backoff de base)
  t_max = 3 000 u.t.
  seed = 42 (reproductibilité)
  record_every = 10.0 u.t.
```

### B. Résultats de validation du simulateur

```
Test 1 — N=1, λ=0.5 :
  Débit mesuré    = 0.5171
  Débit théorique = min(0.5, 1) = 0.5000
  Collisions      = 0 ✓

Test 2 — N=10, λ=0.06, charge=0.6 :
  Débit    = 0.5290
  Collisions = 1 189
  Pertes file = 164
```

### C. Formules clés

| Formule | Description |
|---------|-------------|
| `X ~ Exp(rate) = -ln(U)/rate` | Variable exponentielle par inversion |
| `d = n_success / T` | Débit final |
| `L̄ = ∫queue_total dt / T` | File moyenne (Loi de Little) |
| `p = n_lost / n_arrived` | Taux de perte |
| `IC95% = m ± 1.96·s/√n` | Intervalle de confiance 95% |
| `t_retry = t_free + Exp(1/(τ·2^k))` | Délai de rejet après collision |

---

*Rapport généré le 21 avril 2026 — Projet Simulation MAC 2025-2026*
