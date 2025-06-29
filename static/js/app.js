// Script principal pour l'application Flask

// Fermer le popup automatiquement après 5 secondes
setTimeout(function() {
    closePopup();
}, 5000);

function closePopup() {
    const popup = document.getElementById('configPopup');
    if (popup) {
        popup.style.animation = 'slideOut 0.3s ease-in forwards';
        setTimeout(() => {
            popup.style.display = 'none';
        }, 300);
    }
}

// Gestion du formulaire de recherche
document.addEventListener('DOMContentLoaded', function() {
    const searchForm = document.getElementById('searchForm');
    
    if (searchForm) {
        searchForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const email = document.getElementById('email').value;
            const loadingEl = document.getElementById('loading');
            const errorEl = document.getElementById('errorMessage');
            const errorText = document.getElementById('errorText');
            const resultsEl = document.getElementById('resultsSection');
            const searchBtn = document.getElementById('searchBtn');
            
            // Reset states
            loadingEl.style.display = 'block';
            errorEl.style.display = 'none';
            resultsEl.style.display = 'none';
            searchBtn.disabled = true;
            
            try {
                const formData = new FormData();
                formData.append('email', email);
                
                const response = await fetch('/search', {
                    method: 'POST',
                    body: formData
                });
                
                const data = await response.json();
                
                if (!response.ok) {
                    throw new Error(data.error || 'Erreur lors de la recherche');
                }
                
                displayResults(data);
                
            } catch (error) {
                errorText.textContent = error.message;
                errorEl.style.display = 'block';
            } finally {
                loadingEl.style.display = 'none';
                searchBtn.disabled = false;
            }
        });
    }
});

function displayResults(data) {
    const resultsEl = document.getElementById('resultsSection');
    const statsEl = document.getElementById('stats');
    const contentEl = document.getElementById('resultsContent');
    
    statsEl.textContent = `${data.total} résultat(s) trouvé(s)`;
    
    if (data.results.length === 0) {
        contentEl.innerHTML = '<div class="fr-alert fr-alert--warning"><p>Aucun résultat trouvé pour cette adresse email.</p></div>';
    } else {
        let tableHTML = '<table class="results-table"><thead><tr>';
        
        // En-têtes des colonnes fixes
        data.columns.forEach(col => {
            tableHTML += `<th>${col}</th>`;
        });
        tableHTML += '<th>Lien généré</th></tr></thead><tbody>';
        
        // Lignes de données
        data.results.forEach(result => {
            tableHTML += '<tr>';
            
            // Données des colonnes
            data.columns.forEach(col => {
                const value = result.data[col] || '';
                tableHTML += `<td>${escapeHtml(String(value))}</td>`;
            });
            
            // Colonne URL - toujours en dernière position
            tableHTML += '<td class="url-cell">';
            if (result.url.startsWith('http')) {
                tableHTML += `<a href="${result.url}" target="_blank" class="url-link">📄 Accéder au dossier</a>`;
            } else {
                tableHTML += `<span class="fr-text--sm" style="color: var(--error-425-625);">${escapeHtml(result.url)}</span>`;
            }
            tableHTML += '</td></tr>';
        });
        
        tableHTML += '</tbody></table>';
        contentEl.innerHTML = tableHTML;
    }
    
    resultsEl.style.display = 'block';
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}