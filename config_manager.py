"""
Gestionnaire de configuration persistante pour le bot Discord
Sauvegarde automatique des configurations dans bot_configs.json
"""
import json
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional

# Configuration du logging
logger = logging.getLogger(__name__)

# Fichier de configuration persistante
CONFIG_FILE = "bot_configs.json"

def ensure_config_file():
    """S'assurer que le fichier de configuration existe"""
    if not os.path.exists(CONFIG_FILE):
        logger.info(f"📄 Création du fichier de configuration : {CONFIG_FILE}")
        save_config({})

def load_config() -> Dict[str, Any]:
    """Charger la configuration depuis le fichier JSON"""
    try:
        ensure_config_file()
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            logger.debug(f"📥 Configuration chargée depuis {CONFIG_FILE}")
            return config
    except json.JSONDecodeError as e:
        logger.error(f"❌ Erreur JSON dans {CONFIG_FILE}: {e}")
        logger.info("🔄 Création d'une nouvelle configuration vide")
        save_config({})
        return {}
    except Exception as e:
        logger.error(f"❌ Erreur lors du chargement de {CONFIG_FILE}: {e}")
        return {}

def save_config(config: Dict[str, Any]) -> bool:
    """Sauvegarder la configuration dans le fichier JSON"""
    try:
        # Sauvegarder avec indentation pour lisibilité
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        logger.debug(f"💾 Configuration sauvegardée dans {CONFIG_FILE}")
        return True
    except Exception as e:
        logger.error(f"❌ Erreur lors de la sauvegarde dans {CONFIG_FILE}: {e}")
        return False

def get_guild_config(guild_id: int) -> Dict[str, Any]:
    """Récupérer la configuration complète d'un serveur"""
    config = load_config()
    guild_str = str(guild_id)
    
    if guild_str not in config:
        logger.info(f"🆕 Nouvelle configuration pour le serveur {guild_id}")
        config[guild_str] = create_default_guild_config()
        save_config(config)
    
    return config[guild_str]

def create_default_guild_config() -> Dict[str, Any]:
    """Créer une configuration par défaut pour un serveur"""
    return {
        "security_settings": {},
        "voice_temp_settings": {
            "category_id": None,
            "temp_channel_name": "🔊 Salon temporaire de {user}",
            "user_limit": 0,
            "auto_delete": True
        },
        "bot_settings": {
            "prefix": "/",
            "log_actions": True,
            "welcome_message": True,
            "welcome_channel_id": None
        }
    }

def update_guild_config(guild_id: int, section: str, key_or_data: Any, value: Any = None) -> bool:
    """
    Mettre à jour la configuration d'un serveur
    
    Args:
        guild_id: ID du serveur
        section: Section de configuration (ex: "security_settings")
        key_or_data: Soit une clé spécifique, soit un dictionnaire complet
        value: Valeur (si key_or_data est une clé)
    """
    try:
        config = load_config()
        guild_str = str(guild_id)
        
        # S'assurer que le serveur existe dans la config
        if guild_str not in config:
            config[guild_str] = create_default_guild_config()
        
        # S'assurer que la section existe
        if section not in config[guild_str]:
            config[guild_str][section] = {}
        
        # Mise à jour selon le type de paramètres
        if value is not None:
            # Mise à jour d'une clé spécifique
            config[guild_str][section][key_or_data] = value
            logger.info(f"🔧 Config mise à jour - Guild: {guild_id}, Section: {section}, {key_or_data}: {value}")
        else:
            # Mise à jour complète de la section ou ajout de données
            if isinstance(key_or_data, dict):
                config[guild_str][section].update(key_or_data)
                logger.info(f"🔧 Config mise à jour - Guild: {guild_id}, Section: {section}, Données: {key_or_data}")
            else:
                logger.error(f"❌ Type de données incorrect pour la mise à jour: {type(key_or_data)}")
                return False
        
        # Sauvegarder
        if save_config(config):
            logger.info(f"✅ Configuration sauvegardée avec succès pour le serveur {guild_id}")
            return True
        else:
            logger.error(f"❌ Échec de la sauvegarde pour le serveur {guild_id}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Erreur lors de la mise à jour de la config: {e}")
        return False

def get_voice_temp_settings(guild_id: int) -> Dict[str, Any]:
    """Récupérer les paramètres des salons vocaux temporaires"""
    guild_config = get_guild_config(guild_id)
    return guild_config.get("voice_temp_settings", {
        "category_id": None,
        "temp_channel_name": "🔊 Salon temporaire de {user}",
        "user_limit": 0,
        "auto_delete": True
    })

def get_bot_settings(guild_id: int) -> Dict[str, Any]:
    """Récupérer les paramètres généraux du bot"""
    guild_config = get_guild_config(guild_id)
    return guild_config.get("bot_settings", {
        "prefix": "/",
        "log_actions": True,
        "welcome_message": True,
        "welcome_channel_id": None
    })

def get_security_settings(guild_id: int) -> Dict[str, Any]:
    """Récupérer les paramètres de sécurité"""
    guild_config = get_guild_config(guild_id)
    return guild_config.get("security_settings", {})

def delete_guild_config(guild_id: int) -> bool:
    """Supprimer la configuration d'un serveur"""
    try:
        config = load_config()
        guild_str = str(guild_id)
        
        if guild_str in config:
            del config[guild_str]
            save_config(config)
            logger.info(f"🗑️ Configuration supprimée pour le serveur {guild_id}")
            return True
        else:
            logger.warning(f"⚠️ Aucune configuration trouvée pour le serveur {guild_id}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Erreur lors de la suppression de la config: {e}")
        return False

def get_all_guilds() -> list:
    """Récupérer la liste de tous les serveurs ayant une configuration"""
    try:
        config = load_config()
        return [int(guild_id) for guild_id in config.keys()]
    except Exception as e:
        logger.error(f"❌ Erreur lors de la récupération des serveurs: {e}")
        return []

def backup_config(backup_file: str = None) -> bool:
    """Créer une sauvegarde de la configuration"""
    try:
        if backup_file is None:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = f"bot_configs_backup_{timestamp}.json"
        
        config = load_config()
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        logger.info(f"💾 Sauvegarde créée: {backup_file}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur lors de la création de la sauvegarde: {e}")
        return False

def restore_config(backup_file: str) -> bool:
    """Restaurer la configuration depuis une sauvegarde"""
    try:
        if not os.path.exists(backup_file):
            logger.error(f"❌ Fichier de sauvegarde non trouvé: {backup_file}")
            return False
        
        with open(backup_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        save_config(config)
        logger.info(f"🔄 Configuration restaurée depuis: {backup_file}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur lors de la restauration: {e}")
        return False

# Initialisation du module
logger.info("🔧 Module config_manager initialisé")
ensure_config_file()