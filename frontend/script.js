const chat = document.getElementById("chat");
const input = document.getElementById("question");
const documentSelect = document.getElementById("document-select");
const progressContainer = document.getElementById("progress-container");
const qcmContainer = document.getElementById("qcm-container");

let history = [];

// Auto-resize textarea
input.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = (this.scrollHeight) + 'px';
});

async function loadDocuments() {
    try {
        const res = await fetch("/documents");
        const data = await res.json();
        data.documents.forEach(doc => {
            const option = document.createElement("option");
            option.value = doc;
            option.textContent = doc;
            documentSelect.appendChild(option);
        });
    } catch (e) { console.error("Erreur documents", e); }
}

function addMessage(role, content, isError = false) {
    const div = document.createElement("div");
    div.className = `message ${role} ${isError ? 'error-message' : ''}`;
    
    // Si c'est l'assistant, on transforme le Markdown en HTML
    // Si c'est l'utilisateur, on reste sur du texte simple (ou markdown aussi si tu veux)
    if (role === "assistant" && !content.includes("spinner")) {
        div.innerHTML = marked.parse(content);
    } else {
        // Pour le spinner ou le texte utilisateur simple
        div.innerHTML = content.replace(/\n/g, '<br>');
    }

    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
    return div;
}

async function askQuestion() {
    const question = input.value.trim();
    const selectedDocument = documentSelect.value;
    
    // REMPLACEMENT DE L'ALERT PAR UN MESSAGE DANS LE CHAT
    if (!selectedDocument) {
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
                body: JSON.stringify({ question, history, document: selectedDocument })
            });
        } else {
            const formData = new FormData();
            formData.append("question", question);
            formData.append("document", selectedDocument);
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
        
        // Conteneur pour le feedback spécifique à cette question
        const feedbackArea = document.createElement("div");
        feedbackArea.className = "qcm-feedback hidden";
        
        q.choices.forEach((choice, idx) => {
            const btn = document.createElement("button");
            btn.className = "qcm-choice-btn";
            btn.style = "display:block; width:100%; text-align:left; padding:12px; margin:5px 0; background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.1); color:white; border-radius:8px; cursor:pointer; transition: 0.3s;";
            btn.textContent = choice;
            
            btn.onclick = () => {
                // Désactiver tous les boutons de cette question après le clic
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

document.addEventListener("DOMContentLoaded", loadDocuments);
input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); askQuestion(); } });

documentSelect.addEventListener("change", () => {
    const selected = documentSelect.value;
    const info = document.getElementById("selected-course");
    
    if (selected) {
        // On met à jour le contenu
        info.innerHTML = `<i class="fas fa-file-alt"></i> Focus : <strong>${selected}</strong>`;
        
        // On applique la couleur HEIP
        info.style.color = "var(--accent-color)";
        
        // On ajoute l'animation de battement
        info.classList.remove("pulse-animation");
        void info.offsetWidth; // "Magic trick" pour redémarrer l'animation CSS
        info.classList.add("pulse-animation");
    } else {
        info.textContent = "Aucun document chargé";
        info.style.color = "";
        info.classList.remove("pulse-animation");
    }
});