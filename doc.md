# madmp-core — les choix de conception

*Document interne SOCIB / OSTrails. Le `README.md` dit **ce que fait** le dépôt
et **comment s'en servir** ; ce document dit **pourquoi il est fait comme ça**.
Les commentaires du code, eux, n'expliquent que le code — tout ce qui relève
d'une décision, d'une alternative écartée ou d'une contrainte historique vit
ici.*

*Le dépôt se construit une tranche à la fois, et ce document avec lui : une
section arrive avec le code qu'elle justifie. La numérotation est celle du plan
d'ensemble, donc les numéros ne bougeront pas quand les sections manquantes
arriveront — mais la table des matières ne liste que ce qui existe.*

---

## Table des matières

1. [Le principe](#1-le-principe)
2. [Le format des règles](#2-le-format-des-règles)
14. [Limites connues](#14-limites-connues)

---

## 1. Le principe

> Une règle ajoutée dans un fichier JSON devient une question DSW *et* un
> contrôle qualité, sans code et sans possibilité de dérive.

Tout le dépôt découle de cette phrase. Un jeu de règles déclaratives (RDA DMP
Common Standard + OSTrails Application Profile + extensions SOCIB) est la seule
source de vérité ; les programmes qui suivent en dérivent mécaniquement le
questionnaire, le rendu du document, la baseline pré-remplie et la validation.

Deux mécanismes rendront la promesse **structurelle** plutôt que disciplinaire
— c'est-à-dire qu'on ne pourra pas la violer par inattention : la convention
d'UUID déterministe, qui interdit à un template de référencer une question que
son KM n'a pas, et le point de décision unique, qui interdit à deux générateurs
de diverger sur un cas limite. Chacun sera documenté par la tranche qui
l'apporte.

Le reste — la fusion stricte, la validation au chargement, le report exhaustif
des erreurs — sert à ce que les données de règles restent éditables par
quelqu'un qui ne lit pas Python, sans que la moindre faute de frappe passe.

---

## 2. Le format des règles

Chaque `rules/standards/<standard>/<version>.json` déclare son nom de standard,
sa version, s'il `extends` la base, et un arbre récursif de champs sous `dmp`.

### Deux faits orthogonaux par champ

- `_cardinality` dit **combien** : `1` et `0..1` (valeur simple), `1..n` et
  `0..n` (liste) ;
- `_type` dit **ce qu'est chaque valeur** : `object`, ou un format scalaire
  (`string`, `date`, `datetime`, `email`, `url`, `currency`, `language`,
  `country_code`, `number`, `boolean`).

**Il n'y a volontairement pas de type `list`.** La list-ness est entièrement
portée par la cardinalité. Un type `list` créerait deux façons d'exprimer la même
chose, donc deux façons pour un fichier d'en contredire un autre — et il faudrait
arbitrer, à la fusion, entre `_type: list` et `_cardinality: 0..n`. Séparer
« combien » de « quoi » supprime la question.

### Vocabulaires : stricts et suggérés

- `_allowed_values` — vocabulaire fermé, une violation est un **FAIL** ;
- `_suggested_values` — recommandation, un écart est un **WARNING** seulement.

La distinction n'est pas cosmétique : elle traverse toute la chaîne. Côté DSW,
un vocabulaire strict devient une `OptionsQuestion` sans échappatoire, un
vocabulaire suggéré une `OptionsQuestion` plus une réponse « Other » ouvrant un
champ libre. Côté QC, l'un fait échouer, l'autre avertit.

Les `_suggested_values` de SOCIB listent ce qui a été *observé* dans les
`data_flow.json` des instruments et dans les DMP produits aujourd'hui. Ils sont
non-stricts exprès : le vocabulaire réel grandira avec les instruments et les
productions.

### Un standard n'a qu'une orthographe, et c'est du snake_case

`standard` est un **identifiant de code** : `rda_dcs`, `ostrails`, `socib`. Le
schéma l'impose (`^[a-z][a-z0-9_]*$`), et c'est exactement, au caractère près,
le nom du répertoire où le fichier vit **et** ce qu'un pin de config écrit :

```yaml
rules:
  - rda_dcs: "1.0.0"
```

**Ce qu'un lecteur voit est dérivé, jamais déclaré.** Les tags DSW, les
messages et le rapport du contrôle qualité affichent la forme majuscule
(`RDA_DCS`), obtenue mécaniquement au moment de l'affichage. Il n'y a donc
aucun second champ à tenir accordé au premier.

L'alternative — déclarer le nom humain (`"RDA DCS"`) et en dériver le
répertoire par un slug — a été essayée puis abandonnée. Elle marche, mais elle
fait vivre deux espaces de noms reliés par une transformation qui n'est
inversible que dans un sens : `RDA DCS` → `rda_dcs` se calcule, l'inverse
non (`.title()` ne rend ni `OSTrails` ni `SOCIB`). Et surtout elle laissait un
trou : l'unicité des standards se vérifiait sur le **nom déclaré** pendant que
le rangement se vérifiait sur le **slug**, si bien que `"RDA DCS"` et
`"RDA_DCS"` — deux noms « uniques » — tombaient dans le même répertoire et
pouvaient être fusionnés comme deux standards distincts. Avec une seule
orthographe, ce trou n'existe pas : unicité et rangement parlent de la même
chaîne.

Le prix, assumé : l'affichage n'est pas curé. `OSTrails` s'affiche `OSTRAILS`.
C'est le bon prix, parce qu'il rend la règle **lisible** — un lecteur qui voit
`RDA_DCS` et `OSTRAILS` côte à côte comprend qu'il regarde des identifiants mis
en majuscules, là où `RDA DCS` à côté de `OSTRAILS` laisserait croire à des
libellés choisis un par un.

### Un fichier déclare le standard et la version de son chemin

Le chargement vérifie que les deux champs requis s'accordent avec le chemin :
le répertoire porte le `standard`, le nom de fichier porte la `version`. Ce
sont deux espaces de noms qu'il faut tenir accordés, et rien d'autre ne les
tient. Sans le premier contrôle, un répertoire périmé fait nommer par la
provenance un standard que personne n'a sélectionné. Sans le second,
`cp 1.0.0.json 1.1.0.json` produit une nouvelle version au contenu identique,
sans un mot ; le job `rules` sort aujourd'hui `declares version '1.0.0' but is
named '1.1.0'`.

**Pourquoi dans le chargement et pas à côté.** Un contrôle qu'un appelant doit
penser à invoquer est un contrôle qu'on oublie : `scripts/validate_rules.py` y
penserait, le prochain appelant non. Le prix est assumé — un fichier de règles
ne se charge que depuis `<standard>/<version>.json`, y compris dans les tests,
qui écrivent donc dans une arborescence plutôt qu'à plat.

`version` n'a **pas** de motif dans le schéma : la vraie contrainte est
l'égalité avec le nom de fichier, et un motif semver refuserait des
versionnages qu'on n'a pas rencontrés.

### Validation en trois couches, au chargement

Un fichier malformé doit échouer **à la porte**, pas au fond d'un consommateur.
`load_rules_file` est la seule entrée, et elle valide trois fois :

1. **Structurelle** — validation contre `rules/rules.schema.json` : clés
   requises, énumérations fermées de `_cardinality`/`_type`, aucune métadonnée
   inconnue, noms de champs en snake_case. La syntaxe JSON elle-même est
   comprise dedans : une virgule en trop ressort en `RulesFileError`, pas en
   `json.JSONDecodeError`, pour qu'un seul type d'exception couvre toutes les
   façons dont un fichier de règles peut être faux.
2. **Cohérence** — trois contraintes tenues hors du schéma :
   - seuls les champs `_type: "object"` peuvent déclarer des enfants ;
   - `_allowed_values`/`_suggested_values` ne peuvent apparaître que sur des
     scalaires (un vocabulaire contraint *chaque valeur*, et un objet n'est pas
     une valeur qu'on compare à une chaîne) ;
   - `_chapter_description` ne peut apparaître que sur un champ objet de
     **premier niveau**, le seul qui devienne un chapitre DSW. Ailleurs, les
     générateurs l'ignorent sans un mot.
3. **Rangement** — le fichier déclare le standard et la version que son chemin
   nomme (ci-dessus).

**Pourquoi la cohérence n'est pas dans le schéma.** Non pas parce que JSON
Schema ne saurait pas l'exprimer : `if`/`then` et une définition séparée pour
les champs de premier niveau y arrivent. Ce qu'il ne sait pas faire, c'est dire
*quel* champ est en cause et quoi écrire à la place — il produit `'object'
should not be valid under {'const': 'object'}`. C'est la seule raison qu'elles
soient en Python, et elle laisse la porte ouverte à rejuger.

Les couches 2 et 3 ne tournent que sur un document déjà valide
structurellement, et ce n'est pas qu'une question de bruit après les vraies
erreurs : elles lisent `standard`, `version` et `dmp` **sans garde**, ce qui
n'est sûr que parce que la passe schéma vient de garantir que ces clés existent
et sont du bon type. Inverser l'ordre ne rendrait pas les messages plus
bavards, ça lèverait un `KeyError`.

Trois trous du schéma ont été fermés au passage : un vocabulaire acceptait un
**doublon** (`["rt", "rt"]`, le plus sournois — la fusion compare les
vocabulaires avec `set()`, donc il passait sans bruit et ressortait en double
dans les options DSW) et une **chaîne vide** ; et `dmp: {}` était accepté, un
fichier de règles qui ne contraint rien.

### Tout signaler d'un coup

Le chargement **collecte l'intégralité des problèmes et lève une seule fois** :
une tentative de chargement = une liste de corrections complète. C'est un choix
d'ergonomie assumé, et il vaut pour les trois couches — un fichier à la fois mal
rangé et mal versionné remonte ses deux problèmes ensemble.

La règle a **une seule implémentation**, `utils/errors.ProblemsError` : une
liste de problèmes, un sujet facultatif, un nom de classe. Toute erreur du dépôt
qui porte une liste de problèmes en hérite. Ce n'est pas une factorisation de
mise en forme : c'est la même règle de conception, qui était écrite plusieurs
fois et rendait donc possible qu'un appelant l'applique à moitié.

Une erreur qui n'est **pas** une liste de problèmes n'entre pas dans cette
hiérarchie et ne doit pas y être forcée.

### Les `description` des fichiers de règles sont inertes

Le modèle ne les porte pas ; elles n'atteignent aucun artefact publié. Elles
restent néanmoins la première chose que lit quelqu'un qui ouvre un standard pour
l'éditer — c'est leur seule fonction, et elle suffit à justifier qu'on les tienne
à jour.

---

## 14. Limites connues

### La roue n'embarque aucun fichier de données

`[tool.setuptools.packages.find]` déclare les paquets, mais setuptools
n'embarque que les `.py` tant que le reste n'est pas déclaré à part. Une roue
construite depuis une copie vierge, sans cache, ne contient donc **aucun
JSON** : elle s'importe, puis meurt au premier appel réel sur
`FileNotFoundError: .../site-packages/rules/rules.schema.json`.

**Latent, pas actif :** rien ici ne consomme de roue aujourd'hui. Ça mordra le
jour où on conteneurise, où on publie sur un index, ou où on installe depuis
git sans `-e`. Le correctif tient en deux lignes
(`[tool.setuptools.package-data]`, avec un glob par niveau de répertoire car
ils ne les traversent pas), mais il se décide à la tranche où un consommateur
de la roue existe — c'est là qu'on saura si la roue est la bonne unité de
distribution.

**Deux pièges pour qui vérifiera**, tous deux donnant un faux succès :
setuptools **ne nettoie jamais `build/`** entre deux constructions, donc des
fichiers d'un empaquetage antérieur survivent dans les roues suivantes ; et
`uv build` sans `--no-cache` rend une roue antérieure au changement.

### Le format des fichiers JSON n'est pas vérifié

`ruff format` ne touche pas au JSON, donc rien en CI ne contrôle la mise en
forme de `rules/standards/*.json` — seulement leur contenu, via
`scripts/validate_rules.py`.

**Pourquoi on n'ajoute pas `prettier --check` :** il faudrait Node dans une CI
purement Python — donc un `package.json`, un lockfile npm et un cache, un
deuxième système de dépendances. La version `npx --yes` l'évite mais tire une
version non épinglée à chaque run, ce qui réintroduit exactement le problème
que `uv sync --frozen` règle. Le coût est réel, l'enjeu est cosmétique.

**Déclencheur pour rejuger :** quelqu'un d'autre que Pierre édite les fichiers
de règles, ou un diff de règle devient pénible à relire à cause du bruit de
format. À ce moment-là, un `.prettierrc` versionné (trois lignes, zéro seconde
de CI) répond au premier cas ; le check CI ne se justifie que si le format
dérive vraiment malgré ça.
