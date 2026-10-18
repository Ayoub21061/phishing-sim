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
"""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from flask import Flask, render_template, request, redirect, url_for

APP_DIR = Path(__file__).parent
DB_PATH = APP_DIR / "data.db"

app = Flask(__name__)

# Les champs "piège" du formulaire, autres que le matricule.
# Pour chacun on ne stockera qu'un booléen "rempli / pas rempli".
SENSITIVE_FIELDS = ["adresse", "telephone", "date_naissance"]


def init_db() -> None:
    """Crée la table si besoin. Une colonne booléenne par champ sensible."""
    cols = ", ".join(f"{f}_rempli INTEGER NOT NULL DEFAULT 0" for f in SENSITIVE_FIELDS)
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            f"""
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matricule TEXT,
                matricule_fourni INTEGER NOT NULL DEFAULT 0,
                {cols},
                created_at TEXT NOT NULL
            )
            """
        )
        # Compteur de visites (= nombre d'étudiants ayant "cliqué" / ouvert la page)
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS visits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL
            )
            """
        )


@app.route("/")
def page_piege():
    """Page atteinte via le QR code : le faux formulaire."""
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT INTO visits (created_at) VALUES (?)",
            (datetime.now(timezone.utc).isoformat(),),
        )
    return render_template("form.html", fields=SENSITIVE_FIELDS)


@app.route("/submit", methods=["POST"])
def submit():
    """
    Réception du formulaire.

    ICI est le coeur de la conformité : on calcule des booléens de présence,
    puis on jette toutes les valeurs sensibles. Seul le matricule survit.
    """
    raw = {f: request.form.get(f, "") for f in SENSITIVE_FIELDS}

    # présence = le champ contient autre chose que du vide / espaces
    presence = {f: 1 if raw[f].strip() else 0 for f in SENSITIVE_FIELDS}
    matricule_clean = request.form.get("matricule", "").strip()
    matricule_fourni = 1 if matricule_clean else 0

    # /!\ à partir d'ici, `raw` n'est plus jamais utilisé.
    # Aucune valeur sensible n'atteint la base.
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
    placeholders = ", ".join("?" for _ in cols)
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            f"INSERT INTO submissions ({', '.join(cols)}) VALUES ({placeholders})",
            vals,
        )

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
    with sqlite3.connect(DB_PATH) as con:
        visites = con.execute("SELECT COUNT(*) FROM visits").fetchone()[0]
        total = con.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
        matricules = con.execute(
            "SELECT COUNT(*) FROM submissions WHERE matricule_fourni = 1"
        ).fetchone()[0]
        par_champ = {
            f: con.execute(
                f"SELECT COALESCE(SUM({f}_rempli), 0) FROM submissions"
            ).fetchone()[0]
            for f in SENSITIVE_FIELDS
        }

    return render_template(
        "stats.html",
        visites=visites,
        total=total,
        matricules=matricules,
        par_champ=par_champ,
    )


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
