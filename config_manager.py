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
    """Créer une configuration par défaut pour un serveur avec TOUS les paramètres"""
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
        },
        "warnings": {},  # {user_id: [warning_data, ...]}
        "song_queues": [],  # Queue des chansons
        "loop_modes": {},  # Mode loop par serveur
        "current_songs": {},  # Chanson actuelle
        "support_channels": {
            "active": [],
            "config": {}
        },
        "temp_vocal_channels": [],  # Salons vocaux temporaires actifs
        "raid_protection": {},  # Données de protection anti-raid
        "join_tracker": [],  # Suivi des connexions
        "message_tracker": []  # Suivi des messages
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
            elif isinstance(key_or_data, (list, str, int, float, bool)) or key_or_data is None:
                # Remplacer complètement la section avec les nouvelles données
                config[guild_str][section] = key_or_data
                logger.info(f"🔧 Config remplacée - Guild: {guild_id}, Section: {section}, Nouvelles données: {key_or_data}")
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

def get_warnings(guild_id: int) -> Dict[str, list]:
    """Récupérer les avertissements sauvegardés"""
    guild_config = get_guild_config(guild_id)
    return guild_config.get("warnings", {})

def save_warnings(guild_id: int, warnings_data: Dict[str, list]) -> bool:
    """Sauvegarder les avertissements"""
    return update_guild_config(guild_id, "warnings", warnings_data)

def get_song_queue(guild_id: int) -> list:
    """Récupérer la queue des chansons"""
    guild_config = get_guild_config(guild_id)
    return guild_config.get("song_queues", [])

def save_song_queue(guild_id: int, queue_data: list) -> bool:
    """Sauvegarder la queue des chansons"""
    return update_guild_config(guild_id, "song_queues", queue_data)

def get_support_channels(guild_id: int) -> Dict[str, Any]:
    """Récupérer les données des salons de support"""
    guild_config = get_guild_config(guild_id)
    return guild_config.get("support_channels", {"active": [], "config": {}})

def save_support_channels(guild_id: int, support_data: Dict[str, Any]) -> bool:
    """Sauvegarder les données des salons de support"""
    return update_guild_config(guild_id, "support_channels", support_data)

def get_temp_vocal_channels(guild_id: int) -> list:
    """Récupérer les salons vocaux temporaires"""
    guild_config = get_guild_config(guild_id)
    return guild_config.get("temp_vocal_channels", [])

def save_temp_vocal_channels(guild_id: int, channels_data: list) -> bool:
    """Sauvegarder les salons vocaux temporaires"""
    return update_guild_config(guild_id, "temp_vocal_channels", channels_data)

def save_all_guild_data(guild_id: int, warnings: dict = None, queues: list = None, 
                       support: dict = None, temp_channels: list = None) -> bool:
    """Sauvegarder toutes les données d'un serveur en une fois"""
    try:
        config = load_config()
        guild_str = str(guild_id)
        
        if guild_str not in config:
            config[guild_str] = create_default_guild_config()
        
        # Mettre à jour toutes les données fournies
        if warnings is not None:
            config[guild_str]["warnings"] = warnings
        if queues is not None:
            config[guild_str]["song_queues"] = queues
        if support is not None:
            config[guild_str]["support_channels"] = support
        if temp_channels is not None:
            config[guild_str]["temp_vocal_channels"] = temp_channels
        
        success = save_config(config)
        if success:
            logger.info(f"🔄 Sauvegarde complète effectuée pour le serveur {guild_id}")
        return success
        
    except Exception as e:
        logger.error(f"❌ Erreur lors de la sauvegarde complète: {e}")
        return False

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

def auto_backup() -> bool:
    """Créer une sauvegarde automatique avec horodatage"""
    try:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"bot_configs_auto_backup_{timestamp}.json"
        
        success = backup_config(backup_file)
        if success:
            logger.info(f"🔄 Sauvegarde automatique créée: {backup_file}")
            
            # Nettoyer les anciennes sauvegardes (garder seulement les 10 dernières)
            cleanup_old_backups()
        
        return success
        
    except Exception as e:
        logger.error(f"❌ Erreur lors de la sauvegarde automatique: {e}")
        return False

def cleanup_old_backups(max_backups: int = 10):
    """Nettoyer les anciennes sauvegardes automatiques"""
    try:
        import glob
        
        # Chercher tous les fichiers de sauvegarde automatique
        backup_pattern = "bot_configs_auto_backup_*.json"
        backup_files = glob.glob(backup_pattern)
        
        if len(backup_files) > max_backups:
            # Trier par date de modification
            backup_files.sort(key=os.path.getmtime)
            
            # Supprimer les plus anciens
            files_to_delete = backup_files[:-max_backups]
            for file_path in files_to_delete:
                try:
                    os.remove(file_path)
                    logger.info(f"🗑️ Ancienne sauvegarde supprimée: {file_path}")
                except Exception as e:
                    logger.warning(f"⚠️ Impossible de supprimer {file_path}: {e}")
                    
    except Exception as e:
        logger.error(f"❌ Erreur lors du nettoyage des sauvegardes: {e}")

def load_all_guild_data(guild_id: int) -> Dict[str, Any]:
    """Charger toutes les données d'un serveur"""
    try:
        guild_config = get_guild_config(guild_id)
        
        return {
            "warnings": guild_config.get("warnings", {}),
            "song_queues": guild_config.get("song_queues", []),
            "loop_modes": guild_config.get("loop_modes", {}),
            "current_songs": guild_config.get("current_songs", {}),
            "support_channels": guild_config.get("support_channels", {"active": [], "config": {}}),
            "temp_vocal_channels": guild_config.get("temp_vocal_channels", []),
            "raid_protection": guild_config.get("raid_protection", {}),
            "join_tracker": guild_config.get("join_tracker", []),
            "message_tracker": guild_config.get("message_tracker", [])
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur lors du chargement des données pour le serveur {guild_id}: {e}")
        return {}

# Initialisation du module
logger.info("🔧 Module config_manager initialisé")
ensure_config_file()