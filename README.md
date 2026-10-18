# Plateforme de sensibilisation — Quishing (ECAM 5eisd5L)

Simulation de phishing par QR code, à visée pédagogique. L'étudiant scanne un QR code,
arrive sur une page qui lui demande des infos, puis découvre que c'était un piège.

## Privacy by design (le point central de l'évaluation)

- Le **matricule** est la seule donnée conservée en clair (sert au suivi).
- Pour tout autre champ (adresse, téléphone, date de naissance), on ne garde
  **qu'un booléen oui/non** : l'étudiant a-t-il rempli ce champ ? La valeur tapée
  n'est **jamais** écrite en base ni dans un log (voir la fonction `submit` dans `app.py`).
- Aucun nom / prénom collecté.

## Lancer en local

```bash
cd phishing-sim
python -m venv venv && source venv/bin/activate   # sur Mac M1
pip install -r requirements.txt
uvicorn app:app --reload
```

Puis ouvre http://127.0.0.1:8000

Pages :
- `/`        → le formulaire piège (ce que vise le QR code)
- `/debrief` → la révélation (affichée après soumission)
- `/stats`   → le tableau de bord pour le rapport final

## Mettre en ligne (URL publique pour le QR code)

1. Pousse `phishing-sim/` sur un repo GitHub.
2. Sur render.com : New → Blueprint → sélectionne le repo. Render lit `render.yaml`.
3. Tu obtiens une URL HTTPS (ex. `https://quishing-sim-ecam.onrender.com`).
4. Génère le QR code **vers cette URL** (surtout pas vers un domaine imitant ecam.be).

## Récupérer les données

- Dashboard live : `/stats`.
- Ou télécharge le fichier `data.db` (SQLite) pour faire tes requêtes SQL toi-même.

⚠️ Sur le plan gratuit de Render, le disque n'est pas persistant : `data.db` peut être
remis à zéro à chaque redéploiement. Pour une campagne de 48h c'est généralement ok
(pas de redéploiement entre-temps), mais pour être tranquille, voir la note plus bas.
