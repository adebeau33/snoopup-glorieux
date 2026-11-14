# Déploiement Glorieux

Le projet est synchronisé depuis ce checkout vers `/home/ec2-user/snoopup-glorieux` sur AWS, puis publié dans `/opt/snoopup-glorieux`. Le relais correspond au script utilisateur `~/digi2`. Aucun changement aux services voisins.

- `python3 deploy/sync.py` : synchronise uniquement ce projet, sans environnement ni secrets.
- `python3 deploy/remote.py 'sudo bash /home/ec2-user/snoopup-glorieux/deploy/provision.sh'` : installation/migrations/service du projet.
- `python3 deploy/remote.py 'sudo /opt/snoopup-glorieux/deploy/manage.sh check --deploy'` : contrôle Django.
- `python3 deploy/remote.py 'sudo /opt/snoopup-glorieux/deploy/manage.sh process_jobs'` : traitement manuel.
- Tests : dans le dossier source AWS, `SECRET_KEY=tests DEBUG=1 .venv/bin/python manage.py test --noinput`.
- Charge isolée : même commande avec `test core.load_validation --noinput` (2000 billets, 8 threads, base de test distincte).

Ne jamais remplacer `/etc/glorieux/glorieux.env` par `.env.example`. Les fichiers env existants sont préservés. Aucun `docker compose up`, aucun `docker prune`, aucune modification des bases d’autres applications.

Le service web a un plafond de 192 Mo, 1 worker/4 threads ; le traitement périodique a un plafond de 128 Mo et s’arrête entre les exécutions. Le total temporaire des plafonds est donc 320 Mo. Apache est partagé ; il n’est rechargé qu’après un `httpd -t` réussi. Les plafonds ne garantissent pas le dimensionnement pour n’importe quelle charge.

La base utilise SQLite WAL, transactions IMMEDIATE et attente maximale de 20 secondes. Les cas de jauge et de double scan sont testés en concurrence. Une augmentation sensible du trafic de vente devra être mesurée et pourra justifier une migration vers PostgreSQL.
