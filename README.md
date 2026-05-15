# Projet MAC - Simulation du protocole Medium Access Control

Ce depot contient une simulation Python du protocole MAC (*Medium Access Control*) avec mecanisme d'**Exponential Backoff**. Le programme principal est le notebook Jupyter [projet_MAC.ipynb](./projet_MAC.ipynb).

L'objectif du projet est d'etudier, par simulation a evenements discrets, le comportement d'un canal partage par plusieurs stations : debit, collisions, files d'attente, pertes de paquets et nombre optimal de stations.

## Structure du projet

```text
.
|-- projet_MAC.ipynb              # Programme principal : simulation, experiences et graphes
|-- Rapport_simulation_uvsq.pdf   # Rapport final au format PDF
|-- plot_temporal.png             # Evolution temporelle des metriques
|-- plot_debit_vs_lambda.png      # Debit en fonction de lambda
|-- plot_debit_vs_N.png           # Debit en fonction du nombre de stations N
|-- plot_N_optimal.png            # Recherche du N optimal avec IC a 95 %


## Organisation generale de `projet_MAC.ipynb`

Le notebook est organise en plusieurs parties.

1. **Imports et fonctions utilitaires**

   Cette partie charge les bibliotheques necessaires :
   `heapq`, `random`, `math`, `numpy` et `matplotlib`.

   Elle definit aussi :
   - `exp_rv(rate, rng=None)` : generation d'une variable aleatoire exponentielle par inversion ;
   - `moyenne(vals)` : calcul d'une moyenne empirique ;
   - `ic95(vals)` : calcul d'un intervalle de confiance a 95 % pour les simulations Monte-Carlo.

2. **Simulateur a Evenements Discrets**

   Le coeur du programme est la fonction :

   ```python
   simulate_mac(N, K, lam, tau, t_max, seed=42, record_every=10.0)
   ```

   Elle simule un systeme avec :
   - `N` stations ;
   - une file d'attente de capacite `K` par station ;
   - des arrivees de paquets selon un processus de Poisson de taux `lam` par station ;
   - un backoff exponentiel controle par `tau` ;
   - une duree totale de simulation `t_max`.

   Le simulateur repose sur un echeancier gere par une file de priorite (`heapq`). Deux types d'evenements sont utilises :
   - `ARRIVAL` : arrivee d'un paquet dans une station ;
   - `ATTEMPT` : tentative d'emission d'une station sur le canal.

   Les collisions sont detectees lorsque plusieurs stations tentent d'emettre au meme instant. Les paquets en collision ne sont pas supprimes : ils restent en file et sont retransmis apres un delai de backoff. Les seules pertes definitives arrivent lorsque la file d'une station est pleine au moment de l'arrivee d'un nouveau paquet.

3. **Evolution temporelle des metriques**

   Cette section execute une simulation de base, puis trace :
   - le debit `n(t)/t` ;
   - le nombre moyen de clients dans le systeme ;
   - le taux de perte.

   La figure generee est sauvegardee dans `plot_temporal.png`.

4. **Debit en fonction de `lambda`**

   Le notebook fait varier le taux d'arrivee `lambda` et estime le debit moyen pour chaque valeur. Chaque point correspond a plusieurs simulations independantes, avec un intervalle de confiance a 95 %.

   La figure generee est `plot_debit_vs_lambda.png`.

5. **Debit en fonction de `N`**

   Cette partie etudie l'effet du nombre de stations sur le debit. Le programme lance plusieurs simulations pour differentes valeurs de `N`, puis compare le debit obtenu avec la charge theorique `N * lambda`.

   La figure generee est `plot_debit_vs_N.png`.

6. **Determination du `N` optimal**

   Cette section recherche le nombre de stations qui maximise le debit. Elle utilise davantage de repetitions Monte-Carlo afin d'obtenir des intervalles de confiance plus precis.

   La figure generee est `plot_N_optimal.png`.

7. **Conclusion**

   La derniere partie resume les resultats, les choix de modelisation et les hypotheses du simulateur.

## Utilisation

### 1. Installer les dependances

Le projet utilise principalement Python, Jupyter, NumPy et Matplotlib.

Depuis la racine du projet :

```bash
pip install notebook numpy matplotlib
```

Si l'environnement virtuel `.venv` existe deja, il est preferable de l'activer avant d'installer ou d'executer le notebook.

### 2. Lancer Jupyter

```bash
jupyter notebook
```

Ouvrir ensuite le fichier :

```text
projet_MAC.ipynb
```

### 3. Executer le notebook

Dans Jupyter, executer les cellules dans l'ordre, du haut vers le bas.

Les premieres cellules definissent les fonctions necessaires. Les sections suivantes lancent les experiences et sauvegardent les graphes au format PNG dans le dossier du projet.

## Sorties principales

La fonction `simulate_mac` retourne un dictionnaire contenant notamment :

| Cle | Description |
| --- | --- |
| `times` | Instants d'enregistrement des metriques |
| `throughput` | Evolution temporelle du debit |
| `queue_avg` | Evolution de la taille moyenne des files |
| `loss_rate` | Evolution du taux de perte |
| `throughput_final` | Debit final estime |
| `mean_queue_final` | Nombre moyen final de paquets en file |
| `loss_rate_final` | Taux de perte final |
| `n_success` | Nombre de transmissions reussies |
| `n_collision` | Nombre de collisions detectees |
| `n_lost_full` | Nombre de paquets perdus car file pleine |
| `n_arrived` | Nombre total de paquets arrives |

Exemple d'appel :

```python
res = simulate_mac(
    N=10,
    K=10,
    lam=0.06,
    tau=0.5,
    t_max=3000,
    seed=42,
    record_every=5.0,
)

print(res["throughput_final"])
```

## Parametres importants

| Parametre | Role |
| --- | --- |
| `N` | Nombre de stations partageant le canal |
| `K` | Capacite maximale de la file d'attente de chaque station |
| `lam` | Taux d'arrivee des paquets par station |
| `tau` | Parametre de base du backoff exponentiel |
| `t_max` | Duree totale de la simulation |
| `seed` | Graine aleatoire pour rendre les resultats reproductibles |
| `record_every` | Pas d'enregistrement des series temporelles |

## Remarques

- Les resultats sont aleatoires : ils peuvent varier legerement selon la graine et le nombre de repetitions.
- Pour obtenir des intervalles de confiance plus stables, augmenter le nombre de runs Monte-Carlo.
- Pour reduire le temps d'execution, diminuer `t_max`, le nombre de valeurs testees ou le nombre de repetitions.
- Les fichiers `plot_*.png` peuvent etre regeneres automatiquement en reexecutant le notebook.
