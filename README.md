# Le Glorieux — billetterie BDE

Application responsive Bootstrap/Django pour `https://glorieux.snoopup.io`.

## Fonctionnement

- Comptes étudiants réservés au domaine exact `grandlebrun.com` et aux deux exceptions exactes autorisées pour les tests (`alban.debeaupuis@gmail.com`, `alban@audiopro.fr`). Nom, prénom, email et téléphone sont requis. L’email est vérifié avant l’inscription ; le téléphone est vérifié par SMS au moment de l’achat.
- Mot de passe de 8 caractères minimum. Les erreurs de validation bloquent la création du compte ; une adresse mail non confirmée reste « à vérifier » (le superadmin initial est une exception de configuration).
- Inscription personnelle à la soirée : déclaration de majorité à la date de l’événement. Aucun code événement n’est demandé. Avant paiement, chaque bénéficiaire de l’achat groupé confirme son téléphone par SMS.
- Paiement unique d’une commande de 1 à 20 bénéficiaires via SumUp hébergé. Tarif serveur, récapitulatif signé, jauge protégée par transaction. Vérification API après callback et réconciliation périodique, sans confiance dans le retour navigateur.
- Billet individuel en PNG uniquement, avec nom/prénom, date et QR compact sans URL. Le QR porte la référence événement (3 octets), la signature HMAC-SHA-256 tronquée à 8 octets au milieu du code et la référence d’inscription (4 octets). Le valideur vérifie la signature avant toute recherche en base ; les anciens QR restent acceptés pendant la transition.
- QR public vers la page événement sans consommation. `/validation/` exige un compte habilité, une affectation et un navigateur approuvé, avec expiration. Événement contrôlé explicite ; refus des doubles scans.
- `/gestion/` : KPI, listes par événement, recherche et export CSV. `/admin/` : événements, comptes, affectations, appareils, paiements, billets et envois. Le superadmin seul gère les administrateurs et voit les comptes privilégiés. Aucune option administrateur n’est affichée à l’inscription ; le superadmin accorde ensuite ce rôle aux comptes sélectionnés.
- Partage natif/copie de lien et images Open Graph publiques, sans secret de billet. Les visuels rappellent que les places sont limitées, attribuées par ordre d’arrivée, et qu’aucune inscription ne sera possible sur place le soir même. Polices et bibliothèques JS/CSS hébergées localement.

## Configuration avant ouverture

Modifier **sur AWS uniquement** `/etc/glorieux/glorieux.env`, puis redémarrer `glorieux.service`. Ne jamais committer ce fichier.

1. Renseigner `SUMUP_API_KEY` et `SUMUP_MERCHANT_CODE`.
2. SMS OVH est configuré. Le fournisseur configuré est OVH, avec un utilisateur SMS dédié limité à l’IP AWS et l’expéditeur DIGITALEVEN. Un ancien adaptateur Twilio reste disponible : `SMS_PROVIDER=twilio`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`. Tout autre fournisseur nécessite un adaptateur dans `core/delivery.py`.
3. Créer l’événement : date/heure, lieu, adresse, tarif, jauge, identité/contact de l’organisateur et dates de vente.
4. Compléter l’information juridique et les conditions de vente : identité de l’organisateur, données/conservation, admission des mineurs, remboursement et règle SAM. La déclaration du mineur n’est pas une autorisation parentale.
5. Tester un paiement réel/sandbox et sa notification avec les identifiants fournis, les SMS, puis la caméra sur iPhone et Android avant de publier les ventes.

Les paiements réels sont explicitement en pause (`PAYMENTS_ENABLED=0`). Le mode TEST propose une page de paiement SumUp simulée, réservée aux événements en test : elle ne contacte pas SumUp, ne débite rien et émet des billets TEST seulement après confirmation. Aucun faux paiement n’est utilisé en production. Les appels fournisseurs n’ont pas pu être validés de bout en bout sans ces accès.

AWS SES est configuré en `eu-north-1` avec l’identité `snoopup.io`, DKIM et un utilisateur IAM limité à l’envoi depuis `billetterie@snoopup.io`. Les secrets se trouvent exclusivement dans la configuration privée serveur. SES fournit l’envoi, pas une boîte de réception. Le suivi des rejets/plaintes, MAIL FROM personnalisé et la politique DMARC restent à finaliser avant exploitation des envois en volume.

## Installation et ressources

Voir [deploy/README.md](deploy/README.md). Python 3.12 en venv, service systemd dédié à l’utilisateur `glorieux`, un worker Gunicorn avec 4 threads, SQLite WAL. **Aucun nouveau conteneur ni serveur de base de données.**

Le web est plafonné à 192 Mo ; le traitement périodique à 128 Mo. Les deux plafonds peuvent se cumuler pendant les tâches. Port 8017 accessible uniquement sur loopback, Apache assure HTTPS. Les journaux du vhost excluent les URL contenant les secrets de billets ou de validation.

## Tests

Sur la machine AWS dans `/home/ec2-user/snoopup-glorieux` :

```sh
SECRET_KEY=tests DEBUG=1 .venv/bin/python manage.py test --noinput
SECRET_KEY=tests DEBUG=1 .venv/bin/python manage.py test core.load_validation --noinput
```

La base de test est `/tmp/glorieux-test.sqlite3`, distincte de la production. Ne pas lancer deux suites simultanément.

Le test de charge isolé a mesuré 2 000 validations avec 8 threads en 16,98 s, p95 246 ms, sans double entrée. Il mesure la logique serveur sur la machine, hors caméra, réseau mobile et plafond du service HTTP ; il ne constitue pas une recette de 2 000 téléphones connectés.

## Exploitation et sauvegarde

- Service : `systemctl status glorieux.service` ; jobs : `glorieux-jobs.timer` (20 secondes, processus non permanent).
- Commandes incertaines : action de réconciliation dans l’administration. Les créations introuvables sont libérées seulement après 15 minutes et interrogation SumUp. Une tentative `FAILED` ne libère pas une session encore utilisable ; attendre `EXPIRED`. Un paiement tardif sur une allocation libérée est mis en revue sans émission automatique.
- Les envois laissés dans un état incertain après interruption sont mis en revue pour éviter une répétition automatique. Une acceptation fournisseur ne prouve pas la réception.
- Sauvegarde SQLite cohérente quotidienne à 04:35, sept copies dans `/var/backups/glorieux`, fichiers privés. Cette sauvegarde est **locale au serveur** ; prévoir une copie externe chiffrée pour résister à sa perte.
- Restauration : arrêter `glorieux.service` et `glorieux-jobs.timer`, conserver une copie de l’état courant, restaurer un snapshot SQLite dans `/var/lib/glorieux/db.sqlite3` (propriétaire `glorieux`, mode 600), retirer uniquement les anciens fichiers `db.sqlite3-wal` et `db.sqlite3-shm` après arrêt de toutes les connexions, puis redémarrer et vérifier les commandes auprès de SumUp avant reprise des ventes.
- La configuration secrète et les clés de signature doivent aussi être sauvegardées séparément : une base seule ne suffit pas à conserver les liens et QR valides.

## Limites de cette livraison

Les remboursements bancaires, transferts de billets et réentrées ne sont pas automatisés. Une annulation de billet ne rembourse pas la commande et ne libère pas automatiquement sa place. La remise en circulation d’une place payée doit suivre une règle validée. Une connexion Internet est obligatoire au contrôle. Un numéro de billet complet peut être saisi manuellement par un valideur autorisé.

Le logo source reste inchangé ; l’écusson est présenté par masquage circulaire dans l’interface et composé dans les billets. L’original vectoriel permettrait un meilleur rendu. Aucune publicité ou publication sur les comptes sociaux n’est automatisée.

## Mode TEST et contrôle sur téléphone

La première soirée est actuellement en mode TEST, jauge1000, lieu147 rue des Petits Lapins33000 Bordeaux. Le superadmin active/désactive ce mode dans l’événement, puis génère un billetTEST depuis `/gestion/`. Le billet est enregistré et scannable en modeTEST, sans paiement et sans place réelle retenue. Le PNG porte BILLET TEST ; le type TEST est signé avec une clé dérivée distincte. Un billetTEST ne passe jamais en mode réel. Les déclarations fictives doivent être remplacées avant une réservation réelle.

Téléphone : connexion sur `/validation/`, enregistrement et autorisation de l’appareil. Un superadmin dispose d’un bouton explicite pour autoriser son propre appareil pour12h. Choisir l’événement et le mode : Entrée automatique consomme le billet et journalise l’heure ; Consultation ne consomme rien. Le résultat affiche l’identité et un bip, puis attend un appui sur l’écran avant de relancer. Le son doit être activé par un geste utilisateur et dépend du volume du téléphone ; bouton de test disponible. La caméra native ouvre seulement l’événement public.

Les listes HTML, CSV et PDF incluent les heures d’entrée, avec filtres par événement. Audit conserve l’agent et l’appareil. Les emails des billets comportent le PNG joint ; les SMS contiennent le lien sécurisé vers le PNG. Les codesOTP et liensSMS sont courts et ASCII pour rester dans un SMS. L’adaptateur OVH accepte les retours JSON et texteOK ; un retour incertain ne provoque pas de répétition automatique.

Le superadmin voit les créditsOVH avec la date du dernier relevé. Ce solde partagé est mis à jour au relevé initial puis à chaque SMS accepté ici ; il ne constitue pas un polling des consommations des autres applications. Ne pas transférer les clésOVH globales vers le serveur.
