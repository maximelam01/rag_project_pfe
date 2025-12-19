import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

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


load_dotenv()

# -------------------
# Configuration DB
# -------------------
PG_CONNECTION_STRING = (
    f"postgresql+psycopg2://"
    f"{os.getenv('PG_USER')}:{os.getenv('PG_PASSWORD')}"
    f"@{os.getenv('PG_HOST')}:{os.getenv('PG_PORT')}"
    f"/{os.getenv('PG_DB')}"
)

TABLE_NAME = "documents"


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str

class ChatRequest(BaseModel):
    question: str
    history: list[ChatMessage]


# -------------------
# Embeddings et vectordb
# -------------------
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
vectordb = PGVector(
    connection_string=PG_CONNECTION_STRING,
    embedding_function=embeddings,
    collection_name=TABLE_NAME
)

# -------------------
# Recherche interne
# -------------------
def retrieve_relevant_chunks(question: str, k: int = 5):
    docs = vectordb.similarity_search(query=question, k=k*2)
    unique_docs = []
    seen_texts = set()
    for doc in docs:
        if doc.page_content not in seen_texts:
            unique_docs.append(doc)
            seen_texts.add(doc.page_content)
        if len(unique_docs) >= k:
            break
    return unique_docs

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
    return serp.run(query)

@tool
def internal_document_search(query: str) -> str:
    """
    Recherche des informations pertinentes dans les documents internes
    stockés dans la base vectorielle.
    """
    docs = retrieve_relevant_chunks(query)
    return format_chunks(docs)

# -------------------
# CoT + synthèse
# -------------------


SYSTEM_PROMPT = """
Tu es un assistant pédagogique pour un cours de science politique.

Tu as accès à deux sources :
- Documents internes (via un outil de recherche interne)
- Recherche Internet (via un outil externe)

Règles strictes :
- Utilise TOUJOURS les documents internes en priorité
- Utilise la recherche Internet UNIQUEMENT si les documents internes sont insuffisants
- Indique clairement la provenance des informations utilisées (interne / externe) et commence par dire quelle "tool" tu utilises
- Ne fais aucune supposition sans source

Style :
- Clair
- Structuré
- Pédagogique
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
    agent_kwargs={
        "system_message": SystemMessage(content=SYSTEM_PROMPT)
    }
)

def format_history(history):
    return "\n".join(
        [f"{m.role.upper()}: {m.content}" for m in history]
    )

def answer_question(question: str, history: list):
    history_text = format_history(history)

    response = agent.invoke({
        "input": f"""
Historique de la conversation :
{history_text}

Question utilisateur :
{question}
"""
    })

    return response["output"]




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

@app.post("/ask")
async def ask_question(req: ChatRequest):
    answer = answer_question(
        question=req.question,
        history=req.history
    )
    return {"answer": answer}

