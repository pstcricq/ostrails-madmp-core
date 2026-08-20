# madmp-core : les choix de conception

*Document interne SOCIB / OSTrails. Le `README.md` dit **ce que fait** le dépôt
et **comment s'en servir**, ce document dit **pourquoi il est fait comme ça**.
Les commentaires du code, eux, n'expliquent que le code : tout ce qui relève
d'une décision, d'une alternative écartée ou d'une contrainte historique vit
ici.*

*Le dépôt se construit une tranche à la fois, et ce document avec lui : une
section arrive avec le code qu'elle justifie. La numérotation est celle du plan
d'ensemble, donc les numéros ne bougeront pas quand les sections manquantes
arriveront, mais la table des matières ne liste que ce qui existe.*

*Où on en est, au 20/08/2026. Une tranche apporte un paquet, les tests qui le
couvrent, les dépendances que son code importe réellement, et le job de CI qui
le vérifie. Tout ce que ce document décrit est présent et vérifié en CI, sauf
ce qui est explicitement marqué comme décidé et pas encore construit. Tranche
close : le contrôle qualité d'un DMP soumis, du moteur au verdict commité à
côté du DMP, et `v1.0.0` est publiée, image multi-architecture comprise.
Restent ouverts la reprise de la prose du contenu généré et les contrôles
croisés du contrôle qualité, décidés non construits
([§14](#14-limites-connues)).*

---

## Table des matières

1. [Le principe](#1-le-principe)
2. [Le format des règles](#2-le-format-des-règles)
3. [La fusion tighten-only](#3-la-fusion-tighten-only)
4. [La convention d'UUID déterministe](#4-la-convention-duuid-déterministe)
5. [Le point de décision unique](#5-le-point-de-décision-unique)
6. [Le questionnaire (Knowledge Model)](#6-le-questionnaire-knowledge-model)
7. [Le template de document](#7-le-template-de-document)
10. [Le registre, et la publication](#10-le-registre-et-la-publication)
11. [Le déploiement DSW](#11-le-déploiement-dsw)
14. [Limites connues](#14-limites-connues)

---

## 1. Le principe

> Une règle ajoutée dans un fichier JSON devient une question DSW *et* un
> contrôle qualité, sans code et sans possibilité de dérive.

Tout le dépôt découle de cette phrase. Un jeu de règles déclaratives (RDA DMP
Common Standard + OSTrails Application Profile) est la seule source de vérité,
et les programmes qui suivent en dérivent mécaniquement le questionnaire, le
rendu du document, la baseline pré-remplie et la validation.

Deux mécanismes rendront la promesse **structurelle** plutôt que
disciplinaire, c'est-à-dire qu'on ne pourra pas la violer par inattention : la
convention d'UUID déterministe, qui interdit à un template de référencer une
question que son KM n'a pas, et le point de décision unique, qui interdit à
deux générateurs de diverger sur un cas limite. Chacun sera documenté par la
tranche qui l'apporte.

Le reste, la fusion stricte, la validation au chargement et le report
exhaustif des erreurs, sert à ce que les données de règles restent éditables
par quelqu'un qui ne lit pas Python, sans que la moindre faute de frappe
passe.

### L'unité de déploiement, c'est le fichier de config

Un `configs/projects/<id>.yaml` porte **tout** ce qui définit un projet : ses
propres faits, les versions de règles qu'il épingle, et ce que les paquets DSW
générés annoncent. De lui seul découleront un Knowledge Model, un Document
Template, une baseline, une route de soumission et un dossier de registre.

Conséquence voulue : un projet ne bouge **que** si son propre fichier change et
que sa `version` est incrémentée. Rien n'est partagé à l'exécution, rien ne
dérive dans le dos d'un projet parce qu'un autre a été modifié.

Le fichier se lit de haut en bas en trois blocs, le projet, ses règles et
DSW, et l'ordre n'est pas décoratif : il va du plus stable au plus éditorial.
Il n'y a **pas** de bloc `instruments` : le concept est parti avec le standard
`socib`,
et un champ dont le lecteur a disparu vaut moins que son absence. Le schéma
étant fermé, une config qui en épingle encore un est refusée au chargement
plutôt qu'ignorée en silence.

### Où vit un module

Un module appartient à ce qui l'utilise, pas à ce à quoi il ressemble.

**`utils/` prend ce que plusieurs paquets importent, et rien d'autre.** Deux
conditions, toutes les deux requises : le module ne connaît rien de maDMP, ni
règle, ni config, ni projet, ni DSW, ni registre, **et** au moins deux paquets
l'importent. La première seule ne suffit pas : un code générique à un seul
consommateur appartient à ce consommateur. Être générique rend éligible, être
partagé fait entrer.

**La règle a joué le 20/08/2026.** Le client GitHub a vécu dans `registry/`
tant que le registre était son seul appelant. Le webhook, une fois rapatrié
dans ce dépôt, en portait un second, copié puis dérivé, et la seconde condition
était remplie : le client est devenu `utils/github.py`, et les deux copies ont
disparu ([§10](#10-le-registre-et-la-publication)). Le client DSW, lui, n'a
toujours qu'un consommateur et reste dans `dsw/`.

**`utils/` n'exporte rien.** Une façade nomme l'API publique d'un paquet, et
il n'y en a pas une seule à nommer ici : un appelant importe le module dont il
a besoin (`from utils.errors import ProblemsError`), et cet import dit quelle
pièce de plomberie il va chercher. Ré-exporter la cacherait.

**Deux cas limites, tranchés par la seconde condition.** `project/pins.py` ne
connaît aucun format de fichier et tournerait ailleurs tel quel, mais
`project/` est son seul importateur, et son vocabulaire est celui des règles de
bout en bout, du suffixe `.json` au message « unknown standard ». Il reste donc
là. Le jour où les instruments arriveront sous la même forme que les règles, un
deuxième paquet épinglera des ressources versionnées et la question se
rejugera, avec le suffixe et le nom de la ressource à paramétrer.

`dsw/common.standard_label` est dans le même cas : dériver une forme affichable
d'un identifiant ne demande rien de maDMP, mais tous ses appelants
d'aujourd'hui sont des générateurs, et `common` est précisément le paquet de ce
qui doit rester identique entre eux ([§5](#5-le-point-de-décision-unique)).

### Le schéma de config décrit un projet complet, pas ce que le code lit

À ce stade, le code ne lit que trois champs : `id` et `version` pour rendre
compte, `rules` pour résoudre les épingles. Les sept autres (`name`, `author`,
`license`, `organizationId`, `description`, `references`, `auto_timestamps`)
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
disparu, ici il est daté. Un champ dont personne n'aura besoin ne s'écrit pas,
un champ dont le lecteur arrive à la tranche suivante s'exige tout de suite,
sinon les données arrivent en retard sur le code qui les attend.

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

`name` est l'exception à la règle du §2, *ce qu'un lecteur voit est dérivé,
jamais déclaré*, et l'exception est raisonnée. Pour un standard, la forme
affichable est une fonction **totale** de l'identifiant : mettre en majuscules
marche toujours. Pour un projet, non : `socib-hf-radar` donnerait
`Socib Hf Radar`, et la liste des cas qu'une règle mécanique raterait n'est pas
bornée, sigles, accents, majuscules internes. Une dérivation qu'on doit pouvoir
contourner rend le champ de contournement obligatoire, autant déclarer le nom
directement.

Ce qui protège de la dérive, ce n'est donc pas ici la dérivation, c'est le
**périmètre** : `name` ne nomme rien. Aucun identifiant, aucun chemin, aucun
paquet n'en dépend, et il peut changer à chaque version sans qu'une seule
référence bouge. C'est du texte, et le schéma n'en exige que d'être non vide.

### Trois champs de la config forment un identifiant DSW

`dsw/common.package_id` assemble `organizationId:id:version` : c'est sous ce
nom que DSW connaît un paquet, et c'est ce qui fait qu'un KM et son template se
reconnaissent. La forme des trois tiers n'est donc pas la nôtre, c'est celle du
[guide DSW](https://guide.ds-wizard.org/en/4.31/more/development/document-templates/specification.html) :
minuscules, chiffres et points pour l'organisation, minuscules, chiffres et
tirets pour l'identifiant, semver `X.Y.Z` strict pour la version. Les trois
sont donc des motifs dans le schéma.

**Pourquoi ce n'est pas le raisonnement du §2 sur les règles.** Là-bas,
`version` n'a délibérément aucun motif : la vraie contrainte est l'égalité avec
le nom de fichier, et un motif semver refuserait des versionnages qu'on n'a pas
rencontrés. Le raisonnement tient parce que **nous** décidons de ce qui est une
version acceptable. Ici, non : un `version: "1.0"` ou un `organizationId:
"SOCIB Data"` se génère sans broncher et n'échoue qu'au tout dernier appel du
pipeline, contre un serveur distant, après avoir tout produit. Une contrainte
externe qu'on connaît se vérifie à la porte, un contrôle qui ne peut tomber
qu'en CI, sur une instance, est un contrôle qu'on subit.

`id` n'a rien eu à changer : le motif que le § précédent lui donne pour nos
propres raisons, un nom de fichier, un dossier de registre et une clé de
routage, est déjà exactement ce que DSW demande d'un `kmId`. Coïncidence
heureuse, notée ici pour qu'on ne la casse pas en l'élargissant un jour.

---

## 2. Le format des règles

Chaque `rules/standards/<standard>/<version>.json` déclare son nom de standard,
sa version, s'il `extends` la base, et un arbre récursif de champs sous `dmp`.

### Deux faits orthogonaux par champ

- `_cardinality` dit **combien** : `1` et `0..1` (valeur simple), `1..n` et
  `0..n` (liste)
- `_type` dit **ce qu'est chaque valeur** : `object`, ou un format scalaire
  (`string`, `date`, `datetime`, `email`, `url`, `currency`, `language`,
  `country_code`, `number`, `boolean`).

**Il n'y a volontairement pas de type `list`.** La list-ness est entièrement
portée par la cardinalité. Un type `list` créerait deux façons d'exprimer la même
chose, donc deux façons pour un fichier d'en contredire un autre, et il faudrait
arbitrer, à la fusion, entre `_type: list` et `_cardinality: 0..n`. Séparer
« combien » de « quoi » supprime la question.

### Vocabulaires : stricts et suggérés

- `_allowed_values` : vocabulaire fermé, une violation est un **FAIL**
- `_suggested_values` : recommandation, un écart est un **WARNING** seulement

Les deux **s'excluent sur un même champ**, et la couche de cohérence le refuse.
Un vocabulaire est fermé ou il est recommandé, déclarer les deux c'est dire
d'une même liste qu'un écart est un FAIL et qu'il est un WARNING. Le code, lui,
n'hésite pas, `field_kind` teste `_allowed_values` d'abord et sort, donc les
valeurs suggérées seraient simplement perdues, sans un mot. C'est le défaut que
cette couche existe pour attraper, au même titre qu'un `_chapter_description`
mal placé.

La distinction n'est pas cosmétique : elle traverse toute la chaîne. Côté DSW,
un vocabulaire strict devient une `OptionsQuestion` sans échappatoire, un
vocabulaire suggéré en reçoit une, une réponse « Other » ouvrant un champ
libre, **sauf s'il en nomme déjà une**. Côté QC, l'un fait échouer, l'autre
avertit.

### Un vocabulaire qui nomme son échappatoire garde le monopole

Le RDA DCS termine plusieurs vocabulaires par `other`, DataCite par `Other`.
C'est une **valeur**, pas une porte : elle dit que le type est hors liste, et
ni l'un ni l'autre ne prévoit de champ à côté pour dire lequel. Un champ qui en
déclare une est donc interrogé comme un vocabulaire fermé : sa valeur, dans sa
graphie, et rien d'autre à côté.

**Pourquoi c'est une règle et pas un détail.** Deux échappatoires pour une
seule notion, c'est ce qui faisait disparaître la valeur déclarée de la liste
montrée au chercheur. Sur `dmp.contributor[].role[]`, vocabulaire **contrôlé
et requis**, la valeur DataCite `Other` était absente des vingt cases à
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
écrite. C'est le standard qui a tranché en nommant sa propre sortie, nous ne
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

L'alternative, déclarer le nom humain (`"RDA DCS"`) et en dériver le
répertoire par un slug, a été essayée puis abandonnée. Elle marche, mais elle
fait vivre deux espaces de noms reliés par une transformation qui n'est
inversible que dans un sens : `RDA DCS` → `rda_dcs` se calcule, l'inverse
non (`.title()` ne rend pas `OSTrails`). Et surtout elle laissait un
trou : l'unicité des standards se vérifiait sur le **nom déclaré** pendant que
le rangement se vérifiait sur le **slug**, si bien que `"RDA DCS"` et
`"RDA_DCS"`, deux noms « uniques », tombaient dans le même répertoire et
pouvaient être fusionnés comme deux standards distincts. Avec une seule
orthographe, ce trou n'existe pas : unicité et rangement parlent de la même
chaîne.

Le prix, assumé : l'affichage n'est pas curé. `OSTrails` s'affiche `OSTRAILS`.
C'est le bon prix, parce qu'il rend la règle **lisible** : un lecteur qui voit
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
sans un mot. Le job `rules` sort aujourd'hui `declares version '1.0.0' but is
named '1.1.0'`.

**Pourquoi dans le chargement et pas à côté.** Un contrôle qu'un appelant doit
penser à invoquer est un contrôle qu'on oublie : `scripts/validate_rules.py` y
penserait, le prochain appelant non. Le prix est assumé : un fichier de règles
ne se charge que depuis `<standard>/<version>.json`, y compris dans les tests,
qui écrivent donc dans une arborescence plutôt qu'à plat.

`version` n'a **pas** de motif dans le schéma : la vraie contrainte est
l'égalité avec le nom de fichier, et un motif semver refuserait des
versionnages qu'on n'a pas rencontrés.

### Validation en trois couches, au chargement

Un fichier malformé doit échouer **à la porte**, pas au fond d'un consommateur.
`load_rules_file` est la seule entrée, et elle valide trois fois :

1. **Structurelle**, validation contre `rules/rules.schema.json` : clés
   requises, énumérations fermées de `_cardinality`/`_type`, aucune métadonnée
   inconnue, noms de champs en snake_case. La syntaxe JSON elle-même est
   comprise dedans : une virgule en trop ressort en `RulesFileError`, pas en
   `json.JSONDecodeError`, pour qu'un seul type d'exception couvre toutes les
   façons dont un fichier de règles peut être faux.
2. **Cohérence**, cinq contraintes tenues hors du schéma :
   - seuls les champs `_type: "object"` peuvent déclarer des enfants
   - et chacun d'eux doit en déclarer au moins un : un objet **est** ses
     enfants. Sans enfant, il ne collecte rien, un chapitre vide au premier
     niveau, une porte Oui/Non qui n'ouvre sur rien en `0..1`, des items de
     liste sans une seule question, et en `1` un champ qui disparaît du
     questionnaire sans laisser de trace
   - `_allowed_values`/`_suggested_values` ne peuvent apparaître que sur des
     scalaires (un vocabulaire contraint *chaque valeur*, et un objet n'est pas
     une valeur qu'on compare à une chaîne)
   - jamais les deux sur un même champ : une liste est fermée ou recommandée,
     pas les deux, et `field_kind` lit `_allowed_values` en premier, donc les
     valeurs suggérées n'atteindraient aucun générateur
   - `_chapter_description` ne peut apparaître que sur un champ objet de
     **premier niveau**, le seul qui devienne un chapitre DSW. Ailleurs, les
     générateurs l'ignorent sans un mot.
3. **Rangement**, le fichier déclare le standard et la version que son chemin
   nomme (ci-dessus).

**Pourquoi la cohérence n'est pas dans le schéma.** Non pas parce que JSON
Schema ne saurait pas l'exprimer : `if`/`then` et une définition séparée pour
les champs de premier niveau y arrivent. Ce qu'il ne sait pas faire, c'est dire
*quel* champ est en cause et quoi écrire à la place, il produit `'object'
should not be valid under {'const': 'object'}`. C'est la seule raison qu'elles
soient en Python, et elle laisse la porte ouverte à rejuger.

Les couches 2 et 3 ne tournent que sur un document déjà valide
structurellement, et ce n'est pas qu'une question de bruit après les vraies
erreurs : elles lisent `standard`, `version` et `dmp` **sans garde**, ce qui
n'est sûr que parce que la passe schéma vient de garantir que ces clés existent
et sont du bon type. Inverser l'ordre ne rendrait pas les messages plus
bavards, ça lèverait un `KeyError`.

Trois trous du schéma ont été fermés au passage : un vocabulaire acceptait un
**doublon** (`["rt", "rt"]`, le plus sournois, la fusion comparant les
vocabulaires avec `set()`, donc il passait sans bruit et ressortait en double
dans les options DSW), une **chaîne vide**, et `dmp: {}` était accepté, un
fichier de règles qui ne contraint rien.

### Tout signaler d'un coup

Le chargement **collecte l'intégralité des problèmes et lève une seule fois** :
une tentative de chargement = une liste de corrections complète. C'est un choix
d'ergonomie assumé, et il vaut pour les trois couches : un fichier à la fois
mal rangé et mal versionné remonte ses deux problèmes ensemble.

La règle a **une seule implémentation**, `utils/errors.ProblemsError` : une
liste de problèmes, un sujet facultatif, un nom de classe. Toute erreur du dépôt
qui porte une liste de problèmes en hérite. Ce n'est pas une factorisation de
mise en forme : c'est la même règle de conception, qui était écrite plusieurs
fois et rendait donc possible qu'un appelant l'applique à moitié.

Une erreur qui n'est **pas** une liste de problèmes n'entre pas dans cette
hiérarchie et ne doit pas y être forcée.

### Les `description` des fichiers de règles sont inertes

Le modèle ne les porte pas, elles n'atteignent aucun artefact publié. Elles
restent néanmoins la première chose que lit quelqu'un qui ouvre un standard
pour l'éditer, c'est leur seule fonction, et elle suffit à justifier qu'on les
tienne à jour.

---

## 3. La fusion tighten-only

Exactement un fichier est la base (`extends: false`). Les extensions peuvent
redéclarer un champ que la base définit déjà, dans deux cas seulement :

### Chaque extension est jugée par rapport à la base

**Pas par rapport à ce qu'une autre extension a déjà imposé.** C'est la règle
dont tout le reste de ce chapitre découle, et elle tient à un fait sur les
auteurs : OSTrails est écrit contre RDA DCS, un futur standard SOCIB le sera
aussi, et **aucun des deux ne sait ce que l'autre exige**, ni même qu'un
projet les épinglera ensemble.

La fusion faisait l'inverse : elle appliquait les extensions l'une après
l'autre, chacune comparée au résultat des précédentes. Une extension qui
redéclare la cardinalité de la base, le cas courant, redire un parent pour
atteindre ses propres feuilles, devenait donc un « relâchement » dès qu'une
autre était passée avant :

```
[base 0..1, serre 1, repete 0..1] -> CONFLIT
[base 0..1, repete 0..1, serre 1] -> accepté
```

Mêmes fichiers, verdicts opposés selon l'ordre des épingles. C'était un
artefact d'implémentation, la sémantique ayant suivi la boucle, et il
reprochait à un auteur quelque chose qu'il ne pouvait pas savoir.

Chaque extension est donc validée contre `base_meta`, la déclaration figée du
standard qui a **introduit** le champ, et ce que les extensions exigent se
**combine** ensuite :

- la cardinalité la plus stricte l'emporte. Deux resserrements ne peuvent pas
  se contredire : une forme n'a qu'une forme requise (`0..1 -> 1`,
  `0..n -> 1..n`)
- les vocabulaires s'**intersectent**. Un DMP qui respecte les deux standards
  respecte les deux restrictions, donc le champ ne garde que les valeurs que
  les deux acceptent
- une intersection **vide** est un conflit nommant les deux standards, pas un
  champ que personne ne peut remplir.

L'opération est commutative et associative, donc le résultat ne dépend plus de
l'ordre des épingles, vérifié sur **toutes les permutations** de trois
extensions plutôt que sur l'ordre qu'un test aurait écrit.

Un `Tightening` dit désormais « ce que ce standard-ci exige **de plus que la
base** », et non plus « de plus que ce que j'ai trouvé en arrivant ». C'est la
phrase que le QC doit lire, et elle ne peut pas dépendre de qui a fusionné en
premier.

- **à l'identique**, le cas courant : répéter un parent structurel uniquement
  pour atteindre ses propres feuilles en dessous
- **en resserrant**, rendre obligatoire un champ optionnel (`0..1 -> 1`,
  `0..n -> 1..n`), restreindre un vocabulaire à un sous-ensemble, fermer un
  champ ouvert avec un vocabulaire à soi, ou **fermer un vocabulaire suggéré
  sur les valeurs qu'il recommande**.

Elles ne peuvent **jamais** relâcher ni reformer : affaiblir une cardinalité,
transformer une valeur simple en liste (ou l'inverse), changer un type, élargir
un vocabulaire, ou **rouvrir en suggéré un vocabulaire fermé** sont des
conflits.

### Un champ fusionné ne porte jamais deux vocabulaires

La couche de cohérence interdit `_allowed_values` et `_suggested_values` sur un
même champ **dans un fichier** (§2). La fusion est le seul autre chemin par
lequel un champ pourrait en porter deux, et elle tenait la promesse à moitié :
les deux clés étaient fusionnées indépendamment, donc une base qui suggère et
une extension qui ferme produisaient un champ portant les deux, et comme
`field_kind` lit `_allowed_values` en premier, la recommandation partait en
silence. La
règle du §2 se contournait en écrivant deux fichiers.

Le couple est donc lu comme **un seul fait doté d'une nature**, fermé ou
recommandé, et changer cette nature est un mouvement comme un autre :

- **suggéré → fermé** resserre : un écart passait en WARNING, il devient un
  FAIL. Accepté, et `_suggested_values` **disparaît** du champ fusionné, ce
  n'est pas une information qu'on garde pour mémoire, elle est devenue fausse
- **fermé → suggéré** relâche. Conflit.

**La fermeture doit porter sur un sous-ensemble des valeurs suggérées.** Fermer
sur `["z"]` un champ où la base recommande `["a", "b"]` est plus strict au sens
formel, puisque avant tout était permis, mais ça **interdit ce que la base
recommande**. Ce n'est pas un resserrement, c'est un désaccord entre deux
standards, et le rendre visible est exactement ce à quoi sert la fusion
tighten-only.

La même règle s'applique **entre deux extensions** : si l'une ferme un champ et
l'autre en recommande des valeurs, la fermeture l'emporte, une recommandation
ne pouvant pas retenir une violation, mais seulement sur des valeurs que
l'autre recommande. Sinon les deux standards ne disent pas la même chose du
champ, et
c'est un conflit.

L'audit enregistre **deux** `Tightening` pour ce mouvement, la recommandation
retirée puis le champ fermé. Un seul enregistrement portant les deux devrait se
lire « était fermé sur `[a, b, c]` », ce que le champ n'a jamais été.

### L'ordre d'un vocabulaire appartient à la base

C'est l'ordre dans lequel le chercheur lit les options, et ce n'est pas une
contrainte. La validité se juge donc sur des ensembles, mais deux conséquences
en découlent, qui ne l'étaient pas :

- un vocabulaire **réécrit dans un autre ordre** est le même vocabulaire : le
  no-op d'un champ redéclaré, pas un resserrement. Il n'entre plus dans
  l'audit, et ne change plus l'ordre des options
- un resserrement **conserve l'ordre de la base**, filtré des valeurs retirées.
  Une extension dit *quelles* valeurs sont offertes, la mise en page n'est pas
  ce que tighten-only lui permet de décider.

### Un message de conflit nomme qui a écrit la valeur

`origin` répond « qui a introduit ce champ ». Les messages lui faisaient dire
« qui a produit l'état courant », et ce sont deux questions différentes dès
qu'il y a trois standards : celui qui a resserré n'est ni la base ni celui
qu'on refuse. Trois messages nommaient donc un fichier qui n'avait rien écrit,
le pire étant le conflit de prose, qui accusait la base alors qu'elle n'avait
aucune description.

`_Node.meta_origin` retient, **pour chaque clé de métadonnée**, le standard qui
a écrit la valeur courante. Un dictionnaire plutôt qu'une relecture de
`Tightening` à rebours : il couvre d'un coup la cardinalité, les vocabulaires
**et** la prose, qui ne contraint rien et n'est donc enregistrée nulle part
ailleurs.

### La prose suit la même règle, et pour la même raison

`_description` et `_chapter_description` ne contraignent rien, mais elles ne
sont pas pour autant en roue libre. Une extension peut **décrire un champ que
la base a laissé sans description**, et peut **répéter** ce que la base dit,
c'est à quoi ressemble un parent structurel redéclaré. En dire *autre chose*
est un conflit.

Auparavant, la base gagnait en silence : la prose de l'extension était jetée
sans un mot. C'est exactement la faute que le contrôle de cohérence sur
`_chapter_description` existe pour attraper : du texte qu'un auteur a écrit,
que les générateurs ignorent, et dont rien ne le prévient. Le même mal appelle
le même remède.

Est-ce qu'une extension *devrait* pouvoir remplacer une description ? La
question n'est pas tranchée, et c'est bien pour ça qu'on refuse : un refus le
dit, un silence le cache. Zéro occurrence dans les fichiers actuels, mesuré
avant d'écrire la règle.

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
`rda_dcs` + `ostrails` n'en produit aucun, OSTrails ajoutant 17 champs à lui
et ne restreignant rien de la base. La machinerie est construite et testée sur
des
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
Ce n'est pas de la pureté gratuite, c'est ce qui permet au contrôle qualité de
fusionner les épingles commitées à côté d'un DMP soumis **sans construire de
projet du tout**. Si `merge_rules` appelait `resolve_pins`, ce chemin
demanderait le paquet des configs pour un fichier qui n'en est pas une.

Symétriquement, `assemble_project` ne fait que fixer l'ordre. C'est peu, et
c'est le point : si chaque générateur enchaînait les deux lui-même, deux
d'entre eux finiraient par ne pas être d'accord sur ce que « ce projet » veut
dire. L'ordre, lui, est **forcé** : il n'y a rien à fusionner avant que les
épingles ne résolvent, le même ordre que `merge_rules` s'impose en interne
entre « cet ensemble est-il bien formé » et « fusionne-t-il ».

### La convention `<standard>/<version>.json`, tenue par les deux bouts

`resolve_pins` **fabrique** le chemin depuis l'épingle, la couche 3 de
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
"string", "minLength": 1}`), donc une config ne peut pas le porter jusqu'ici.

Le nom du standard y est tenu par le **même** motif que dans le fichier de
règles qu'il désigne (`propertyNames`, `^[a-z][a-z0-9_]*$`). Un identifiant
dont la forme est obligatoire d'un côté et libre de l'autre est un identifiant
qui a deux orthographes en attente : `RDA DCS: "1.0.0"` se chargeait, pour
n'échouer qu'à la résolution. Les deux messages sont bons, `resolve_pins`
allant jusqu'à lire le disque pour lister les standards existants, donc ce qui
est gagné n'est pas la lisibilité de l'erreur, c'est que la règle du §2 (« un
standard n'a qu'une orthographe ») vaille **partout où il s'écrit**.

`resolve_pins` ne revérifie pas la forme d'une épingle, c'est écrit dans son
module comme une **précondition**, pas comme un oubli. Le prix est nommé en
[§14](#14-limites-connues) : des épingles venant d'ailleurs qu'une config
validée, et celles qu'un DMP soumis porte avec lui sont exactement ce cas.

---

## 4. La convention d'UUID déterministe

Chaque entité DSW, chapitre, question, réponse ou portillon Oui/Non, reçoit un
UUID dérivé par `uuid5` du **chemin du champ** pour lequel elle a été générée.

**Ce que ça achète :** le KM et le template sont produits par deux programmes
indépendants qui n'échangent **aucune table de correspondance**, et référencent
pourtant les mêmes entités. Un template ne peut structurellement pas pointer
vers une question que son KM n'a pas, là où une table tenue à la main aurait
dérivé au premier oubli. C'est aussi ce qui permet de tester l'accord des deux
sans sortie attendue : on génère les deux et on vérifie que tout UUID lu par le
template est une entité émise par le KM.

### La contrainte qui en découle

Le namespace et les chaînes de parties sont **gelés à vie une fois un KM
publié**. Les changer changerait tous les UUID dérivés et casserait toutes les
références existantes dans DSW. C'est le prix de la garantie, et il est assumé.

Ce n'est pas une consigne mais un test : `tests/test_dsw_uuids.py` tient neuf
valeurs dérivées, une par genre d'entité, contre ce qui a déjà été publié. Ce
ne sont pas des tests d'algorithme, `uuid5` n'en a pas besoin, mais la garde
sur des valeurs qui n'ont pas le droit de bouger.

### Ce qui est identité et ce qui est affichage

Le tag d'un standard dérive son UUID du nom **de code** (`rda_dcs`) et affiche
la forme majuscule (§2). Les deux ne se croisent jamais : changer ce qu'un
lecteur voit ne déplace aucune entité.

---

## 5. Le point de décision unique

`field_kind()` répond à une seule question : ce champ, logiquement, c'est quoi ?
La réponse est l'une de onze : `computed`, `list`, `object_gated`,
`object_inline`, `options_strict`, `options_suggested`, `options_strict_multi`,
`options_suggested_multi`, `boolean`, `value`, `value_multi`.

Les générateurs interrogent **cette fonction et aucune autre**. Le risque
classique, deux générateurs qui divergent sur un cas limite, est éliminé par
construction et non par discipline : un champ que le KM demande en liste et que
le template rend en valeur simple est une paire de paquets impossible à
remplir, et aucun test de l'un ou de l'autre pris seul ne le verrait.

C'est la règle de `dsw/common.py` en entier : ce qui doit rester littéralement
identique entre les générateurs vit là, et **ce qu'un seul utilise n'y a pas sa
place**, ça appartient à ce générateur-là.

### Ce n'est pas qu'entre les générateurs

`common` porte trois accords, pas un, et les deux autres traversent la
publication :

- `km_path()` / `template_path()` : un générateur écrit, `publish` relit, dans
  une autre exécution et en CI sur une autre machine. Deux chemins épelés
  séparément se contrediraient un jour, et l'erreur dirait « lance d'abord le
  générateur », c'est-à-dire la seule chose qui n'avait pas manqué
- `SUBMISSION_FORMAT` / `format_uuid()` : `generate_template` émet un format
  DSW sous ce nom, `publish` nomme l'uuid de ce format dans le service de
  soumission. Aucun des deux ne lit l'autre. Un service qui nomme un format que
  le bundle ne porte pas est une entrée du menu Submit qui ne produit rien, et
  renommer le format suffisait à l'obtenir : `publish` redérivait l'uuid depuis
  la chaîne `"JSON"` écrite chez lui. Un test le confronte désormais à un vrai
  bundle.

Le critère est le même dans les trois cas, et il a deux moitiés : plusieurs
modules doivent y répondre **pareil**, *et* diverger serait une faute. Une
valeur que les deux calculent chacun de son côté, correctement, aujourd'hui,
remplit déjà la première moitié, c'est la seconde qui décide.

### La règle du découpage en chapitres

Un champ `dmp` de premier niveau devient **son propre chapitre** si et
seulement si c'est un objet, simple ou liste, et tous les scalaires de premier
niveau vont dans un unique chapitre général partagé.

C'est un découpage, pas un filtre : **tout champ déclaré est demandé**, parce
que les règles sont le questionnaire en entier. Seuls les champs *calculés* sont
sautés, par les générateurs eux-mêmes.

### Les champs calculés

Trois champs ne sont jamais demandés au chercheur, parce que leur valeur vient
entièrement du contexte de rendu :

- `dmp_id`, **toujours** calculé, sans rien à déclarer : son identifiant est
  l'URL courante du DMP dans DSW (`ctx.config.clientUrl` + `/projects/<uuid>`),
  résolue au rendu. Le webhook de soumission la réécrit ensuite vers
  l'emplacement dmp-registry au moment du commit
- `created` / `modified`, optionnels, activés par `auto_timestamps` dans la
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
| `_suggested_values` | `OptionsQuestion` + réponse « Other » ouvrant un champ libre, sauf si le vocabulaire nomme déjà son échappatoire |
| variantes `1..n`/`0..n` des deux | `MultiChoiceQuestion` |
| objet `0..1` | portillon Oui/Non, enfants sous la réponse « Yes » |
| objet `1` | enfants émis en ligne |
| liste d'objets | `ListQuestion` |
| scalaire répété | `ListQuestion` avec un unique `ValueQuestion` modèle d'item |

**L'ordre des événements est l'ordre de lecture** : DSW déduit l'ordre des
frères de la séquence des événements sous un même `parentUuid`. Il n'y a pas de
champ d'ordre à maintenir, et une seule invariante à tenir, vraie pour
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
extensions comprises, c'est `origin` qui le dit, et il vient de la fusion (§3).

### Les annotations `rules_path`

Chaque question porte une annotation qui la retrace jusqu'à son champ de règles,
pour qu'un consommateur puisse relier une réponse au chemin qu'elle remplit.
C'est ce dont le contrôle qualité aura besoin pour lire un DMP soumis.

**Chaque** question, désormais, y compris le modèle d'item d'un scalaire répété
, et c'est un revirement. Cette page disait qu'ils en étaient « volontairement
dépourvus : ils n'ont pas de chemin propre ». La prémisse est juste, la
conséquence était fausse.

Sur un `value_multi`, la réponse de la `ListQuestion` est la liste des uuid
d'items, la **valeur**, elle, est stockée contre le modèle d'item, sous le
chemin `<liste>.<item>.<modèle>`. C'est ce que lit le template, et c'est donc la
seule entité qu'un consommateur rencontre en parcourant les réponses. Ne pas
l'annoter, c'est laisser sans chemin la seule qui en porte une valeur : quatre
champs de `glider` étaient dans ce cas, et leurs réponses étaient impossibles à
replacer.

Le modèle d'item porte donc le chemin de son champ, le même que la liste qui le
contient. Deux entités nomment un seul champ, et c'est la vérité d'un scalaire
répété : DSW n'a pas d'autre façon de vouloir plusieurs fois une valeur, donc il
faut un emballage. Elles restent distinguables par leur type et par leur
parenté, et la convention de chemins pointés du QC (`dmp.dataset[].title`) ne
donne de toute façon pas de chemin séparé à un élément.

Ce qui reste sans annotation : le chapitre général, qui est le nôtre et non
celui d'un standard. Un chapitre a le droit de n'avoir pas de chemin, une
question n'en a pas le droit, elle a été posée parce qu'un champ de règles l'a
demandée. Un test le dit dans ce sens-là, sur les événements et non sur les
champs, celui qui parcourait les champs ne voyait pas une question qu'aucun
champ ne fait chercher, ce qui est exactement le cas qui manquait.

### La version de métamodèle est gelée à la main

`METAMODEL_VERSION = 20` (KM) et `TEMPLATE_METAMODEL_VERSION = "18.0"` (document
template) sont deux concepts distincts, liés à **l'instance DSW** et non au
projet. Référence :
<https://github.com/ds-wizard/dsw-schemas/tree/main/schemas>.

**Revérifiés le 06/08/2026 contre `engine-backend` au tag `v4.31.0`**, plutôt
que crus sur parole : `knowledgeModelMetamodelVersion = 20`, et
`documentTemplateMetamodelVersion = SemVer2Tuple 18 1`. `18.0` est donc
**accepté**, `isDocumentTemplateSupported` prenant la même majeure avec une
mineure inférieure, mais 4.31 est à 18.1.

Ce que le dépôt ne fait pas, c'est vérifier que l'instance visée les accepte :
c'est écrit en [§14](#14-limites-connues).

### Un champ que le métamodèle ne définit pas n'est pas un champ qu'on envoie

Chaque `Add*EventContent` de `kmp_schema_v20.json` est
`additionalProperties: false`. Le générateur émettait pourtant `answerUuids: []`
sur les `OptionsQuestion` et `itemTemplateQuestionUuids: []` sur les
`ListQuestion`, que v20 n'a ni l'un ni l'autre : 60 erreurs de schéma, zéro
après retrait.

Les deux étaient **inertes**, DSW déduisant l'ordre des entités sœurs de
l'ordre des événements et non de ces listes, ce qui explique à la fois que
rien ne les
ait rejetés (le décodeur Aeson du serveur ignore les clés inconnues) et que
rien ne se perde à les retirer. Un bundle hors schéma se publie aujourd'hui et
reste un bundle que personne d'autre ne peut valider.

Le contrat est tenu par un test qui énumère, pour chaque type d'événement, les
champs que le métamodèle définit. Écrit là plutôt que vérifié contre le fichier
de schéma lui-même : l'épingler voudrait dire embarquer cent kilo-octets de
JSON qui ne sont pas les nôtres, alors que les champs émis tiennent en deux
douzaines de noms qui disent en un seul endroit ce qu'est un événement de KM.

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
sont optionnels, `cost { type?, unit? }` étant une forme ordinaire, et fermer
cet objet est le problème du générateur, pas celui des règles. L'exiger d'elles
reviendrait à demander qu'un fichier de règles mente sur son standard pour
arranger notre émetteur.

**Ce que ça remplace, et pourquoi.** Les clés requises étaient auparavant
jointes par des virgules littérales et émises en premier, ce qui obligeait
chaque objet à posséder au moins une clé inconditionnelle comme **ancre**. Cette
contrainte n'était écrite nulle part ailleurs que dans une docstring, et rien ne
la vérifiait : un objet sans ancre produisait `{,` et donc un document que
personne ne peut parser, sans qu'aucun job de CI ne rougisse, le Jinja émis
étant, lui, parfaitement valide.

L'ordre requis-d'abord est conservé, mais il ne décide plus que de la **lecture**
du document. Vérifié au moment du changement : sur `glider`, le document rendu
est identique octet pour octet, avec zéro réponse comme avec toutes.

**Le test qui tient tout ça** rend le template avec deux jeux de réponses, et
c'est le second qui compte. Avec **zéro réponse** aucun bloc optionnel ne
s'ouvre, donc aucune virgule ne peut être orpheline : c'est le seul état sous
lequel la faute ne peut pas se produire. Il faut un objet **rempli** pour la
voir.

### Tout ce qui est du texte passe par `js()`

Le document étant assemblé en **texte JSON littéral**, rien ne s'interpose entre
une réponse et le fichier : une valeur est écrite entre deux guillemets, et si
elle en contient un elle ferme la chaîne. Ce n'est pas un champ abîmé, c'est
l'export entier qui cesse d'être du JSON.

Le template déclare donc une macro `js(text)` qui rend le corps d'une chaîne
JSON, et **toute expression qui rend du texte y passe** :

| macro / expression | ce qu'elle rend | échappée |
| --- | --- | --- |
| `js(text)` | n'importe quel texte, prêt à tenir entre guillemets | (aucun) |
| `jv(path)` | une réponse, c'est-à-dire `js()` sur une lecture brute | oui |
| `js(av(path, ''))` | un libellé de vocabulaire | oui |
| `js(AL.get(..., 'unknown'))` | un libellé dans un tableau multi-choix | oui |
| `sv(path)` / `av(path, d)` | les lecteurs **bruts** | non, jamais émis |

`sv` et `av` restent nus parce que ce qu'ils servent, ce sont les
**comparaisons** : `av(...) == 'other'` détecte la réponse « Other »
synthétique, `av(...) == 'yes'` décide d'un booléen. Une valeur qu'on compare
n'est pas une valeur qu'on écrit, et les mélanger est exactement ce qui avait
laissé le texte libre sans échappement.

**Ce qui était cassé.** `jv()` existait déjà, mais n'était appliqué qu'aux
valeurs simples. Les libellés passaient bruts, et surtout la réponse libre
derrière « Other » aussi, c'est-à-dire le seul champ du questionnaire conçu
pour recevoir une saisie arbitraire, sur les 16 champs qui en reçoivent une
aujourd'hui. Un guillemet, un antislash ou un retour à la ligne dans ce champ,
et le maDMP n'était plus parsable. Et `jv()` lui-même était incomplet : il
traitait `\`, `"`, `\n`, supprimait `\r`, et laissait passer la tabulation, que
JSON interdit telle quelle dans une chaîne.

**Ce que `js()` couvre.** L'antislash, le guillemet double, et **tout**
caractère sous U+0020, les cinq à échappement nommé (`\b \f \n \r \t`), les
autres en `\u00XX`. La table est écrite en Python (`_JSON_ESCAPES`) et la
chaîne de `|replace` est engendrée à partir d'elle : personne n'a à retenir la
liste, et rien n'y manque par oubli. L'antislash vient en premier, sinon il
échapperait les antislashs que les autres substitutions viennent de produire.

`\r` est désormais **échappé** et non plus supprimé : un texte collé depuis
Windows garde ses fins de ligne au lieu d'être discrètement réécrit.

**Pourquoi pas `|tojson`.** Le filtre de Jinja ferait le travail, mais il est
aussi *HTML-safe* : il rend l'esperluette et l'apostrophe sous leur forme
`\u`. Un maDMP est commité dans le registre pour être lu et diffé, et les deux
sont ordinaires dans un nom d'institution.

### Un libellé de vocabulaire est du *code*, pas seulement une donnée

La table `AL` traduit un uuid de réponse stocké en son libellé, et elle est
écrite dans le template sous forme de littéraux Jinja. Un libellé n'y est donc
pas une donnée que le template lit : c'est de la **source** que le générateur
écrit.

`Institut d'Optique` fermait son littéral avant la fin, et le corps cessait
d'être du Jinja, pas d'être du JSON, d'être du Jinja. Rien ne l'aurait vu :
le test qui parse le corps ne couvre que `glider`, et le contrôle par config
ne parse pas ce qu'il engendre. La panne serait arrivée au rendu, devant un
chercheur.

`q()` échappe donc maintenant l'antislash, l'apostrophe et les caractères de
contrôle. Une seule fonction pour les uuid et pour les libellés, et non une
sûre à côté d'une rapide : une deuxième façon d'écrire une chaîne Jinja est un
deuxième endroit où un libellé peut finir dans la mauvaise. Un uuid, lui, en
ressort inchangé, il n'y a rien à y échapper.

### Le contrôle par config demande à Jinja, projet par projet

Un libellé étant de la source, ce qu'il casse dépend des **données**, donc de
choses qu'aucun test unitaire n'a vues. `scripts/validate_generation.py` est le
seul endroit où toutes les configs passent par les générateurs, et c'était
justement sa raison d'être : « les règles, vocabulaires et épingles d'un second
projet sont des données qu'aucun test n'a vues ». Il vérifiait pourtant les
entités en double et rien d'autre, pas que ce qu'il écrit compile.

Il le fait maintenant. Deux contrôles, et tous deux portent sur ce que la
**donnée** décide, jamais sur ce que le code décide : aucune entité émise deux
fois, et un corps de template qui est du Jinja. Sans eux, la première faute est
rendue par DSW en laissant tomber une question, la seconde au rendu, devant un
chercheur.

`jinja2` reste une dépendance de **développement** : le générateur écrit du
Jinja, il ne l'exécute jamais, et un contrôle de dépôt n'est pas quelque chose
qu'un paquet installé doit porter. La CI l'a, `uv sync --frozen` installant le
groupe dev.

### Un champ requis est émis même sans réponse, et c'est maintenant un choix

Avant, ce comportement était **forcé** par l'ancre de virgules. L'ancre partie,
il n'a plus de raison mécanique, et il aurait disparu à la première passe de
simplification si celle-ci n'était pas écrite. La voici : un requis vide est
**visible** dans le document (`"title": ""`), un requis absent ne l'est pas. Un
DMP à qui il manque un champ obligatoire doit le dire, pas se taire.

Le prix est connu et assumé : `""` veut dire « fourni, vide » là où l'absence
veut dire « pas fourni », et c'est ce mécanisme qui produit les `title` vides
des DMP issus d'une baseline. La moitié qui manque est côté contrôle qualité,
juste en dessous.

#### Un booléen n'a pas de chaîne vide : il rend `null`

Un scalaire dit « fourni, vide » avec `""`. Un booléen n'a pas cette valeur-là,
et il disait donc `false`, sauf que **`false` n'est pas un silence, c'est une
réponse**. « Personne n'a répondu » et « on a répondu non » rendaient le même
document, sur des champs comme `is_reused` où les deux affirmations n'ont rien
à voir.

Trois états, donc trois valeurs : `true`, `false`, et `null` pour le non
répondu. Le QC lira `null` comme il lira `""`, une absence, et la clé reste
émise, puisque c'est elle qui dit que le champ manque.

Le prix, lui aussi assumé : `null` n'est pas un booléen valide au regard du
schéma d'un standard. Mais `""` ne satisfait pas davantage un titre requis, et
c'est la même doctrine qui l'accepte : entre un document **prouvablement
incomplet** et un document qui affirme tranquillement quelque chose que
personne n'a dit, on prend le premier.

**Corrigé avant d'être atteignable.** Aucun standard sur disque ne déclare de
booléen requis, `dmp.dataset[].is_reused` étant en `0..1`, donc conditionnel, et
n'a jamais rien inventé. Mais `0..1 → 1` est un **resserrement autorisé** par la
fusion : une extension activait ça sans une ligne de code et sans rien de rouge.

### Le repli d'un champ non répondu : `''`, jamais une valeur de vocabulaire

Un champ sans réponse retombe sur la chaîne vide, y compris pour un vocabulaire.
Retomber sur une valeur du vocabulaire rendrait une non-réponse **indiscernable
d'une réponse** : `unknown` est une réponse légitime pour `ethical_issues_exist`,
`personal_data` et `sensitive_data`, sur les trois champs les plus lourds de
conséquence du DMP, l'absence de réponse passerait pour un « je ne sais pas »
assumé.

Pour un vocabulaire suggéré **qui a reçu une réponse « Other » synthétique**,
`'other'` est le sentinelle qui la détecte : son uuid est délibérément absent
de la table de libellés `AL`, et c'est le repli du lookup sur `'other'` qui
l'identifie. Lui donner un libellé ferait taire le repli et perdrait la valeur
saisie à la main. Seule la valeur finalement émise retombe sur `''`.

Un vocabulaire qui **nomme lui-même** son échappatoire n'a pas de sentinelle :
sa valeur est une réponse comme les autres, présente dans `AL`, et le template
la lit sans détour. C'était le trou : le sentinelle occupait la place, et un
chercheur qui répondait « Other » sans rien préciser produisait `""` au lieu de
la valeur du standard.

Le pendant côté contrôle qualité, où `""` compte comme une absence, arrivera avec
lui. Les deux moitiés doivent bouger ensemble.

### L'UUID de fichier est dérivé, pas tiré au sort

DSW indexe le contenu d'un fichier par cet UUID. Deux exigences s'opposent en
apparence : il ne doit pas être **réutilisé** d'une version publiée à l'autre,
sinon l'ancien contenu est servi pour le nouveau paquet, et il ne doit pas être
**aléatoire**, sinon deux générations d'un même projet diffèrent sans raison
visible.

Le dériver de l'identifiant de paquet satisfait les deux : l'identifiant porte
la `version` du projet, qu'une publication oblige justement à incrémenter.

### Les formats de sortie

`FORMATS` est la source de vérité unique pour les `formats` du bundle **et** pour
le tableau des formats du README. Seules les entrées `available: true`
deviennent un vrai format DSW. JSON-LD y figure en `available: false` : déclaré,
honnêtement non implémenté.

### Les deux README sont composés au même endroit

`readme_head()` et `readme_tail()` donnent aux deux paquets leur ouverture et
leur fermeture. Le bloc « Compatibility » recevait des lignes **déjà puchées**
par l'appelant, et les deux ne s'en souvenaient pas pareil : le template
puçait tout, le KM ouvrait sur une phrase nue. Rien n'était faux, les deux
paquets se contredisaient simplement sur une page que des lecteurs comparent.

`readme_tail()` reçoit maintenant des **faits**, un par ligne, et pose les
puces. `rules_provenance_line()` rend un fait et non une ligne, pour la même
raison. Une mise en forme que chaque appelant doit se rappeler est une mise en
forme qui divergera.

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
**immédiatement après la validation**, avant tout ce qui se construit, et
c'est aussi ce qui permet de la mener à bien aujourd'hui, alors que la
publication attend un déploiement joignable.

**Un seul client GitHub, dans `utils/`, depuis le 20/08/2026.** Il y en a eu
deux, `registry/github.py` et `submission/github_client.py`, le second né d'une
copie du premier dans `madmp-dsw` puis rentré ici avec le webhook. Les fondre a
demandé de trancher quatre écarts, dont trois avaient un gagnant clair :

- **le 404** est traité par chaque lecture, pas par le transport. `_request`
  lève sur tout statut d'erreur, et `get_file` et `branch_head` sont les deux
  seules à savoir qu'un 404 leur dit « pas là ». Une écriture n'a plus à
  connaître cette règle pour y échapper.
- **GitHub injoignable**, DNS mort, connexion refusée ou expiration, devient la
  même `GitHubError`, sans statut. Un appelant a un seul type à attraper. Côté
  registre, un `URLError` sortait tel quel et traversait le `except GitHubError`
  de `publish.py`.
- **au-delà d'1 Mo**, la lecture lève au lieu de rendre un fichier vide
  ([§14](#14-limites-connues)).

Le quatrième écart, ce que rend `get_file`, découle du troisième : des octets,
ou `None`.

**Le `sha` a disparu dans la fusion.** Il ne servait qu'à remplacer un fichier
en nommant la version lue, et personne ne remplace, `converge()` n'écrivant que
les `.gitkeep` absents. Sans `sha`, une écriture ne peut que créer, et GitHub
refuse par un 422 un fichier déjà là au lieu de l'écraser : le garde-fou est
chez GitHub, pas dans le paramètre. D'où le nom, `create_file` et non
`put_file`, qui promettait la sémantique de PUT. Enlever le `sha` ne coûte donc
rien, et le jour où un remplacement sera nécessaire, celui qui le remettra sera
celui qui doit penser à la course entre sa lecture et son écriture.

`dsw/` garde le sien, `DswClient`, qui n'a qu'un consommateur. Une asymétrie
entre les deux, et elle est justifiée : le jeton du registre se
**lit dans l'environnement** (`token_from_env`), celui de DSW s'**obtient par
un appel**. D'où `DswClient.login(instance)` comme constructeur : ce qui fait
des appels est ce qui fait celui-là.

### Le dossier porte l'`id`, sans transformation

`projects/<id>/`. Il n'y a pas de champ qui dise où va un projet, parce qu'il
n'y a rien à dire : le nom du fichier de config, le dossier du registre et les
identifiants DSW sont **la même chaîne**. Avant, `id: socib-glider` et
`github.folder: glider` désignaient la même chose de deux façons, et chaque
générateur devait choisir. Le motif du schéma (`^[a-z0-9-]{1,64}$`) est
exactement celui que le registre exige d'un nom de dossier, pas de point, pas
de barre oblique, donc une soumission ne peut jamais écrire hors de son propre
dossier.

### Ce que le dossier ne dit plus, et pourquoi

Jusqu'au 18/08/2026, `converge` écrivait un `meta.yaml` de deux clés à la
racine du dossier, l'`id` du projet et ses épingles de règles.

L'intention était juste : un DMP doit être vérifiable contre les règles avec
lesquelles il a été bâti, les épingles d'une config bougent, et personne ne
saura plus tard ce qui était épinglé au moment où un DMP donné a été soumis.
Ce fichier était censé geler ça.

Il ne le gelait pas. `registry-sync` tourne à **chaque** push sur la branche
par défaut et récrit les clés possédées avec celles de la config du jour. Le
fichier disait donc où en est le projet **aujourd'hui**, pas avec quoi ce
DMP-là a été rempli. Un contrôle qualité qui l'aurait lu aurait comparé un
document rempli sous `ostrails 1.0.0` à des règles `2.0.0`, et rendu des
échecs que personne n'aurait pu corriger autrement qu'en refaisant le DMP. Le
cas le plus vicieux ne demandait même pas de montée de version : changer les
épingles sans toucher à `version` laisse DSW sur l'ancien KM, `publish` étant
idempotent par version, pendant que le registre annonce déjà les nouvelles
règles.

La correction n'est pas d'écrire ce fichier mieux, c'est de ne plus l'écrire.
**Fait le 18/08/2026 :** `registry/` ne connaît plus les épingles du tout, et
ce que ce dépôt écrit dans le registre se réduit à deux `.gitkeep`.

**Décidé le même jour, et construit depuis :** les épingles voyagent **avec le
DMP**. Le template les inscrit dans le document qu'il rend, sous une clé
`metadata` sœur de `dmp`, le webhook sort ce bloc du document et le commite à
côté de lui, dans le même commit. Un seul écrivain par fait, et un document qui
ne peut pas être en désaccord avec ce qui le décrit. Les deux moitiés sont en
place, `_metadata_object()` dans `dsw/generate_template.py` pour l'estampille
et `take_provenance()` dans le webhook pour la reprise.

Ce qui disparaît avec le fichier : la règle des clés possédées
(`OWNED = ("id", "rules")`, tout le reste recopié sans être comparé), la
comparaison sur le document analysé plutôt que sur les octets, la garde contre
un `meta.yaml` illisible, et la détection de collision. Cette dernière était de
toute façon inatteignable depuis ce dépôt seul, le dossier étant l'`id` et
l'`id` étant le nom du fichier de config. Elle n'avait pour source qu'un `id`
renommé, ce qui est arrivé une fois, à la fusion des identifiants, et a été
résolu par une migration à la main.

### Trois états, aucune faute

| état | ce que c'est | ce qui suit |
|---|---|---|
| `missing` | aucun des deux sous-répertoires | création |
| `stale` | un des deux manque | mise à jour |
| `registered` | les deux sont là | rien n'est envoyé |

Aucun des trois n'est une faute. Un dossier qui n'existe pas encore n'en est
pas une : ajouter un projet, c'est une config d'abord et un enregistrement
ensuite, et faire échouer le contrôle sur le push qui ajoute la config
apprendrait à tout le monde à ignorer ce job. Un sous-répertoire à remettre
n'en est pas une non plus, la synchronisation qui le rattrape tourne juste
après.

Ce qui fait échouer la lecture est ailleurs : une config qui ne charge pas, ou
un registre qu'on n'atteint pas avec le jeton qu'on lui a donné. C'est ce qui
reste au job `registry` de la CI, et c'est la raison de le garder : il est le
seul contrôle qui vérifie **avant** le job qui agit que le registre répond.

### Le layout du dossier est à nous, pas au webhook

`converge` dispose `template/` et `productions/`, chacun avec un `.gitkeep`,
git ne stockant pas de répertoire vide. Le webhook, lui, écrit **dans un
dossier déjà disposé** : il ne crée ni dépôt ni échafaudage, et refuse un
dossier non disposé, parce qu'un DMP déposé là serait orphelin.

Le partage des rôles est celui-là et pas un autre : ce qui *dispose* connaît la
config, ce qui *dépose* ne connaît que le nom du dossier reçu en paramètre.

Les `.gitkeep` sont donc devenus le portail, alors qu'ils n'étaient qu'un
supplément du temps de `meta.yaml`. Ce qu'ils achetaient déjà reste vrai et
reste voulu : la forme du dossier **préexiste et se voit**, avant qu'aucun DMP
n'arrive. Un dossier enregistré ressemble à ce qu'il sera.

### Un dossier, c'est les deux morceaux, pour les deux verbes

`converge` disposait trois choses et `folder_status` n'en lisait qu'une. Un
`.gitkeep` disparu donnait donc : `folder_status` → `registered`, puis
`converge` → **`unchanged` en envoyant un commit**. Le verbe répondait pour
`meta.yaml`, pas pour le dossier.

Les deux verbes lisent les mêmes morceaux, et `converge` rend son verbe
**d'après ce qu'il a envoyé**. Un sous-répertoire manquant rend `stale` côté
lecture et `updated` côté écriture. Ce n'est pas de la minutie : c'est ce qui
fait que les deux parlent du même objet, sans quoi le contrôle annonce « rien
à faire » sur un dossier que la synchro va modifier.

C'est aussi ce qui rend **vraie** la phrase sur laquelle repose le job de
synchro, « rien n'est envoyé quand rien n'a changé », écrite ici, dans
`ci.yml` et dans le README du registre. Un test la figeait à l'envers
(`unchanged` *plus* des écritures, décrit comme deux écritures indépendantes) :
une promesse contredite par le test censé la tenir.

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
poser : ils construisent le `Registry` qu'ils veulent. Le déploiement, lui,
est déclaré en variables de dépôt, `vars.REGISTRY_OWNER` et
`vars.REGISTRY_REPO`, que `ci.yml` passe aux trois jobs qui touchent au
registre. Elles étaient écrites en clair dans le workflow jusqu'au 14/08/2026,
sorties ce jour-là pour que le dépôt se porte tel quel vers une autre forge,
au prix de deux variables à créer avant le premier run.

Le raisonnement n'a pas changé pour autant : les coordonnées d'un déploiement
sont déclarées par ce déploiement, pas devinées par le code.

`REGISTRY_TOKEN` est la seule des trois à ne pas pouvoir l'être, et la seule
dont l'absence n'est pas une erreur en soi : le contrôle s'abstient, la
synchronisation refuse, et seuls eux savent lequel des deux.

### `REGISTRY_TOKEN`, et pourquoi aucun repli

Un seul nom, celui que tout le déploiement utilise, le webhook lit le même.
Localement `REGISTRY_TOKEN=$(gh auth token)`, qui ne le laisse nulle part.

**Pas de repli sur `GITHUB_TOKEN`.** Le jeton par défaut d'un workflow est
limité au dépôt qui l'exécute, jamais au registre : il ne pourrait pas faire ce
travail. Et un jeton sans accès se lit **404**, que le client traduit en « pas
de fichier » sur un GET. Le repli rapporterait donc un projet `missing` alors
que la vérité est « mauvais jeton », vert et faux exactement là où aucune
écriture ne vient contredire.

Le registre étant privé, même **lire** demande un jeton. Le contrôle s'abstient
donc bruyamment quand il n'en a pas (une PR issue d'un fork n'a pas les
secrets), la synchronisation refusant de s'abstenir.

### Un 404 GitHub n'est « fichier absent » que sur une lecture

Sur une écriture, un 404 veut dire que le dépôt ou l'accès du jeton est faux,
GitHub répond 404 plutôt que 403 pour ne pas confirmer l'existence d'un dépôt
privé, et il ne doit jamais passer pour un succès. C'est la seule asymétrie du
transport, et elle est testée dans les deux sens.

Le transport s'arrête là. Il rend et prend des **octets**, le base64 et les
codes de statut sont son affaire seule, si bien qu'aucun module de sens
n'importe `base64`. Le webhook l'importait encore avant la fusion, pour décoder
ce que sa lecture lui rendait brut : l'encodage du transport fuyait dans le
module de sens.

### Rendre compte, ou agir

Huit jobs ne font que **rendre compte** : ils tournent en parallèle, sans
`needs:`, et chacun nomme son propre fautif. Trois **agissent**, et ce sont les
trois seuls à porter un `needs:` : `registry-sync` écrit dans le dépôt du
registre, `publish` écrit dans une instance DSW, `release` pousse l'image du
webhook dans GHCR. Les deux premiers ne tournent que sur la branche par défaut
et le troisième que sur un tag. La ligne est là, et pas à « avant ou après la
validation ».

Sur une pull request il apparaît **`skipped`** : présent dans la liste des
contrôles, donc son abstention se lit au lieu de passer inaperçue.

Il tourne à **chaque** push sur la branche par défaut, pas seulement quand une
config a changé. Ce qu'il rattrape est un dossier qui n'est plus disposé, une
config ajoutée dans un push qui touchait autre chose, ou un `.gitkeep` retiré à
la main. Le prix serait un commit à chaque push, il n'est pas payé, puisque
rien n'est envoyé quand rien n'a changé.

### Le webhook est ici, et son image aussi

**Depuis le 19/08/2026 le code du webhook est dans ce dépôt**, paquet
`submission/`, à côté des règles contre lesquelles il contrôle un document. Il
a vécu dans `madmp-dsw` du 10/08 au 19/08, où il embarquait sa propre copie du
client GitHub, et les deux côtés ne partageaient alors que le *layout* du
registre. Le `README.md` du registre reste le contrat qu'ils honorent tous les
deux.

**Son `Dockerfile` l'a suivi le même jour**, et pour la même raison. Tout ce
que l'image empaquette est ici : le webhook, les règles, le moteur qui les
applique. L'entrypoint `submission.app:app` et l'extra `[submission]` qu'elle
installe sont écrits dans `pyproject.toml`, donc un `Dockerfile` posé ailleurs
est un fichier d'un autre dépôt qui casse quand l'un des deux bouge, sans que
rien ne le dise avant la construction suivante.

Ce que ça change concrètement : l'image se construit depuis le checkout et ne
lit **aucun identifiant**, là où une installation depuis un tag d'un dépôt
privé demandait un jeton et `git` dans la construction. Le déploiement, lui, ne
construit plus rien, il tire une image épinglée comme il tire déjà celles de
DSW, de Postgres et de MinIO.

**Le prix, et il est réel :** publier une correction demande maintenant un tag
ici et une CI qui pousse l'image, là où un `docker compose build` suffisait.
C'est le même arbitrage qu'au 19/08, les règles bougent rarement.

**Porte de sortie :** le paquet GHCR est privé parce que le dépôt l'est, donc
le tirer demande un `docker login ghcr.io`. La visibilité d'un paquet se règle
indépendamment de celle du dépôt, la rendre publique retirerait ce dernier
identifiant du déploiement. Non fait, pas tranché.

**État au 14/08/2026 :** l'instance visée ne fait pas encore tourner le
webhook. `publish submission` y écrit donc un service avant que quoi que ce
soit ne réponde à l'adresse qu'il annonce, ce qui est justement ce qu'il refuse
de faire quand le dossier de registre manque. C'est délibéré ici, et ce qui est
affirmé est que le service **peut être créé**, pas qu'une soumission aboutit.
Le jour où l'instance déploie le webhook, la valeur cesse d'être une promesse
sans que rien ne change dans le dépôt.

### Un contrôle a une seule forme, et quatre listes

**Fondu le 20/08/2026.** Il y avait deux formes pour la même chose :
l'enveloppe que la commande écrit dans `--json`, complète, et le `.check.json`
commité à côté du DMP, court. L'écart était historique et non conçu, l'une
avait été écrite pour être exhaustive et l'autre pour tenir en dix lignes. Un
lecteur devait donc savoir laquelle il tenait. Il n'y en a plus qu'une, produite
par `envelope()` dans `engine.py`, et les deux appelants s'en servent.

Les résultats y sont **découpés par statut**, quatre listes dans l'ordre de
gravité, `fail`, `warning`, `missing`, `pass`, au lieu d'une liste plate que
chaque lecteur refiltrait. L'invariant qui en découle est vérifiable et testé :
`len(enveloppe[statut])` vaut `enveloppe["summary"][statut]` pour les quatre.

**Ce que ça coûte, et pourquoi c'est accepté.** Sur un glider complet, le
fichier commité passe de 764 octets à 26 Ko, la seule liste `pass` pesant 70 %
du total pour dire quatre-vingt-dix fois qu'un champ est un champ. La retirer
aurait ramené l'exception qu'on venait de supprimer, et un lecteur aurait dû
réapprendre pourquoi une liste sur quatre manque. Git delta-compresse très bien
des JSON quasi identiques, une soumission inchangée ne commite rien du tout, et
`verdict` puis `summary` restent en tête du fichier, donc l'humain qui l'ouvre a
sa réponse en trois lignes.

**Deux clés ont disparu dans la fusion.** `generated_at` ne pouvait pas
survivre : un horodatage change les octets à chaque contrôle d'un document
inchangé, donc un appelant qui commite ce fichier ne pourrait plus jamais le
rapporter `unchanged`. Et `rules`, la liste d'épingles recopiée telle quelle,
cède la place à `standards` et `rules_versions`, qui disent la même chose en
mieux, `standards` portant en plus l'ordre de fusion, base d'abord puis
extensions.

Deux choses à savoir en lisant un fichier commité : `fail` y est
**structurellement vide**, un document qui échoue n'atteignant jamais le
registre, et la clé est là quand même pour qu'un lecteur qui affiche par
gravité n'ait pas de cas particulier. Et l'ordre du parcours du document, lui,
ne survit qu'à l'intérieur de chaque liste, plus entre elles. C'est l'échange
qu'on fait en triant par gravité.

### L'image s'installe depuis le lockfile, pas depuis les fourchettes

**Fermé le 20/08/2026**, et c'était une limite connue jusque-là. Le
`Dockerfile` faisait `pip install "/src[submission]"`, donc pip résolvait les
dépendances au moment de la construction, à partir des fourchettes de
`pyproject.toml`, dont la plupart n'ont pas de borne du tout. Deux
constructions du même tag, à quelques semaines d'écart, pouvaient embarquer
des versions différentes. Le `uv.lock` était commité et lu par tous les jobs
de CI, l'image était le seul endroit du dépôt qui l'ignorait.

Elle installe maintenant avec `uv sync --frozen`, en deux temps. Le premier ne
copie que `pyproject.toml` et `uv.lock` et installe les dépendances seules, le
second copie les sources et installe le projet. Deux gains d'un coup :

- **la reproductibilité.** Les versions viennent du lockfile, donc deux
  constructions d'un tag rendent les mêmes octets. Ce que le verdict commité à
  côté d'un DMP annonce sous `engine` vaut alors pour tout ce qui a jugé, et
  pas seulement pour le code de ce dépôt.
- **le cache.** La couche des dépendances ne bouge que quand le lockfile
  bouge. Mesuré : un commit qui ne touche que du code source reconstruit en
  2,4 secondes contre une réinstallation complète avant.

Trois drapeaux ne sont pas décoratifs, et chacun casse quelque chose de
différent si on l'oublie. `UV_PROJECT_ENVIRONMENT=/venv` met le venv là où
l'étage d'exécution le cherche. `--no-dev` empêche le groupe `dev`, que uv
installe par défaut, de faire entrer un lanceur de tests et un linter dans un
webhook. `--no-editable` empêche le venv de garder un chemin vers `/src`, qui
n'existe pas dans l'étage final.

**Ce que ça coûte.** Un correctif de sécurité dans une dépendance transitive
n'arrive plus par une simple reconstruction, il demande un `uv lock`, un commit
et un tag. C'est le sens voulu : ce dépôt rend des verdicts, et le jeu de
bibliothèques qui les rend doit bouger par décision. Mais c'est un devoir
d'entretien qui n'existait pas. L'image de base, elle, continue de flotter pour
les mises à jour Debian, ce sont deux couches et deux risques distincts.

### Ce que DSW montre d'une soumission, et ce qu'il jette

**Relevé le 20/08/2026**, en lisant le bundle du client de la pile locale
plutôt qu'en supposant. DSW garde trois choses par soumission, sa table
`submission` porte `state`, `location` et `returned_data`, et son client en
affiche ceci :

| état | ce que le chercheur voit |
|---|---|
| `Submitting` | un badge |
| `Submitted` | un badge, et un lien « View submission » vers l'en-tête `Location` |
| `Error` | un badge, et un lien « View error » ouvrant une fenêtre « Submission error » |

Dans la fenêtre d'erreur, le client écrit `Response Body:` puis le **corps brut
de la réponse**, sans le parser, après avoir retransformé les `\n` échappés en
vraies fins de ligne.

**D'où le texte brut sur tous les chemins de refus.** Le rendu par défaut de
FastAPI, `{"detail": "..."}`, mettrait l'emballage JSON sous les yeux du
chercheur, et un message écrit en lignes lui arriverait sur une seule. Un
gestionnaire d'exception unique dans `app.py` rend donc chaque `HTTPException`
en `PlainTextResponse`, les 400, 401, 422 et 502 compris, puisqu'ils
atterrissent tous dans la même fenêtre.

**Et d'où le message de succès qui n'est lu par personne.** Sur un `Submitted`,
le client ne rend que le lien, il ne lit `returned_data` que dans la branche
`Error`. Les trois cas d'affichage qu'on voulait au succès, avertissements ou
pas, n'ont donc nulle part où s'écrire. Le champ `message` est quand même dans
le corps du 200 : il ne coûte rien, il est en base côté DSW, il sert à tout
autre client, et le jour où DSW l'affichera il sera déjà juste. Les comptes,
eux, sont dans le `.check.json`, qui est précisément au bout du lien que le
chercheur a sous la main.

**La coupe à vingt violations.** Un document très incomplet en produit des
dizaines, cinq datasets vides en donnent vingt-sept, et la fenêtre de DSW n'est
pas un rapport. Le compte total est annoncé au-dessus de la liste et la coupe
se referme sur `[...] N more not shown`, pour qu'on ne corrige jamais vingt
violations en croyant avoir tout fait. Les avertissements suivent, dans un bloc
qui dit qu'ils ne bloquent pas, et la dernière ligne donne l'échelle, ce qui a
tenu et ce qui est resté vide.

### Trois cibles, et deux natures

`km`, `template`, `submission`. Les deux premières publient un **paquet** :
une identité, une version, immuable. La troisième modifie la **configuration
du tenant** de l'instance : mutable, upsertée par `id`, à côté des entrées des
autres projets.

Deux objets différents, donc deux idempotences différentes, par la version
d'un côté, par l'upsert de l'autre. C'est la raison d'être des trois cibles :
les fondre en une seule ferait croire à une opération unique là où il y en a
deux, qui ne se rejouent pas de la même façon.

### L'idempotence par la version

Une version de paquet DSW est immuable : republier un `package_id` déjà présent
serait rejeté. `publish` interroge donc la liste d'abord et **saute** ce qui est
là, en le disant. Conséquence voulue : passer tous les projets à chaque push sur
`main` ne coûte presque rien, et **seul un `version` incrémenté publie**. Il n'y
a pas de « republier de force », il y a une version à monter.

Vérifié le 05/08/2026 contre l'instance locale, hors mocks : deuxième
exécution, les deux cibles sautent, code de sortie 0. Revérifié le 06/08 sur
`publish all` complet, les trois cibles.

**« Déjà publié » est exact de la dernière version, et d'elle seule.**
`/knowledge-model-packages` et `/document-templates` rendent **une ligne par
`kmId`**, la plus récente. Constaté le 06/08 : `1.0.2` a disparu de la liste à
la seconde où `1.0.3` a été publiée. Rien n'est supprimé pour autant, la 1.0.2
répond toujours quand on la demande par son uuid, elle est seulement invisible
dans ce que `publish` interroge.

La conséquence est bornée. Une version ne fait que monter, donc celle qu'on
publie est toujours la dernière et la réponse est juste. Publier une version
**antérieure**, un vieux commit rejoué, se ferait répondre « pas publiée »,
tenterait l'envoi, et DSW le rejetterait : une erreur et un code de sortie 1,
pas un écrasement. Le mode dégradé est un refus, ce pour quoi il n'y a rien à
corriger : rendre la réponse exacte demanderait d'interroger l'instance version
par version pour se prémunir d'un scénario que le flux normal ne produit pas.

### La pagination n'est pas une optimisation

`list_all` suit le nombre de pages au lieu de faire confiance à une grande page.
Une liste tronquée répondrait « pas publié » à propos de quelque chose qui l'est
, et c'est cette réponse-là qui décide s'il y a republication.

### Registre avant soumission, et c'est le code qui le tient

Le webhook refuse un dossier qui n'est pas disposé. Un service de soumission
qui pointe vers un dossier non enregistré transforme donc **chaque Submit en
échec**,
et c'est le chercheur qui en porte la faute. `publish submission` appelle
`folder_status` et refuse.

Tenir ça par l'ordre des cibles serait le tenir par une convention, et une
convention, c'est ce qu'on saute quand on lance une cible à la main. L'ordre
dans la CI reste, mais il n'est plus ce qui garantit.

`stale` passe : un sous-répertoire à remettre est à un sync près, et le
dossier est là, c'est tout ce dont le webhook a besoin.

### Le service de soumission n'est pas générable

Question posée le 05/08/2026 : pourquoi n'a-t-il pas son `generate_*` ?

Parce qu'une de ses entrées n'existe pas au moment du build : `template_uuid`
est attribué par DSW et **change à chaque publication**. Un module `generate_*`
produit une fonction du commit seul, déterministe, uploadable dans
l'artefact. Celui-ci est une fonction du commit **et de l'instance vivante**.

Ce qui *peut* être décidé sans instance l'est : `submission_service()` est une
fonction pure qui rend le dict, testée sans rien joindre, et
`publish_submission()` fait les appels. La séparation existe, comme frontière
de fonction, un fichier de plus la redirait sans l'ajouter.

### Le scopage : deux choses le rendent propre à un projet

Le dossier dans l'URL (`?project=<id>`), **seule** entrée de routage dont le
webhook dispose, jamais la lecture du document, et `supportedFormats` nommant
le template de ce projet, pour que le menu Submit propose ce service aux
documents de ce projet et à rien d'autre.

### Le service n'est réécrit que s'il dirait autre chose

Décidé le 05/08/2026. L'API n'a pas de point de terminaison pour *un* service :
écrire le nôtre, c'est renvoyer la configuration **entière** du tenant,
organisation, authentification, apparence. Tout ce qui a changé dans la console
entre la lecture et l'écriture est donc réverti sans un mot. `submission_service()`
étant pure, la comparer à ce que l'instance détient déjà suffit : égale et les
soumissions activées, on n'envoie rien. La fenêtre ne s'ouvre plus que sur les
exécutions qui avaient quelque chose à changer, et l'écrasante majorité n'a
rien à changer, une version de template inchangée gardant le même uuid.

L'état `enabled` compte dans la comparaison : un service que personne ne peut
joindre parce que les soumissions sont désactivées, c'est un bouton Submit qui
n'est pas là.

#### Ce qu'on compare, c'est ce qu'une écriture porte

Le garde-fou ci-dessus **ne se déclenchait jamais**, et c'est le contraire d'une
comparaison trop laxiste : elle était inatteignable.

Un `GET /tenants/current/config` rend le service tel qu'il est **stocké**, un
`tenantUuid` sur le service et un sur chaque `supportedFormats`, le `serviceId`
répété dans le format, `createdAt` et `updatedAt`. Le `PUT` prend un
`TenantConfigChangeDTO`, qui n'a aucun de ces champs. Neuf clés d'un côté, six
de l'autre : `current == service` ne pouvait pas être vrai, donc **chaque
exécution écrivait**, donc chaque exécution rétablissait ce que la console avait
changé depuis le `GET`. Vérifié contre `engine-backend` au tag `v4.31.0`.

Deux corrections, et la seconde est la vraie :

1. `submission_service()` ne produit plus que ce qu'une écriture porte, plus de
   `tenantUuid`, plus de `serviceId` dans le format. Un champ que l'API ne lit
   pas n'est pas un champ qu'on envoie. Le paramètre `tenant_uuid` disparaît
   avec, et avec lui la recherche qui allait le chercher dans un autre service.
2. `installed_service()` relit ce que l'instance rend **à travers ce contrat**,
   et c'est cette réduction qu'on compare. Un champ que l'instance a apposé
   n'est pas un champ sur lequel cette exécution a un avis, donc pas un champ
   d'où lire un désaccord.

**Pourquoi le test ne le voyait pas.** Le faux instance rendait exactement la
sortie de `submission_service()`, c'est-à-dire ce que le code écrit, pas ce que
DSW rend. Un double qui se met d'accord avec le code sur une forme dont ni l'un
ni l'autre n'est propriétaire ne teste plus rien. Il passe maintenant par
`as_dsw_returns_it()`, et deux tests tiennent les deux moitiés ensemble :
`installed_service(submission_service(...)) == submission_service(...)`, pour
qu'un champ ajouté d'un côté et oublié de l'autre ne puisse pas retomber hors
de la comparaison.

### Publier consomme l'artefact, il ne régénère pas

Décidé le 05/08/2026. Le job `publish` retélécharge ce que `generate` a
construit dans le même run. Une seule définition de « ce que ce commit
produit », et ce qui part dans DSW est ce qui a été produit une fois, pas une
seconde construction que personne n'a regardée.

L'alternative, régénérer dans le job, rendait `publish` autonome, mais ne
donnait **aucun artefact** tant qu'il est `skipped` faute d'instance, c'est-à-
dire aujourd'hui et pour un moment.

**Ne pas construire n'est pas ne pas vérifier.** Un bundle porte son propre
`package_id`, et son nom de fichier ne porte **pas** de version : `glider_km.km`
et rien de plus. Une `version` incrémentée sans régénérer laisse donc l'ancien
bundle exactement là où le nouveau irait, et rien en aval ne le rattrape : la
liste est interrogée sur le **nouvel** id, répond « pas publié », et c'est
l'**ancien** bundle qui monte, sous la version avec laquelle il a été
construit. L'exécution imprime alors un succès qui ne nomme ni la version
demandée ni celle qu'elle vient de publier.

`_artifact()` confronte donc les deux avant tout téléversement. Cette étape
étant celle qui n'a pas de retour arrière, l'ordre des commandes n'est pas
quelque chose sur quoi on se repose : on regarde.

### Aucune coordonnée n'a de défaut, et pas toutes au même moment

Les cinq noms sont lus sans défaut : un point de terminaison par défaut, ce
sont les coordonnées d'un déploiement gravées dans tous les autres. Et à la
différence d'un mauvais registre, une mauvaise instance n'est rattrapée par
rien en aval, elle accepte le paquet et personne n'en sait rien.

`DSW_API_URL` / `DSW_EMAIL` / `DSW_PASSWORD` disent quelle instance et en tant
que qui : les trois sont exigés ensemble, et l'erreur les nomme **tous d'un
coup**. `SUBMISSION_URL` et `SUBMISSION_TOKEN` ne sont pas des coordonnées de
l'instance mais celles du webhook, donc seule la cible qui en a besoin les
réclame, publier un KM ne doit pas exiger de savoir où les documents seront un
jour envoyés.

**`SUBMISSION_URL` contient la route.** `publish` n'y ajoute que
`?project=<id>` : contre la pile locale c'est
`http://submission:8080/submissions`, nom de service compose **et** chemin que
`submission/app.py` expose. Omettre le chemin écrit un service qui poste sur la
racine du conteneur, un bouton Submit qui 404, écrit par-dessus un qui
marchait, sur une valeur que rien en aval ne peut contrôler. Le piège a été
tendu et évité le 06/08/2026 : c'est en relisant le service **stocké** avant
d'écrire que l'écart s'est vu.

Le secret est exigé autant que l'adresse, corrigé le 05/08/2026. Le code le
disait facultatif au motif qu'« un webhook déployé sans secret accepte les
appels non authentifiés » : ce déploiement n'existe pas. Le webhook de
`madmp-dsw` refuse de démarrer quand il n'en détient aucun, les quatre variables
étant lues au démarrage, et répond **401** quand l'en-tête ne correspond pas
([`submission/app.py`]). Un service écrit sans secret est donc un bouton Submit
qui échoue à tous les coups, et il serait écrit *par-dessus* un service qui
marchait, sur la seule absence d'un nom dans une exécution. Même
faute que le repli sur `GITHUB_TOKEN` : un cas d'usage justifié par un mécanisme
inexistant.

---

## 11. Le déploiement DSW

Le dépôt `ostrails-madmp-dsw` fait tourner une instance Data Stewardship Wizard
4.31 et le webhook de soumission à côté d'elle. Il part de l'[exemple de
déploiement officiel](https://github.com/ds-wizard/dsw-deployment-example) à sa
version 4.31, gardé en remote `upstream` pour comparer les versions suivantes,
jamais pour les fusionner.

Ce qui suit était dans un `TECHNICAL_GUIDE.md` de ce dépôt jusqu'au 19/08/2026.
Il a été rapatrié ici : les décisions du projet vivent dans un seul document, et
chaque dépôt ne garde qu'un `README.md` qui dit son fonctionnement.

Tout ce qui est donné comme une mesure a été observé sur ce déploiement.

### Le périmètre : un déploiement, et rien d'autre

Pas de règles maDMP, pas de contrôle qualité, pas de code applicatif, et depuis
le 19/08/2026 pas même un `Dockerfile`. Le webhook qui reçoit un document rendu,
le contrôle et le commite vit ici, dans `madmp-core`, qui construit et publie
aussi son image, et le déploiement nomme un tag de celle-ci. Il a porté ce code
du 10/08 au 19/08/2026, et le lui avoir rendu, image comprise, est ce qui rend
cette frontière vraie plutôt qu'à peu près vraie.

Le test de la frontière est simple : **rien là-bas n'a à changer quand le
webhook change.** Un moteur plus récent ou des règles plus récentes, c'est une
valeur dans `.env`.

### La configuration passe par l'environnement

DSW résout un réglage depuis l'environnement d'abord, puis son fichier de
configuration, puis un défaut compilé dans l'image. Cet ordre est ce qui rend
un `application.yml` inutile, et s'en passer est la décision la plus lourde de
conséquences de ce dépôt.

**Pourquoi elle compte :** l'exemple livré par DSW met des **secrets de
signature fonctionnels dans un dépôt public**. Une instance qui les garde peut
se voir forger un jeton valide par quiconque a lu cet exemple. Passer par
l'environnement donne aux secrets exactement un domicile, `.env`, qui est
gitignoré.

L'image porte quand même son propre `application.yml` en dessous, et ses défauts
ne sont pas neutres : il nomme la base `wizard` là où ce déploiement utilise
`engine-wizard`. Toute valeur qui compte est donc posée explicitement plutôt que
laissée à un repli.

Il n'y a **aucun `:-default` dans `docker-compose.yml`**. Un défaut écrit là
serait un second domicile pour une valeur dont le domicile est `.env.example`,
libre d'en diverger.

### `.env` se remplit à la main

Aucun script n'écrit un secret. `.env.example` porte, à côté de chaque valeur
vide, ce qu'elle est et la commande qui la produit.

L'exemple ne livre **jamais un secret fonctionnel, ni un mot de passe
bouche-trou**. « Vide » est ce qui force un choix : une valeur dans l'exemple
est une valeur que chaque déploiement hérite en silence, et l'un d'eux ferait
tourner son stockage objet sur un mot de passe publié dans un dépôt git.

Trois contraintes de ce fichier sont mesurées et non supposées :

- MinIO refuse de démarrer sur un mot de passe de moins de 8 caractères, et
  nomme la variable quand il en manque une.
- `GENERAL_SECRET` doit faire exactement 32 caractères ASCII, ce que produit
  `openssl rand -hex 16`.
- La clé RSA est la seule valeur multi-lignes, et elle doit être collée entre
  guillemets doubles. Sans eux, compose lit chaque ligne suivante comme une
  nouvelle variable et refuse le fichier entier, donc **aucune** des vingt
  valeurs n'est lue. C'est le seul contrôle qui attrape ça, aucune clé prise
  isolément n'a l'air fausse.

### Le fichier compose

**Nom de projet épinglé.** Les noms de conteneurs, de volumes et de réseau
survivent au renommage du dossier.

**Volumes nommés.** Sans eux, `docker compose down` détruit la base et le
bucket.

**Le healthcheck du serveur est redéfini.** L'image DSW en livre un avec un
intervalle de 300 secondes et sans période de démarrage. Docker ne lance le
premier contrôle qu'après un intervalle complet, donc le conteneur ne peut pas
se déclarer sain en moins de cinq minutes quelle que soit sa vitesse de réponse,
et une panne met jusqu'à cinq minutes à se voir. Mesuré, depuis une base vide :

| | |
|---|---|
| avec le healthcheck de l'image | 307 s |
| avec le nôtre, intervalle 10 s et période de démarrage 300 s | **12 s** |
| les 67 migrations elles-mêmes | 7 s |

Les migrations ne sont pas le coût.

**Postgres a aussi un healthcheck**, pour que `server` et `docworker` attendent
une base qui répond plutôt qu'un conteneur qui existe. Il utilise
`pg_isready -h 127.0.0.1` : par la socket unix, le serveur temporaire que lance
`initdb` répond déjà, et le contrôle passerait au vert avant que la base
n'accepte une seule connexion TCP.

**`platform: linux/amd64` sur le serveur seul.** Vérifié contre les manifestes
publiés : `wizard-server:4.31` est amd64 uniquement, alors que `wizard-client`,
`document-worker` et `mailer` sont multi-architecture avec une variante arm64.
Ajouter la ligne aux trois autres les met en émulation pour rien, la retirer du
serveur le casse sur une machine ARM.

**`createbucket` est un service compose sous un profil.** DSW ne crée pas son
bucket : dans l'API S3, `CreateBucket` et `PutObject` sont deux opérations
distinctes, et écrire dans un bucket absent rend `NoSuchBucket`. Un service
compose connaît son propre réseau, lit `.env` et résout `${MC_VERSION}`, là où
un script shell devrait deviner les trois. Le profil le garde hors de `up`, qui
traiterait sinon une tâche unique comme un service qui n'arrête pas de s'arrêter.

**Le mailer est présent mais commenté.** Le mail étant désactivé, il n'a rien à
traiter. Ce que ça coûte : ni réinitialisation de mot de passe ni invitation par
courriel, deux choses déjà impossibles sans mail. À décommenter **en même temps**
qu'on active le mail, faute de quoi le serveur empile des commandes que personne
ne traite pendant que l'interface annonce les messages comme envoyés.

**`engine-wizard` est à la fois le nom de la base et celui du bucket, et c'est
une coïncidence.** Ce sont deux espaces de noms sans rapport, et l'image le
prouve : son propre défaut pour la base est `wizard`. L'un se renomme sans
l'autre.

**Tout est lié à `127.0.0.1`.** Publier sur `0.0.0.0` expose le service à tout
le réseau où la machine se trouve, et sous Linux contourne `ufw` entièrement.

**Il n'y a pas de surcharge nginx pour le client.** L'image cliente redirige `/`
vers une adresse absolue en `http://`, construite depuis le protocole que nginx
écoute lui-même, ce qui casse derrière un terminateur TLS. Masquer le fichier de
configuration de l'image pour réparer une seule adresse coûte plus que ça ne
répare : derrière un proxy, la redirection appartient au proxy, avec
`proxy_redirect http:// https://`.

### Le script de mise en route

Il rapporte la configuration, puis lance deux commandes. Il n'écrit rien, ce qui
est ce qui le rend rejouable sans un seul contrôle d'idempotence.

Il rapporte la valeur **que compose utilisera**, pas celle de `.env` :
l'environnement l'emporte sur ce fichier, donc lire le fichier seul annoncerait
une valeur que les conteneurs ne voient jamais. Les secrets sont rapportés comme
`set`, jamais imprimés, et les valeurs qui n'en sont pas sont imprimées en
entier, parce que c'est là qu'une URL de portable oubliée dans le `.env` d'un
serveur devient visible.

Il s'arrête avant de démarrer quoi que ce soit quand une valeur manque, et les
nomme toutes d'un coup.

Rien n'y attend l'API : `up --wait` rend la main quand les healthchecks passent,
soit la même information obtenue de ce qui la connaît déjà.

Le `.gitignore` couvre `.env.*` et pas seulement `.env`, parce qu'un second
fichier d'environnement est la chose naturelle à créer quand on déploie vers
deux cibles, et qu'il porte les mêmes secrets.

### Le webhook, vu du déploiement

Ce qui reste là-bas, c'est le déploiement : le service compose, les quatre
variables qu'il passe, et le healthcheck. C'est la même ligne que pour tous les
autres services de ce fichier.

**Les quatre variables ne peuvent pas venir d'ici.** Ce sont l'environnement
d'un conteneur qui tourne, et seul ce qui lance le conteneur peut le fournir.
Deux d'entre elles sont des secrets, qui n'ont leur place dans aucun dépôt. Les
deux autres sont des coordonnées, qui pourraient avoir un défaut dans l'image,
mais ça collerait une image publiée à un registre unique alors qu'elle est faite
pour être tirée par n'importe quel déploiement.

**`REGISTRY_` plutôt que `GITHUB_`.** Compose laisse le shell l'emporter sur
`.env`, et `GITHUB_TOKEN` est un nom que le shell d'un développeur porte très
souvent déjà. La collision ferait commiter le webhook avec les identifiants de
quelqu'un d'autre, en silence.

**Le HTTPS sortant vers `api.github.com`** est la seule chose que ce déploiement
fait à l'exécution qui sorte de l'hôte. Tout le reste parle sur le réseau
compose, `ghcr.io` n'étant joint que lorsqu'une image est tirée.

### L'image n'est pas construite là-bas

Le compose nomme `ghcr.io/pstcricq/ostrails-madmp-core/submission:${MADMP_CORE_VERSION}`
et la tire, exactement comme il tire les trois images DSW, Postgres et MinIO. Le
service de soumission était le seul `build:` de ce fichier, il ne l'est plus.

Le raisonnement du déplacement est au §10, [Le webhook est ici, et son image
aussi](#le-webhook-est-ici-et-son-image-aussi). Ce qu'il change **pour le
déploiement** :

**Ce qu'il gagne.** Aucune construction, donc pas de `git`, pas de secret
BuildKit, et pas de jeton qui lit un dépôt de *code source* privé, ce qui est
strictement plus qu'un déploiement n'a jamais eu besoin de détenir.
`MADMP_CORE_VERSION` passe d'un `ARG` dans un `Dockerfile` à `.env`, à côté des
cinq autres versions d'images, là où une épingle de version a sa place et là où
le script de mise en route la rapporte déjà.

**Ce qu'il coûte.** Publier une correction demande maintenant un tag ici et un
run de CI, là où un `docker compose build submission` suffisait.

**Le paquet est privé**, parce que le dépôt l'est, donc un hôte doit faire
`docker login ghcr.io` une fois avec un jeton portant `read:packages`. Un hôte
qui ne l'a pas fait échoue le pull sur un 401 qui se lit comme si l'image
n'existait pas. La visibilité d'un paquet est un réglage à part, distinct de
celle du dépôt, donc la rendre publique retirerait le dernier identifiant dont
un déploiement a besoin pour se lever. Non fait, non tranché.

### Ce que la CI de ce dépôt peut dire

Trois contrôles, tous sur les fichiers de déploiement : `docker compose config`
contre `.env.example`, `shellcheck` sur le script, et `actionlint` sur les
workflows.

La distinction est délibérée. Une CI peut dire si les fichiers de déploiement
**parsent et se résolvent**. Elle ne peut pas dire si un déploiement est
**correct**, ce qui ne se voit que sur un vrai hôte. Prétendre le contraire
serait pire que ne rien vérifier.

Ce que ces contrôles n'attrapent pas, mesuré le 19/08/2026 : `docker compose
config` sort 0 sur une variable que `.env.example` ne porte pas, il se contente
d'avertir et substitue une chaîne vide. Ce qui refuse là-dessus, c'est le script
de mise en route, sur la machine qui déploie.

### Ce qui reste ouvert

- **`S3_URL` derrière un proxy.** Le navigateur récupère les documents
  directement depuis MinIO par une URL présignée, donc MinIO a besoin d'une
  adresse publique. Un sous-domaine évite de réécrire des chemins, MinIO mettant
  le nom du bucket dans le chemin. C'est la seule des trois URL qui ne découle
  pas des autres.
- **Postgres ou S3 managés.** Si l'infrastructure fournit l'un des deux, le
  changement n'est pas une valeur dans `.env` mais le retrait de services du
  fichier compose.
- **Un reverse proxy sur une autre machine.** Tout est lié à `127.0.0.1`, ce qui
  convient à un proxy sur le même hôte. Autre chose veut élargir la liaison et
  laisser un pare-feu prendre le relais.

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
venant *pas* d'une config validée. L'enregistrement au registre n'en est plus
un, il n'écrit aucune épingle depuis le 18/08/2026. Le candidat reste le
contrôle qualité, qui lira celles qu'un DMP soumis porte avec lui, un fichier
sans **aucun** schéma que personne ne valide en entrant, mais il est repoussé
sans date, et le correctif se décide avec son appelant sous les yeux : une
passe de forme dans `resolve_pins`, ou un schéma pour ce fichier.

### La roue embarque ses fichiers de données, depuis le 19/08/2026

Elle ne les embarquait pas. `[tool.setuptools.packages.find]` déclare les
paquets, mais setuptools n'embarque que les `.py` tant que le reste n'est pas
déclaré à part, donc une roue construite depuis une copie vierge ne contenait
**ni JSON ni YAML** : elle s'importait, puis mourait au premier appel réel sur
`FileNotFoundError: .../site-packages/rules/rules.schema.json`.

C'était noté « latent, et destiné à le rester », l'unité d'exécution étant le
dépôt cloné et non la roue. **Le déclencheur prévu s'est produit** : le webhook
de soumission entre dans ce dépôt et sera installé depuis lui, sans `-e`, dans
l'image qui tourne à côté de DSW. Il lui faut les règles pour contrôler un
document, donc il lui faut la roue complète.

Le correctif tient dans ce qui avait été prévu, `[tool.setuptools.package-data]`
avec un glob par niveau de répertoire, ceux-ci ne traversant pas. Vérifié
autrement que par la construction, seule preuve qui vaille : roue installée
dans un venv neuf, `cd /` hors de tout checkout, fusion des deux standards et
contrôle d'un document, 163 champs et 21 contrôles.

Ce qui n'entre pas dans la roue et ne doit pas y entrer : `configs/projects/`,
qui est la donnée du dépôt et non du paquet. Un appelant passe le chemin de la
config qu'il veut.

**Deux pièges pour qui vérifiera**, tous deux donnant un faux succès :
setuptools **ne nettoie jamais `build/`** entre deux constructions, donc des
fichiers d'un empaquetage antérieur survivent dans les roues suivantes, et
`uv build` sans `--no-cache` rend une roue antérieure au changement.

### Rien ne confronte les artefacts générés à une vraie instance DSW

Deux constantes décrivent l'instance visée et non le projet :
`METAMODEL_VERSION = 20` et `TEMPLATE_METAMODEL_VERSION = "18.0"` (§6). Rien
dans le dépôt ne vérifie qu'une instance donnée les accepte, ni que le Jinja
émis se rend réellement. Ce qui est vérifié : le corps **parse**, pour chaque
projet (§7), et les tests le **rendent** avec les trois filtres de DSW
(`reply_path`, `reply_str_value`, `reply_items`) **remplacés par des
doublures**. Un désaccord sur ce que fait un de ces filtres ne se verrait donc
qu'à l'exécution, dans DSW, devant un chercheur.

Le bundle KM, lui, est conforme au schéma `kmp_schema_v20.json` : vérifié le
06/08/2026 contre le fichier officiel, zéro erreur, et tenu par un test qui
énumère les champs du métamodèle (§6). Mais c'est le schéma qui est confronté,
pas l'instance.

**Pourquoi on s'en tient là :** une instance est bien atteignable depuis la CI,
celle de Miguel, et le job `publish` l'a exercée de bout en bout. Mais elle est
encore en développement : elle ne répond pas à tous les coups et ne conserve
pas les paquets publiés. Un test qui en dépendrait serait rouge pour des
raisons étrangères à ce dépôt, ce qui est la pire espèce de test.

**Déclencheur pour rejuger :** cette instance stabilisée. La question devient
alors « publier puis rendre un DMP de test » plutôt que « imiter les filtres
mieux ».

### Le format des fichiers de données n'est pas vérifié

`ruff format` ne touche ni au JSON ni au YAML, donc rien en CI ne contrôle la
mise en forme de `rules/standards/*.json` ni de `configs/projects/*.yaml`,
seulement leur contenu, via `scripts/validate_rules.py` et
`scripts/validate_configs.py`.

**Pourquoi on n'ajoute pas `prettier --check` :** il faudrait Node dans une CI
purement Python, donc un `package.json`, un lockfile npm et un cache, un
deuxième système de dépendances. La version `npx --yes` l'évite mais tire une
version non épinglée à chaque run, ce qui réintroduit exactement le problème
que `uv sync --frozen` règle. Le coût est réel, l'enjeu est cosmétique.

**Déclencheur pour rejuger :** quelqu'un d'autre que Pierre édite les fichiers
de règles, ou un diff de règle devient pénible à relire à cause du bruit de
format. À ce moment-là, un `.prettierrc` versionné (trois lignes, zéro seconde
de CI) répond au premier cas, le check CI ne se justifiant que si le format
dérive vraiment malgré ça.

### Le contrôle qualité ne juge jamais deux valeurs ensemble

Chaque valeur est contrôlée seule, contre la règle qui la déclare. Rien ne
compare deux valeurs entre elles, donc deux datasets de même titre passent,
deux distributions qui pointent la même `access_url` aussi, et un `modified`
antérieur à `created` ne dit rien. Il n'y a pas non plus de règle
conditionnelle, du genre « si `ethical_issues_exist` vaut `yes` alors
`ethical_issues_description` devient requis ».

C'est une limite du **format des règles** avant d'être une limite du moteur.
Un fichier de règles décrit un arbre de champs, chacun portant sa cardinalité,
son type et ses vocabulaires, et il n'a aucun moyen de parler d'un autre champ
que lui-même. Les lever demanderait donc d'inventer cette expression dans
`rules.schema.json` d'abord, et un second parcours du document ensuite, un
contrôle croisé ne pouvant pas se rendre pendant la descente qui le découvre.

Constaté le 20/08/2026, et accepté tel quel : ce que le QC garantit
aujourd'hui, champ par champ, est ce qu'on lui demande.

### Un fichier de plus d'1 Mo ne se lit pas

L'API Contents de GitHub inline le contenu d'un fichier jusqu'à 1 Mo et répond
un `content` vide au-delà, et c'est cette lecture qui compare une soumission à
ce que le registre détient. **La lecture lève** plutôt que de rendre ce vide,
depuis le 20/08/2026, donc un DMP de cette taille fait échouer la soumission.
Avant, le webhook ne le trouvait jamais égal à ce qu'il détenait et le
recommittait à chaque envoi en rapportant `updated`, sans que rien ne le
signale. La dégradation silencieuse est devenue un échec, ce qui n'est pas la
même chose qu'une garantie.

Seule la lecture est concernée, un commit porte ses fichiers en entrées
d'arbre et n'a pas cette limite.

### Rien n'empêche de republier un tag déjà publié

GHCR accepte un push sur un tag existant et l'écrase sans rien dire. La règle
« un tag publié ne se réécrit pas » est donc tenue à la main, pas par un
contrôle. Deux déploiements épinglant `v1.0.0` tourneraient alors sur des codes
différents en annonçant la même version, et le verdict commité à côté de chaque
DMP porterait ce numéro-là des deux côtés.

Ce qui limite les dégâts : `version` refuse depuis le 20/08/2026 un tag qui ne
dit pas ce que dit `pyproject.toml`, donc republier `v1.0.0` demande que la
version du paquet soit restée `1.0.0`, c'est-à-dire que rien n'ait été relâché
entre-temps. Le cas qui passe encore est le retag d'un même numéro sur un autre
commit.

Fermer le trou demanderait une étape qui interroge GHCR avant de pousser et
refuse un tag déjà là. Pas construit, la discipline suffit à un dépôt à un
seul auteur, et le jour où ce n'est plus le cas c'est cette étape qu'il faut.

### Le webhook n'a ni reprise ni gestion du quota

GitHub répondant 403 ou 429 ressort en 502 vers DSW. Acceptable pour une
instance qui soumet occasionnellement.

### `api_url` du client GitHub est paramétrable et inutilisé

Il permettrait GitHub Enterprise. Rien ne le passe, les tests compris.

### Les comptes de démonstration sont une étape manuelle

DSW en sème trois dont les identifiants sont publiés. Le script de mise en route
avertit tant qu'ils répondent, et c'est tout ce qu'il fait.
