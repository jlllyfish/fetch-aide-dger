"""
Interface Flask pour la génération d'URLs pré-remplies Démarches Simplifiées
à partir des données Grist avec design conforme au DSFR.
Version optimisée pour Railway (sans pandas)
"""

from flask import Flask, render_template, request, jsonify
import os
import json
import requests
import logging

# Configuration depuis les variables d'environnement
GRIST_API_KEY = os.getenv("GRIST_API_KEY")
GRIST_DOC_ID = os.getenv("GRIST_DOC_ID") 
GRIST_BASE_URL = os.getenv("GRIST_BASE_URL", "https://grist.numerique.gouv.fr/api")
GRIST_TABLE_ID = os.getenv("GRIST_TABLE_ID")
API_TOKEN = os.getenv("API_TOKEN_AIDE")
DEMARCHE_ID = os.getenv("DEMARCHE_ID")
CONFIG_FILE_PATH = os.getenv("CONFIG_FILE_PATH")

# Vérification du chargement des variables d'environnement
print("=== VÉRIFICATION DES VARIABLES D'ENVIRONNEMENT ===")
print(f"GRIST_API_KEY chargé: {'Oui' if GRIST_API_KEY else 'Non'}")
print(f"GRIST_DOC_ID chargé: {'Oui' if GRIST_DOC_ID else 'Non'}")
print(f"API_TOKEN chargé: {'Oui' if API_TOKEN else 'Non'}")
print(f"CONFIG_FILE_PATH chargé: {'Oui' if CONFIG_FILE_PATH else 'Non'}")
print("==================================================\n")

app = Flask(__name__)

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration du logging pour supprimer seulement les messages socket.io
class NoSocketIOFilter(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        return 'socket.io' not in message and 'Socket.IO' not in message

werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.addFilter(NoSocketIOFilter())

# Charger le fichier de configuration de mapping
def load_field_mapping():
    """Charge le mapping des champs depuis le fichier JSON"""
    try:
        if not CONFIG_FILE_PATH:
            logger.error("❌ Variable CONFIG_FILE_PATH non définie")
            return {}, None
        
        logger.info(f"📁 Tentative de chargement du fichier: {os.path.basename(CONFIG_FILE_PATH)}")
        logger.info(f"📍 Chemin complet: {CONFIG_FILE_PATH}")
        
        if not os.path.exists(CONFIG_FILE_PATH):
            logger.error(f"❌ Fichier non trouvé: {CONFIG_FILE_PATH}")
            return {}, CONFIG_FILE_PATH
            
        with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        field_mappings = config.get("field_mappings", {})
        
        # Inverser le mapping : colonne_grist -> id_ds
        inverted_mapping = {}
        for ds_field_id, mapping_info in field_mappings.items():
            grist_column = mapping_info.get("columnId")
            if grist_column:
                inverted_mapping[grist_column] = ds_field_id
        
        logger.info(f"✅ Fichier chargé avec succès. Mappings trouvés: {len(inverted_mapping)}")
        for grist_col, ds_id in inverted_mapping.items():
            logger.info(f"   {grist_col} -> {ds_id}")
        
        return inverted_mapping, CONFIG_FILE_PATH
        
    except Exception as e:
        logger.error(f"❌ Erreur lors du chargement du mapping: {e}")
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
        """Récupère les données d'une table Grist - Version sans pandas"""
        url = f"{self.base_url}/docs/{self.doc_id}/tables/{table_id}/records"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            data = response.json()
            if 'records' not in data:
                return []
            
            # Extraire les données sous forme de liste de dictionnaires
            rows = []
            for record in data['records']:
                if 'fields' in record:
                    row_data = record['fields'].copy()
                    row_data['id'] = record.get('id')
                    rows.append(row_data)
            
            return rows
        
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des données: {e}")
            return []

def find_display_columns(data):
    """
    Trouve automatiquement les colonnes à afficher dans le tableau avec noms personnalisés
    Version sans pandas - travaille avec une liste de dictionnaires
    """
    if not data:
        return []
    
    # Obtenir toutes les colonnes disponibles
    all_columns = set()
    for row in data:
        all_columns.update(row.keys())
    
    all_columns = list(all_columns)
    logger.info(f"🔍 Analyse des colonnes disponibles: {all_columns}")
    
    email_column = None
    dossier_column = None
    nom_column = None
    pays_column = None
    
    for col in all_columns:
        col_lower = col.lower()
        
        # Recherche de colonnes email
        email_patterns = ['email', 'mail', 'e-mail', 'e_mail', 'courriel']
        if any(pattern in col_lower for pattern in email_patterns):
            email_column = col
            logger.info(f"✅ Colonne email trouvée: {col}")
        
        # Recherche de colonnes dossier
        elif any(pattern in col_lower for pattern in [
            'numero_dossier', 'numéro_dossier', 
            'numero dossier', 'numéro dossier',
            'dossier_number', 'dossier number',
            'dossier_num', 'dossier num',
            'num_dossier', 'num dossier',
            'id_dossier', 'id dossier'
        ]):
            dossier_column = col
            logger.info(f"✅ Colonne dossier trouvée: {col}")
        
        # Recherche de la colonne Nom (Nom_maj_) - RECHERCHE PRÉCISE
        elif col.lower() in ['nom_maj_', 'nom_maj'] or col == 'Nom_maj_':
            nom_column = col
            logger.info(f"✅ Colonne nom trouvée: {col}")
        
        # Recherche de la colonne Pays
        elif col_lower in ['pays', 'country', 'pays_', 'country_']:
            pays_column = col
            logger.info(f"✅ Colonne pays trouvée: {col}")
    
    # Valeurs par défaut si rien trouvé
    if not email_column:
        email_column = 'email'
        logger.warning(f"⚠️ Aucune colonne email trouvée, utilisation par défaut: {email_column}")
    
    if not dossier_column:
        dossier_column = 'dossier_number'
        logger.warning(f"⚠️ Aucune colonne dossier trouvée, utilisation par défaut: {dossier_column}")
    
    if not nom_column:
        nom_column = 'Nom_maj_'
        logger.warning(f"⚠️ Aucune colonne nom trouvée, utilisation par défaut: {nom_column}")
    
    if not pays_column:
        pays_column = 'Pays'
        logger.warning(f"⚠️ Aucune colonne pays trouvée, utilisation par défaut: {pays_column}")
    
    # Construire la configuration des colonnes
    columns_config = [
        {'column': email_column, 'display': 'Email'},
        {'column': dossier_column, 'display': 'Numéro de dossier'},
        {'column': nom_column, 'display': 'Nom'},
        {'column': pays_column, 'display': 'Pays'}
    ]
    
    logger.info(f"📊 Configuration finale des colonnes:")
    for config in columns_config:
        logger.info(f"   {config['column']} -> {config['display']}")
    
    return columns_config

def filter_data_by_email(data, email, email_column):
    """Filtre les données par email - Version sans pandas"""
    filtered = []
    for row in data:
        row_email = str(row.get(email_column, '')).lower()
        if row_email == email.lower():
            filtered.append(row)
    return filtered

def filter_data_by_aide_dger(data):
    """Filtre les données par Aide_DGER_demandee = True - Version sans pandas"""
    if not data:
        return data, None
    
    # Trouver la colonne Aide_DGER_demandee
    aide_dger_column = None
    for row in data:
        for col in row.keys():
            if col.lower() in ['aide_dger_demandee', 'aide_dger_demandée'] or col == 'Aide_DGER_demandee':
                aide_dger_column = col
                logger.info(f"✅ Colonne Aide_DGER_demandee trouvée: {col}")
                break
        if aide_dger_column:
            break
    
    if not aide_dger_column:
        logger.warning(f"⚠️ Colonne Aide_DGER_demandee non trouvée, pas de filtrage appliqué")
        return data, None
    
    # Filtrer les données
    before_count = len(data)
    filtered = []
    for row in data:
        aide_value = row.get(aide_dger_column)
        # Gérer différents types de valeurs booléennes
        if aide_value is True or str(aide_value).lower() in ['true', '1', 'oui', 'yes']:
            filtered.append(row)
    
    after_count = len(filtered)
    logger.info(f"📊 Filtrage Aide_DGER_demandee: {before_count} → {after_count} enregistrements")
    
    return filtered, aide_dger_column

def remove_duplicates(data):
    """Supprime les doublons - Version sans pandas"""
    seen = set()
    unique_data = []
    
    for row in data:
        # Créer une clé unique basée sur tous les champs
        row_key = tuple(sorted(row.items()))
        if row_key not in seen:
            seen.add(row_key)
            unique_data.append(row)
    
    return unique_data

def clean_prefill_data_for_ds(prefill_data):
    """Nettoie et formate les données de pré-remplissage pour l'API DS"""
    cleaned_data = {}
   
    for field_key, value in prefill_data.items():
        if value is None or value == "":
            continue
       
        if isinstance(value, list):
            if len(value) > 0:
                cleaned_values = []
                for v in value:
                    if v is not None and str(v).strip():
                        clean_val = str(v).strip()
                        clean_val = clean_val.replace('\r\n', ' ').replace('\r', ' ').replace('\n', ' ')
                        clean_val = ' '.join(clean_val.split())
                        cleaned_values.append(clean_val)
               
                if cleaned_values:
                    cleaned_data[field_key] = cleaned_values
                    logger.info(f"🔗 Champ multiple {field_key}: {len(cleaned_values)} valeur(s)")
        else:
            cleaned_value = str(value).strip()
           
            if cleaned_value:
                cleaned_value = cleaned_value.replace('\r\n', ' ').replace('\r', ' ').replace('\n', ' ')
                cleaned_value = ' '.join(cleaned_value.split())
               
                if ',' in cleaned_value and len(cleaned_value.split(',')) > 1:
                    parsed_values = [v.strip() for v in cleaned_value.split(',') if v.strip()]
                    if len(parsed_values) > 1:
                        cleaned_data[field_key] = parsed_values
                        logger.info(f"🔗 Champ multiple re-parsé {field_key}: {len(parsed_values)} valeur(s)")
                    else:
                        cleaned_data[field_key] = cleaned_value
                else:
                    cleaned_data[field_key] = cleaned_value
   
    total_fields = len(cleaned_data)
    multiple_fields = sum(1 for value in cleaned_data.values() if isinstance(value, list))
    simple_fields = total_fields - multiple_fields
   
    logger.info(f"📊 DONNÉES NETTOYÉES: {total_fields} champ(s) total - {simple_fields} simples, {multiple_fields} multiples")
   
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
    
    # Mapper les données aux champs DS
    mapped_data = {}
    mapped_count = 0
    
    for field_name, field_value in row_data.items():
        if field_name in field_mapping:
            ds_field_id = field_mapping[field_name]
            mapped_data[f"champ_{ds_field_id}"] = field_value
            mapped_count += 1
            logger.info(f"✅ Mapping: {field_name} -> champ_{ds_field_id}")
        else:
            logger.debug(f"⚠️ Champ non mappé: {field_name}")
    
    logger.info(f"📊 Total champs mappés: {mapped_count}")
    
    # Nettoyer les données
    cleaned_data = clean_prefill_data_for_ds(mapped_data)
    
    try:
        response = requests.post(api_url, headers=headers, json=cleaned_data)
        
        logger.info(f"📡 Réponse DS - Status: {response.status_code}")
        
        if response.status_code == 201:
            return response.json().get("dossier_url", "URL non disponible")
        else:
            logger.error(f"Erreur API DS: {response.status_code} - {response.text}")
            return f"Erreur API: {response.status_code} - {response.text}"
    
    except Exception as e:
        logger.error(f"❌ Exception lors de l'appel API: {e}")
        return f"Erreur: {str(e)}"

@app.route('/')
def index():
    """Page principale"""
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
    data = client.get_table_data(GRIST_TABLE_ID)
    
    if not data:
        return jsonify({'error': 'Aucune donnée trouvée dans la table'}), 404
    
    logger.info(f"📋 Nombre d'enregistrements: {len(data)}")
    
    # Charger le mapping des champs
    if not FIELD_MAPPING:
        return jsonify({'error': 'Mapping des champs non disponible. Vérifiez la configuration.'}), 500
    
    # Trouver les colonnes à afficher
    columns_config = find_display_columns(data)
    
    # Extraire la colonne email pour la recherche
    email_column = columns_config[0]['column']  # Premier élément est toujours email
    
    # Filtrer par email
    email_filtered = filter_data_by_email(data, email, email_column)
    
    if not email_filtered:
        return jsonify({'error': f'Aucun enregistrement trouvé pour l\'email: {email}'}), 404
    
    # Filtrer par le booléen Aide_DGER_demandee = True
    filtered_rows, aide_dger_column = filter_data_by_aide_dger(email_filtered)
    
    if not filtered_rows:
        return jsonify({'error': f'Aucun enregistrement trouvé pour l\'email {email} pour un dossier Aide DGER'}), 404
    
    # Supprimer les doublons
    filtered_rows = remove_duplicates(filtered_rows)
    
    # Préparer les résultats
    results = []
    
    for row in filtered_rows:
        # Extraire les données selon la configuration des colonnes
        row_data = {}
        for config in columns_config:
            column_name = config['column']
            display_name = config['display']
            value = row.get(column_name, '')
            row_data[display_name] = str(value) if value is not None else ''
        
        # Générer l'URL pré-remplie
        url = generate_prefilled_url(row, FIELD_MAPPING)
        
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

# Configuration pour Railway
if __name__ == '__main__':
    # Railway fournit automatiquement la variable PORT
    port = int(os.getenv('PORT', 5000))
    
    logger.info("🚀 Démarrage de l'application Flask...")
    logger.info(f"📍 Port: {port}")
    logger.info("⏹️  Appuyez sur Ctrl+C pour arrêter\n")
    
    # Pour Railway: host='0.0.0.0' pour accepter les connexions externes
    app.run(host='0.0.0.0', port=port, debug=False)
