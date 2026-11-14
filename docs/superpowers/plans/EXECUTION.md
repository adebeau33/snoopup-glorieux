# Exécution

- Choix : implémentation directe, dépôt initialement vide ; source locale synchronisée sur AWS pour tous les tests et l’exécution.
- Ruling : aucun conteneur supplémentaire, SQLite WAL et systemd, après avertissement mémoire utilisateur. Coût si charge supérieure : mesure puis migration PostgreSQL/augmentation RAM.
- Ruling : chaque bénéficiaire d’un achat groupé doit être personnellement préinscrit et doublement vérifié ; aucune déclaration parentale par un tiers. Coût : préparation préalable de tous les comptes.
- Ruling : adaptateur SMS Twilio prêt mais désactivé sans configuration ; autre fournisseur nécessite un adaptateur.
- Ruling : URL publiques partageables, téléchargements privés séparés ; pas de publication automatique.
- Tests initiaux : 18 réussis ; après corrections 30 réussis.
- Charge : 2000 entrées / 8 threads / 17,06 s, p95 245 ms, aucune double entrée, base isolée. Hors plafond HTTP et réseau mobile.
- Revue indépendante : IP proxy, réinitialisation asynchrone et limitée, résolution des commandes, événement explicite du scanner, téléphone masqué dans achat groupé, canevas billet dynamique, essais SMS distincts des tokens email et capacité/budget des tâches corrigés. Régressions ajoutées.
- Paiement FAILED : allocation conservée car la session peut être réessayée ; libération sur EXPIRED seulement. Création incertaine récupérée par référence ; paiement tardif sans allocation en revue.
- DNS créé vers 13.51.188.194. HTTPS Let’s Encrypt obtenu ; vhosts dédiés, rechargement Apache après contrôle syntaxique.
- Superadmin initial créé, accès privé dans `.secrets/superadmin.txt` (ignoré de Git) et fichier serveur protégé.
- Secrets SES dédiés limités à billetterie@snoopup.io en eu-north-1. Aucun secret dans Git.
- Limites : configuration SumUp/SMS, recette caméras réelles, conditions juridiques finales et suivi des rebonds SES requis avant exploitation complète ; remboursements/transferts/réentrées non automatisés ; sauvegardes locales à externaliser.

- Recette finale : 36 tests réussis, contrôles HTTP publics et authentifiés superadmin réussis, captures mobiles à 390 px vérifiées. Service web observé à environ 44 Mo au repos, plafond192 Mo. Deux avertissements Django facultatifs HSTS sous-domaines/preload restent volontairement non activés.
- Première soirée publiée au 21/11/2026 à 22 h, Death before sunlight à Bordeaux, ventes fermées ; organisateur BDE Grand Lebrun, adresse scolaire séparée du lieu.

- Dernière demande : exceptions email exactes Gmail/Audiopro conservant double vérification ; aucune option administrateur à l’inscription. Action d’attribution réservée au superadmin après inscription. Tests de non-élévation et d’approbation ajoutés.

- Billets graphiques avec logo, référence GL-UUID et HMAC imprimés. QR v1 autoportant (ref, événement, prix, devise), vérification sans base avant recherche. Référence authentique absente : orange sans consommation ; signature invalide : rouge. Saisie manuelle exige prix + signature.
- 44 tests réussis avec régressions signature inconnue authentique/fausse et contrôle manuel ; revue ciblée indépendante sans défaut important. Aperçu fictif avec clé distincte et filigrane non valable. Lecture du QR contrôlée par un décodeur indépendant, original et version540px.

- Vérification finale après format QR autonome : 45 tests réussis ; charge2000/8 en16,98s, p95 246ms, zéro double entrée. Version déployée après ces vérifications.

- Demandes suivantes : SMS OVH HTTP2SMS via utilisateur dédié glorieux limité à IP13.51.188.194 ; sender DIGITALEVEN confirmé enable. SNOOPUPIO refused ; GLORIEUX demandé waitingValidation puis utilisateur a choisi DIGITALEVEN. Les clés OVH globales n’ont pas été transférées. Paiements en pause avec PAYMENTS_ENABLED=0.
- Jauge1000 et lieu147 rue des Petits Lapins33000 Bordeaux. ModeTEST Event.is_test réservé superadmin ; Order/Ticket is_test snapshots ; signatures t1 avec clé dérivée et références GL-T ; FAKE sur visuel sans QR. Génération superadmin sans encaissement et sans held, email test optionnel. Les déclarations fictives ne permettent pas une réservation réelle après changement de mode.
- Contrôle entry/consult ; consult ne consomme rien. Horodatages HTML/CSV/PDF ; Audit.device ajouté. Compteur SMS Balance réservé superadmin, solde horodaté initial/dernier envoi accepté, pas de polling globalOVH. Mot de passe inscription : œil ajouté aux deux champs.
- Revue ciblée : bloquer begin_checkout pour commande/événementTEST actuel ; confirm_payment refuse TEST ; ticket_sms_ready distinct de SMS OTP court. Garde-fous implémentés avec tests.
- Numéro de test explicitement fourni par utilisateur ; ne pas committer le numéro. À faire après déploiement/migration0003 : activer modeTEST de première soirée, initialiser relevéSMS, associer téléphone au superadmin si libre, émettre un codeSMS et email de vérification et un billetFAKE par email vers Gmail autorisé ; inspecter états sans codes/liens dans les sorties.

- Corrections produit demandées le 14/11/2026 : mot de passe minimum 8 caractères et transaction signup évitant tout compte partiel ; email seul avant inscription, OTP téléphone au parcours d’achat pour chaque bénéficiaire ; connexion libellée Adresse mail ; retrait du code événement et vocabulaire « inscription ».
- Le mode TEST inclut maintenant une page de paiement SumUp simulée locale (aucun appel marchand ni débit) avec émission de billets TEST après confirmation. Le médaillon de la soirée est détouré depuis l’image fournie et utilisé indépendamment du logo BDE. Message public ajouté : ordre d’arrivée, jauge limitée et pas d’inscription sur place.
