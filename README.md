# Audit des PDF avec Jev

## Démarrage simple sous Windows (recommandé : uv)

Installer [uv](https://docs.astral.sh/uv/getting-started/installation/) une fois,
dans PowerShell :

```powershell
winget install --id astral-sh.uv -e
```

Fermer puis rouvrir PowerShell après l’installation. Télécharger le dépôt avec
**Code → Download ZIP** sur [GitHub](https://github.com/bertran2born/jev-classifier),
extraire l’archive, puis ouvrir PowerShell dans le dossier extrait. Si Git est
déjà installé, on peut utiliser à la place :

```powershell
git clone https://github.com/bertran2born/jev-classifier.git
cd jev-classifier
```

Ouvrir le site en une commande (ou double-cliquer sur `ouvrir-site.cmd`) :

```powershell
uv run jev.py
```

uv installe automatiquement Python 3.13 et les dépendances nécessaires si elles
manquent. Les versions des bibliothèques sont figées dans `uv.lock`. Le premier
lancement nécessite une connexion pour télécharger les composants. Il n’y a ni
environnement à activer manuellement, ni installation de Nix ou de Docker.
Le navigateur s’ouvre sur le serveur local ; garder le terminal ouvert et
utiliser Ctrl+C pour arrêter. Si le port est occupé : `uv run jev.py --port 8001`.

Créer un dossier `pdfs` dans le projet et y copier les études. Pour retrouver
sur Windows les résultats déjà calculés sur un autre ordinateur, copier aussi
le dossier `jev-audit-results` : ces données ne sont pas présentes sur GitHub.
Les liens vers les PDF et extraits utilisent les sous-dossiers locaux du projet.

Dans un **deuxième terminal**, lancer l’analyse de tous les PDF :

```powershell
uv run jev.py audit
```

La clé API est demandée en saisie masquée et reste en mémoire pour cette
exécution. Si `TYPESAFE_API_KEY` est déjà définie dans l’environnement, elle est
utilisée directement. Le lanceur ne lit pas de fichier `.env`.

Autres commandes :

```powershell
# Extraction de trois PDF, sans appel API ni clé
uv run jev.py audit --dry-run --limit 3

# Classer les 50 premiers PDF
uv run jev.py audit --limit 50

# Relancer les classifications après modification des critères
uv run jev.py audit --force

# Utiliser un autre dossier de PDF
uv run jev.py audit "C:\Mes etudes\pdfs" --limit 50

# Tests Python, avec des réponses API simulées
uv run python -m unittest discover -s tests -v
```

Pour modifier l’interface, éditer `index.html`, `viewer.css` ou `viewer.js`, puis
recharger la page : aucun build ni redémarrage du serveur n’est nécessaire.
Le bouton **Actualiser** recharge les résultats CSV. Le tri et la recherche dans
le site ne font aucun appel API.

Pour modifier la classification, éditer `jev_pdf_audit.py`, notamment
`QUESTIONS`, puis relancer `audit`. Utiliser **`--force`** pour remplacer les
résultats déjà calculés : cette option entraîne de nouveaux appels API payants.
Sans cette option, les résultats compatibles sont repris. Après une modification
du code Python, il faut relancer la commande pour qu’elle soit prise en compte.

Si le dépôt a été cloné, `git pull --ff-only` récupère les mises à jour lorsque
les modifications locales le permettent. Les PDF et résultats restent locaux.
Le lanceur fonctionne également sur macOS et Linux ; sous NixOS, utiliser le
flake présenté ci-dessous pour les dépendances natives.

### Pourquoi uv plutôt que Docker ici ?

Pour cet outil Python avec une interface HTML locale, uv permet de modifier
directement les fichiers et de lancer le projet sans machine virtuelle Linux.
Docker reste pertinent pour déployer un service ou si Docker Desktop est déjà
installé, mais impose une installation et une gestion des volumes supplémentaires
sur Windows. Aucun conteneur n’est nécessaire pour les commandes ci-dessus.
Voir les documentations officielles de
[uv](https://docs.astral.sh/uv/guides/scripts/) et de
[Docker Desktop sous Windows](https://docs.docker.com/desktop/setup/install/windows-install/).

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
L’option `--force` désactive cette reprise, notamment après modification de
`QUESTIONS`, et remplace la ligne courante de chaque étude dans le CSV tout en
conservant l’historique des exécutions dans `results.jsonl`.

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
