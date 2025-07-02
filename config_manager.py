"""
Gestionnaire de configuration persistante pour le bot Discord
Sauvegarde automatique des configurations dans bot_configs.json
"""
import json
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from collections import defaultdict, deque
from datetime import datetime

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
            json.dump(config, f, indent=2, ensure_ascii=False, default=str)
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

# ============================
# FONCTIONS DE SAUVEGARDE AUTOMATIQUE COMPLÈTE
# ============================

def save_all_data(warnings=None, song_queues=None, loop_modes=None, current_songs=None,
                  support_channels=None, support_config=None, temp_vocal_config=None,
                  temp_vocal_channels=None, raid_protection=None, join_tracker=None,
                  message_tracker=None, extraction_stats=None) -> bool:
    """Sauvegarder TOUTES les données du bot automatiquement"""
    try:
        config = load_config()
        
        # Créer la section global_data si elle n'existe pas
        if "global_data" not in config:
            config["global_data"] = {}
        
        # Sauvegarder toutes les données si elles sont fournies
        if warnings is not None:
            # Convertir defaultdict en dict normal pour JSON
            config["global_data"]["warnings"] = dict(warnings)
            logger.debug("💾 WARNINGS sauvegardées")
        
        if song_queues is not None:
            config["global_data"]["song_queues"] = song_queues
            logger.debug("💾 SONG_QUEUES sauvegardées")
        
        if loop_modes is not None:
            config["global_data"]["loop_modes"] = loop_modes
            logger.debug("💾 LOOP_MODES sauvegardées")
        
        if current_songs is not None:
            config["global_data"]["current_songs"] = current_songs
            logger.debug("💾 CURRENT_SONGS sauvegardées")
        
        if support_channels is not None:
            config["global_data"]["support_channels"] = support_channels
            logger.debug("💾 SUPPORT_CHANNELS sauvegardées")
        
        if support_config is not None:
            config["global_data"]["support_config"] = support_config
            logger.debug("💾 SUPPORT_CONFIG sauvegardée")
        
        if temp_vocal_config is not None:
            config["global_data"]["temp_vocal_config"] = temp_vocal_config
            logger.debug("💾 TEMP_VOCAL_CONFIG sauvegardée")
        
        if temp_vocal_channels is not None:
            config["global_data"]["temp_vocal_channels"] = temp_vocal_channels
            logger.debug("💾 TEMP_VOCAL_CHANNELS sauvegardées")
        
        if raid_protection is not None:
            config["global_data"]["raid_protection"] = raid_protection
            logger.debug("💾 RAID_PROTECTION sauvegardée")
        
        if join_tracker is not None:
            # Convertir defaultdict en dict normal pour JSON
            config["global_data"]["join_tracker"] = dict(join_tracker)
            logger.debug("💾 JOIN_TRACKER sauvegardé")
        
        if message_tracker is not None:
            # Convertir defaultdict en dict normal pour JSON
            config["global_data"]["message_tracker"] = dict(message_tracker)
            logger.debug("💾 MESSAGE_TRACKER sauvegardé")
        
        if extraction_stats is not None:
            config["global_data"]["extraction_stats"] = extraction_stats
            logger.debug("💾 EXTRACTION_STATS sauvegardées")
        
        # Ajouter timestamp de dernière sauvegarde
        config["global_data"]["last_save"] = datetime.now().isoformat()
        
        # Sauvegarder
        if save_config(config):
            logger.info("✅ Toutes les données automatiquement sauvegardées")
            return True
        else:
            logger.error("❌ Échec de la sauvegarde automatique")
            return False
    
    except Exception as e:
        logger.error(f"❌ Erreur lors de la sauvegarde automatique: {e}")
        return False

def load_all_data() -> Dict[str, Any]:
    """Charger TOUTES les données du bot depuis le JSON"""
    try:
        config = load_config()
        global_data = config.get("global_data", {})
        
        # Préparer les données avec valeurs par défaut
        result = {
            "warnings": defaultdict(list),
            "song_queues": {},
            "loop_modes": {},
            "current_songs": {},
            "support_channels": {},
            "support_config": {},
            "temp_vocal_config": {},
            "temp_vocal_channels": {},
            "raid_protection": {},
            "join_tracker": defaultdict(list),
            "message_tracker": defaultdict(list),
            "extraction_stats": {"success": 0, "failed": 0, "youtube": 0, "spotify": 0, "soundcloud": 0}
        }
        
        # Charger les données sauvegardées
        if "warnings" in global_data:
            warnings_data = global_data["warnings"]
            # Convertir les clés string en int
            for user_id_str, warns in warnings_data.items():
                result["warnings"][int(user_id_str)] = warns
            logger.debug("📥 WARNINGS chargées")
        
        if "song_queues" in global_data:
            song_queues_data = global_data["song_queues"]
            result["song_queues"] = {}
            # Convertir les listes de nouveau en deques
            for guild_id, queue_list in song_queues_data.items():
                result["song_queues"][int(guild_id)] = deque(queue_list)
            logger.debug("📥 SONG_QUEUES chargées et converties en deques")
        
        if "loop_modes" in global_data:
            loop_data = global_data["loop_modes"]
            # Convertir les clés string en int
            for guild_id_str, mode in loop_data.items():
                result["loop_modes"][int(guild_id_str)] = mode
            logger.debug("📥 LOOP_MODES chargées")
        
        if "current_songs" in global_data:
            songs_data = global_data["current_songs"]
            # Convertir les clés string en int
            for guild_id_str, song in songs_data.items():
                result["current_songs"][int(guild_id_str)] = song
            logger.debug("📥 CURRENT_SONGS chargées")
        
        if "support_channels" in global_data:
            support_data = global_data["support_channels"]
            # Convertir les clés string en int
            for guild_id_str, channels in support_data.items():
                result["support_channels"][int(guild_id_str)] = channels
            logger.debug("📥 SUPPORT_CHANNELS chargées")
        
        if "support_config" in global_data:
            support_config_data = global_data["support_config"]
            # Convertir les clés string en int
            for guild_id_str, config in support_config_data.items():
                result["support_config"][int(guild_id_str)] = config
            logger.debug("📥 SUPPORT_CONFIG chargée")
        
        if "temp_vocal_config" in global_data:
            temp_config_data = global_data["temp_vocal_config"]
            # Convertir les clés string en int
            for guild_id_str, config in temp_config_data.items():
                result["temp_vocal_config"][int(guild_id_str)] = config
            logger.debug("📥 TEMP_VOCAL_CONFIG chargée")
        
        if "temp_vocal_channels" in global_data:
            temp_channels_data = global_data["temp_vocal_channels"]
            # Convertir les clés string en int
            for guild_id_str, channels in temp_channels_data.items():
                result["temp_vocal_channels"][int(guild_id_str)] = channels
            logger.debug("📥 TEMP_VOCAL_CHANNELS chargées")
        
        if "raid_protection" in global_data:
            raid_data = global_data["raid_protection"]
            # Convertir les clés string en int
            for guild_id_str, protection in raid_data.items():
                result["raid_protection"][int(guild_id_str)] = protection
            logger.debug("📥 RAID_PROTECTION chargée")
        
        if "join_tracker" in global_data:
            join_data = global_data["join_tracker"]
            # Convertir les clés string en int et recréer defaultdict
            for guild_id_str, joins in join_data.items():
                result["join_tracker"][int(guild_id_str)] = joins
            logger.debug("📥 JOIN_TRACKER chargé")
        
        if "message_tracker" in global_data:
            message_data = global_data["message_tracker"]
            # Convertir les clés string en int et recréer defaultdict
            for guild_id_str, messages in message_data.items():
                result["message_tracker"][int(guild_id_str)] = messages
            logger.debug("📥 MESSAGE_TRACKER chargé")
        
        if "extraction_stats" in global_data:
            result["extraction_stats"] = global_data["extraction_stats"]
            logger.debug("📥 EXTRACTION_STATS chargées")
        
        last_save = global_data.get("last_save", "Jamais")
        logger.info(f"✅ Toutes les données chargées (dernière sauvegarde: {last_save})")
        
        return result
    
    except Exception as e:
        logger.error(f"❌ Erreur lors du chargement automatique: {e}")
        # Retourner valeurs par défaut en cas d'erreur
        return {
            "warnings": defaultdict(list),
            "song_queues": {},
            "loop_modes": {},
            "current_songs": {},
            "support_channels": {},
            "support_config": {},
            "temp_vocal_config": {},
            "temp_vocal_channels": {},
            "raid_protection": {},
            "join_tracker": defaultdict(list),
            "message_tracker": defaultdict(list),
            "extraction_stats": {"success": 0, "failed": 0, "youtube": 0, "spotify": 0, "soundcloud": 0}
        }

def auto_save_data(**kwargs) -> bool:
    """Fonction raccourci pour sauvegarde automatique partielle"""
    return save_all_data(**kwargs)