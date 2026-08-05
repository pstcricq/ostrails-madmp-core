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
4. [La convention d'UUID déterministe](#4-la-convention-duuid-déterministe)
5. [Le point de décision unique](#5-le-point-de-décision-unique)
6. [Le questionnaire (Knowledge Model)](#6-le-questionnaire-knowledge-model)
7. [Le template de document](#7-le-template-de-document)
10. [Le registre, et la publication](#10-le-registre-et-la-publication)
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
un vocabulaire strict devient une `OptionsQuestion` sans échappatoire ; un
vocabulaire suggéré en reçoit une — une réponse « Other » ouvrant un champ
libre — **sauf s'il en nomme déjà une**. Côté QC, l'un fait échouer, l'autre
avertit.

### Un vocabulaire qui nomme son échappatoire garde le monopole

Le RDA DCS termine plusieurs vocabulaires par `other`, DataCite par `Other`.
C'est une **valeur**, pas une porte : elle dit que le type est hors liste, et
ni l'un ni l'autre ne prévoit de champ à côté pour dire lequel. Un champ qui en
déclare une est donc interrogé comme un vocabulaire fermé — sa valeur, dans sa
graphie, et rien d'autre à côté.

**Pourquoi c'est une règle et pas un détail.** Deux échappatoires pour une
seule notion, c'est ce qui faisait disparaître la valeur déclarée de la liste
montrée au chercheur. Sur `dmp.contributor[].role[]` — vocabulaire **contrôlé
et requis** — la valeur DataCite `Other` était absente des vingt cases à
cocher, récupérable seulement en la tapant à la main dans la question voisine
« Role (specify) ». Et sur les vocabulaires qui l'écrivent en minuscules, les
deux n'avaient même pas le choix d'être distinctes : un uuid dérive de la
valeur, donc la réponse déclarée et la réponse synthétique **sont la même
entité**.

La décision vit dans `dsw/common.needs_a_synthetic_escape`, avec `field_kind`,
parce que les deux générateurs doivent y répondre pareil : un KM qui propose la
réponse synthétique là où le template lit la valeur déclarée est une paire que
personne ne peut remplir.

Le prix, assumé : ces champs-là n'ont plus de saisie libre. Un identifiant de
créateur de type `viaf` se répond `other`, et l'information « viaf » n'est pas
écrite. C'est le standard qui a tranché en nommant sa propre sortie ; nous ne
lui en ajoutons pas une seconde.

La valeur d'échappement est **écrite dans le code** (`ESCAPE_VALUE`), pas
déclarée par fichier de règles : aucun fichier n'a besoin de la dire, et une
seconde façon d'orthographier une même convention est exactement ce que cette
règle sert à supprimer.

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

## 4. La convention d'UUID déterministe

Chaque entité DSW — chapitre, question, réponse, portillon Oui/Non — reçoit un
UUID dérivé par `uuid5` du **chemin du champ** pour lequel elle a été générée.

**Ce que ça achète :** le KM et le template sont produits par deux programmes
indépendants qui n'échangent **aucune table de correspondance**, et référencent
pourtant les mêmes entités. Un template ne peut structurellement pas pointer
vers une question que son KM n'a pas — là où une table tenue à la main aurait
dérivé au premier oubli. C'est aussi ce qui permet de tester l'accord des deux
sans sortie attendue : on génère les deux et on vérifie que tout UUID lu par le
template est une entité émise par le KM.

### La contrainte qui en découle

Le namespace et les chaînes de parties sont **gelés à vie une fois un KM
publié**. Les changer changerait tous les UUID dérivés et casserait toutes les
références existantes dans DSW. C'est le prix de la garantie, et il est assumé.

Ce n'est pas une consigne mais un test : `tests/test_dsw_uuids.py` tient neuf
valeurs dérivées, une par genre d'entité, contre ce qui a déjà été publié. Ce
ne sont pas des tests d'algorithme — `uuid5` n'en a pas besoin — mais la garde
sur des valeurs qui n'ont pas le droit de bouger.

### Ce qui est identité et ce qui est affichage

Le tag d'un standard dérive son UUID du nom **de code** (`rda_dcs`) et affiche
la forme majuscule (§2). Les deux ne se croisent jamais : changer ce qu'un
lecteur voit ne déplace aucune entité.

---

## 5. Le point de décision unique

`field_kind()` répond à une seule question : ce champ, logiquement, c'est quoi ?
La réponse est l'une de onze — `computed`, `list`, `object_gated`,
`object_inline`, `options_strict`, `options_suggested`, `options_strict_multi`,
`options_suggested_multi`, `boolean`, `value`, `value_multi`.

Les générateurs interrogent **cette fonction et aucune autre**. Le risque
classique — deux générateurs qui divergent sur un cas limite — est éliminé par
construction et non par discipline : un champ que le KM demande en liste et que
le template rend en valeur simple est une paire de paquets impossible à
remplir, et aucun test de l'un ou de l'autre pris seul ne le verrait.

C'est la règle de `dsw/common.py` en entier : ce qui doit rester littéralement
identique entre les générateurs vit là, et **ce qu'un seul utilise n'y a pas sa
place** — ça appartient à ce générateur-là.

### La règle du découpage en chapitres

Un champ `dmp` de premier niveau devient **son propre chapitre** si et seulement
si c'est un objet (simple ou liste) ; tous les scalaires de premier niveau vont
dans un unique chapitre général partagé.

C'est un découpage, pas un filtre : **tout champ déclaré est demandé**, parce
que les règles sont le questionnaire en entier. Seuls les champs *calculés* sont
sautés, par les générateurs eux-mêmes.

### Les champs calculés

Trois champs ne sont jamais demandés au chercheur, parce que leur valeur vient
entièrement du contexte de rendu :

- `dmp_id` — **toujours** calculé, sans rien à déclarer : son identifiant est
  l'URL courante du DMP dans DSW (`ctx.config.clientUrl` + `/projects/<uuid>`),
  résolue au rendu. Le webhook de soumission la réécrit ensuite vers
  l'emplacement dmp-registry au moment du commit ;
- `created` / `modified` — optionnels, activés par `auto_timestamps` dans la
  config.

Un champ calculé de premier niveau ne reçoit **aucun chapitre**, pas un chapitre
vide. Et le test qui compte est celui du champ imbriqué : `computed` ne
s'applique qu'à la profondeur 1, donc un `dmp_id` sous un objet reste une
question comme une autre.

---

## 6. Le questionnaire (Knowledge Model)

Le générateur parcourt le modèle et émet un bundle d'événements DSW complet.
Les correspondances :

| règle | entité DSW |
|---|---|
| `_allowed_values` | `OptionsQuestion` stricte, sans échappatoire |
| `_suggested_values` | `OptionsQuestion` + réponse « Other » ouvrant un champ libre — sauf si le vocabulaire nomme déjà son échappatoire |
| variantes `1..n`/`0..n` des deux | `MultiChoiceQuestion` |
| objet `0..1` | portillon Oui/Non, enfants sous la réponse « Yes » |
| objet `1` | enfants émis en ligne |
| liste d'objets | `ListQuestion` |
| scalaire répété | `ListQuestion` avec un unique `ValueQuestion` modèle d'item |

**L'ordre des événements est l'ordre de lecture** : DSW déduit l'ordre des
frères de la séquence des événements sous un même `parentUuid`. Il n'y a pas de
champ d'ordre à maintenir — et une seule invariante à tenir, vraie pour
n'importe quel projet : aucun événement ne référence un parent que personne n'a
émis. DSW applique les événements dans l'ordre sur un modèle vide, donc un
parent qui arrive plus tard est une entité qui disparaît sans bruit.

### Un tag par standard, dérivé et non câblé

Les tags de standard sont dérivés de la déclaration `standard` de chaque fichier
de règles. Ajouter un fichier ne demande donc jamais de câbler son tag à la
main. Ils s'affichent en majuscules, à côté de `REQUIRED`, `OPTIONAL` et
`CONTROLLED VOCABULARY` qui le sont aussi.

Le tag `REQUIRED` et la phase ne créditent **pas** le standard de base pour
toute exigence : ils nomment le standard qui impose réellement la contrainte,
extensions comprises — c'est `origin` qui le dit, et il vient de la fusion (§3).

### Les annotations `rules_path`

Chaque question porte une annotation qui la retrace jusqu'à son champ de règles,
pour qu'un consommateur puisse relier une réponse au chemin qu'elle remplit.
C'est ce dont le contrôle qualité aura besoin pour lire un DMP soumis. Seuls les
modèles d'items en sont volontairement dépourvus : ils n'ont pas de chemin
propre.

### La version de métamodèle est gelée à la main

`METAMODEL_VERSION = 20` (KM) et `TEMPLATE_METAMODEL_VERSION = "18.0"` (document
template) sont deux concepts distincts, liés à **l'instance DSW** et non au
projet (20 correspond à DSW 4.31). Référence :
<https://github.com/ds-wizard/dsw-schemas/tree/main/schemas/km-package>.

Ce que le dépôt ne fait pas, c'est vérifier que l'instance visée les accepte :
c'est écrit en [§14](#14-limites-connues).

---

## 7. Le template de document

Le template est un Jinja2 qui produit un export JSON simple. DSW le rend contre
les réponses d'un projet pour produire le maDMP final. Il ne fait **que** rendre
des réponses : aucun contenu ne s'y incorpore.

### L'assemblage en texte JSON littéral

Chaque clé porte sa virgule **devant elle**, requise comme optionnelle, et
chaque clé optionnelle est enveloppée dans son propre bloc `{%- if ... %}`. Le
corps d'un objet est capturé par un `{% set %}` de bloc, et la virgule de celle
qui s'est retrouvée première est retirée au rendu.

**Aucune clé n'a donc besoin d'être inconditionnelle.** C'est le point : un
standard a parfaitement le droit de déclarer un objet dont tous les enfants
sont optionnels — `cost { type?, unit? }` est une forme ordinaire — et fermer
cet objet est le problème du générateur, pas celui des règles. L'exiger d'elles
reviendrait à demander qu'un fichier de règles mente sur son standard pour
arranger notre émetteur.

**Ce que ça remplace, et pourquoi.** Les clés requises étaient auparavant
jointes par des virgules littérales et émises en premier, ce qui obligeait
chaque objet à posséder au moins une clé inconditionnelle comme **ancre**. Cette
contrainte n'était écrite nulle part ailleurs que dans une docstring, et rien ne
la vérifiait : un objet sans ancre produisait `{,` et donc un document que
personne ne peut parser — sans qu'aucun job de CI ne rougisse, le Jinja émis
étant, lui, parfaitement valide.

L'ordre requis-d'abord est conservé, mais il ne décide plus que de la **lecture**
du document. Vérifié au moment du changement : sur `glider`, le document rendu
est identique octet pour octet, avec zéro réponse comme avec toutes.

**Le test qui tient tout ça** rend le template avec deux jeux de réponses, et
c'est le second qui compte. Avec **zéro réponse** aucun bloc optionnel ne
s'ouvre, donc aucune virgule ne peut être orpheline : c'est le seul état sous
lequel la faute ne peut pas se produire. Il faut un objet **rempli** pour la
voir.

### Un champ requis est émis même sans réponse — et c'est maintenant un choix

Avant, ce comportement était **forcé** par l'ancre de virgules. L'ancre partie,
il n'a plus de raison mécanique, et il aurait disparu à la première passe de
simplification si celle-ci n'était pas écrite. La voici : un requis vide est
**visible** dans le document (`"title": ""`), un requis absent ne l'est pas. Un
DMP à qui il manque un champ obligatoire doit le dire, pas se taire.

Le prix est connu et assumé : `""` veut dire « fourni, vide » là où l'absence
veut dire « pas fourni », et c'est ce mécanisme qui produit les `title` vides
des DMP issus d'une baseline. La moitié qui manque est côté contrôle qualité,
juste en dessous.

### Le repli d'un champ non répondu : `''`, jamais une valeur de vocabulaire

Un champ sans réponse retombe sur la chaîne vide, y compris pour un vocabulaire.
Retomber sur une valeur du vocabulaire rendrait une non-réponse **indiscernable
d'une réponse** : `unknown` est une réponse légitime pour `ethical_issues_exist`,
`personal_data` et `sensitive_data` — sur les trois champs les plus lourds de
conséquence du DMP, l'absence de réponse passerait pour un « je ne sais pas »
assumé.

Pour un vocabulaire suggéré **qui a reçu une réponse « Other » synthétique**,
`'other'` est le sentinelle qui la détecte : son uuid est délibérément absent
de la table de libellés `AL`, et c'est le repli du lookup sur `'other'` qui
l'identifie. Lui donner un libellé ferait taire le repli et perdrait la valeur
saisie à la main. Seule la valeur finalement émise retombe sur `''`.

Un vocabulaire qui **nomme lui-même** son échappatoire n'a pas de sentinelle :
sa valeur est une réponse comme les autres, présente dans `AL`, et le template
la lit sans détour. C'était le trou — le sentinelle occupait la place, et un
chercheur qui répondait « Other » sans rien préciser produisait `""` au lieu de
la valeur du standard.

Le pendant côté contrôle qualité — `""` compte comme une absence — arrivera avec
lui. Les deux moitiés doivent bouger ensemble.

### L'UUID de fichier est dérivé, pas tiré au sort

DSW indexe le contenu d'un fichier par cet UUID. Deux exigences s'opposent en
apparence : il ne doit pas être **réutilisé** d'une version publiée à l'autre,
sinon l'ancien contenu est servi pour le nouveau paquet ; et il ne doit pas être
**aléatoire**, sinon deux générations d'un même projet diffèrent sans raison
visible.

Le dériver de l'identifiant de paquet satisfait les deux : l'identifiant porte
la `version` du projet, qu'une publication oblige justement à incrémenter.

### Les formats de sortie

`FORMATS` est la source de vérité unique pour les `formats` du bundle **et** pour
le tableau des formats du README. Seules les entrées `available: true`
deviennent un vrai format DSW. JSON-LD y figure en `available: false` : déclaré,
honnêtement non implémenté.

### Markdown et texte brut

DSW rend le `readme` d'un paquet en Markdown mais sa `description` en texte
brut, alors que les deux dérivent de la même prose de config. D'où
`strip_markdown()`.

---

## 10. Le registre, et la publication

### Enregistrer n'est pas publier

`registry/` n'est pas dans `dsw/`, et la raison est mesurable : enregistrer un
projet n'appelle aucune instance DSW, ne demande aucun paquet publié et rien
de généré. Une config valide suffit. C'est donc l'étape qui vient
**immédiatement après la validation**, avant tout ce qui se construit — et
c'est aussi ce qui permet de la mener à bien aujourd'hui, alors que la
publication attend un déploiement joignable.

Chaque destination porte son client. `registry/` connaît l'API Contents de
GitHub et embarque `GitHubClient` ; `dsw/` connaît l'API DSW et embarque
`DswClient`. `utils/` est pour ce que **plusieurs** paquets partagent, et un
client n'a qu'un consommateur : sa destination. La règle qui permet à
`registry/` de refuser un ajout est celle-là — *rien d'autre dans ce dépôt
n'appelle GitHub*.

Une asymétrie entre les deux, et elle est justifiée : le jeton du registre se
**lit dans l'environnement** (`token_from_env`), celui de DSW s'**obtient par
un appel**. D'où `DswClient.login(instance)` comme constructeur : ce qui fait
des appels est ce qui fait celui-là.

### Le dossier porte l'`id`, sans transformation

`projects/<id>/`. Il n'y a pas de champ qui dise où va un projet, parce qu'il
n'y a rien à dire : le nom du fichier de config, le dossier du registre et les
identifiants DSW sont **la même chaîne**. Avant, `id: socib-glider` et
`github.folder: glider` désignaient la même chose de deux façons, et chaque
générateur devait choisir. Le motif du schéma (`^[a-z0-9-]{1,64}$`) est
exactement celui que le registre exige d'un nom de dossier — pas de point, pas
de barre oblique, donc une soumission ne peut jamais écrire hors de son propre
dossier.

### `meta.yaml` : deux clés, et une qui n'a pas encore de lecteur

```yaml
id: glider
rules:
  - rda_dcs: "1.0.0"
  - ostrails: "1.0.0"
```

C'est tout. Un champ n'entre ici que s'il a un lecteur **du côté registre**,
et il y en a trois possibles : le webhook, la CI du registre, un humain qui
ouvre le dossier. `name` n'en a aucun — le recopier obligerait à mettre le
registre à jour quand une prose change, et inviterait un lecteur à faire
confiance à une copie plutôt qu'à la config.

`rules` est l'exception assumée : **rien ne le lit encore**. Le contrôle
qualité qui le lira n'est pas construit. On l'écrit quand même parce que c'est
la seule information qu'on ne pourra **pas** ajouter après coup : un DMP doit
être vérifiable contre les règles avec lesquelles il a été bâti, les épingles
d'une config bougent, et personne ne saura plus tard ce qui était épinglé au
moment où un DMP donné a été soumis. Geler coûte deux lignes aujourd'hui et
est irrattrapable demain.

Pas d'horodatage, pas de `sha` de commit, pas de « écrit par ». Ce serait
tentant, et ça tuerait l'idempotence : `unchanged` deviendrait impossible et
chaque push sur la branche par défaut laisserait un commit dans le registre.
La provenance existe déjà, c'est l'historique git du registre.

### Ce fichier a deux écrivains, et chacun ses clés

`OWNED = ("id", "rules")`. Tout ce qu'on trouve d'autre dans `meta.yaml`
appartient à quelqu'un d'autre — la CI du registre, aujourd'hui ou demain —
est recopié tel quel, et **n'entre pas dans la comparaison**.

Les deux moitiés de la règle comptent. Reconstruire le fichier depuis la seule
config effacerait le travail de l'autre écrivain en silence, remarqué
seulement par qui irait chercher un verdict qui n'y est plus. Et comparer sur
*ses* clés à lui ferait lire son premier verdict comme une dérive : on
récrirait le fichier pour le lui reprendre, à chaque push, indéfiniment.

L'alternative essayée dans le prototype était un emplacement `qc` réservé,
écrit vide à la création. Elle prévoit un consommateur qui n'existe pas, et ne
couvre que celui-là. La règle de possession ne prévoit rien et les couvre tous.

### Ce qui décide d'écrire, c'est le document, pas les octets

Un fichier qui dit ce qu'il faut avec ses clés dans un autre ordre, ou écrit
par un autre sérialiseur YAML, est **déjà juste**. Le comparer octet par octet
le ferait récrire pour une différence que personne ne peut lire, et vaudrait
un commit dans le registre. La comparaison porte donc sur le document analysé.

### Quatre états, une seule faute

| état | ce que c'est | ce qui suit |
|---|---|---|
| `missing` | rien là-bas | création |
| `registered` | présent, à nous, et d'accord avec la config | rien n'est envoyé |
| `stale` | à nous, mais ne dit plus ce que dit la config | mise à jour |
| `collision` | présent, et c'est le dossier d'un autre projet | refus |

Seule la collision est une **faute**. Un dossier qui n'existe pas encore n'en
est pas une : ajouter un projet, c'est une config d'abord et un enregistrement
ensuite, et faire échouer le contrôle sur le push qui ajoute la config
apprendrait à tout le monde à ignorer ce job. Un `meta.yaml` qui a pris du
retard n'en est pas une non plus : la synchronisation qui le rattrape tourne
juste après. La collision, elle, ne se répare par aucune synchronisation — deux
projets ne peuvent pas avoir raison sur une même destination — et elle ferait
atterrir les DMP d'un projet dans le dossier d'un autre.

**Une collision est inatteignable depuis ce dépôt seul.** Le dossier étant
l'`id`, et l'`id` étant le nom du fichier, deux configs ne peuvent pas viser le
même dossier ; un mauvais nom lève une `ConfigFileError` bien avant. Elle ne
peut venir que d'un `id` renommé, ou d'un autre déploiement écrivant dans le
même registre. Les deux sont arrivés : le prototype a dû semer un dossier pour
exercer le contrôle, et la fusion des identifiants a rendu la collision réelle
sur `glider`, dont le registre disait encore `socib-glider`. Elle a été
résolue par une migration à la main, une fois, plutôt que par du code qui
aurait dû connaître à jamais l'ancien format.

### Le layout du dossier est à nous, pas au webhook

`converge` crée `meta.yaml`, puis `template/` et `productions/` — chacun avec
un `.gitkeep`, git ne stockant pas de répertoire vide. Le webhook, lui, écrit
**un document dans un dossier déjà disposé** : il ne crée ni dépôt ni
échafaudage, et refuse un dossier sans `meta.yaml`, parce qu'un dossier non
initialisé n'a pas d'épingles et qu'un DMP déposé là serait orphelin.

Le partage des rôles est celui-là et pas un autre : ce qui *dispose* connaît la
config, ce qui *dépose* ne connaît que le nom du dossier reçu en paramètre.

### Où écrire ne se devine pas

`REGISTRY_OWNER` et `REGISTRY_REPO` sont lus **sans valeur par défaut**, et
leur absence est une erreur qui les nomme toutes les deux d'un coup. Une valeur
par défaut serait les coordonnées d'un déploiement gravées dans tous les
autres : un fork, le checkout d'un collègue ou un job mal configuré écrirait
dans ce registre-ci sans que personne l'ait demandé. Un programme peut ignorer
beaucoup de choses, mais pas *où il écrit*.

Elles ne sont donc pas des constantes de module mais une valeur, `Registry`,
lue à l'entrée par les scripts et passée aux deux verbes. `folder.py` ne lit
plus l'environnement du tout pour ça, et les tests n'ont plus besoin d'en
poser : ils construisent le `Registry` qu'ils veulent. Le déploiement, lui, est
déclaré là où il vit — dans `ci.yml`, en clair, où un diff le montre.

`REGISTRY_TOKEN` est la seule des trois à ne pas pouvoir l'être, et la seule
dont l'absence n'est pas une erreur en soi : le contrôle s'abstient, la
synchronisation refuse, et seuls eux savent lequel des deux.

### `REGISTRY_TOKEN`, et pourquoi aucun repli

Un seul nom, celui que tout le déploiement utilise — le webhook lit le même.
Localement `REGISTRY_TOKEN=$(gh auth token)`, qui ne le laisse nulle part.

**Pas de repli sur `GITHUB_TOKEN`.** Le jeton par défaut d'un workflow est
limité au dépôt qui l'exécute, jamais au registre : il ne pourrait pas faire ce
travail. Et un jeton sans accès se lit **404**, que le client traduit en « pas
de fichier » sur un GET. Le repli rapporterait donc un projet `missing` alors
que la vérité est « mauvais jeton » — vert, et faux, exactement là où aucune
écriture ne vient contredire.

Le registre étant privé, même **lire** demande un jeton. Le contrôle s'abstient
donc bruyamment quand il n'en a pas (une PR issue d'un fork n'a pas les
secrets) ; la synchronisation, elle, refuse de s'abstenir.

### Un 404 GitHub n'est « fichier absent » que sur un GET

Sur une écriture, un 404 veut dire que le dépôt ou l'accès du jeton est faux —
GitHub répond 404 plutôt que 403 pour ne pas confirmer l'existence d'un dépôt
privé — et il ne doit jamais passer pour un succès. C'est la seule asymétrie du
transport, et elle est testée dans les deux sens.

Le transport s'arrête là. Il rend et prend des **octets** ; le base64, le `sha`
qu'une mise à jour doit nommer et les codes de statut sont son affaire seule,
si bien que `folder.py` n'importe que `yaml`. Dans le prototype, `folder.py`
importait `base64` : l'encodage du transport fuyait dans le module de sens.

### Rendre compte, ou agir

Cinq jobs ne font que **rendre compte** : ils tournent en parallèle, sans
`needs:`, et chacun nomme son propre fautif. Un seul **agit** —
`registry-sync`, la seule chose de ce dépôt qui écrive à l'extérieur — et lui
attend tous les verdicts, et ne tourne que sur la branche par défaut. La ligne
est là, et pas à « avant ou après la validation ».

Sur une pull request il apparaît **`skipped`** : présent dans la liste des
contrôles, donc son abstention se lit au lieu de passer inaperçue.

Il tourne à **chaque** push sur la branche par défaut, pas seulement quand une
config a changé. `meta.yaml` gèle des épingles, et la panne à empêcher est la
dérive : une épingle relevée dans la config pendant que le registre nomme
encore l'ancienne version. Converger à chaque fois la rend impossible au lieu
de la rendre improbable. Le prix serait un commit à chaque push — il n'est pas
payé, puisque rien n'est envoyé quand rien n'a changé.

### Le webhook n'est pas dans ce dépôt

Il est déployé à côté de DSW et embarque **sa propre copie** du client GitHub.
Les deux côtés partagent le *layout* du registre, pas ce code : un changement
ici n'atteint le webhook que si quelqu'un l'y reporte. Le `README.md` du
registre est le contrat qu'ils honorent tous les deux, et ni l'un ni l'autre ne
peut en dériver.

### Trois cibles, et deux natures

`km`, `template`, `submission`. Les deux premières publient un **paquet** :
une identité, une version, immuable. La troisième modifie la **configuration
du tenant** de l'instance : mutable, upsertée par `id`, à côté des entrées des
autres projets.

Deux objets différents, donc deux idempotences différentes — par la version
d'un côté, par l'upsert de l'autre. C'est la raison d'être des trois cibles :
les fondre en une seule ferait croire à une opération unique là où il y en a
deux, qui ne se rejouent pas de la même façon.

### L'idempotence par la version

Une version de paquet DSW est immuable : republier un `package_id` déjà présent
serait rejeté. `publish` interroge donc la liste d'abord et **saute** ce qui est
là, en le disant. Conséquence voulue : passer tous les projets à chaque push sur
`main` ne coûte presque rien, et **seul un `version` incrémenté publie**. Il n'y
a pas de « republier de force » — il y a une version à monter.

Vérifié le 05/08/2026 contre l'instance locale, hors mocks : deuxième
exécution, les deux cibles sautent, code de sortie 0.

### La pagination n'est pas une optimisation

`list_all` suit le nombre de pages au lieu de faire confiance à une grande page.
Une liste tronquée répondrait « pas publié » à propos de quelque chose qui l'est
— et c'est cette réponse-là qui décide s'il y a republication.

### Registre avant soumission, et c'est le code qui le tient

Le webhook refuse un dossier sans `meta.yaml`. Un service de soumission qui
pointe vers un dossier non enregistré transforme donc **chaque Submit en échec**,
et c'est le chercheur qui en porte la faute. `publish submission` appelle
`folder_status` et refuse.

Tenir ça par l'ordre des cibles serait le tenir par une convention — et une
convention, c'est ce qu'on saute quand on lance une cible à la main. L'ordre
dans la CI reste, mais il n'est plus ce qui garantit.

`stale` passe : un `meta.yaml` qui ne dit plus ce que dit la config est à un
sync près, et le dossier est là — c'est tout ce dont le webhook a besoin.

### Le service de soumission n'est pas générable

Question posée le 05/08/2026 : pourquoi n'a-t-il pas son `generate_*` ?

Parce que deux de ses trois entrées n'existent pas au moment du build.
`template_uuid` est attribué par DSW et **change à chaque publication** ;
`tenant_uuid` est lu dans la config de l'instance. Un module `generate_*`
produit une fonction du commit seul — déterministe, uploadable dans
l'artefact. Celui-ci est une fonction du commit **et de l'instance vivante**.

Ce qui *peut* être décidé sans instance l'est : `submission_service()` est une
fonction pure qui rend le dict, testée sans rien joindre, et
`publish_submission()` fait les appels. La séparation existe, comme frontière
de fonction ; un fichier de plus la redirait sans l'ajouter.

### Le scopage : deux choses le rendent propre à un projet

Le dossier dans l'URL (`?project=<id>`), **seule** entrée de routage dont le
webhook dispose — jamais la lecture du document ; et `supportedFormats` nommant
le template de ce projet, pour que le menu Submit propose ce service aux
documents de ce projet et à rien d'autre.

### Le service n'est réécrit que s'il dirait autre chose

Décidé le 05/08/2026. L'API n'a pas de point de terminaison pour *un* service :
écrire le nôtre, c'est renvoyer la configuration **entière** du tenant —
organisation, authentification, apparence. Tout ce qui a changé dans la console
entre la lecture et l'écriture est donc réverti sans un mot. `submission_service()`
étant pure, la comparer à ce que l'instance détient déjà suffit : égale et les
soumissions activées, on n'envoie rien. La fenêtre ne s'ouvre plus que sur les
exécutions qui avaient quelque chose à changer — et l'écrasante majorité n'a
rien à changer, une version de template inchangée gardant le même uuid.

L'état `enabled` compte dans la comparaison : un service que personne ne peut
joindre parce que les soumissions sont désactivées, c'est un bouton Submit qui
n'est pas là.

### Publier consomme l'artefact, il ne régénère pas

Décidé le 05/08/2026. Le job `publish` retélécharge ce que `generate` a
construit dans le même run. Une seule définition de « ce que ce commit
produit », et ce qui part dans DSW est ce qui a été produit une fois, pas une
seconde construction que personne n'a regardée.

L'alternative — régénérer dans le job — rendait `publish` autonome, mais ne
donnait **aucun artefact** tant qu'il est `skipped` faute d'instance, c'est-à-
dire aujourd'hui et pour un moment.

### Aucune coordonnée n'a de défaut, et pas toutes au même moment

Les cinq noms sont lus sans défaut : un point de terminaison par défaut, ce
sont les coordonnées d'un déploiement gravées dans tous les autres. Et à la
différence d'un mauvais registre, une mauvaise instance n'est rattrapée par
rien en aval — elle accepte le paquet, et personne n'en sait rien.

`DSW_API_URL` / `DSW_EMAIL` / `DSW_PASSWORD` disent quelle instance et en tant
que qui : les trois sont exigés ensemble, et l'erreur les nomme **tous d'un
coup**. `SUBMISSION_URL` et `SUBMISSION_TOKEN` ne sont pas des coordonnées de
l'instance mais celles du webhook, donc seule la cible qui en a besoin les
réclame — publier un KM ne doit pas exiger de savoir où les documents seront un
jour envoyés.

Le secret est exigé autant que l'adresse, corrigé le 05/08/2026. Le code le
disait facultatif au motif qu'« un webhook déployé sans secret accepte les
appels non authentifiés » : ce déploiement n'existe pas. Le webhook de
`dsw-test` répond **500** quand il n'en détient aucun et **401** quand l'en-tête
ne correspond pas ([`submission/app.py`]). Un service écrit sans secret est donc
un bouton Submit qui échoue à tous les coups — et il serait écrit *par-dessus*
un service qui marchait, sur la seule absence d'un nom dans une exécution. Même
faute que le repli sur `GITHUB_TOKEN` : un cas d'usage justifié par un mécanisme
inexistant.

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

### Rien ne confronte les artefacts générés à une vraie instance DSW

Deux constantes décrivent l'instance visée et non le projet :
`METAMODEL_VERSION = 20` et `TEMPLATE_METAMODEL_VERSION = "18.0"` (§6). Rien
dans le dépôt ne vérifie qu'une instance donnée les accepte, ni que le Jinja
émis se rend réellement : les tests demandent à Jinja lui-même s'il **parse**,
et rendent le template avec les trois filtres de DSW (`reply_path`,
`reply_str_value`, `reply_items`) **remplacés par des doublures**. Un désaccord
sur ce que fait un de ces filtres ne se verrait donc qu'à l'exécution, dans
DSW, devant un chercheur.

**Pourquoi on s'en tient là :** la seule vérification qui vaudrait mieux
demande une instance DSW joignable, ce qu'un runner GitHub n'est pas
aujourd'hui.

**Déclencheur pour rejuger :** le déploiement Codespaces, qui rend une instance
atteignable depuis la CI. C'est le même jalon qui débloque la publication, et à
ce moment-là la question devient « publier puis rendre un DMP de test » plutôt
que « imiter les filtres mieux ».

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
