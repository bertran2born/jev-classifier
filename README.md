# Audit des PDF avec Jev

## Visualiser les résultats

La page `index.html` fournit recherche, filtres, tri des neuf critères, tri par
probabilité du critère exploré, pagination, répartitions, fiches détaillées et
export de la sélection en CSV. Elle fonctionne sans dépendance JavaScript ni
clé API et n’envoie pas les données à un service externe.

Depuis ce dossier, lancer le serveur local puis ouvrir <http://localhost:8000> :

```sh
nix develop path:. -c python -m http.server 8000 --bind 127.0.0.1
```

La page recherche successivement `jev-audit-results/results.csv`, `results.csv`,
puis `jev-audit-api-check/results.csv`. Cliquer sur **Actualiser** après une
nouvelle analyse. Pour un autre dossier de sortie, utiliser **Importer un CSV**
ou glisser-déposer le fichier. L’import remplace le fichier courant, sans fusion.
Le bouton Actualiser recharge les chemins par défaut ; pour actualiser un fichier
importé manuellement, l’importer à nouveau.

On peut aussi ouvrir `index.html` directement dans le navigateur et importer
le CSV manuellement. Le serveur local permet en plus le chargement automatique
et l’ouverture des PDF et des extraits conservés dans les dossiers du projet.

**À relire** signifie : une alerte du script, une erreur d’extraction, une
classification inconnue/manquante ou au moins une probabilité inférieure au seuil
réglable (80 % par défaut). Les compteurs portent sur tout le fichier ; le tableau
et la répartition suivent les filtres. Les extractions seules (`dry_run`) ne sont
pas considérées comme des classifications incertaines. Une absence d’alerte ne
constitue pas une validation scientifique.

## Exécuter l’audit

Le flake fournit Python 3.13, PyMuPDF, Requests et la commande
`jev-pdf-audit`. Nix gère les dépendances, sans installation par pip.

Depuis ce dossier, vérifier l'extraction sur trois études, sans clé ni appel API :

```sh
nix develop path:. -c python jev_pdf_audit.py pdfs --dry-run --limit 3 --out jev-audit-check
```

Exécuter les tests locaux (PDF de test générés et réponses API simulées) :

```sh
nix develop path:. -c python -m unittest discover -s tests -v
# Ou construire l'environnement et exécuter les tests dans le bac à sable Nix :
nix flake check path:.
```

Pour classer 50 études, saisir la clé sans l'inscrire dans l'historique
(commandes pour zsh, le shell utilisé ici) :

```sh
read -rs 'TYPESAFE_API_KEY?Clé API TypeSafe : '; echo
export TYPESAFE_API_KEY
nix run path:. -- pdfs --limit 50 --workers 4
unset TYPESAFE_API_KEY
```

Autre possibilité : `nix develop path:. -c python jev_pdf_audit.py pdfs --limit 50`.
Le fichier `flake.lock` fige les versions des dépendances. Les commandes utilisent
`path:.` pour fonctionner également dans un dossier sans dépôt Git initialisé.

`--limit 50` sélectionne les 50 premiers chemins triés, sans tirage aléatoire,
et inclut les études déjà traitées dans cette limite. Relancer la même commande
reprend les résultats valides si les fichiers, la version du schéma et les
paramètres d'extraction sont identiques. Les erreurs seront retentées.

Les résultats sont enregistrés dans `jev-audit-results/results.csv` et
`results.jsonl`, avec les extraits dans `excerpts/`. Le mode `--dry-run`
écrit `dry-run.csv` et `dry-run.jsonl` et conserve les classifications existantes.
Une erreur de traitement produit un code de sortie 1, une interruption 130.
Les statuts `needs_ocr` et `needs_review` signalent les documents à vérifier.

Le script classe neuf dimensions : domaine, soutien à l'hypothèse scientifique
explicite, significativité, préenregistrement, chronologie des choix analytiques,
tests multiples, robustesse, exclusions et interprétation. Il ne définit pas de
catégorie de sensibilité idéologique et ne calcule pas d'association entre
résultats et choix statistiques à l'échelle du corpus. Les classifications
portent sur des extraits sélectionnés (100 pages et 22 000 caractères maximum
par défaut), sans OCR. Les probabilités concernent les étiquettes proposées,
pas la probabilité de p-hacking ou d'une intention idéologique.

Le format de requête et de réponse est décrit dans la
[documentation officielle TypeSafe](https://docs.typesafe.ai/api/system-one).
Sans clé API, les tests vérifient les échanges simulés mais pas l'authentification
réelle ni la qualité des classifications de Jev.
