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
3. [La fusion « tighten-only »](#3-la-fusion--tighten-only-)
14. [Limites connues](#14-limites-connues)

---

## 1. Le principe

> Une règle ajoutée dans un fichier JSON devient une question DSW *et* un
> contrôle qualité, sans code et sans possibilité de dérive.

Tout le dépôt découle de cette phrase. Un jeu de règles déclaratives (RDA DMP
Common Standard + OSTrails Application Profile) est la seule source de vérité ;
les programmes qui suivent en dérivent mécaniquement le questionnaire, le rendu
du document, la baseline pré-remplie et la validation.

Deux mécanismes rendront la promesse **structurelle** plutôt que disciplinaire
— c'est-à-dire qu'on ne pourra pas la violer par inattention : la convention
d'UUID déterministe, qui interdit à un template de référencer une question que
son KM n'a pas, et le point de décision unique, qui interdit à deux générateurs
de diverger sur un cas limite. Chacun sera documenté par la tranche qui
l'apporte.

Le reste — la fusion stricte, la validation au chargement, le report exhaustif
des erreurs — sert à ce que les données de règles restent éditables par
quelqu'un qui ne lit pas Python, sans que la moindre faute de frappe passe.

### L'unité de déploiement, c'est le fichier de config

Un `configs/projects/<id>.yaml` porte **tout** ce qui définit un projet : ses
propres faits, les versions de règles qu'il épingle, et ce que les paquets DSW
générés annoncent. De lui seul découleront un Knowledge Model, un Document
Template, une baseline, une route de soumission et un dossier de registre.

Conséquence voulue : un projet ne bouge **que** si son propre fichier change et
que sa `version` est incrémentée. Rien n'est partagé à l'exécution, rien ne
dérive dans le dos d'un projet parce qu'un autre a été modifié.

Le fichier se lit de haut en bas en trois blocs — le projet, ses règles, DSW —
et l'ordre n'est pas décoratif : il va du plus stable au plus éditorial. Il n'y
a **pas** de bloc `instruments` : le concept est parti avec le standard `socib`,
et un champ dont le lecteur a disparu vaut moins que son absence. Le schéma
étant fermé, une config qui en épingle encore un est refusée au chargement
plutôt qu'ignorée en silence.

### Le schéma de config décrit un projet complet, pas ce que le code lit

À ce stade, le code ne lit que trois champs : `id` et `version` pour rendre
compte, `rules` pour résoudre les épingles. Les sept autres — `name`, `author`,
`license`, `organizationId`, `description`, `references`, `auto_timestamps` —
n'ont aucun lecteur, et sont pourtant tous `required`. C'est délibéré, et ça
n'est **pas** une entorse à la règle « les dépendances se gagnent » : celle-ci
porte sur ce que le code importe, pas sur ce qu'une donnée déclare.

Un schéma de config est un contrat avec **l'auteur du fichier**, pas avec le
programme. Il dit à un humain ce qu'il faut écrire pour qu'un projet soit
complet, et cette liste est connue d'avance : chacun des sept est consommé par
la génération DSW, une tranche plus loin. Les rendre optionnels aujourd'hui
pour les remettre `required` demain obligerait à repasser sur chaque config,
pour n'avoir rien vérifié entre-temps.

La distinction avec `instruments` tient donc en un mot : là, le lecteur avait
disparu ; ici, il est daté. Un champ dont personne n'aura besoin ne s'écrit
pas ; un champ dont le lecteur arrive à la tranche suivante s'exige tout de
suite, sinon les données arrivent en retard sur le code qui les attend.

### Un projet a un nom machine et un nom humain, et rien entre les deux

`id` est le **seul** identifiant. C'est le nom du fichier, le nom du dossier de
destination dans le registre (donc la clé de routage `?project=`), et ce dont
héritent le KM, le template, la seed et le projet DSW. Le motif
`^[a-z0-9-]{1,64}$` l'impose, pour que ces noms ne dépendent jamais de la façon
dont il a été tapé.

**Trois identifiants nommaient le même projet**, et deux d'entre eux le
nommaient avec deux chaînes différentes : `id: socib-glider` d'un côté,
`github.folder: glider` de l'autre, plus le nom du fichier. Les fondre supprime
la question « lequel des deux ce générateur-ci utilise-t-il ? ». Il reste une
redondance, inévitable puisqu'un fichier a forcément un nom : le loader la
vérifie, sinon renommer une config publierait le projet ailleurs, sans un mot.

`name` est l'exception à la règle du §2 — *ce qu'un lecteur voit est dérivé,
jamais déclaré* — et l'exception est raisonnée. Pour un standard, la forme
affichable est une fonction **totale** de l'identifiant : mettre en majuscules
marche toujours. Pour un projet, non : `socib-hf-radar` donnerait
`Socib Hf Radar`, et la liste des cas qu'une règle mécanique raterait n'est pas
bornée — sigles, accents, majuscules internes. Une dérivation qu'on doit
pouvoir contourner rend le champ de contournement obligatoire ; autant déclarer
le nom directement.

Ce qui protège de la dérive, ce n'est donc pas ici la dérivation, c'est le
**périmètre** : `name` ne nomme rien. Aucun identifiant, aucun chemin, aucun
paquet n'en dépend, et il peut changer à chaque version sans qu'une seule
référence bouge. C'est du texte, et le schéma n'en exige que d'être non vide.

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

### Un standard n'a qu'une orthographe, et c'est du snake_case

`standard` est un **identifiant de code** : `rda_dcs`, `ostrails`. Le
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
non (`.title()` ne rend pas `OSTrails`). Et surtout elle laissait un
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

## 3. La fusion « tighten-only »

Exactement un fichier est la base (`extends: false`). Les extensions peuvent
redéclarer un champ que la base définit déjà, dans deux cas seulement :

- **à l'identique** — le cas courant : répéter un parent structurel uniquement
  pour atteindre ses propres feuilles en dessous ;
- **en resserrant** — rendre obligatoire un champ optionnel (`0..1 -> 1`,
  `0..n -> 1..n`), restreindre un vocabulaire à un sous-ensemble, ou fermer un
  champ ouvert avec un vocabulaire à soi.

Elles ne peuvent **jamais** relâcher ni reformer : affaiblir une cardinalité,
transformer une valeur simple en liste (ou l'inverse), changer un type, élargir
un vocabulaire sont des conflits.

### L'invariant, et pourquoi il est le bon

> Un document valide sous le modèle fusionné doit rester valide sous chaque
> standard pris isolément.

Relâcher casserait cette propriété : un DMP conforme à notre modèle pourrait
violer le RDA DCS, et on aurait produit un format qui *dit* implémenter un
standard sans le faire. Le sens de la contrainte est donc une conséquence, pas
une préférence.

### La provenance des resserrements

Chaque resserrement est enregistré sur le champ (`Tightening`) avec le standard
qui l'a imposé. C'est ce qui permettra au QC de dire « obligatoire selon
OSTrails, optionnel dans RDA DCS » au lieu d'accuser silencieusement le
standard de base.

**Le compte de resserrements sur le modèle réel est aujourd'hui zéro** :
`rda_dcs` + `ostrails` n'en produit aucun — OSTrails ajoute 17 champs à lui et
ne restreint rien de la base. La machinerie est construite et testée sur des
fixtures. À ne pas confondre avec du code mort : c'est du code sans utilisateur
*pour l'instant*, et la distinction est délibérée.

### Trois questions, trois modules

Le paquet `project/` répond à « ce projet, résolu, c'est quoi ? », en trois
étapes qui **se composent sans s'appeler** :

| | croise | rend |
|---|---|---|
| `resolve_pins` | une déclaration × une arborescence | des chemins |
| `merge_rules` | N documents entre eux | un `Model` |
| `assemble_project` | une config × son modèle | un `Project` |

`merge_rules` ne connaît ni épingle ni config : on lui donne des chemins.
Ce n'est pas de la pureté gratuite — c'est ce qui permet au contrôle qualité de
fusionner les épingles enregistrées dans le `meta.yaml` d'un DMP soumis **sans
construire de projet du tout**. Si `merge_rules` appelait `resolve_pins`, ce
chemin demanderait le paquet des configs pour un fichier qui n'en est pas une.

Symétriquement, `assemble_project` ne fait que fixer l'ordre. C'est peu, et
c'est le point : si chaque générateur enchaînait les deux lui-même, deux
d'entre eux finiraient par ne pas être d'accord sur ce que « ce projet » veut
dire. L'ordre, lui, est **forcé** — il n'y a rien à fusionner avant que les
épingles ne résolvent, le même ordre que `merge_rules` s'impose en interne
entre « cet ensemble est-il bien formé » et « fusionne-t-il ».

### La convention `<standard>/<version>.json`, tenue par les deux bouts

`resolve_pins` **fabrique** le chemin depuis l'épingle ; la couche 3 de
`rules/loader.py` **vérifie** que le fichier déclare le standard et la version
de son chemin. Aucun des deux ne suffit : le premier trouverait un fichier mal
rangé, le second ne saurait pas qu'on le cherchait.

Il n'y a **pas de dérivation** entre les deux espaces de noms, parce qu'il n'y
en a qu'un : un standard s'écrit en snake_case, et la même chaîne est le nom du
répertoire, la déclaration dans le fichier et ce qu'un pin écrit (§2). La
version se verrouille au passage : le chemin étant construit depuis l'épingle,
un répertoire concordant fait du `<version>.json` la version épinglée par
construction.

### Le piège YAML des épingles

`ostrails: 1.0` est un **flottant** en YAML, contrairement à `1.0.0` qui est
une chaîne. Le schéma de config l'attrape (`additionalProperties: {"type":
"string"}`), donc une config ne peut pas le porter jusqu'ici.

`resolve_pins` ne revérifie pas la forme d'une épingle — c'est écrit dans son
module comme une **précondition**, pas comme un oubli. Le prix est nommé en
[§14](#14-limites-connues) : des épingles venant d'ailleurs qu'une config
validée, et le `meta.yaml` du registre est exactement ce cas.

---

## 14. Limites connues

### Une épingle non validée casse `resolve_pins` en `TypeError`

`resolve_pins` tient la forme d'une épingle pour acquise : `config.schema.json`
exige déjà une liste de mappings à une clé dont les valeurs sont des chaînes.
Mesuré : `resolve_pins([{"ostrails": 1.0}], ...)` lève un `TypeError` nu
(`argument should be a str or an os.PathLike object`), pas une
`UnresolvedPinsError`.

**Latent, pas actif :** le seul appelant est `assemble_project`, qui charge la
config d'abord.

**Déclencheur pour rejuger :** le premier appelant qui passe des épingles ne
venant *pas* d'une config validée. L'enregistrement au registre n'en est pas
un — il écrit les épingles dans `meta.yaml` et ne les relit jamais. Le candidat
reste le contrôle qualité, qui lira celles du `meta.yaml` d'un dossier de
registre — un fichier sans **aucun** schéma, que personne ne valide en entrant
— mais il est repoussé sans date, et le correctif se décide avec son appelant
sous les yeux : une passe de forme dans `resolve_pins`, ou un schéma pour le
sidecar.

### La roue n'embarque aucun fichier de données

`[tool.setuptools.packages.find]` déclare les paquets, mais setuptools
n'embarque que les `.py` tant que le reste n'est pas déclaré à part. Une roue
construite depuis une copie vierge, sans cache, ne contient donc **ni JSON ni
YAML** : elle s'importe, puis meurt au premier appel réel sur
`FileNotFoundError: .../site-packages/rules/rules.schema.json`.

**Latent, et destiné à le rester.** L'unité d'exécution est le **dépôt cloné**,
pas la roue : la CI fait `uv sync --frozen` dans le checkout, et le code y lit
ses fichiers de données là où ils sont, sur le disque. Le déploiement Codespaces
fera pareil — décidé le 05/08/2026 en constatant que « le jour où on
conteneurise » était le prochain jalon, et qu'aucun consommateur de roue n'y
apparaissait pour autant.

**Déclencheur pour rejuger :** publier sur un index, ou installer depuis git
sans `-e`. Le correctif tient alors en deux lignes
(`[tool.setuptools.package-data]`, avec un glob par niveau de répertoire car
ils ne les traversent pas).

**Deux pièges pour qui vérifiera**, tous deux donnant un faux succès :
setuptools **ne nettoie jamais `build/`** entre deux constructions, donc des
fichiers d'un empaquetage antérieur survivent dans les roues suivantes ; et
`uv build` sans `--no-cache` rend une roue antérieure au changement.

### Le format des fichiers de données n'est pas vérifié

`ruff format` ne touche ni au JSON ni au YAML, donc rien en CI ne contrôle la
mise en forme de `rules/standards/*.json` ni de `configs/projects/*.yaml` —
seulement leur contenu, via `scripts/validate_rules.py` et
`scripts/validate_configs.py`.

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
