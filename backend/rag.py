import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from fastapi import UploadFile, File
from fastapi import Form
from fastapi.responses import JSONResponse
import json

import re
import logging
import sys
from pydantic import BaseModel
from dotenv import load_dotenv

# LangChain
from langchain_community.vectorstores import PGVector
from langchain_openai import OpenAIEmbeddings
from langchain.chat_models import ChatOpenAI
from langchain_community.utilities import SerpAPIWrapper
from langchain.tools import tool
from langchain.schema import Document
from langchain.agents import initialize_agent, AgentType
from langchain.schema import SystemMessage
from langchain.schema import HumanMessage

from sqlalchemy import create_engine, text

# PDF generation
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
import io
from fastapi.responses import StreamingResponse

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s %(levelname)s %(message)s"
)

# Logger principal
logger = logging.getLogger("uvicorn")  # ou "uvicorn.error" pour tout
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.propagate = False

# -------------------
# Configuration DB
# -------------------
PG_CONNECTION_STRING = (
    f"postgresql+psycopg2://"
    f"{os.getenv('PG_USER')}:{os.getenv('PG_PASSWORD')}"
    f"@{os.getenv('PG_HOST')}:{os.getenv('PG_PORT')}"
    f"/{os.getenv('PG_DB')}"
)

engine = create_engine(PG_CONNECTION_STRING)

TABLE_NAME = "langchain_pg_embedding"
CURRENT_SELECTED_DOC = None
CURRENT_USER_QUESTION = None

class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str

class ChatRequest(BaseModel):
    question: str
    history: list[ChatMessage]
    document: str | list[str] | None = None

# -------------------
# Embeddings et vectordb
# -------------------
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
vectordb = PGVector(
    connection_string=PG_CONNECTION_STRING,
    embedding_function=embeddings,
    collection_name="documents" # Correspond au nom dans langchain_pg_collection
)

# -------------------
# Recherche interne
# -------------------
def retrieve_relevant_chunks(question: str, k: int = 8, document_name: str | list | None = None):
    filter_metadata = None

    if document_name:
        # Cas 1 : C'est une liste
        if isinstance(document_name, list):
            if len(document_name) == 1:
                # UN SEUL document dans la liste -> on simplifie le filtre
                filter_metadata = {"source": document_name[0]}
            elif len(document_name) > 1:
                # PLUSIEURS documents -> on utilise $in
                filter_metadata = {"source": {"$in": document_name}}
        
        # Cas 2 : C'est une string (et pas GLOBAL)
        elif isinstance(document_name, str) and document_name != "GLOBAL":
            filter_metadata = {"source": document_name}

    logger.info("="*50)
    logger.info("--- 🔍 DÉBUT RECHERCHE VECTORIELLE ---")
    logger.info(f"Question envoyée à PGVector: '{question}'")
    logger.info(f"Filtre appliqué: {filter_metadata}")

    docs = vectordb.similarity_search(
        query=question,
        k=k,
        filter=filter_metadata
    )

    logger.info(f"✅ [VECTOR SEARCH] {len(docs)} chunks récupérés.")
    for i, doc in enumerate(docs):
        # On affiche les 100 premiers caractères de chaque chunk pour le suivi
        content_snippet = doc.page_content.replace('\n', ' ')[:100]
        logger.info(f"   [Chunk {i+1}] Source: {doc.metadata.get('source')} | Contenu: {content_snippet}...")
    logger.info("="*50)

    return docs

def format_chunks(chunks):
    return "\n\n".join([doc.page_content for doc in chunks])

# -------------------
# Recherche externe
# -------------------
serp = SerpAPIWrapper()  # nécessite SERPAPI_API_KEY dans .env

@tool
def external_search_tool(query: str) -> str:
    """
    Effectue une recherche Internet via SerpAPI.
    À utiliser uniquement si les informations ne sont pas disponibles
    dans les documents internes ou si des notions sont complexes.
    """

    logger.info(f"🛠️ Tool utilisé avec la question forcée : {query}")
    logger.info(f"🌐 [TOOL: EXTERNAL] Recherche web pour : '{query}'")
    
    res = serp.run(query)
    logger.info(f"✅ [TOOL: EXTERNAL] Résultat récupéré (reponse: {res} ")
    return res

@tool
def internal_document_search(query: str) -> str:
    """
    Recherche des informations pertinentes dans les cours de science politique.
    Utilise cet outil pour répondre aux questions sur le contenu des cours.
    """

    

    logger.info(f"🛠️ [TOOL: INTERNAL] Requête finale choisie : '{query}'")
    logger.info(f"📍 [TOOL: INTERNAL] Contexte Document: {CURRENT_SELECTED_DOC}")

    docs = retrieve_relevant_chunks(query, document_name=CURRENT_SELECTED_DOC)
    return "\n\n".join([doc.page_content for doc in docs])

# -------------------
# CoT + synthèse
# -------------------


SYSTEM_PROMPT = """
Tu es Polly AI, un assistant pédagogique strict pour un cours de science politique ({course_name}). (mentionne ce nom si l'utilisateur pose des questions sur l'identité du cours). 

### 🎓 POSTURE PÉDAGOGIQUE & ÉTHIQUE
1. TON BUT : Tu es un mentor dont l'objectif est la COMPRÉHENSION. Tu dois aider l'étudiant à assimiler les concepts, pas faire le travail à sa place.
2. INTERDICTION : Tu ne dois JAMAIS rédiger un devoir complet, une dissertation entière ou répondre à un exercice de bout en bout.
3. MÉTHODE : Si un étudiant demande de faire un travail, décompose la tâche. Explique la méthodologie, définis les concepts clés et aiguille l'étudiant vers les parties pertinentes du cours pour qu'il puisse construire sa propre réponse.
4. GUIDAGE : Pose des questions réflexives pour vérifier la compréhension ou suggère des pistes de réflexion.

### 🛠️ PROTOCOLE DE RÉPONSE OBLIGATOIRE
1. Tu dois TOUJOURS commencer par utiliser l'outil 'internal_document_search' pour chercher l'information, même si la question semble générale ou factuelle.
2. Si, et seulement si, l'outil interne ne renvoie pas l'information (ou si tu as un doute sérieux), tu dois répondre : 
   "Je suis désolé, je ne trouve pas cette information dans le cours '{course_name}'. Souhaitez-vous que je fasse une recherche sur Internet pour vous ?"
3. INTERDICTION : Tu ne dois JAMAIS utiliser l'outil 'external_search_tool' de ta propre initiative.
4. Tu ne peux utiliser 'external_search_tool' QUE SI l'utilisateur a explicitement répondu "Oui" ou "Cherche sur internet" à ta proposition.

### 📋 RÈGLES STRICTES
1. Si l'utilisateur pose une question globale ("De quoi parle ce cours ?", "Fais un résumé"), utilise l'outil 'internal_document_search' avec une requête large comme "résumé thèmes principaux" pour obtenir du contexte.
2. Si un document est sélectionné, RESTE strictement dans le cadre de ce document.
3. Si tu ne trouves pas la réponse dans le document interne, dis-le clairement avant de proposer une recherche Internet.
4. Ne réponds jamais à une question qui n'a aucun rapport avec le cours sélectionné.
5. Indique clairement la provenance des informations utilisées (interne / externe) et commence par dire quelle "tool" tu utilises
6. Ne fais aucune supposition sans source

### 🧠 RÈGLE DE REFORMULATION
Avant d'utiliser un outil (interne ou externe), tu dois transformer la question de l'utilisateur en une requête complète et autonome, en utilisant l'historique de la conversation.
Exemple : 
- User : "Parle moi de la démocratie." 
- Agent : (Cherche "démocratie")
- User : "Donne moi des exemples." 
- Agent : (Cherche "exemples de démocratie science politique") et non juste "exemples".

### 🎨 DIRECTIVES DE STYLE ET FORMATAGE (MARKDOWN OBLIGATOIRE)
1. Titres : Utilise '###' pour les sections principales.
2. Mise en forme : Utilise le **gras** pour les concepts clés et l'italique pour les citations ou termes latins.
3. Listes : Organise tes explications avec des listes à puces (•) ou numérotées.
4. Structure : Tes réponses doivent être aérées avec des sauts de ligne clairs.
5. Emojis : Utilise des emojis pertinents (📚, ⚖️, 🏛️, 🗳️) pour rendre la lecture agréable.
6. Tableaux : Si tu compares deux concepts (ex: Démocratie vs Totalitarisme), utilise un tableau Markdown.
"""


llm = ChatOpenAI(model_name="gpt-4", temperature=0)

tools = [
    internal_document_search,
    external_search_tool
]

agent = initialize_agent(
    tools=tools,
    llm=llm,
    agent=AgentType.OPENAI_FUNCTIONS,
    verbose=True,
)

def format_history(history):
    return "\n".join(
        [f"{m.role.upper()}: {m.content}" for m in history]
    )

def answer_question(question: str, history: list):
    history_text = format_history(history)
    
    if isinstance(CURRENT_SELECTED_DOC, list):
        doc_display = ", ".join(CURRENT_SELECTED_DOC)
    else:
        doc_display = CURRENT_SELECTED_DOC

    dynamic_system_prompt = SYSTEM_PROMPT.format(course_name=doc_display)

    response = agent.invoke({
        "input": f"""
SYSTEM_INSTRUCTIONS: {dynamic_system_prompt}

### 💡 RAPPEL DE TA MISSION
Tu es un **tuteur pédagogique**. Ton but est d'accompagner l'étudiant vers la compréhension. 
Si la question demande de "faire à sa place", refuse poliment et propose une décomposition méthodologique.

### 📚 CONTEXTE DE TRAVAIL
Document(s) sélectionné(s) : "{CURRENT_SELECTED_DOC}"
(Si "GLOBAL", tu as accès à toute la base de connaissance).

### 💬 ÉCHANGES PRÉCÉDENTS
{history_text}

### ❓ QUESTION À TRAITER
{question}

RAPPEL : **CONSIGNE DE SORTIE :** Réponds en utilisant un Markdown riche (###, **, •).
"""
    })

    return response["output"]


def normalize_llm_json(text: str) -> str:
    # Supprimer balises ```json ``` si présentes
    text = re.sub(r"```json|```", "", text)

    # Remplacer guillemets typographiques
    text = text.replace("“", "\"").replace("”", "\"")

    # Supprimer virgules finales avant } ou ]
    text = re.sub(r",\s*([}\]])", r"\1", text)

    return text.strip()


def validate_qcm(qcm: dict):
    if "title" not in qcm or "questions" not in qcm:
        raise ValueError("Structure QCM invalide")

    if not isinstance(qcm["questions"], list) or len(qcm["questions"]) == 0:
        raise ValueError("Aucune question dans le QCM")

    for q in qcm["questions"]:
        for key in ["question", "choices", "correct", "explanation"]:
            if key not in q:
                raise ValueError(f"Champ manquant : {key}")

        if not isinstance(q["choices"], list):
            raise ValueError("choices doit être une liste")

        q["correct"] = int(q["correct"])  # sécurité

# -------------------
# FastAPI
# -------------------
app = FastAPI()

# CORS pour frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# Serve frontend statique
app.mount("/static", StaticFiles(directory="frontend"), name="static")
@app.get("/")
async def serve_index():
    return FileResponse("frontend/index.html")

class Question(BaseModel):
    question: str


@app.get("/documents")
async def list_documents():
    """
    Récupère la liste des documents avec un cast explicite en JSONB
    """
    # On ajoute ::jsonb pour régler le problème d'opérateur
    query = text("""
        SELECT DISTINCT cmetadata->>'source' AS source_name
        FROM langchain_pg_embedding
        WHERE cmetadata IS NOT NULL 
          AND cmetadata::jsonb ? 'source'
        ORDER BY source_name;
    """)
    try:
        with engine.connect() as conn:
            results = conn.execute(query).fetchall()
            documents = [row[0] for row in results if row[0] is not None]
            logger.info(f"✅ Documents récupérés : {documents}")
            return {"documents": documents}
    except Exception as e:
        logger.error(f"❌ Erreur SQL dans list_documents : {e}")
        return JSONResponse(
            status_code=500, 
            content={"error": "Erreur SQL", "details": str(e)}
        )


@app.post("/ask")
async def ask_question(req: ChatRequest):
    global CURRENT_SELECTED_DOC, CURRENT_USER_QUESTION
    
    logger.info("\n" + "🚀"*20)
    logger.info(f"RÉCEPTION REQUÊTE /ASK")
    logger.info(f"Utilisateur demande: '{req.question}'")
    logger.info(f"Document sélectionné: '{req.document}'")

    if not req.document:
        return {"answer": "⚠️ Veuillez sélectionner un cours."}

    CURRENT_SELECTED_DOC = req.document 
    CURRENT_USER_QUESTION = req.question  
    
    answer = answer_question(
        question=req.question,
        history=req.history
    )

    logger.info(f"📤 RÉPONSE FINALE ENVOYÉE : {answer[:100]}...")
    logger.info("🚀"*20 + "\n")

    return {"answer": answer}

@app.post("/generate-qcm")
async def generate_qcm(question: str = Form(...), document: str = Form(None)):

    actual_docs = document
    if document and "," in document:
        actual_docs = [d.strip() for d in document.split(",")]

    logger.info("📝 [QCM] Demande de génération reçue")
    logger.info(f"📝 [QCM] Sujet: '{question}' | Source: '{actual_docs}'")
    
    try:
        # 1️⃣ Récupérer les documents internes
        # Utilisation du filtre aussi pour le QCM
        docs = retrieve_relevant_chunks(question, k=8, document_name=actual_docs)
        context_text = "\n\n".join([doc.page_content for doc in docs])

        if not context_text.strip():
            return JSONResponse(
                status_code=404, 
                content={"error": "Aucun contenu trouvé pour générer ce QCM."}
            )

        # 2️⃣ Prompt
        QCM_PROMPT = """
Tu es un enseignant expert en science politique. 
L'élève souhaite un QCM spécifique sur le sujet suivant : "{user_query}"

Utilise les documents de référence fournis ci-dessous pour créer les questions. 

Réponds EXCLUSIVEMENT par du JSON valide.

Format attendu :
{{
  "title": "Titre du QCM",
  "questions": [
    {{
      "question": "Texte de la question",
      "choices": ["Choix 0", "Choix 1", "Choix 2", "Choix 3"],
      "correct": 0,
      "explanation": "Pourquoi c'est la bonne réponse"
    }}
  ]
}}

Documents de référence :
{document}
"""
        # Injection des variables
        prompt = QCM_PROMPT.format(user_query=question, document=context_text)  
        # 3️⃣ Appel LLM
        response = llm.invoke([HumanMessage(content=prompt)])
        raw_content = response.content
        logger.info("Raw response du LLM : %s", raw_content)

        # 4️⃣ Extraction robuste du JSON par Regex
        # Cherche le premier '{' et le dernier '}' pour ignorer le texte autour
        match = re.search(r"(\{.*\})", raw_content, re.DOTALL)
        
        if not match:
            return JSONResponse(
                status_code=500, 
                content={"error": "Le modèle n'a pas généré un format JSON valide", "raw": raw_content}
            )

        clean_content = normalize_llm_json(match.group(1))

        try:
            qcm_json = json.loads(clean_content)
            validate_qcm(qcm_json)
            return JSONResponse(content=qcm_json)
        except json.JSONDecodeError as e:
            logger.error("Erreur parsing : %s", clean_content)
            return JSONResponse(
                status_code=500, 
                content={"error": "Erreur de décodage JSON", "details": str(e)}
            )

    except Exception as e:
        logger.exception("Erreur interne generate-qcm")
        return JSONResponse(
            status_code=500, 
            content={"error": "Erreur serveur interne", "details": str(e)}
        )
    
@app.post("/generate-revision-sheet")
async def generate_revision_sheet(document: str = Form(...)):
    actual_docs = [d.strip() for d in document.split(",")] if "," in document else [document]
    doc_name = actual_docs[0]
    
    # 1. Récupération et synthèse par le LLM
    chunks = retrieve_relevant_chunks("Concepts clés, définitions importantes et résumé structuré", k=15, document_name=actual_docs)
    context_text = format_chunks(chunks)

    prompt = f"""
    Tu es un expert en pédagogie spécialisé en Science Politique. 
    Génère une fiche de révision académique pour le cours : "{doc_name}".
    Utilise exclusivement les documents fournis.

    ### 🎨 DIRECTIVES DE STYLE ET FORMATAGE (OBLIGATOIRE)
    1. Titres : Utilise '###' pour les sections principales.
    2. Mise en forme : Utilise le **gras** pour les concepts clés.
    3. Listes : Organise avec des listes à puces (•).
    4. Structure : Aérée avec des sauts de ligne clairs.
    5. ⚠️ INTERDICTION (TABLEAUX) : Ne génère JAMAIS de tableaux Markdown. Si tu dois comparer des éléments ou présenter des données, utilise systématiquement des listes à puces structurées et hiérarchisées.
    6. ⚠️ INTERDICTION : N'utilise AUCUN emoji dans cette fiche. Reste sur un ton formel et académique.

    Structure attendue :
    - Un titre majestueux
    - Introduction (Les enjeux du cours)
    - Concepts Clés (Définitions en gras)
    - Synthèse thématique (Points essentiels)

    Texte de référence : {context_text}
    """
    
    response = llm.invoke([HumanMessage(content=prompt)])
    content = response.content

    # 2. Construction du PDF
    buffer = io.BytesIO()
    # Marges plus larges pour un look plus pro
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    styles = getSampleStyleSheet()
    
    # Styles personnalisés
    style_header = ParagraphStyle('Header', parent=styles['Normal'], fontSize=9, textColor=colors.grey)
    style_title = ParagraphStyle(
        'Title', 
        parent=styles['Heading1'], 
        fontSize=24, 
        textColor=colors.HexColor("#96151b"), # Correction ici
        spaceAfter=30, 
        alignment=1
    )
    style_sub = ParagraphStyle(
        'Sub', 
        parent=styles['Heading2'], 
        fontSize=14, 
        textColor=colors.HexColor("#96151b"), # Correction ici
        spaceBefore=15, 
        spaceAfter=10, 
        borderPadding=5
    )
    
    elements = []

    # En-tête : "Polly AI - Assistant Pédagogique"
    elements.append(Paragraph("POLLY AI | Assistant Pédagogique Intelligent", style_header))
    elements.append(Spacer(1, 12))
    
    # Transformation du contenu LLM
    lines = content.split('\n')
    for line in lines:
        clean_line = line.strip()
        if not clean_line: continue

        # 1. Gestion des Titres (###)
        if clean_line.startswith('###'):
            # On retire les ### et on nettoie les éventuels ** que le LLM aurait mis dans le titre
            text_content = clean_line.replace('###', '').replace('**', '').replace('*', '').strip()
            elements.append(Paragraph(text_content, style_sub))
        
        # 2. Gestion des Listes (• ou -)
        elif clean_line.startswith('•') or clean_line.startswith('-'):
            text_content = clean_line.lstrip('•- ').strip()
            # Transformation du gras/italique Markdown en balises PDF
            text_content = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text_content)
            text_content = re.sub(r"\*(.*?)\*", r"<i>\1</i>", text_content)
            elements.append(Paragraph(text_content, styles['Bullet']))
            
        # 3. Texte standard
        else:
            # Transformation du gras/italique Markdown en balises PDF
            clean_line = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", clean_line)
            clean_line = re.sub(r"\*(.*?)\*", r"<i>\1</i>", clean_line)
            elements.append(Paragraph(clean_line, styles['Normal']))
        
        elements.append(Spacer(1, 8))

    # Pied de page
    elements.append(Spacer(1, 30))
    elements.append(Paragraph("<hr/>", styles['Normal']))
    elements.append(Paragraph(f"Généré par Polly AI - Projet de Fin d'Études 2026 - Cours : {doc_name}", style_header))

    doc.build(elements)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Fiche_{doc_name.replace(' ', '_')}.pdf"}
    )