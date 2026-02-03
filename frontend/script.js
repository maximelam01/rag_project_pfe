const chat = document.getElementById("chat");
const input = document.getElementById("question");
const progressContainer = document.getElementById("progress-container");
const qcmContainer = document.getElementById("qcm-container");

let history = [];
let currentMode = 'GLOBAL';
let selectedDoc = 'GLOBAL'; // Valeur par défaut pour le mode GLOBAL
let selectedDocsSet = new Set();

// Auto-resize textarea
input.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = (this.scrollHeight) + 'px';
});

async function loadDocuments() {
    try {
        const res = await fetch("/documents");
        const data = await res.json();
        const container = document.getElementById("document-cards");
        container.innerHTML = "";
        
        data.documents.forEach(doc => {
            const card = document.createElement("div");
            card.title = doc;
            card.className = "doc-card";
            card.innerHTML = `<i class="far fa-file-alt"></i> <span>${doc}</span>`;
            
            card.onclick = () => {
                if (selectedDocsSet.has(doc)) {
                    selectedDocsSet.delete(doc);
                    card.classList.remove("selected");
                } else {
                    selectedDocsSet.add(doc);
                    card.classList.add("selected");
                }
                
                // Mise à jour de la variable globale pour le backend
                selectedDoc = Array.from(selectedDocsSet);
                if (selectedDoc.length === 0) selectedDoc = null;
                
                updateInfoDisplay();
            };
            
            container.appendChild(card);
        });
    } catch (e) { console.error("Erreur documents", e); }
}

function setMode(mode) {
    currentMode = mode;
    const btnGlobal = document.getElementById('btn-global');
    const btnPrecis = document.getElementById('btn-precis');
    const listContainer = document.getElementById('document-list-container');
    const info = document.getElementById("selected-course");

    // Mise à jour visuelle des boutons
    if(btnGlobal) btnGlobal.classList.toggle('active', mode === 'GLOBAL');
    if(btnPrecis) btnPrecis.classList.toggle('active', mode === 'PRECIS');
    
    if (mode === 'GLOBAL') {
        if(listContainer) listContainer.classList.add('hidden');
        selectedDoc = 'GLOBAL';
    } else {
        if(listContainer) listContainer.classList.remove('hidden');
        // On récupère les documents sélectionnés dans le Set
        selectedDoc = Array.from(selectedDocsSet);
        // Si le set est vide, on met null pour afficher l'alerte
        if (selectedDoc.length === 0) selectedDoc = null;
    }
    updateInfoDisplay();
}

// Fonction pour mettre à jour l'affichage du cours sélectionné
function updateInfoDisplay() {
    const info = document.getElementById("selected-course");
    if (!info) return;

    if (currentMode === 'GLOBAL') {
        info.innerHTML = `<i class="fas fa-globe"></i> Mode : <strong>Recherche Globale</strong>`;
    } else if (selectedDoc && Array.isArray(selectedDoc)) {
        const count = selectedDoc.length;
        info.innerHTML = `<i class="fas fa-file-alt"></i> Focus : <strong>${count} cours sélectionné(s)</strong>`;
        info.style.color = "var(--accent-color)";
    } else {
        info.innerHTML = `<span style="color: #fca5a5;">⚠️ Sélectionnez au moins un cours</span>`;
    }
}

function addMessage(role, content, isError = false) {
    const div = document.createElement("div");
    div.className = `message ${role} ${isError ? 'error-message' : ''}`;
    
    if (role === "assistant" && !content.includes("spinner")) {
        div.innerHTML = marked.parse(content);
    } else {
        div.innerHTML = content.replace(/\n/g, '<br>');
    }

    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
    return div;
}

async function askQuestion() {
    const question = input.value.trim();
    console.log("Valeur de selectedDoc avant envoi:", selectedDoc);
    console.log("Type de selectedDoc:", Array.isArray(selectedDoc) ? "Array" : typeof selectedDoc);
    // On utilise selectedDoc qui est mis à jour par le mode ou le select
    const finalDoc = selectedDoc;
    
    if (!finalDoc) {
        addMessage("assistant", "⚠️ **Action requise** : Veuillez sélectionner un cours dans la barre latérale avant de poser une question.", true);
        return;
    }
    if (!question) return;

    input.value = "";
    input.style.height = 'auto';
    addMessage("user", question);
    history.push({ role: "user", content: question });

    const isQCM = question.toLowerCase().match(/(qcm|quiz|test)/);
    const loadingMsg = addMessage("assistant", "<div class='spinner'></div>");

    if (isQCM) progressContainer.classList.remove("hidden");

    try {
        let res;
        if (!isQCM) {
            res = await fetch("/ask", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ 
                    question, 
                    history, 
                    document: finalDoc // On envoie soit "GLOBAL" soit le nom du cours
                })
            });
        } else {
            const formData = new FormData();
            formData.append("question", question);
            const docValue = Array.isArray(finalDoc) ? finalDoc.join(",") : finalDoc;
            formData.append("document", docValue);
            res = await fetch("/generate-qcm", { method: "POST", body: formData });
        }

        const data = await res.json();
        loadingMsg.remove();
        progressContainer.classList.add("hidden");

        if (isQCM) {
            if (data.error) {
                addMessage("assistant", `❌ ${data.error}`, true);
            } else {
                renderQCM(data);
            }
        } else {
            addMessage("assistant", data.answer);
            history.push({ role: "assistant", content: data.answer });
        }
    } catch (e) {
        loadingMsg.innerHTML = "❌ Erreur de connexion au serveur.";
    }
}

function renderQCM(qcm) {
    qcmContainer.innerHTML = `<button class='close-qcm' onclick='this.parentElement.classList.add("hidden")'>&times;</button>
                              <h2 style='color:var(--accent-color); margin-bottom:20px;'>${qcm.title}</h2>`;
    qcmContainer.classList.remove("hidden");

    qcm.questions.forEach((q, i) => {
        const div = document.createElement("div");
        div.className = "qcm-question";
        div.innerHTML = `<h4>${i+1}. ${q.question}</h4>`;
        
        const feedbackArea = document.createElement("div");
        feedbackArea.className = "qcm-feedback hidden";
        
        q.choices.forEach((choice, idx) => {
            const btn = document.createElement("button");
            btn.className = "qcm-choice-btn";
            btn.style = "display:block; width:100%; text-align:left; padding:12px; margin:5px 0; background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.1); color:white; border-radius:8px; cursor:pointer; transition: 0.3s;";
            btn.textContent = choice;
            
            btn.onclick = () => {
                const siblingBtns = div.querySelectorAll(".qcm-choice-btn");
                siblingBtns.forEach(b => b.style.pointerEvents = "none");

                feedbackArea.classList.remove("hidden");
                if(idx == q.correct) {
                    btn.style.background = "#22c55e";
                    btn.style.borderColor = "#22c55e";
                    feedbackArea.innerHTML = `<p style="color:#22c55e; margin-top:10px;">✅ <strong>Correct !</strong> ${q.explanation}</p>`;
                } else {
                    btn.style.background = "#ef4444";
                    btn.style.borderColor = "#ef4444";
                    feedbackArea.innerHTML = `<p style="color:#ef4444; margin-top:10px;">❌ <strong>Faux.</strong> ${q.explanation}</p>`;
                }
            };
            div.appendChild(btn);
        });
        div.appendChild(feedbackArea);
        qcmContainer.appendChild(div);
    });
}


input.addEventListener("keydown", (e) => { 
    if (e.key === "Enter" && !e.shiftKey) { 
        e.preventDefault(); 
        askQuestion(); 
    } 
});



window.setMode = setMode; 

document.addEventListener("DOMContentLoaded", () => {
    loadDocuments();
    setMode('GLOBAL'); 
});

document.getElementById('card-search')?.addEventListener('input', function(e) {
    const term = e.target.value.toLowerCase();
    const cards = document.querySelectorAll('.doc-card');
    
    cards.forEach(card => {
        const text = card.innerText.toLowerCase();
        card.style.display = text.includes(term) ? 'flex' : 'none';
    });
});

async function generateRevision() {
    const finalDoc = selectedDoc;
    
    if (!finalDoc || finalDoc === 'GLOBAL') {
        addMessage("assistant", "⚠️ **Action requise** : Veuillez sélectionner un cours spécifique pour générer une fiche.", true);
        return;
    }

    const btn = document.getElementById("btn-revision");
    btn.disabled = true;
    const loadingMsg = addMessage("assistant", "<div class='spinner'></div><p>Génération de votre fiche de révision personnalisée...</p>");

    try {
        const formData = new FormData();
        const docValue = Array.isArray(finalDoc) ? finalDoc.join(",") : finalDoc;
        formData.append("document", docValue);

        const res = await fetch("/generate-revision-sheet", { method: "POST", body: formData });

        if (res.ok) {
            const blob = await res.blob();
            const url = window.URL.createObjectURL(blob);
            
            loadingMsg.remove(); 

            const div = document.createElement("div");
            div.className = "message assistant";
            div.innerHTML = `
                <p>✅ Ta fiche de révision pour <strong>${docValue}</strong> est prête !</p>
                <div class="pdf-action-container">
                    <a href="${url}" target="_blank" class="download-link-card" style="flex: 1;">
                        <i class="fas fa-eye"></i>
                        <span>Aperçu</span>
                    </a>
                    <a href="${url}" download="Fiche_${docValue.replace(/\s+/g, '_')}.pdf" class="download-link-card" style="flex: 1;">
                        <i class="fas fa-download"></i>
                        <span>Télécharger</span>
                    </a>
                </div>
            `;
            chat.appendChild(div);
            chat.scrollTop = chat.scrollHeight;
        }
    } catch (e) {
        loadingMsg.innerHTML = "❌ Erreur lors de la génération.";
    } finally {
        btn.disabled = false;
    }
}