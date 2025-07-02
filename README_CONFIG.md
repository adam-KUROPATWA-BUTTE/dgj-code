# 🔧 Système de Configuration Persistante

## 📋 Vue d'ensemble

Ce bot Discord utilise un système de configuration persistante avancé qui sauvegarde automatiquement **TOUTES** les configurations dans un fichier JSON et les recharge au redémarrage.

## ✨ Fonctionnalités

### 🔄 **Persistance Automatique**
- ✅ Sauvegarde automatique à chaque modification
- ✅ Rechargement automatique au démarrage
- ✅ Aucune perte de configuration lors des redémarrages
- ✅ Support multi-serveurs indépendants

### 🛡️ **Sécurité & Robustesse**
- ✅ Gestion d'erreurs complète
- ✅ Récupération gracieuse en cas de JSON corrompu
- ✅ Création automatique des configurations par défaut
- ✅ Validation des données

### 🎯 **Facilité d'utilisation**
- ✅ Commandes Discord intuitives
- ✅ Confirmations de sauvegarde
- ✅ Interface utilisateur claire
- ✅ Logs détaillés

## 📁 Structure des Fichiers

```
dgj-code/
├── bot.py                 # Bot principal avec intégration
├── config_manager.py      # Gestionnaire de configuration
├── bot_configs.json       # Fichier de sauvegarde (auto-créé)
└── .gitignore            # Exclusions Git
```

## 🏗️ Architecture

### `config_manager.py`
Module central qui gère toute la persistance:

```python
# Fonctions principales
get_guild_config(guild_id)          # Récupérer config complète
update_guild_config(guild_id, ...)  # Mettre à jour et sauvegarder
get_voice_temp_settings(guild_id)   # Paramètres salons vocaux
get_security_settings(guild_id)     # Paramètres sécurité
```

### `bot.py` - Intégration
Fonctions modifiées pour utiliser la persistance:
- `get_security_config()` - Lecture persistante
- `update_security_config()` - Écriture persistante

## 🗂️ Structure JSON

```json
{
  "123456789": {
    "security_settings": {
      "raid_protection": true,
      "auto_ban_bots": false,
      "max_mentions": 5,
      "max_messages_per_minute": 10,
      "anti_spam": true,
      "auto_delete_invites": false,
      "max_account_age_days": 7
    },
    "voice_temp_settings": {
      "category_id": null,
      "temp_channel_name": "🔊 Salon temporaire de {user}",
      "user_limit": 0,
      "auto_delete": true
    },
    "bot_settings": {
      "prefix": "/",
      "log_actions": true,
      "welcome_message": true,
      "welcome_channel_id": null
    }
  }
}
```

## 💬 Commandes Discord

### `/config_security`
**Configure la sécurité avec sauvegarde automatique**

Paramètres disponibles:
- `raid_protection` - Protection anti-raid
- `auto_ban_bots` - Ban automatique des bots suspects
- `max_mentions` - Mentions maximum par message (1-20)
- `max_messages_per_minute` - Messages max/minute (1-60)
- `anti_spam` - Détection de spam
- `auto_delete_invites` - Suppression auto des invitations
- `max_account_age_days` - Âge minimum compte (0-365 jours)

**Exemple d'utilisation:**
```
/config_security raid_protection:True max_mentions:5 anti_spam:True
```

### `/show_config_complete`
**Affiche toute la configuration sauvegardée**

Montre:
- 🛡️ Paramètres de sécurité
- 🎤 Configuration salons vocaux temporaires
- 🤖 Paramètres généraux du bot
- 💾 Statut de sauvegarde

## 🔧 Installation & Configuration

### Prérequis
```bash
pip install discord.py python-dotenv
```

### Variables d'environnement
```env
DISCORD_TOKEN=votre_token_bot
OWNER_ID=votre_id_discord
```

### Démarrage
```bash
python bot.py
```

Le fichier `bot_configs.json` sera créé automatiquement au premier lancement.

## 🚀 Utilisation

### Premier lancement
1. Le bot crée automatiquement `bot_configs.json`
2. Les configurations par défaut sont initialisées
3. Toutes les modifications sont automatiquement sauvegardées

### Configuration d'un serveur
1. Utilisez `/config_security` pour configurer la sécurité
2. Utilisez `/show_config_complete` pour voir la config
3. Toutes les modifications sont **instantanément sauvegardées**

### Redémarrage
1. Arrêtez le bot
2. Redémarrez avec `python bot.py`
3. **Toutes les configurations sont automatiquement restaurées**

## 🔍 Monitoring & Logs

### Logs automatiques
Le système génère des logs détaillés:
```
🔒 Config sécurité sauvegardée - Guild: 123456789, raid_protection: True
✅ Configuration sauvegardée avec succès pour le serveur 123456789
🆕 Nouvelle configuration pour le serveur 987654321
```

### Vérification de l'état
- Utilisez `/show_config_complete` pour voir l'état complet
- Vérifiez les logs dans la console
- Inspectez `bot_configs.json` si nécessaire

## 🛠️ Maintenance

### Sauvegarde manuelle
```python
import config_manager
config_manager.backup_config("sauvegarde_20240102.json")
```

### Restauration
```python
import config_manager
config_manager.restore_config("sauvegarde_20240102.json")
```

### Nettoyage
Pour supprimer la configuration d'un serveur:
```python
import config_manager
config_manager.delete_guild_config(guild_id)
```

## ⚠️ Gestion d'erreurs

### JSON corrompu
- Le système détecte automatiquement les fichiers corrompus
- Recrée un fichier vide avec logs d'avertissement
- Aucune interruption du service

### Permissions insuffisantes
- Logs d'erreur détaillés
- Fallback sur configuration en mémoire
- Tentatives de récupération automatiques

### Serveur inexistant
- Création automatique de configuration par défaut
- Initialisation avec paramètres sécurisés

## 🎯 Avantages

### Pour les administrateurs
- ✅ **Aucune reconfiguration** après redémarrage
- ✅ **Interface intuitive** avec commandes Discord
- ✅ **Confirmations visuelles** de sauvegarde
- ✅ **Configurations indépendantes** par serveur

### Pour les développeurs
- ✅ **Code modulaire** et réutilisable
- ✅ **Gestion d'erreurs robuste**
- ✅ **Logs détaillés** pour debugging
- ✅ **Architecture extensible**

### Pour la production
- ✅ **Haute disponibilité** (pas de perte de config)
- ✅ **Récupération automatique** après crash
- ✅ **Support multi-serveurs** scalable
- ✅ **Sauvegarde automatique** sans intervention

---

## 📞 Support

En cas de problème, vérifiez:
1. Les logs dans la console
2. Les permissions de fichier pour `bot_configs.json`
3. La validité du JSON avec un validateur en ligne

**Le système est conçu pour être robuste et nécessiter un minimum de maintenance !** 🚀