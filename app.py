"""
Plateforme de sensibilisation au quishing — ECAM 5eisd5L
=========================================================

Principe de privacy-by-design (exigence centrale du brief, slide 21) :
  - Le MATRICULE est la seule donnée conservée en clair (sert au suivi).
  - Pour tout autre champ (adresse, téléphone, date de naissance...), on ne
    conserve QU'UN indicateur oui/non : l'étudiant a-t-il rempli ce champ ?
    La valeur saisie n'est JAMAIS écrite en base, ni dans un log.
  - Aucun nom / prénom n'est collecté.

La conversion valeur -> booléen se fait dès la réception, et la valeur réelle
n'est jamais réutilisée ailleurs que pour ce test de présence.

Stockage : PostgreSQL si DATABASE_URL est défini (cas Render, disque
persistant), sinon SQLite en local (pratique pour développer sur ta
machine). Le choix est automatique, rien à changer à la main.
"""

from datetime import datetime, timezone
from pathlib import Path
import os

from flask import Flask, render_template, request, redirect, url_for, abort

APP_DIR = Path(__file__).parent
DB_PATH = APP_DIR / "data.db"

DATABASE_URL = os.environ.get("DATABASE_URL")
USING_POSTGRES = bool(DATABASE_URL)

if USING_POSTGRES:
    import psycopg2

    def get_conn():
        return psycopg2.connect(DATABASE_URL)

    PLACEHOLDER = "%s"
    ID_COLUMN = "id SERIAL PRIMARY KEY"
else:
    import sqlite3

    def get_conn():
        return sqlite3.connect(DB_PATH)

    PLACEHOLDER = "?"
    ID_COLUMN = "id INTEGER PRIMARY KEY AUTOINCREMENT"

app = Flask(__name__)

# Jeton d'accès pour la page /admin (voir plus bas). À définir comme variable
# d'environnement ADMIN_TOKEN sur Render — jamais commité en clair dans le code.
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN")

# Les champs "piège" du formulaire, autres que le matricule.
# Pour chacun on ne stockera qu'un booléen "rempli / pas rempli".
SENSITIVE_FIELDS = ["adresse", "telephone", "date_naissance"]


def init_db() -> None:
    """Crée les tables si besoin. Une colonne booléenne par champ sensible."""
    cols = ", ".join(f"{f}_rempli INTEGER NOT NULL DEFAULT 0" for f in SENSITIVE_FIELDS)
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS submissions (
                {ID_COLUMN},
                matricule TEXT,
                matricule_fourni INTEGER NOT NULL DEFAULT 0,
                {cols},
                created_at TEXT NOT NULL
            )
            """
        )
        # Compteur de visites (= nombre d'étudiants ayant "cliqué" / ouvert la page)
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS visits (
                {ID_COLUMN},
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


@app.route("/")
def page_piege():
    """Page atteinte via le QR code : le faux formulaire."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            f"INSERT INTO visits (created_at) VALUES ({PLACEHOLDER})",
            (datetime.now(timezone.utc).isoformat(),),
        )
        conn.commit()
    finally:
        conn.close()
    return render_template("form.html", fields=SENSITIVE_FIELDS)


@app.route("/submit", methods=["POST"])
def submit():
    """
    Réception du formulaire.

    ICI est le coeur de la conformité : le frontend (voir le <script> dans
    form.html) calcule déjà les booléens de présence EN LOCAL, dans le
    navigateur de l'étudiant, et c'est tout ce qu'il envoie. Les valeurs
    saisies (adresse, téléphone, date de naissance) ne sont jamais
    transmises sur le réseau — ce backend ne les reçoit donc jamais, il n'y
    a rien à "jeter" ici. On se contente de valider que ce qu'on reçoit est
    bien des 0/1, sans jamais s'attendre à du texte libre pour ces champs.
    """
    matricule_clean = request.form.get("matricule", "").strip()
    matricule_fourni = 1 if matricule_clean else 0

    # Le frontend n'envoie que "0" ou "1" pour ces champs. On le vérifie
    # strictement : toute autre valeur (texte libre glissé par erreur ou
    # tentative de contournement) est traitée comme "non rempli", jamais
    # stockée telle quelle.
    presence = {
        f: 1 if request.form.get(f"{f}_rempli") == "1" else 0
        for f in SENSITIVE_FIELDS
    }
    cols = (
        ["matricule", "matricule_fourni"]
        + [f"{f}_rempli" for f in SENSITIVE_FIELDS]
        + ["created_at"]
    )
    vals = (
        [matricule_clean if matricule_fourni else None, matricule_fourni]
        + [presence[f] for f in SENSITIVE_FIELDS]
        + [datetime.now(timezone.utc).isoformat()]
    )
    placeholders = ", ".join(PLACEHOLDER for _ in cols)

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            f"INSERT INTO submissions ({', '.join(cols)}) VALUES ({placeholders})",
            vals,
        )
        conn.commit()
    finally:
        conn.close()

    return redirect(url_for("debrief"))


@app.route("/debrief")
def debrief():
    """Page de révélation : on explique le piège."""
    return render_template("debrief.html")


@app.route("/stats")
def stats():
    """
    Tableau de bord pour le rapport final (slide 24).
    Ne montre que des agrégats, jamais une ligne individuelle exploitable.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM visits")
        visites = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM submissions")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM submissions WHERE matricule_fourni = 1")
        matricules = cur.fetchone()[0]
        par_champ = {}
        for f in SENSITIVE_FIELDS:
            cur.execute(f"SELECT COALESCE(SUM({f}_rempli), 0) FROM submissions")
            par_champ[f] = cur.fetchone()[0]
    finally:
        conn.close()

    return render_template(
        "stats.html",
        visites=visites,
        total=total,
        matricules=matricules,
        par_champ=par_champ,
    )


@app.route("/admin")
def admin():
    """
    Vue "brute" des soumissions, pour consulter les données sans passer par
    le Shell Render (payant) ni par psql depuis un réseau qui bloque le port
    5432 (eduroam, par ex.). Protégée par un jeton passé en query string :
        /admin?token=...
    Reste des agrégats pour toute personne non autorisée : on n'affiche
    jamais ça publiquement, seul le lien avec le bon token donne accès.
    """
    if not ADMIN_TOKEN or request.args.get("token") != ADMIN_TOKEN:
        abort(403)

    conn = get_conn()
    try:
        cur = conn.cursor()
        cols = (
            ["id", "matricule", "matricule_fourni"]
            + [f"{f}_rempli" for f in SENSITIVE_FIELDS]
            + ["created_at"]
        )
        cur.execute(f"SELECT {', '.join(cols)} FROM submissions ORDER BY id DESC")
        rows = cur.fetchall()
    finally:
        conn.close()

    return render_template("admin.html", cols=cols, rows=rows, token=ADMIN_TOKEN)


@app.route("/admin/reset", methods=["POST"])
def admin_reset():
    """
    Vide les tables submissions/visits. Protégé par le même jeton que
    /admin. Utile pour repartir de zéro après une phase de tests, avant de
    diffuser le vrai QR code.
    """
    if not ADMIN_TOKEN or request.form.get("token") != ADMIN_TOKEN:
        abort(403)

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM submissions")
        cur.execute("DELETE FROM visits")
        conn.commit()
    finally:
        conn.close()

    return redirect(url_for("admin", token=ADMIN_TOKEN))


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
