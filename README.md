# 🎓 Assistant Pédagogique Intelligent - Science Politique

Cet assistant est une plateforme d'apprentissage interactive conçue pour accompagner les étudiants en science politique. Grâce à une architecture **RAG (Retrieval-Augmented Generation)** et un système d'**Agents autonomes**, l'application permet d'interroger des supports de cours spécifiques et de générer des QCM personnalisés.



## 🚀 Fonctionnalités Clés

* **RAG Sécurisé** : L'assistant priorise systématiquement les documents de cours chargés en base de données vectorielle (PostgreSQL/PGVector).
* **Agent de Reformulation** : Capacité à comprendre les questions de suivi (ex: "Dis-m'en plus", "Donne-moi un exemple") en utilisant l'historique de la conversation pour générer des requêtes autonomes riches en mots-clés.
* **Recherche Hybride** : Bascule intelligente vers Internet (SerpAPI) uniquement après validation de l'utilisateur si l'information est absente du cours.
* **Générateur de QCM** : Création automatique de questionnaires au format JSON basés sur le contexte spécifique du document sélectionné.
* **Audit Log Complet** : Suivi en temps réel des processus de recherche (Vector search, Tool usage, Query translation).

---

## 🛠️ Stack Technique

* **Backend** : FastAPI (Python 3.10+)
* **IA & Orchestration** : LangChain, OpenAI GPT-4
* **Base de Données Vectorielle** : PostgreSQL avec l'extension **PGVector**
* **Embeddings** : OpenAI `text-embedding-3-small`
* **Recherche Web** : SerpAPI
* **Frontend** : HTML5 / CSS3 / JavaScript (Vanilla)

---

## 🏗️ Architecture du Système

Le projet repose sur un **Agent de type "OpenAI Functions"** qui arbitre entre deux outils principaux via un processus de réflexion (Chain of Thought) :

1.  **`internal_document_search`** : Interroge la base PostgreSQL pour extraire les paragraphes les plus pertinents via une recherche par similarité cosinus sur les embeddings.
2.  **`external_search_tool`** : Effectue une recherche Google via SerpAPI en cas de lacune avérée dans le corpus interne, après consentement explicite de l'utilisateur.



---

## ⚙️ Installation et Configuration

### 1. Pré-requis
* PostgreSQL 15+ avec l'extension `vector` installée.
* Clé API OpenAI et Clé API SerpAPI.

### 2. Configuration de l'environnement
Créez un fichier `.env` à la racine du projet :
```env
OPENAI_API_KEY=votre_cle_openai
SERPAPI_API_KEY=votre_cle_serpapi
PG_HOST=localhost
PG_PORT=5432
PG_USER=votre_user
PG_PASSWORD=votre_mdp
PG_DB=votre_base
```
3. Lancement
Bash

# Installation des dépendances
pip install -r requirements.txt

# Lancement du serveur
uvicorn main:app --reload
📋 Logique de Dialogue (Chain of Thought)
Le système garantit la traçabilité des décisions et la pertinence des recherches. Voici un exemple de comportement lors d'une question de suivi :

Input Utilisateur : "Dis-m'en plus sur ça."

Reformulation IA : L'Agent analyse l'historique (ex: le pouvoir législatif) et transforme l'input en : "Détails sur les fonctions du parlement et le processus législatif".

Action : Appel de l'outil internal_document_search avec la requête reformulée.

Synthèse : Analyse des chunks récupérés. Si l'info est absente, l'agent déclenche le protocole de demande d'accès à Internet.

🧠 Protocole du Prompt Système
L'agent est piloté par un protocole strict défini dans le SYSTEM_PROMPT :

Priorité absolue au document sélectionné (course_name).

Interdiction de recherche internet autonome (consentement utilisateur obligatoire).

Honnêteté intellectuelle : L'IA indique clairement l'origine de l'information (Interne vs Externe).

Style pédagogique : Clair, structuré et sans suppositions hors-contexte.

📝 Format des Données (QCM)
Les QCM générés suivent une structure JSON stricte, permettant une intégration dynamique côté Frontend :

JSON

{
  "title": "Titre du QCM",
  "questions": [
    {
      "question": "Texte de la question",
      "choices": ["Choix A", "Choix B", "Choix C", "Choix D"],
      "correct": 0,
      "explanation": "Explication pédagogique basée sur le cours"
    }
  ]
}
👨‍💻 Auteur
[Maxime LAMBERT] - Projet de Fin d'Études (2026)
