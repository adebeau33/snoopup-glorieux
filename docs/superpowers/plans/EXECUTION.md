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
