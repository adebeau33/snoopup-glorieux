# Billetterie et contrôle d’accès — BDE Glorieux

Version du 14 novembre 2026. Document de référence avant développement.

Ce document rassemble les demandes validées et les propositions nécessaires à leur réalisation. Les propositions et décisions restantes sont explicitement indiquées. État initial : aucun développement ni déploiement à la première rédaction. Voir la section « État de livraison » pour l’état actuel.

## 1. Objectif et périmètre

Créer une application web Bootstrap, responsive sur téléphone et ordinateur, pour organiser des soirées : inscription, paiement SumUp, émission de billets nominatifs PNG et PDF, distribution par SMS et contrôle des entrées avec la caméra d’un téléphone sans application à installer.

Projet courant : `/Users/alban.debeaupuis/script/BDE`. Cible d’installation demandée : `~/digi2`. Le chemin absolu, la machine cible et les modalités de déploiement restent à confirmer avant intervention hors du projet courant.

Logo source : `IMG_2559 2.PNG`. Détourer l’écusson et fournir un fichier transparent ; reprendre les couleurs bleu marine et or. La qualité est limitée par la capture source ; un original pourra la remplacer.

## 2. Rôles et interfaces

| Rôle | Accès |
| --- | --- |
| Superadmin | Le propriétaire du système, c’est-à-dire le demandeur. Accès à toute l’application, gestion des administrateurs, rôles, paramètres techniques et intégrations. |
| Administrateur | Interface complète de gestion : utilisateurs opérationnels, événements, participants, commandes, paiements, billets, envois SMS, contrôles et statistiques. |
| Organisateur | Gestion des événements auxquels il est affecté, de leurs commandes et de leurs équipes de contrôle. |
| Valideur | Scanner et contrôler uniquement les billets des événements pour lesquels il est autorisé. |
| Client / participant | Inscription et accès sécurisé à ses propres billets. |

Proposition de séparation : les administrateurs ont accès à toutes les fonctions métier, mais seul le superadmin crée des administrateurs, attribue ce rôle et modifie les secrets ou la configuration technique. Aucun administrateur ne peut retirer les droits du superadmin ni se promouvoir lui-même.

Tous les droits sont vérifiés côté serveur, y compris pour les téléchargements et les appels directs aux API. Le masquage d’un bouton ne constitue pas une protection.

### Interface d’administration

- Tableau de bord : ventes, montants payés, places disponibles, entrées et échecs d’envoi.
- Gestion des événements : code d’accès, nom, description, date, heure, fuseau horaire, lieu, adresse, prix, jauge et périodes de vente.
- Gestion des comptes, rôles, affectations et appareils des valideurs.
- Recherche des participants, commandes et billets ; filtres par événement et état.
- Suivi SumUp : référence de paiement, montant, devise et état vérifié.
- Correction contrôlée des coordonnées et relance des SMS.
- Annulation et réémission des billets avec historique ; l’ancien billet devient inutilisable.
- Historique des scans et actions sensibles, avec auteur et date.
- Export des listes et statistiques, réservé aux rôles autorisés.

Le périmètre exact des remboursements dans l’interface reste à décider avant implémentation ; une annulation de billet ne vaut pas remboursement bancaire.

## 3. Inscription et commande

1. L’acheteur saisit le code d’événement fourni par l’organisation.
2. Il choisit le nombre de places.
3. Il renseigne chaque participant : nom, prénom, téléphone obligatoire et classe.
4. Le site présente les bénéficiaires, les coordonnées, le tarif et le montant total avant paiement.
5. Le serveur réserve temporairement les places et initie le paiement.

Une commande peut contenir plusieurs participants et donne lieu à un paiement global. Chaque place correspond à un billet individuel et un QR code unique ; les participants peuvent arriver séparément.

Un numéro distinct est obligatoire par participant. Les numéros sont normalisés au format international pour reconnaître les doublons (`06…` et `+33 6…`). Proposition : un seul billet actif par numéro et par événement, y compris entre commandes différentes ; réutilisation possible pour un autre événement. La politique après annulation ou remboursement doit permettre un nouvel achat légitime.

Le code d’événement limite l’accès à l’inscription ; il n’accorde aucun droit d’administration ou de validation.

Mise à jour validée : l’étudiant crée un compte avec nom, prénom, adresse email et téléphone obligatoires. Les adresses dont le domaine exact n’est pas `grandlebrun.com` sont refusées côté serveur. Comparer le domaine sans tenir compte de la casse après validation syntaxique ; refuser les domaines ressemblants et sous-domaines non autorisés.

Un code à usage unique est envoyé par SMS au téléphone pour valider le compte. Proposition : code de 6 chiffres, valable 5 minutes, 5 essais maximum, renvoi après 60 secondes et quotas par téléphone et adresse IP. Le code est lié au compte et au téléphone, stocké sous une forme protégée, invalidé après succès ou remplacement, et jamais journalisé. Un changement de téléphone nécessite une nouvelle validation. Les comptes ne peuvent ni réserver de place ni passer au paiement tant que le téléphone ET l’email scolaire ne sont pas vérifiés.

Double vérification obligatoire validée : le code SMS confirme le téléphone et un lien de vérification à usage unique envoyé à l’adresse `@grandlebrun.com` confirme l’email scolaire. Les deux validations doivent être acquises avant toute réservation. Le lien email doit expirer, être stocké sous une forme protégée et être invalidé après utilisation ou remplacement. Le renvoi est limité. Modifier l’email ou le téléphone invalide la vérification correspondante et bloque les nouvelles réservations jusqu’à sa nouvelle validation ; ne pas annuler automatiquement les billets déjà payés.

L’achat pour plusieurs personnes reste disponible. À préciser : chaque bénéficiaire doit-il posséder un compte validé avant paiement, ou l’acheteur peut-il renseigner un bénéficiaire qui finalisera sa validation ensuite ? Prévoir l’email scolaire obligatoire pour chaque bénéficiaire si tous doivent être étudiants de l’établissement. La méthode de connexion après inscription reste à choisir.

## 4. Paiement SumUp

Approche recommandée : page de paiement hébergée par SumUp. Alternative : formulaire SumUp intégré, qui ajoute du travail d’intégration. Le choix recommandé reste à approuver.

- Créer le paiement côté serveur, avec montant calculé depuis les tarifs enregistrés, devise et référence unique de commande.
- Conserver la correspondance entre commande et paiement SumUp.
- Rediriger l’acheteur vers SumUp ; aucune donnée bancaire brute ne transite dans l’application.
- Après notification ou retour de paiement, vérifier le statut auprès de l’API SumUp, la référence, le montant et la devise.
- Émettre les billets uniquement après confirmation du paiement attendu.
- Traiter les notifications répétées sans créer de doublons.
- Prévoir une réconciliation des paiements restés en attente après une interruption technique.
- Ne pas dépendre du retour de l’acheteur sur le site pour délivrer les billets.

Les places réservées sont libérées à expiration si le paiement n’est pas confirmé. Proposition : aligner la réservation sur l’expiration du paiement et gérer explicitement les confirmations tardives pour éviter une vente au-delà de la jauge.

Le compte marchand n’est pas encore fourni. Les identifiants seront transmis dans un fichier de configuration privé. Fournir un fichier exemple sans secrets ; exclure la configuration réelle du dépôt et des fichiers publics. Ne jamais afficher les clés dans les interfaces ou journaux.

Références :
- https://developer.sumup.com/online-payments/checkouts/hosted-checkout/
- https://developer.sumup.com/online-payments/webhooks/

## 5. Billets PNG et PDF

Chaque participant reçoit son billet dans les deux formats, avec le même identifiant et le même QR code. L’utilisation d’un format rend l’autre inutilisable pour une seconde entrée.

Informations sur chaque billet :
- Logo et identité de l’organisation.
- Nom et prénom du participant.
- Prix effectivement payé pour cette place, avec devise.
- Nom de l’événement.
- Date et heure de l’événement, lieu et adresse complète.
- Numéro de billet et QR code lisible.
- Mentions de participation et de prévention.

Le PNG est adapté à la consultation sur téléphone et à l’enregistrement dans les photos. Le PDF est adapté à l’archivage et à l’impression. Préserver une zone blanche autour du QR code et vérifier sa lisibilité à l’écran et sur papier.

Mentions demandées ou proposées :
> Billet personnel — valable pour une seule entrée.
> Ne partagez pas votre billet ni son QR code.
> Ne pas déposer sur la voie publique.
> L’abus d’alcool est dangereux pour la santé. À consommer avec modération.
> Prévoyez votre retour : désignez un SAM, un conducteur qui ne boit pas.

La mention demandée « SAM obligatoire » reste à préciser : obligation par groupe venant en voiture, déclaration à l’inscription et éventuel contrôle à l’entrée. Ne pas présenter une règle non définie comme une condition d’accès. Ces mentions ne constituent pas une liste exhaustive d’obligations réglementaires ; leur version finale dépendra des conditions réelles de la soirée.

## 6. Distribution par SMS

Un SMS classique ne contient pas de pièces jointes PNG ou PDF. Chaque participant reçoit donc directement sur son numéro un lien sécurisé donnant accès à ses deux formats.

- Lien non devinable et transmis en HTTPS.
- Téléchargements accessibles sans compte, via un jeton secret distinct de l’identifiant public utilisé dans le QR code.
- Le scan public du QR code ne doit jamais donner accès au PDF nominatif.
- Suivi des envois et des échecs ; les états de livraison disponibles dépendront du prestataire SMS.
- Relances contrôlées, sans recréer de billet ni multiplier les messages sur notification de paiement répétée.
- Une panne SMS ne transforme pas une commande payée en commande impayée.
- En cas de correction du téléphone, possibilité de révoquer les anciens liens et de réémettre le billet si nécessaire.

Prestataire SMS, budget, durée de validité des liens et politique de renvoi à choisir.

## 7. QR code et protection du billet

Le QR code contient une URL HTTPS avec un identifiant aléatoire non devinable et une signature. Proposition : HMAC-SHA-256 avec secret exclusivement côté serveur, couvrant au minimum l’identifiant du billet, l’événement, le prix en centimes et la devise. Un simple hash SHA du prix n’est pas suffisant.

Ne pas inclure de données personnelles dans le QR code. Le prix et les champs signés sont figés à l’émission ; une modification ultérieure du tarif de l’événement n’invalide pas les billets déjà vendus. Prévoir une version de signature pour la rotation des clés.

### Scan par un participant

Une ouverture normale du lien affiche la page publique de l’événement. Elle ne consomme jamais le billet, même en cas d’ouvertures répétées, de prévisualisation de lien ou de scan par la caméra native. Elle n’affiche aucune donnée personnelle ou état détaillé du billet.

### Scan par un valideur

Le scanner du site reconnaît le billet et appelle une opération serveur protégée pour enregistrer l’entrée. Aucune requête de simple consultation ne peut utiliser un billet.

La signature empêche la fabrication ou l’altération d’un billet ; la base et le contrôle atomique empêchent les utilisations répétées. Une copie du QR reste une copie du même billet : la première entrée autorisée consomme ce billet.

## 8. Autorisation du téléphone et validation

Parcours proposé pour `/validation` :
1. L’organisateur crée un valideur et l’affecte à l’événement.
2. Le valideur ouvre la page en HTTPS sur Safari ou Chrome et saisit son identifiant et son code personnel.
3. Lors du premier accès, cet appareil est placé en attente d’approbation.
4. Un organisateur autorisé, un administrateur ou le superadmin approuve l’appareil.
5. Le valideur autorise la caméra et ouvre le scanner.
6. Le serveur contrôle les droits à chaque validation.

L’autorisation porte sur le navigateur enregistré, et ne constitue pas une identification matérielle absolue du téléphone. Un changement de navigateur ou l’effacement de ses données impose un nouvel enregistrement. Proposition : session sécurisée, expiration à la fin de la soirée, code personnel protégé contre les tentatives répétées et révocation immédiate. Une passkey peut renforcer l’accès si souhaité.

Vérifications avant d’accepter : session, appareil autorisé, affectation à l’événement, signature correcte, paiement confirmé, billet actif, événement correct et absence de passage précédent.

L’entrée est enregistrée dans une transaction atomique. Deux scans simultanés sur deux téléphones ne peuvent accepter le même billet deux fois. Les répétitions réseau d’une même opération doivent conserver le résultat de cette opération.

| Situation | Résultat |
| --- | --- |
| Billet accepté | Vert, message explicite et entrée enregistrée |
| Billet déjà utilisé | Rouge, heure du premier passage |
| Billet invalide, annulé ou autre événement | Rouge, motif lisible |
| Serveur ou connexion indisponible | État distinct, aucune acceptation supposée |

Prévoir une saisie manuelle du numéro de billet réservée aux valideurs autorisés. Ne pas charger une URL arbitraire issue d’un QR inconnu. Les informations nominatives utiles au contrôle sont visibles uniquement aux agents autorisés.

Première version proposée : contrôle en ligne obligatoire. Une connexion de secours est à prévoir sur place. Le mode hors ligne est exclu de cette version sauf demande explicite et conception supplémentaire.

Conserver le valideur, l’appareil, l’événement, le billet, l’heure serveur et le résultat. Le retour arrière sur une entrée doit être une action privilégiée, motivée et historisée, si cette fonction est retenue.

## 9. Données et exploitation

Entités prévues : comptes et rôles, événements, affectations, appareils autorisés, commandes, participants, billets, paiements, envois SMS, validations et journal d’audit.

Séparer l’état du paiement, l’état du billet et l’état de livraison du SMS. Une relance SMS ne change pas le paiement ; une annulation de billet ne déclenche pas implicitement un remboursement.

Prévoir HTTPS, sauvegardes avec procédure de restauration, dates stockées sans ambiguïté, contrôle des accès et protection des formulaires. Les journaux ne doivent contenir ni clés de configuration ni liens secrets complets des billets.

Ajouter une information sur l’utilisation des données, définir leur durée de conservation et limiter les exports aux personnes habilitées. Ne pas réutiliser les numéros pour de la prospection sans parcours distinct adapté.

Propositions complémentaires : authentification renforcée pour superadmin et administrateurs, récupération sécurisée du compte superadmin, fermeture automatique des ventes et annulation d’événement avec communication aux participants.

## 10. Critères de recette

- Achat de plusieurs places avec coordonnées individuelles obligatoires et contrôle des doublons de téléphone.
- Refus serveur d’un montant modifié par le navigateur et respect de la jauge en cas d’achats simultanés.
- Paiement confirmé même si l’acheteur ferme son navigateur ; aucune émission sur simple retour de page.
- Notifications répétées et reprise après panne sans création de billets supplémentaires.
- Livraison individuelle de liens vers PNG et PDF ; relance possible après échec.
- Correspondance exacte entre nom, montant, événement, date, heure et adresse sur les deux formats.
- Scan public sans effet sur le billet et sans exposition des informations personnelles.
- Scan autorisé consommant exactement une entrée, y compris lors de scans simultanés.
- Refus d’un valideur non affecté, appareil non approuvé ou accès révoqué.
- Refus d’un billet modifié, annulé, déjà utilisé ou associé à un autre événement.
- Fonctionnement responsive sur téléphone et PC ; caméra vérifiée sur iPhone/Safari et Android/Chrome réels.
- Permissions vérifiées pour tous les rôles, dont la protection du superadmin.

## 11. Décisions restantes avant développement

1. Nombre de participants attendu et nombre de téléphones de contrôle simultanés.
2. Domaine retenu : `glorieux.snoopup.io`. Restent le serveur cible, son adresse IP ou sa cible DNS, le chemin absolu de `~/digi2` et l’hébergement.
3. Validation de l’approche SumUp hébergée et disponibilité du compte marchand.
4. Prestataire SMS et budget d’envoi.
5. Prix, jauge, dates de vente et durée des réservations.
6. Classe à renseigner obligatoirement dans la préinscription après validation du compte ; liste des classes à fournir.
7. Coordonnées de l’acheteur et accès à sa commande.
8. Règles de remboursement, transfert de billet, sortie et éventuelle réentrée.
9. Règle SAM, conditions d’admission et mentions définitives.
10. Validation de la séparation administrateur/superadmin et des fonctions proposées.
11. Durées de conservation, validité des liens et procédure de récupération d’accès.
12. Méthode de connexion des étudiants et inscription des bénéficiaires d’un achat groupé ; les deux vérifications email et SMS sont obligatoires avant réservation.
13. Choix de la pile serveur et de la base, à proposer après confirmation de l’environnement cible.

## 12. Suite

Faire relire et approuver ce cahier des charges, résoudre les décisions structurantes, puis établir le plan de réalisation. Aucun secret SumUp réel n’est nécessaire pour commencer les développements et tests en environnement de simulation.


## 13. Domaine, DNS OVH et email AWS SES

Domaine web retenu : `https://glorieux.snoopup.io`. L’utilisateur autorise la configuration du DNS OVH pour ce sous-domaine et de l’envoi des emails de la plateforme via AWS SES pour `snoopup.io`. Les accès, la cible d’hébergement et la région AWS doivent être vérifiés avant les opérations.

- Inventorier les enregistrements existants avant modification et préserver les autres services du domaine.
- Créer l’enregistrement du sous-domaine vers le serveur choisi et configurer HTTPS.
- Vérifier ou réutiliser l’identité SES `snoopup.io` dans la région choisie ; ajouter les enregistrements DKIM fournis par AWS dans la zone DNS faisant autorité.
- Vérifier SPF, DMARC et, si retenu, un sous-domaine MAIL FROM dédié ; ne pas ajouter de second enregistrement SPF pour un même nom ni remplacer les MX de réception de `snoopup.io`.
- Vérifier le statut sandbox, les quotas et l’accès production SES dans la région choisie. Une demande d’accès production ne garantit pas son acceptation immédiate.
- Proposition d’expéditeur : `Glorieux <billetterie@snoopup.io>`. Adresse de réponse et responsable de réception à définir ; SES n’est pas une boîte de réception.
- Prévoir les confirmations, liens de vérification email obligatoires, notifications transactionnelles et suivi des rejets/plaintes ; aucun envoi réel à des tiers pendant la configuration sans instruction correspondante.
- SES assure les emails ; un prestataire SMS distinct reste nécessaire pour les codes d’inscription et les liens des billets.

À cette mise à jour, aucun changement DNS ou SES n’a été effectué et aucun accès cloud n’a été confirmé. Aucun fichier de configuration cloud n’est présent dans le projet courant ; AWS CLI est disponible, mais aucune variable d’environnement AWS ou OVH n’est exposée à la session.


## 14. Tableau de bord, classes et déclaration de majorité

Demandes complémentaires : afficher immédiatement les KPI dans l’interface administrateur et permettre la consultation des listes globales et par classe.

KPI par événement, visibles dès l’ouverture :
- Participants avec billet payé et actif / jauge, et taux de remplissage.
- Places encore disponibles, en tenant compte des réservations temporaires actives.
- Préinscriptions sans billet payé, présentées séparément des ventes confirmées.
- Entrées validées / billets actifs et montant total des paiements confirmés.

Ne pas confondre nombre de comptes, nombre de commandes et nombre de participants. Proposition : « inscrits » désigne les détenteurs d’un billet payé et actif. Le terme « sous-inscrits » est provisoirement interprété comme les sous-listes par classe et reste à clarifier s’il désigne un statut distinct.

Listes : recherche par nom/prénom, filtres événement, classe, paiement et entrée ; effectif par classe et ouverture de la liste correspondante. Présenter les préinscrits et les inscrits payés séparément. Les exports et coordonnées restent réservés aux rôles habilités.

Après validation du compte, l’étudiant remplit une préinscription propre à l’événement : classe obligatoire (liste administrable), puis une déclaration obligatoire avec deux choix exclusifs, sans choix présélectionné :

- « Je déclare être âgé(e) de dix-huit ans révolus à la date de l’événement. »
- « Je déclare que je serai mineur(e) à la date de l’événement et avoir informé mon ou mes représentants légaux de mon inscription et de ma participation à cette soirée, ainsi que de sa date, de ses horaires et de son lieu. »

Ces formulations sont proposées pour validation éditoriale et juridique selon les conditions d’admission réelles. La seconde atteste une information déclarée par le mineur ; elle ne prouve pas une autorisation donnée par un représentant légal et ne constitue pas une décharge de responsabilité de l’organisateur. Si une autorisation parentale est requise, prévoir un parcours distinct de consentement du représentant légal.

Conserver l’auteur de la déclaration, l’événement, le choix, la date de validation et la version exacte du texte. La déclaration doit être personnelle : lors d’un achat groupé, l’acheteur ne doit pas attester à la place d’un autre participant de l’information de ses représentants légaux. Le parcours bénéficiaire reste à arrêter avant implémentation.

La majorité est appréciée à la date de l’événement ; la déclaration seule ne vaut pas preuve d’âge pour la délivrance d’alcool. L’accès des mineurs et le contrôle d’âge doivent suivre les règles applicables au lieu et à l’événement. Référence : https://www.legifrance.gouv.fr/codes/affichCode.do?cidTexte=LEGITEXT000006072665&idSectionTA=LEGISCTA000006171207

Recette supplémentaire : préinscription inaccessible avant validation du compte ; classe et choix de déclaration obligatoires côté serveur ; refus des choix simultanés ; KPI sans double comptage et exclusions des billets annulés ; filtres par classe conformes aux effectifs ; historique du texte accepté conservé.

## 15. Accès infrastructure autorisés

L’utilisateur indique que les accès AWS et OVH se trouvent dans `~/script/aws-script/` et autorise explicitement la consultation de ce répertoire pour les opérations DNS et SES de cette plateforme. Ne pas afficher ni recopier les secrets dans ce document. Cette autorisation ne s’étend pas aux autres projets ou services hébergés.

Vérification des accès : répertoire `~/script/aws-script/` trouvé ; authentification AWS confirmée par une requête STS en lecture seule. Configuration OVH présente avec les champs de connexion attendus ; droits effectifs sur la zone `snoopup.io` encore à tester. Aucun secret affiché, aucune mutation cloud effectuée.


## 16. Identité visuelle et partage social

Demandes validées : le site reprend au maximum les couleurs et l’esprit typographique du logo, avec un design adapté aux 17–20 ans, et permet de partager rapidement les événements sur les réseaux sociaux.

### Direction visuelle

- Utiliser principalement le bleu marine, l’or et le crème visibles dans l’écusson ; relever les couleurs depuis le logo lors de la préparation des assets.
- Employer une typographie de titres de style universitaire/sportif proche de « GLORIEUX ». La police exacte n’est pas identifiée depuis la capture : choisir une équivalente utilisable sur le web et compatible avec sa licence.
- Réserver cette typographie expressive aux titres et actions courtes ; utiliser une police lisible pour formulaires, informations pratiques et textes longs.
- Proposer une ambiance festive et contemporaine : titres marqués, mise en avant de l’événement et de ses informations, boutons faciles à utiliser sur téléphone, parcours courts.
- Conserver une bonne lisibilité, des contrastes suffisants et une navigation clavier ; respecter les préférences de réduction des animations.
- Garder les interfaces de contrôle et d’administration particulièrement lisibles et rapides.

### Partage

Interprétation retenue : « transférable dans les réseaux sociaux » signifie partager rapidement la page publique d’un événement, et non publier automatiquement sur des comptes sociaux.

- Bouton « Partager l’événement » ouvrant le partage natif du téléphone lorsque disponible.
- Solution de repli : copie du lien public, avec confirmation visible.
- Prévisualisation de lien avec titre, description et image de l’événement (métadonnées Open Graph).
- Proposition : fournir un visuel vertical téléchargeable adapté aux stories et un visuel de publication, avec logo et informations pratiques, sans donnée personnelle.
- Le partage est déclenché par l’utilisateur ; aucune publication automatique ni connexion à un compte social requise.
- Partager exclusivement la page publique de l’événement, sans code d’accès privé, lien secret de téléchargement ni identifiant de billet. Le code d’événement reste requis pour s’inscrire.
- Ne pas promettre un partage direct en story sur tous les réseaux : les possibilités dépendent du navigateur et des applications installées ; téléchargement du visuel et copie du lien restent disponibles.

### Recette complémentaire

- Un compte ayant seulement validé son téléphone ne peut pas réserver ; même refus si seul l’email est validé. Les deux validations débloquent la réservation, sous réserve des autres conditions de préinscription.
- Vérifier ces blocages côté serveur sur toutes les routes de réservation et de création de paiement, sans permettre de contournement par appel direct.
- Un lien email expiré, déjà utilisé ou remplacé ne valide pas le compte ; le parcours propose un renvoi contrôlé.
- La page publique reste partageable sans compte ; sa prévisualisation n’expose aucune information de participant ni secret.
- Vérifier partage natif, copie du lien et présentation sur téléphone et ordinateur.


## 17. Mention du prestataire technique sur les billets

Demande : afficher sur chaque billet PNG et PDF une mention indiquant que Snoopup.io fournit la billetterie sans organiser la soirée.

Formulation proposée :
> Billet émis via Snoopup.io, prestataire technique de billetterie. Snoopup.io n’intervient pas dans l’organisation ni dans le déroulement de cette soirée. L’organisation de l’événement relève de [nom de l’organisateur], joignable à [contact]. Cette mention ne limite pas les responsabilités légalement applicables à chacun.

Afficher l’identité et le contact réels de l’organisateur, configurables par événement. La mention ne doit pas présenter Snoopup.io comme exonéré de toute responsabilité liée à ses propres prestations ; son contenu doit correspondre au rôle réel du service. Formulation à valider juridiquement avant publication. Conserver une taille lisible sans réduire la lisibilité du QR code.

## 18. État de configuration DNS et SES au 14 novembre 2026

- Région AWS SES : `eu-north-1` ; accès production et envoi activés constatés.
- Identité `snoopup.io` créée ; vérification SES réussie, DKIM `SUCCESS`.
- Trois enregistrements CNAME DKIM ajoutés dans la zone OVH de `snoopup.io` et zone rafraîchie. MX et SPF préexistants conservés.
- Email de test explicitement demandé envoyé depuis `Glorieux <billetterie@snoopup.io>` vers `alban.debeaupuis@gmail.com` : accepté par SES, identifiant `011001a1da490007-f95c1498-a536-47c1-b99e-d367758ff3f0-000000`. L’acceptation SES ne prouve pas la réception en boîte principale.
- Aucun enregistrement pour `glorieux.snoopup.io` créé : serveur cible à confirmer. Aucun site déployé.
- MAIL FROM personnalisé, politique DMARC et suivi des rejets/plaintes restent à finaliser avant exploitation ; la vérification DKIM et l’envoi test ne signifient pas que toute l’exploitation email est terminée.


## 19. État de livraison

L’utilisateur a approuvé le développement, le dépôt GitHub `adebeau33/snoopup-glorieux` et le déploiement HTTPS sur le serveur AWS accessible par `~/digi2`. Le domaine pointe vers `13.51.188.194` et le certificat Let’s Encrypt est installé.

Après demande de limiter la mémoire : Django/Python 3.12, Bootstrap, SQLite WAL et service systemd sous compte dédié `glorieux`. Aucun nouveau conteneur ; web plafonné à 192 Mo et tâche périodique plafonnée à 128 Mo, soit 320 Mo de plafonds cumulables pendant les tâches. Port privé 8017 et vhosts Apache dédiés.

Le superadmin propriétaire est créé. Son accès initial est conservé dans des fichiers privés exclus de Git. L’interface respecte les tons marine/or/crème et utilise des polices locales proches de l’identité du logo ; l’écusson source est présenté par masquage circulaire.

Règle retenue pour l’achat groupé : chaque bénéficiaire doit terminer sa double vérification et sa propre préinscription avant achat. La déclaration des mineurs reste personnelle. Le téléphone complet des autres bénéficiaires n’est pas révélé lors de la recherche par email.

Fonctions implémentées : comptes, double vérification, préinscriptions, classes, administration et rôles, KPI et exports CSV, intégration SumUp hébergée avec réconciliation, billets PNG/PDF et signatures, envois persistants, contrôle par appareil et événement, partage public sans secrets, journal et sauvegarde locale quotidienne.

Réserves de mise en exploitation : renseigner SumUp et le prestataire SMS (adaptateur Twilio fourni), créer les classes et événements réels, compléter les conditions juridiques et la conservation, vérifier les caméras iPhone/Android et réaliser les tests fournisseurs de bout en bout. Les ventes sont bloquées sans les intégrations nécessaires. Remboursements, transferts, réémissions et réentrées restent à définir/automatiser séparément. MAIL FROM personnalisé, politique DMARC, suivi SES des rejets/plaintes et externalisation des sauvegardes restent à finaliser. Le rôle SES de la plateforme est limité à l’envoi depuis `billetterie@snoopup.io`.

Test de charge isolé sur AWS : 2 000 validations avec 8 threads en 17,06 secondes, p95 245 ms, sans double entrée ; ce test mesure la logique serveur, hors caméra et réseau mobile et hors plafond du service HTTP. Ce résultat ne remplace pas la recette sur site.


## 20. Première soirée et conditions d’admission

Première soirée : samedi 21 novembre 2026 à partir de 22 h, au « Death before sunlight », à Bordeaux. L’adresse exacte, le tarif, la jauge et les coordonnées de l’organisateur restent à compléter avant ouverture des ventes. L’événement est affiché avec ventes fermées ; aucun tarif gratuit n’est annoncé par défaut.

Afficher sur la page événement, la préinscription, le récapitulatif avant paiement et sur les billets PNG/PDF :

> Merci de présenter une pièce d’identité à l’entrée afin de permettre la vérification de votre identité. Cette soirée privée est réservée aux membres de l’établissement Sainte-Marie Grand Lebrun munis d’un billet nominatif valide. Toute personne sans billet valide ou extérieure à l’établissement se verra refuser l’accès.

Le contrôle d’identité est réalisé visuellement par l’accueil ; aucune copie de pièce d’identité n’est demandée ou stockée par la plateforme. Le compte scolaire vérifié et le billet ne remplacent pas le contrôle humain à l’entrée.

Le formulaire de création de compte indique explicitement qu’un email de confirmation sera envoyé à la boîte scolaire. Le logo figure dans la barre supérieure des pages intérieures.


Organisateur communiqué : **BDE Grand Lebrun — 164 avenue Charles de Gaulle, 33200 Bordeaux-Caudéran**. Adresse de l’établissement vérifiée sur https://grandlebrun.com/reglements-et-tarifs/ . Conserver cette adresse dans un champ distinct de l’adresse du lieu de la soirée ; affichage sur la page événement et les billets.
