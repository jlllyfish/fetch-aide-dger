"""
Interface Flask pour la génération d'URLs pré-remplies Démarches Simplifiées
à partir des données Grist avec design conforme au DSFR.
"""

from flask import Flask, render_template, request, jsonify
import os
import json
import requests
import pandas as pd
import logging
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Configuration depuis les variables d'environnement
GRIST_API_KEY = os.getenv("GRIST_API_KEY")
GRIST_DOC_ID = os.getenv("GRIST_DOC_ID") 
GRIST_BASE_URL = os.getenv("GRIST_BASE_URL", "https://grist.numerique.gouv.fr/api")
GRIST_TABLE_ID = os.getenv("GRIST_TABLE_ID")
API_TOKEN = os.getenv("API_TOKEN_AIDE")
DEMARCHE_ID = os.getenv("DEMARCHE_ID")

# Vérification du chargement du .env
print("=== VÉRIFICATION DU FICHIER .ENV ===")
print(f"Fichier .env trouvé: {os.path.exists('.env')}")
print(f"GRIST_API_KEY chargé: {'Oui' if GRIST_API_KEY else 'Non'}")
print(f"GRIST_DOC_ID chargé: {'Oui' if GRIST_DOC_ID else 'Non'}")
print(f"API_TOKEN chargé: {'Oui' if API_TOKEN else 'Non'}")
print(f"Répertoire de travail: {os.getcwd()}")
print("=====================================\n")

app = Flask(__name__)

# Configuration du logging pour supprimer seulement les messages socket.io
class NoSocketIOFilter(logging.Filter):
    def filter(self, record):
        # Filtrer seulement les requêtes socket.io, garder les autres messages
        message = record.getMessage()
        return 'socket.io' not in message and 'Socket.IO' not in message

# Appliquer le filtre seulement aux messages de requêtes, pas aux messages de démarrage
werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.addFilter(NoSocketIOFilter())

# Charger le fichier de configuration de mapping
def load_field_mapping():
    """Charge le mapping des champs depuis le fichier JSON"""
    try:
        # Priorité à la variable d'environnement
        config_file = os.getenv("CONFIG_FILE_PATH")
        
        if not config_file:
            print("❌ Variable CONFIG_FILE_PATH non définie dans le .env")
            return {}, None
        
        print(f"📁 Tentative de chargement du fichier: {os.path.basename(config_file)}")
        print(f"📍 Chemin complet: {config_file}")
        
        if not os.path.exists(config_file):
            print(f"❌ Fichier non trouvé: {config_file}")
            
            # Debug: lister tous les fichiers JSON du répertoire
            directory = os.path.dirname(config_file)
            if os.path.exists(directory):
                print(f"📂 Fichiers JSON disponibles dans le répertoire:")
                for file in os.listdir(directory):
                    if file.endswith('.json'):
                        print(f"   - {file}")
                        
            return {}, config_file
            
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        field_mappings = config.get("field_mappings", {})
        
        # Inverser le mapping : colonne_grist -> id_ds
        # Dans le JSON: "Q2hhbXAtNjIyMzQw": {"columnId": "titre_du_projet"}
        # On veut: "titre_du_projet" -> "Q2hhbXAtNjIyMzQw"
        inverted_mapping = {}
        for ds_field_id, mapping_info in field_mappings.items():
            grist_column = mapping_info.get("columnId")
            if grist_column:
                inverted_mapping[grist_column] = ds_field_id
        
        print(f"✅ Fichier chargé avec succès. Mappings trouvés: {len(inverted_mapping)}")
        print(f"📋 Mappings configurés:")
        for grist_col, ds_id in inverted_mapping.items():
            print(f"   {grist_col} -> {ds_id}")
        
        return inverted_mapping, config_file
        
    except Exception as e:
        print(f"❌ Erreur lors du chargement du mapping: {e}")
        return {}, None

# Charger le mapping au démarrage
FIELD_MAPPING, CONFIG_FILE_LOADED = load_field_mapping()

class GristClient:
    def __init__(self):
        self.base_url = GRIST_BASE_URL.rstrip('/')
        self.api_key = GRIST_API_KEY
        self.doc_id = GRIST_DOC_ID
        self.headers = {"Authorization": f"Bearer {self.api_key}"}

    def get_table_data(self, table_id):
        """Récupère les données d'une table Grist"""
        url = f"{self.base_url}/docs/{self.doc_id}/tables/{table_id}/records"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            data = response.json()
            if 'records' not in data:
                return pd.DataFrame()
            
            # Extraire les données
            rows = []
            for record in data['records']:
                if 'fields' in record:
                    row_data = record['fields'].copy()
                    row_data['id'] = record.get('id')
                    rows.append(row_data)
            
            return pd.DataFrame(rows)
        
        except Exception as e:
            print(f"Erreur lors de la récupération des données: {e}")
            return pd.DataFrame()

def find_display_columns(df):
    """
    Trouve automatiquement les colonnes à afficher dans le tableau avec noms personnalisés
    """
    email_column = None
    dossier_column = None
    nom_column = None
    pays_column = None
    
    print(f"🔍 Analyse des colonnes disponibles: {list(df.columns)}")
    
    for col in df.columns:
        col_lower = col.lower()
        
        # Recherche de colonnes email
        email_patterns = ['email', 'mail', 'e-mail', 'e_mail', 'courriel']
        if any(pattern in col_lower for pattern in email_patterns):
            email_column = col
            print(f"✅ Colonne email trouvée: {col}")
        
        # Recherche de colonnes dossier - VERSION AMÉLIORÉE
        elif any(pattern in col_lower for pattern in [
            'numero_dossier', 'numéro_dossier', 
            'numero dossier', 'numéro dossier',
            'dossier_number', 'dossier number',
            'dossier_num', 'dossier num',
            'num_dossier', 'num dossier',
            'id_dossier', 'id dossier'
        ]):
            dossier_column = col
            print(f"✅ Colonne dossier trouvée: {col}")
        
        # Recherche de la colonne Nom (Nom_maj_) - RECHERCHE PRÉCISE
        elif col.lower() in ['nom_maj_', 'nom_maj'] or col == 'Nom_maj_':
            nom_column = col
            print(f"✅ Colonne nom trouvée: {col}")
        
        # Recherche de la colonne Pays
        elif col_lower in ['pays', 'country', 'pays_', 'country_']:
            pays_column = col
            print(f"✅ Colonne pays trouvée: {col}")
    
    # Valeurs par défaut si rien trouvé
    if not email_column:
        email_column = 'email'
        print(f"⚠️ Aucune colonne email trouvée, utilisation par défaut: {email_column}")
    
    if not dossier_column:
        dossier_column = 'dossier_number'
        print(f"⚠️ Aucune colonne dossier trouvée, utilisation par défaut: {dossier_column}")
    
    if not nom_column:
        nom_column = 'Nom_maj_'
        print(f"⚠️ Aucune colonne nom trouvée, utilisation par défaut: {nom_column}")
    
    if not pays_column:
        pays_column = 'Pays'
        print(f"⚠️ Aucune colonne pays trouvée, utilisation par défaut: {pays_column}")
    
    # Construire la configuration des colonnes avec mapping nom de colonne -> nom d'affichage
    columns_config = [
        {'column': email_column, 'display': 'Email'},
        {'column': dossier_column, 'display': 'Numéro de dossier'},
        {'column': nom_column, 'display': 'Nom'},
        {'column': pays_column, 'display': 'Pays'}
    ]
    
    print(f"📊 Configuration finale des colonnes:")
    for config in columns_config:
        print(f"   {config['column']} -> {config['display']}")
    
    return columns_config

def clean_prefill_data_for_ds(prefill_data):
    """
    Nettoie et formate les données de pré-remplissage pour l'API DS
    Version corrigée qui re-parse les champs multiples reçus comme chaînes
    """
    cleaned_data = {}
   
    for field_key, value in prefill_data.items():
        if value is None or value == "":
            continue
       
        # ✅ CORRECTION MAJEURE : Préserver les tableaux pour les champs multiples
        if isinstance(value, list):
            # C'est déjà un tableau (champ multiple traité côté client)
            if len(value) > 0:
                # Nettoyer chaque valeur du tableau SANS le transformer en chaîne
                cleaned_values = []
                for v in value:
                    if v is not None and str(v).strip():
                        # Nettoyer les retours à la ligne dans chaque valeur
                        clean_val = str(v).strip()
                        clean_val = clean_val.replace('\r\n', ' ').replace('\r', ' ').replace('\n', ' ')
                        clean_val = ' '.join(clean_val.split())  # Remplacer multiples espaces
                        cleaned_values.append(clean_val)
               
                if cleaned_values:
                    # ✅ GARDER LE FORMAT TABLEAU pour l'API DS
                    cleaned_data[field_key] = cleaned_values
                    print(f"🔗 Champ multiple {field_key}: {len(cleaned_values)} valeur(s) → {cleaned_values}")
       
        else:
            # ✅ NOUVEAU : Détecter les champs multiples reçus comme chaînes et les re-parser
            cleaned_value = str(value).strip()
           
            if cleaned_value:
                # Nettoyer les retours à la ligne
                cleaned_value = cleaned_value.replace('\r\n', ' ').replace('\r', ' ').replace('\n', ' ')
                cleaned_value = ' '.join(cleaned_value.split())  # Remplacer multiples espaces
               
                # ✅ DÉTECTION : Si la chaîne contient des virgules, c'est probablement un champ multiple mal sérialisé
                if ',' in cleaned_value and len(cleaned_value.split(',')) > 1:
                    # Re-parser comme champ multiple
                    parsed_values = [v.strip() for v in cleaned_value.split(',') if v.strip()]
                    if len(parsed_values) > 1:
                        cleaned_data[field_key] = parsed_values
                        print(f"🔗 Champ multiple re-parsé {field_key}: chaîne → {len(parsed_values)} valeur(s) → {parsed_values}")
                    else:
                        cleaned_data[field_key] = cleaned_value
                        print(f"📝 Champ simple {field_key}: {cleaned_value[:50]}...")
                else:
                    cleaned_data[field_key] = cleaned_value
                    print(f"📝 Champ simple {field_key}: {cleaned_value[:50]}...")
   
    # ✅ NOUVEAU : Log de résumé
    total_fields = len(cleaned_data)
    multiple_fields = sum(1 for value in cleaned_data.values() if isinstance(value, list))
    simple_fields = total_fields - multiple_fields
   
    print(f"📊 DONNÉES NETTOYÉES POUR DS: {total_fields} champ(s) total - {simple_fields} simples, {multiple_fields} multiples")
   
    return cleaned_data

def generate_prefilled_url(row_data, field_mapping):
    """Génère une URL pré-remplie pour Démarches Simplifiées"""
    
    if not API_TOKEN:
        return "Erreur: Token API manquant"
    
    if not field_mapping:
        return "Erreur: Mapping des champs non disponible"
    
    api_url = f'https://www.demarches-simplifiees.fr/api/public/v1/demarches/{DEMARCHE_ID}/dossiers'
    headers = {
        "Content-Type": "application/json", 
        "Authorization": f"Bearer {API_TOKEN}"
    }
    
    # Debug: afficher les données d'entrée
    print(f"🔍 Données de la ligne Grist:")
    for key, value in row_data.items():
        print(f"   {key}: {value}")
    
    # Mapper les données aux champs DS
    mapped_data = {}
    mapped_count = 0
    
    for field_name, field_value in row_data.items():
        if field_name in field_mapping:
            ds_field_id = field_mapping[field_name]
            mapped_data[f"champ_{ds_field_id}"] = field_value
            mapped_count += 1
            print(f"✅ Mapping: {field_name} -> champ_{ds_field_id} = {field_value}")
        else:
            print(f"⚠️ Champ non mappé: {field_name}")
    
    print(f"📊 Total champs mappés: {mapped_count}")
    print(f"📤 Données brutes envoyées à DS: {mapped_data}")
    
    # ✅ NOUVEAU : Nettoyer les données pour gérer les champs multiples
    cleaned_data = clean_prefill_data_for_ds(mapped_data)
    
    print(f"📤 Données nettoyées envoyées à DS: {cleaned_data}")
    
    try:
        response = requests.post(api_url, headers=headers, json=cleaned_data)
        
        print(f"📡 Réponse DS - Status: {response.status_code}")
        print(f"📡 Réponse DS - Contenu: {response.text[:500]}")
        
        if response.status_code == 201:
            return response.json().get("dossier_url", "URL non disponible")
        else:
            return f"Erreur API: {response.status_code} - {response.text}"
    
    except Exception as e:
        print(f"❌ Exception lors de l'appel API: {e}")
        return f"Erreur: {str(e)}"

@app.route('/')
def index():
    """Page principale"""
    # Informations sur le statut du mapping
    mapping_status = {
        'loaded': bool(FIELD_MAPPING),
        'filename': os.path.basename(CONFIG_FILE_LOADED) if CONFIG_FILE_LOADED else None,
        'mappings_count': len(FIELD_MAPPING) if FIELD_MAPPING else 0
    }
    return render_template('index.html', mapping_status=mapping_status)

@app.route('/search', methods=['POST'])
def search():
    """Recherche par email et génération des URLs"""
    email = request.form.get('email', '').strip()
    
    if not email:
        return jsonify({'error': 'Email requis'}), 400
    
    # Initialiser le client Grist
    client = GristClient()
    
    # Récupérer les données de la table
    df = client.get_table_data(GRIST_TABLE_ID)
    
    if df.empty:
        return jsonify({'error': 'Aucune donnée trouvée dans la table'}), 404
    
    print(f"📋 Colonnes disponibles dans Grist: {list(df.columns)}")
    print(f"📋 Nombre d'enregistrements: {len(df)}")
    
    # Charger le mapping des champs
    if not FIELD_MAPPING:
        return jsonify({'error': 'Mapping des champs non disponible. Vérifiez la configuration.'}), 500
    
    # Trouver les colonnes à afficher
    columns_config = find_display_columns(df)
    
    # Extraire la colonne email pour la recherche
    email_column = columns_config[0]['column']  # Premier élément est toujours email
    
    # Filtrer par email
    email_filtered = df[df[email_column].astype(str).str.lower() == email.lower()]
    
    if email_filtered.empty:
        return jsonify({'error': f'Aucun enregistrement trouvé pour l\'email: {email}'}), 404
    
    # Filtrer par le booléen Aide_DGER_demandee = True
    aide_dger_column = None
    for col in df.columns:
        if col.lower() in ['aide_dger_demandee', 'aide_dger_demandée'] or col == 'Aide_DGER_demandee':
            aide_dger_column = col
            print(f"✅ Colonne Aide_DGER_demandee trouvée: {col}")
            break
    
    if aide_dger_column and aide_dger_column in email_filtered.columns:
        # Filtrer pour ne garder que les enregistrements où Aide_DGER_demandee = True
        before_count = len(email_filtered)
        filtered_rows = email_filtered[email_filtered[aide_dger_column] == True]
        after_count = len(filtered_rows)
        
        print(f"📊 Filtrage Aide_DGER_demandee: {before_count} → {after_count} enregistrements")
        
        if filtered_rows.empty:
            return jsonify({'error': f'Aucun enregistrement trouvé pour l\'email {email} pour un dossier Aide DGER'}), 404
    else:
        print(f"⚠️ Colonne Aide_DGER_demandee non trouvée, pas de filtrage appliqué")
        filtered_rows = email_filtered
    
    # Supprimer les doublons
    filtered_rows = filtered_rows.drop_duplicates()
    
    # Préparer les résultats
    results = []
    
    for _, row in filtered_rows.iterrows():
        # Extraire les données selon la configuration des colonnes
        row_data = {}
        for config in columns_config:
            column_name = config['column']
            display_name = config['display']
            value = row.get(column_name, '') if column_name in row else ''
            row_data[display_name] = str(value) if value is not None else ''
        
        # Générer l'URL pré-remplie
        url = generate_prefilled_url(row.to_dict(), FIELD_MAPPING)
        
        result = {
            'data': row_data,
            'url': url
        }
        results.append(result)
    
    # Extraire les noms d'affichage des colonnes
    display_column_names = [config['display'] for config in columns_config]
    
    return jsonify({
        'results': results,
        'columns': display_column_names,
        'total': len(results)
    })

@app.template_filter('dict_items')
def dict_items_filter(d):
    """Filtre pour itérer sur les items d'un dictionnaire dans Jinja2"""
    return d.items() if isinstance(d, dict) else []

if __name__ == '__main__':
    print("🚀 Démarrage de l'application Flask...")
    print("📍 Interface disponible sur: http://127.0.0.1:5000")
    print("🔗 Ou sur: http://localhost:5000")
    print("⏹️  Appuyez sur Ctrl+C pour arrêter\n")
    
    app.run(debug=True, host='127.0.0.1', port=5000)