// ==========================================
// 1. Variables Globales & Selecteurs
// ==========================================
const chat = document.getElementById("chat");
const input = document.getElementById("question");
// On récupère ces éléments ici pour qu'ils soient accessibles par toutes les fonctions
const documentSelect = document.getElementById("document-select");
const selectedCourseLabel = document.getElementById("selected-course");

let history = [];
const MAX_MESSAGES = 20;

// ==========================================
// 2. Fonctions Utilitaires
// ==========================================

function isQCMRequest(text) {
    const lowerText = text.toLowerCase();
    return lowerText.includes("qcm") || lowerText.includes("quiz") || lowerText.includes("test");
}

function addMessage(role, content) {
    const div = document.createElement("div");
    div.className = `message ${role}`;
    div.textContent = content;
    chat.appendChild(div);
    
    // Scroll automatique
    setTimeout(() => {
        chat.scrollTo({
            top: chat.scrollHeight,
            behavior: 'smooth'
        });
    }, 50); 
    
    return div;
}

// ==========================================
// 3. Logique Principale (Chat & QCM)
// ==========================================

async function loadDocuments() {
    try {
        const res = await fetch("/documents");
        const data = await res.json();
        
        console.log("Documents reçus du backend :", data.documents); 

        // On vide d'abord sauf l'option par défaut si besoin, 
        // ou on ajoute simplement à la suite.
        // Ici on garde "Tous les cours" (déjà dans le HTML) et on ajoute le reste.
        data.documents.forEach(doc => {
            const option = document.createElement("option");
            option.value = doc;
            option.textContent = doc;
            documentSelect.appendChild(option);
        });
    } catch (e) {
        console.error("Erreur chargement documents", e);
    }
}

async function askQuestion() {
    const question = input.value.trim();
    // Utilisation de la variable globale définie en haut
    const selectedDocument = documentSelect.value;
    
    // BLOCAGE : Si aucun document n'est sélectionné, on alerte l'utilisateur
    if (!selectedDocument) {
        alert("⚠️ Veuillez sélectionner un cours dans la liste avant de poser votre question.");
        return;
    }
    
    if (!question) return;

    // Elements de progression
    const progressContainer = document.getElementById("progress-container");
    const qcmContainer = document.getElementById("qcm-container");

    input.value = "";
    addMessage("user", question);
    history.push({ role: "user", content: question });

    const loadingMsg = addMessage("assistant", "⏳ Chargement...");
    const isQCM = isQCMRequest(question);
    const endpoint = isQCM ? "/generate-qcm" : "/ask";

    // Afficher la barre si c'est un QCM
    if (isQCM) {
        progressContainer.classList.remove("hidden");
        qcmContainer.classList.add("hidden"); 
    }

    try {
        let res;
        if (endpoint === "/ask") {
            res = await fetch(endpoint, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    question,
                    history,
                    document: selectedDocument || null
                })
            });
        } else {
            const formData = new FormData();
            formData.append("question", question);
            formData.append("document", selectedDocument || "");
            res = await fetch(endpoint, {
                method: "POST",
                body: formData
            });
        }

        const text = await res.text();
        
        // Nettoyage de l'interface après réception
        loadingMsg.remove();
        progressContainer.classList.add("hidden");

        let data;
        try {
            data = JSON.parse(text.trim());
        } catch (err) {
            console.error("Réponse non JSON reçue :", text);
            addMessage("assistant", "❌ Erreur de formatage.");
            return;
        }

        if (endpoint === "/generate-qcm") {
            if (data.error) {
                addMessage("assistant", `❌ ${data.error}`);
                return;
            }
            addMessage("assistant", "📝 QCM généré !");
            renderQCM(data);
        } else {
            if (data.answer) {
                addMessage("assistant", data.answer);
                history.push({ role: "assistant", content: data.answer });
            }
        }

    } catch (e) {
        loadingMsg.remove();
        progressContainer.classList.add("hidden");
        console.error("Fetch error:", e);
        addMessage("assistant", `❌ Erreur de connexion.`);
    }
}

function renderQCM(qcm) {
    const container = document.getElementById("qcm-container");
    container.innerHTML = "";
    container.classList.remove("hidden");

    const title = document.createElement("h3");
    title.textContent = qcm.title || "QCM";
    container.appendChild(title);

    if (!Array.isArray(qcm.questions)) return;

    qcm.questions.forEach((q, i) => {
        const div = document.createElement("div");
        div.className = "qcm-question";
        div.innerHTML = `<h4>Q${i + 1}. ${q.question || "Question manquante"}</h4>`;

        if (Array.isArray(q.choices)) {
            q.choices.forEach((choice, idx) => {
                const label = document.createElement("label");
                label.style.display = "block"; 
                label.innerHTML = `
                    <input type="radio" name="q${i}" value="${idx}">
                    ${choice}
                `;
                div.appendChild(label);
            });
        } else {
            const errorMsg = document.createElement("p");
            errorMsg.textContent = "Erreur : choix manquants";
            div.appendChild(errorMsg);
        }

        const feedback = document.createElement("div");
        feedback.className = "feedback"; 
        div.appendChild(feedback);

        div.dataset.correct = q.correct ?? -1;
        div.dataset.explanation = q.explanation ?? "";
        container.appendChild(div);
    });

    const btn = document.createElement("button");
    btn.textContent = "Valider le QCM";
    btn.onclick = validateQCM;
    container.appendChild(btn);
}

function validateQCM() {
    const questions = document.querySelectorAll(".qcm-question");

    questions.forEach((qDiv) => {
        const selected = qDiv.querySelector("input:checked");
        const feedback = qDiv.lastChild;
        const correct = qDiv.dataset.correct;

        if (!selected) {
            feedback.textContent = "❌ Pas de réponse";
            feedback.className = "wrong";
            return;
        }

        if (selected.value == correct) {
            feedback.textContent = "✅ Bonne réponse";
            feedback.className = "correct";
        } else {
            feedback.textContent = `❌ Mauvaise réponse. ${qDiv.dataset.explanation}`;
            feedback.className = "wrong";
        }
    });
}

// ==========================================
// 4. Écouteurs d'événements (Event Listeners)
// ==========================================

// Gestion de la touche Entrée
input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault(); 
        askQuestion();      
    }
});

// Mise à jour de l'affichage quand on change le select
documentSelect.addEventListener("change", () => {
    const value = documentSelect.value;
    if (value) {
        selectedCourseLabel.innerHTML = `📘 Cours sélectionné : <strong>${value}</strong>`;
    } else {
        selectedCourseLabel.innerHTML = `📘 Cours sélectionné : <strong>Aucun</strong>`;
    }
});

// Chargement initial
document.addEventListener("DOMContentLoaded", () => {
    loadDocuments();
});