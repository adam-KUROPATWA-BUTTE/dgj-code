import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from collections import deque, defaultdict
import asyncio
import logging
import subprocess
from datetime import datetime, timedelta
import aiohttp
import json
import re
import random
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import tempfile
import urllib.parse

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Variables d'environnement
load_dotenv()
BOT_TOKEN = os.getenv('DISCORD_TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID', 0))
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID', '')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET', '')

if not BOT_TOKEN:
    logger.error("❌ DISCORD_TOKEN manquant")
    exit(1)

if not OWNER_ID:
    logger.error("❌ OWNER_ID manquant")
    exit(1)

# Configuration du bot
SONG_QUEUES = {}
LOOP_MODES = {}
CURRENT_SONGS = {}
EXTRACTION_STATS = {"success": 0, "failed": 0, "youtube": 0, "spotify": 0, "soundcloud": 0}

# Système de support
SUPPORT_CHANNELS = {}
SUPPORT_CONFIG = {}

# Système de salons vocaux temporaires
TEMP_VOCAL_CONFIG = {}
TEMP_VOCAL_CHANNELS = {}

# ============================
# SYSTÈME DE MODÉRATION ET ANTI-RAID
# ============================

# Configuration de sécurité par serveur
SECURITY_CONFIG = {}

# Système d'avertissements
WARNINGS = defaultdict(list)

# Système anti-raid
RAID_PROTECTION = {}
JOIN_TRACKER = defaultdict(list)
MESSAGE_TRACKER = defaultdict(list)

# Configuration par défaut pour la sécurité
DEFAULT_SECURITY_CONFIG = {
    "enabled": True,
    "max_joins_per_minute": 5,
    "max_messages_per_minute": 10,
    "auto_ban_suspicious": True,
    "log_channel_id": None,
    "whitelist": [],
    "blacklist": [],
    "raid_mode": False,
    "max_warns": 3,
    "timeout_duration": 300,  # 5 minutes
    "delete_spam_messages": True,
    "anti_spam_enabled": True,
    "anti_raid_enabled": True,
    "new_account_threshold": 7,  # jours
    "punishment_type": "timeout"  # timeout, kick, ban
}

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True
intents.members = True
intents.moderation = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ============================
# FONCTIONS UTILITAIRES DE SÉCURITÉ
# ============================

def get_security_config(guild_id):
    """Récupère la configuration de sécurité d'un serveur"""
    if guild_id not in SECURITY_CONFIG:
        SECURITY_CONFIG[guild_id] = DEFAULT_SECURITY_CONFIG.copy()
    return SECURITY_CONFIG[guild_id]

def is_admin(member):
    """Vérifie si un membre est administrateur"""
    return member.guild_permissions.administrator

def is_suspicious_account(member):
    """Détecte si un compte est suspect"""
    config = get_security_config(member.guild.id)
    
    # Compte trop récent
    account_age = (datetime.now() - member.created_at).days
    if account_age < config["new_account_threshold"]:
        return True, f"Compte créé il y a {account_age} jour(s)"
    
    # Pas d'avatar
    if not member.avatar:
        return True, "Pas d'avatar"
    
    # Nom suspect (que des chiffres ou caractères spéciaux)
    if re.match(r'^[0-9\W]+$', member.display_name):
        return True, "Nom suspect"
    
    return False, None

#########################
# /message sepration
#########################
def split_long_message(message, max_length=4000):
    """Divise un long message en plusieurs parties intelligemment"""
    
    if len(message) <= max_length:
        return [message]
    
    parts = []
    
    # Séparateurs prioritaires pour couper intelligemment
    separators = [
        '\n---\n',  # Séparateurs de section
        '\n## ',    # Titres de niveau 2
        '\n### ',   # Titres de niveau 3
        '\n\n',     # Paragraphes
        '\n',       # Lignes
        '. ',       # Phrases
        ' '         # Mots
    ]
    
    remaining = message
    
    while len(remaining) > max_length:
        # Trouver le meilleur endroit pour couper
        best_cut = max_length
        
        for separator in separators:
            # Chercher le dernier séparateur avant la limite
            last_sep = remaining.rfind(separator, 0, max_length)
            if last_sep > max_length * 0.5:  # Au moins 50% de la limite
                best_cut = last_sep + len(separator)
                break
        
        # Extraire la partie
        part = remaining[:best_cut].strip()
        if part:
            parts.append(part)
        
        # Continuer avec le reste
        remaining = remaining[best_cut:].strip()
    
    # Ajouter la dernière partie
    if remaining:
        parts.append(remaining)
    
    return parts

async def log_action(guild, action_type, moderator, target, reason, duration=None):
    """Log une action de modération"""
    config = get_security_config(guild.id)
    
    if not config["log_channel_id"]:
        return
    
    log_channel = guild.get_channel(config["log_channel_id"])
    if not log_channel:
        return
    
    embed = discord.Embed(
        title=f"🔧 Action de Modération - {action_type.upper()}",
        color=0xff6b6b if action_type in ["ban", "kick"] else 0xffa726,
        timestamp=datetime.now()
    )
    
    embed.add_field(name="👤 Utilisateur", value=f"{target.mention} ({target.id})", inline=True)
    embed.add_field(name="👮 Modérateur", value=f"{moderator.mention}", inline=True)
    embed.add_field(name="📋 Raison", value=reason or "Aucune raison spécifiée", inline=False)
    
    if duration:
        embed.add_field(name="⏱️ Durée", value=f"{duration} secondes", inline=True)
    
    embed.set_footer(text=f"Bot de Modération - {guild.name}")
    
    try:
        await log_channel.send(embed=embed)
    except Exception as e:
        logger.error(f"❌ Erreur log modération: {e}")

# ============================
# SYSTÈME ANTI-RAID
# ============================

async def check_raid_protection(member):
    """Vérifie et applique la protection anti-raid"""
    guild = member.guild
    config = get_security_config(guild.id)
    
    if not config["anti_raid_enabled"]:
        return
    
    now = datetime.now()
    guild_id = guild.id
    
    # Ajouter à la liste des joins récents
    JOIN_TRACKER[guild_id].append(now)
    
    # Nettoyer les anciens joins (plus de 1 minute)
    JOIN_TRACKER[guild_id] = [
        join_time for join_time in JOIN_TRACKER[guild_id]
        if (now - join_time).seconds < 60
    ]
    
    recent_joins = len(JOIN_TRACKER[guild_id])
    
    # Si trop de joins récents, activer le mode raid
    if recent_joins > config["max_joins_per_minute"]:
        config["raid_mode"] = True
        logger.warning(f"🚨 Mode raid activé sur {guild.name} - {recent_joins} joins en 1 minute")
        
        # Notifier les modérateurs
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                embed = discord.Embed(
                    title="🚨 MODE RAID ACTIVÉ",
                    description=f"**{recent_joins} utilisateurs** ont rejoint en moins d'une minute !",
                    color=0xff0000
                )
                embed.add_field(name="🛡️ Mesures prises", value="• Surveillance renforcée\n• Auto-ban des comptes suspects\n• Vérification manuelle recommandée", inline=False)
                await channel.send(embed=embed)
                break
    
    # Si en mode raid, vérifier si le compte est suspect
    if config["raid_mode"] and config["auto_ban_suspicious"]:
        is_suspect, reason = is_suspicious_account(member)
        
        if is_suspect:
            try:
                await member.ban(reason=f"Auto-ban anti-raid: {reason}")
                logger.info(f"🔨 Auto-ban anti-raid: {member} - {reason}")
                
                # Log l'action
                await log_action(guild, "auto-ban", guild.me, member, f"Anti-raid: {reason}")
                
            except Exception as e:
                logger.error(f"❌ Erreur auto-ban: {e}")

async def check_message_spam(message):
    """Vérifie et gère le spam de messages"""
    if message.author.bot:
        return
    
    guild = message.guild
    if not guild:
        return
    
    config = get_security_config(guild.id)
    
    if not config["anti_spam_enabled"]:
        return
    
    user_id = message.author.id
    now = datetime.now()
    
    # Ajouter le message à la liste
    MESSAGE_TRACKER[user_id].append(now)
    
    # Nettoyer les anciens messages (plus de 1 minute)
    MESSAGE_TRACKER[user_id] = [
        msg_time for msg_time in MESSAGE_TRACKER[user_id]
        if (now - msg_time).seconds < 60
    ]
    
    recent_messages = len(MESSAGE_TRACKER[user_id])
    
    # Si trop de messages récents
    if recent_messages > config["max_messages_per_minute"]:
        # Supprimer les messages spam si activé
        if config["delete_spam_messages"]:
            try:
                await message.delete()
            except:
                pass
        
        # Punir l'utilisateur selon la configuration
        punishment = config["punishment_type"]
        reason = f"Spam détecté - {recent_messages} messages en 1 minute"
        
        try:
            if punishment == "timeout":
                timeout_until = datetime.now() + timedelta(seconds=config["timeout_duration"])
                await message.author.timeout(timeout_until, reason=reason)
                
            elif punishment == "kick":
                await message.author.kick(reason=reason)
                
            elif punishment == "ban":
                await message.author.ban(reason=reason)
            
            # Log l'action
            await log_action(guild, f"anti-spam-{punishment}", guild.me, message.author, reason)
            
            logger.info(f"🚫 Anti-spam {punishment}: {message.author} - {reason}")
            
        except Exception as e:
            logger.error(f"❌ Erreur punition anti-spam: {e}")

# ============================
# SPOTIFY API (identique)
# ============================

spotify_client = None

def init_spotify():
    """Initialise le client Spotify"""
    global spotify_client
    
    if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
        try:
            client_credentials_manager = SpotifyClientCredentials(
                client_id=SPOTIFY_CLIENT_ID,
                client_secret=SPOTIFY_CLIENT_SECRET
            )
            spotify_client = spotipy.Spotify(client_credentials_manager=client_credentials_manager)
            logger.info("✅ Client Spotify initialisé")
            return True
        except Exception as e:
            logger.error(f"❌ Erreur Spotify: {e}")
    else:
        logger.warning("⚠️ Spotify non configuré")
    
    return False

def spotify_to_search_query(spotify_url):
    """Convertit un lien Spotify en requête de recherche"""
    if not spotify_client:
        return None
    
    try:
        # Extraire l'ID de la track depuis l'URL
        track_id = spotify_url.split('/')[-1].split('?')[0]
        
        # Récupérer les métadonnées
        track_info = spotify_client.track(track_id)
        
        artist = track_info['artists'][0]['name']
        title = track_info['name']
        
        search_query = f"{artist} {title}"
        
        logger.info(f"🎵 Spotify converti: {search_query}")
        return search_query, track_info
    
    except Exception as e:
        logger.error(f"❌ Erreur conversion Spotify: {e}")
        return None

async def search_spotify_metadata(query):
    """Recherche des métadonnées sur Spotify"""
    if not spotify_client:
        return None
    
    try:
        results = spotify_client.search(q=query, type='track', limit=1)
        tracks = results['tracks']['items']
        
        if tracks:
            track = tracks[0]
            artist = track['artists'][0]['name']
            title = track['name']
            duration = track['duration_ms'] // 1000
            thumbnail = track['album']['images'][0]['url'] if track['album']['images'] else None
            spotify_url = track['external_urls']['spotify']
            
            return {
                'artist': artist,
                'title': title,
                'duration': duration,
                'thumbnail': thumbnail,
                'spotify_url': spotify_url,
                'search_query': f"{artist} {title}"
            }
    
    except Exception as e:
        logger.error(f"❌ Erreur recherche Spotify: {e}")
    
    return None

# ============================
# YT-DLP DIRECT - MÉTHODES ROBUSTES (identique)
# ============================

async def extract_with_ytdlp(query, source_type="youtube"):
    """Extraction directe avec yt-dlp - MULTIPLE MÉTHODES"""
    
    # Préparer la requête selon la source
    if source_type == "youtube":
        if query.startswith("http"):
            search_query = query
        else:
            search_query = f"ytsearch1:{query}"
    elif source_type == "soundcloud":
        if query.startswith("http"):
            search_query = query
        else:
            search_query = f"scsearch1:{query}"
    else:
        search_query = f"ytsearch1:{query}"
    
    # Options yt-dlp ULTRA ROBUSTES
    ytdl_options = {
        'format': 'bestaudio[ext=webm]/bestaudio[ext=mp4]/bestaudio',
        'extractaudio': True,
        'audioformat': 'mp3',
        'audioquality': '192K',
        'noplaylist': True,
        'no_warnings': True,
        'quiet': True,
        'extract_flat': False,
        'writethumbnail': False,
        'writeinfojson': False,
        'ignoreerrors': True,
        # Headers pour éviter les blocages
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        },
        # Options avancées
        'extractor_retries': 3,
        'fragment_retries': 3,
        'retries': 5,
        'socket_timeout': 30,
        'geo_bypass': True,
        'geo_bypass_country': 'US'
    }
    
    # Méthodes d'extraction (8 différentes pour plus de robustesse)
    extraction_methods = [
        # Méthode 1: Standard
        {**ytdl_options},
        
        # Méthode 2: Android client
        {**ytdl_options, 'extractor_args': {'youtube': {'player_client': ['android']}}},
        
        # Méthode 3: Web + Android
        {**ytdl_options, 'extractor_args': {'youtube': {'player_client': ['android', 'web']}}},
        
        # Méthode 4: TV Embedded
        {**ytdl_options, 'extractor_args': {'youtube': {'player_client': ['tv_embedded']}}},
        
        # Méthode 5: iOS client
        {**ytdl_options, 'extractor_args': {'youtube': {'player_client': ['ios']}}},
        
        # Méthode 6: Age gate bypass
        {**ytdl_options, 'age_limit': 999},
        
        # Méthode 7: Minimal quality
        {
            'format': 'worst[ext=webm]/worst',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False
        },
        
        # Méthode 8: Dernière chance avec proxy bypass
        {
            'format': 'bestaudio',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'geo_bypass': True,
            'extractor_args': {'youtube': {'player_client': ['android', 'web', 'tv_embedded']}}
        }
    ]
    
    for i, options in enumerate(extraction_methods, 1):
        try:
            logger.info(f"🔄 Tentative yt-dlp {i}/8: {source_type}")
            
            # Commande yt-dlp
            cmd = ['yt-dlp', '--dump-json']
            for key, value in options.items():
                if key == 'format':
                    cmd.extend(['-f', str(value)])
                elif key == 'http_headers':
                    for header_key, header_value in value.items():
                        cmd.extend(['--add-header', f'{header_key}:{header_value}'])
                elif key == 'extractor_args':
                    for extractor, args in value.items():
                        if isinstance(args, list):
                            for arg in args:
                                cmd.extend(['--extractor-args', f'{extractor}:player_client={arg}'])
                        else:
                            cmd.extend(['--extractor-args', f'{extractor}:{args}'])
                elif isinstance(value, bool) and value:
                    cmd.append(f'--{key.replace("_", "-")}')
                elif not isinstance(value, (bool, dict)):
                    cmd.extend([f'--{key.replace("_", "-")}', str(value)])
            
            cmd.append(search_query)
            
            # Exécuter avec timeout
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
                
                if process.returncode == 0 and stdout:
                    info = json.loads(stdout.decode())
                    
                    # Extraire les informations
                    title = info.get('title', 'Titre inconnu')
                    uploader = info.get('uploader', 'Auteur inconnu')
                    duration = info.get('duration', 0)
                    url = info.get('url', info.get('webpage_url', ''))
                    thumbnail = info.get('thumbnail', '')
                    
                    logger.info(f"✅ Extraction réussie méthode {i}: {title}")
                    EXTRACTION_STATS["success"] += 1
                    
                    if source_type == "youtube":
                        EXTRACTION_STATS["youtube"] += 1
                    elif source_type == "soundcloud":
                        EXTRACTION_STATS["soundcloud"] += 1
                    
                    return {
                        'title': title,
                        'uploader': uploader,
                        'duration': duration,
                        'url': url,
                        'thumbnail': thumbnail,
                        'source': source_type
                    }
                
            except asyncio.TimeoutError:
                logger.warning(f"⚠️ Timeout méthode {i}")
                process.kill()
                continue
            
        except Exception as e:
            logger.warning(f"⚠️ Méthode {i} échouée: {e}")
            continue
    
    # Toutes les méthodes ont échoué
    logger.error(f"❌ Échec extraction {source_type}: {query}")
    EXTRACTION_STATS["failed"] += 1
    return None

# ============================
# LECTURE AUDIO DIRECTE (identique)
# ============================

async def play_extracted_audio(voice_client, audio_info, channel):
    """Joue l'audio extrait directement"""
    
    try:
        if not audio_info or not audio_info.get('url'):
            return False
        
        # Options FFmpeg optimisées
        ffmpeg_options = {
            'before_options': (
                '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 30 '
                '-analyzeduration 1000000 -probesize 1000000 '
                '-user_agent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"'
            ),
            'options': '-vn -bufsize 512k -maxrate 128k -filter:a volume=0.6'
        }
        
        source = discord.FFmpegPCMAudio(audio_info['url'], **ffmpeg_options)
        
        def after_play(error):
            if error:
                logger.error(f"Erreur FFmpeg: {error}")
            asyncio.run_coroutine_threadsafe(play_next_in_queue(voice_client, channel), bot.loop)
        
        voice_client.play(source, after=after_play)
        
        # Message de succès
        embed = create_embed("🎵 Lecture en cours", f"**{audio_info['title']}**")
        embed.add_field(name="👤 Auteur", value=audio_info['uploader'], inline=True)
        embed.add_field(name="⏱️ Durée", value=format_duration(audio_info['duration']), inline=True)
        embed.add_field(name="🎯 Source", value=audio_info['source'].title(), inline=True)
        
        if audio_info.get('thumbnail'):
            embed.set_thumbnail(url=audio_info['thumbnail'])
        
        await channel.send(embed=embed)
        
        logger.info(f"🎵 Lecture démarrée: {audio_info['title']}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur lecture audio: {e}")
        return False

async def play_next_in_queue(voice_client, channel):
    """Joue la chanson suivante dans la queue"""
    
    guild_id = str(voice_client.guild.id)
    
    if guild_id in SONG_QUEUES and SONG_QUEUES[guild_id]:
        # Récupérer la prochaine chanson
        query, source_type = SONG_QUEUES[guild_id].popleft()
        
        # Message de progression
        embed = create_embed("🔍 Extraction suivante...", f"Recherche: `{query}`", 0xffff00)
        progress_msg = await channel.send(embed=embed)
        
        # Extraire l'audio
        audio_info = await extract_with_ytdlp(query, source_type)
        
        # Supprimer le message de progression
        try:
            await progress_msg.delete()
        except:
            pass
        
        if audio_info:
            # Jouer l'audio
            await play_extracted_audio(voice_client, audio_info, channel)
        else:
            # Échec, essayer la suivante ou radio
            embed = create_embed("❌ Extraction échouée", f"Impossible d'extraire: `{query}`", 0xff9900)
            await channel.send(embed=embed)
            
            # Essayer la suivante
            await play_next_in_queue(voice_client, channel)
    
    else:
        # Queue vide, jouer radio
        await play_radio_fallback(voice_client, channel)

async def play_radio_fallback(voice_client, channel):
    """Joue une radio en fallback"""
    
    radios = [
        {"name": "FIP Radio France", "url": "https://icecast.radiofrance.fr/fip-hifi.aac"},
        {"name": "SomaFM Groove Salad", "url": "http://ice1.somafm.com/groovesalad-256-mp3"},
        {"name": "Swiss Radio", "url": "http://stream.srg-ssr.ch/rsp/aacp_48.aac"},
        {"name": "Lofi Hip Hop Radio", "url": "http://streams.fluxfm.de/Lofi/mp3-320/audio/"},
        {"name": "Chill Radio", "url": "http://air.radiorecord.ru:805/chill_320"}
    ]
    
    for radio in radios:
        try:
            ffmpeg_options = {
                'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 30',
                'options': '-vn -filter:a volume=0.4'
            }
            
            source = discord.FFmpegPCMAudio(radio["url"], **ffmpeg_options)
            voice_client.play(source)
            
            embed = create_embed("📻 Radio en cours", f"**{radio['name']}**\nMusique en continu")
            await channel.send(embed=embed)
            
            logger.info(f"📻 Radio fallback active: {radio['name']}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Radio {radio['name']} échouée: {e}")
            continue
    
    return False

# ============================
# SYSTÈME DE SUPPORT COMPLET (identique)
# ============================

async def handle_support_join(member, waiting_channel):
    guild = member.guild
    guild_id = guild.id
    admin_role_id = SUPPORT_CONFIG[guild_id]["admin_role_id"]
    admin_role = guild.get_role(admin_role_id)
    is_admin = admin_role in member.roles if admin_role else False
    
    try:
        support_channel = await find_or_create_support_channel(guild, is_admin)
        if support_channel:
            await member.move_to(support_channel)
            logger.info(f"📞 {member.display_name} déplacé vers {support_channel.name}")
    except Exception as e:
        logger.error(f"❌ Erreur déplacement support: {e}")

async def find_or_create_support_channel(guild, is_admin=False):
    guild_id = guild.id
    category_id = SUPPORT_CONFIG[guild_id]["category_id"]
    admin_role_id = SUPPORT_CONFIG[guild_id]["admin_role_id"]
    
    category = guild.get_channel(category_id)
    if not category:
        return None
    
    active_channels = SUPPORT_CHANNELS[guild_id]["active"]
    
    for channel_id in active_channels[:]:
        channel = guild.get_channel(channel_id)
        if not channel:
            active_channels.remove(channel_id)
            continue
        
        non_admin_count = 0
        admin_role = guild.get_role(admin_role_id)
        
        for member in channel.members:
            if not admin_role or admin_role not in member.roles:
                non_admin_count += 1
        
        if non_admin_count < 5:
            return channel
    
    new_number = len(active_channels) + 1
    channel_name = f"⏳│Besoin d'aide {new_number}"
    
    admin_role = guild.get_role(admin_role_id)
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False, connect=False),
        guild.me: discord.PermissionOverwrite(view_channel=True, connect=True, manage_channels=True, move_members=True)
    }
    
    if admin_role:
        overwrites[admin_role] = discord.PermissionOverwrite(
            view_channel=True, connect=True, speak=True, move_members=True, manage_channels=True
        )
    
    try:
        new_channel = await category.create_voice_channel(channel_name, overwrites=overwrites, user_limit=6)
        active_channels.append(new_channel.id)
        logger.info(f"✅ Nouveau channel de support créé: {channel_name}")
        return new_channel
    except Exception as e:
        logger.error(f"❌ Erreur création channel support: {e}")
        return None

async def cleanup_empty_support_channel(channel):
    if not channel.name.startswith("⏳│Besoin d'aide "):
        return
    
    await asyncio.sleep(5)
    
    if len(channel.members) == 0:
        guild_id = channel.guild.id
        if guild_id in SUPPORT_CHANNELS:
            active_channels = SUPPORT_CHANNELS[guild_id]["active"]
            if channel.id in active_channels:
                active_channels.remove(channel.id)
            try:
                await channel.delete(reason="Channel de support vide")
                logger.info(f"🗑️ Channel de support supprimé: {channel.name}")
            except Exception as e:
                logger.error(f"❌ Erreur suppression channel: {e}")

# ============================
# SYSTÈME DE SALONS VOCAUX TEMPORAIRES (identique)
# ============================

async def handle_temp_vocal_join(member, create_channel):
    """Gère la création d'un salon vocal temporaire"""
    guild = member.guild
    guild_id = guild.id
    
    if guild_id not in TEMP_VOCAL_CONFIG:
        return
    
    config = TEMP_VOCAL_CONFIG[guild_id]
    category_id = config["category_id"]
    
    try:
        category = guild.get_channel(category_id)
        if not category:
            logger.error(f"❌ Catégorie vocale introuvable: {category_id}")
            return
        
        # Créer un salon vocal avec le nom de l'utilisateur
        channel_name = f"🎤 {member.display_name}"
        
        # Permissions : le créateur a des permissions de gestion
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=True, connect=True),
            member: discord.PermissionOverwrite(
                view_channel=True, 
                connect=True, 
                speak=True, 
                manage_channels=True, 
                move_members=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, 
                connect=True, 
                manage_channels=True, 
                move_members=True
            )
        }
        
        # Créer le salon
        new_channel = await category.create_voice_channel(
            name=channel_name,
            overwrites=overwrites,
            user_limit=10  # Limite par défaut
        )
        
        # Déplacer l'utilisateur vers le nouveau salon
        await member.move_to(new_channel)
        
        # Ajouter à la liste des salons temporaires
        if guild_id not in TEMP_VOCAL_CHANNELS:
            TEMP_VOCAL_CHANNELS[guild_id] = []
        
        TEMP_VOCAL_CHANNELS[guild_id].append({
            'channel_id': new_channel.id,
            'creator_id': member.id,
            'created_at': datetime.now()
        })
        
        logger.info(f"🎤 Salon vocal temporaire créé: {channel_name} pour {member.display_name}")
        
        # Démarrer la surveillance pour le nettoyage automatique
        asyncio.create_task(monitor_temp_channel(new_channel, member.id))
        
    except Exception as e:
        logger.error(f"❌ Erreur création salon temporaire: {e}")

async def monitor_temp_channel(channel, creator_id):
    """Surveille un salon temporaire et le supprime quand il est vide"""
    guild_id = channel.guild.id
    
    while True:
        try:
            await asyncio.sleep(5)  # Vérifier toutes les 5 secondes
            
            # Vérifier si le salon existe encore
            channel = bot.get_channel(channel.id)
            if not channel:
                break
            
            # Si le salon est vide, le supprimer
            if len(channel.members) == 0:
                await channel.delete(reason="Salon vocal temporaire vide")
                
                # Retirer de la liste
                if guild_id in TEMP_VOCAL_CHANNELS:
                    TEMP_VOCAL_CHANNELS[guild_id] = [
                        ch for ch in TEMP_VOCAL_CHANNELS[guild_id] 
                        if ch['channel_id'] != channel.id
                    ]
                
                logger.info(f"🗑️ Salon vocal temporaire supprimé: {channel.name}")
                break
                
        except Exception as e:
            logger.error(f"❌ Erreur surveillance salon temporaire: {e}")
            break

async def cleanup_temp_vocal_channel(channel):
    """Nettoie un salon vocal temporaire vide"""
    if not channel.name.startswith("🎤 "):
        return
    
    guild_id = channel.guild.id
    
    # Vérifier si c'est un salon temporaire enregistré
    if guild_id in TEMP_VOCAL_CHANNELS:
        temp_channels = TEMP_VOCAL_CHANNELS[guild_id]
        channel_info = next((ch for ch in temp_channels if ch['channel_id'] == channel.id), None)
        
        if channel_info and len(channel.members) == 0:
            try:
                await channel.delete(reason="Salon vocal temporaire vide")
                
                # Retirer de la liste
                TEMP_VOCAL_CHANNELS[guild_id] = [
                    ch for ch in temp_channels if ch['channel_id'] != channel.id
                ]
                
                logger.info(f"🗑️ Salon vocal temporaire nettoyé: {channel.name}")
            except Exception as e:
                logger.error(f"❌ Erreur nettoyage salon temporaire: {e}")

# ============================
# FONCTIONS UTILITAIRES
# ============================

def format_duration(seconds):
    if not seconds:
        return "Durée inconnue"
    hours, remainder = divmod(int(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{seconds:02d}s"
    else:
        return f"{minutes}m{seconds:02d}s"

def create_embed(title, description, color=0x00ff00):
    embed = discord.Embed(title=title, description=description, color=color)
    embed.timestamp = datetime.now()
    embed.set_footer(text="🎵 Bot Musical Direct Pro + Modération Anti-Raid - 2025-07-01")
    return embed

# ============================
# ÉVÉNEMENTS DISCORD
# ============================

@bot.event
async def on_ready():
    print(f"🤖 {bot.user} est connecté et prêt !")
    print(f"🏠 Serveurs: {len(bot.guilds)}")
    
    try:
        # Sync global
        print("🌍 Synchronisation globale...")
        synced_global = await bot.tree.sync()
        print(f"✅ Global: {len(synced_global)} commandes")
        
        # Sync pour chaque serveur individuellement
        for guild in bot.guilds:
            try:
                print(f"🏠 Sync pour {guild.name}...")
                synced_guild = await bot.tree.sync(guild=guild)
                print(f"✅ {guild.name}: {len(synced_guild)} commandes")
            except Exception as e:
                print(f"❌ {guild.name}: {e}")
        
        print("🔄 Synchronisation complète terminée !")
        
    except Exception as e:
        print(f"❌ Erreur sync: {e}")

    # Initialiser Spotify
    init_spotify()
    
    # Vérifier yt-dlp
    try:
        process = await asyncio.create_subprocess_exec(
            'yt-dlp', '--version',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await process.communicate()
        version = stdout.decode().strip()
        logger.info(f"✅ yt-dlp version: {version}")
    except Exception as e:
        logger.error(f"❌ yt-dlp non trouvé: {e}")
    
    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Activity(type=discord.ActivityType.watching, name="Bot De Mada - /help pour plus d'infos")
    )
    
    print("=" * 80)
    print(f"🎵 BOT COMPLET AVEC MODÉRATION ET ANTI-RAID PRÊT !")
    print(f"👤 Connecté: {bot.user.name}")
    print(f"🏠 Serveurs: {len(bot.guilds)}")
    print(f"🎧 Spotify API: {'✅ Configurée' if spotify_client else '⚠️ Non configurée'}")
    print(f"🔥 yt-dlp: ✅ 8 méthodes d'extraction robustes")
    print(f"🎯 Sources: YouTube direct + SoundCloud + Spotify→YouTube")
    print(f"🎧 Support: Système vocal automatique")
    print(f"🎤 Salons vocaux: Création automatique temporaire")
    print(f"🛡️ Modération: Ban/Kick/Timeout/Warn/Clear")
    print(f"🚨 Anti-Raid: Protection automatique avancée")
    print(f"📻 Radio: 5 stations de fallback")
    print(f"📋 Commandes: /play, /ban, /kick, /timeout, /warn, /clear, /config_security")
    print("=" * 80)

@bot.event
async def on_member_join(member):
    """Événement quand un membre rejoint"""
    await check_raid_protection(member)

@bot.event
async def on_message(message):
    """Événement pour chaque message"""
    await check_message_spam(message)
    await bot.process_commands(message)

@bot.event
async def on_voice_state_update(member, before, after):
    guild = member.guild
    guild_id = guild.id
    
    # Système de support
    if guild_id in SUPPORT_CHANNELS:
        support_config = SUPPORT_CHANNELS[guild_id]
        waiting_channel_id = support_config["waiting"]
        
        if after.channel and after.channel.id == waiting_channel_id:
            await handle_support_join(member, after.channel)
        
        if before.channel and before.channel.name.startswith("⏳│Besoin d'aide "):
            await cleanup_empty_support_channel(before.channel)
    
    # Système de salons vocaux temporaires
    if guild_id in TEMP_VOCAL_CONFIG:
        config = TEMP_VOCAL_CONFIG[guild_id]
        create_channel_id = config["create_channel_id"]
        
        # Si l'utilisateur rejoint "Créer un salon vocal"
        if after.channel and after.channel.id == create_channel_id:
            await handle_temp_vocal_join(member, after.channel)
        
        # Si l'utilisateur quitte un salon temporaire
        if before.channel and before.channel.name.startswith("🎤 "):
            await cleanup_temp_vocal_channel(before.channel)

# ============================
# COMMANDES SLASH MUSICALES (identiques à l'original)
# ============================

@bot.tree.command(name="play", description="🎵 Jouer une chanson (8 méthodes yt-dlp)")
@app_commands.describe(song="Nom de la chanson ou URL")
async def play(interaction: discord.Interaction, song: str):
    """Commande play avec yt-dlp direct - 8 méthodes"""
    await interaction.response.defer()
    
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.followup.send("❌ Vous devez être dans un canal vocal !", ephemeral=True)
        return
    
    voice_channel = interaction.user.voice.channel
    
    # Se connecter au voice
    if not interaction.guild.voice_client:
        voice_client = await voice_channel.connect()
    else:
        voice_client = interaction.guild.voice_client
        if voice_client.channel != voice_channel:
            await voice_client.move_to(voice_channel)
    
    guild_id = str(interaction.guild_id)
    
    # Initialiser la queue si nécessaire
    if guild_id not in SONG_QUEUES:
        SONG_QUEUES[guild_id] = deque()
    
    # Si rien ne joue, jouer immédiatement
    if not voice_client.is_playing() and not voice_client.is_paused():
        # Message de progression
        embed = create_embed("🔍 Extraction en cours...", f"Recherche: `{song}`\n\n🔥 8 méthodes yt-dlp robustes", 0xffff00)
        progress_msg = await interaction.followup.send(embed=embed)
        
        # Extraire l'audio
        audio_info = await extract_with_ytdlp(song, "youtube")
        
        # Supprimer le message de progression
        try:
            await progress_msg.delete()
        except:
            pass
        
        if audio_info:
            # Jouer immédiatement
            success = await play_extracted_audio(voice_client, audio_info, interaction.channel)
            if success:
                embed = create_embed("✅ Lecture démarrée", f"Chanson: `{song}`")
                await interaction.followup.send(embed=embed)
            else:
                embed = create_embed("❌ Erreur lecture", f"Impossible de jouer: `{song}`", 0xff0000)
                await interaction.followup.send(embed=embed)
        else:
            # Échec extraction
            embed = create_embed("❌ Extraction échouée", f"Toutes les 8 méthodes ont échoué pour: `{song}`\n\n📻 Radio à la place", 0xff9900)
            await interaction.followup.send(embed=embed)
            
            # Radio fallback
            await play_radio_fallback(voice_client, interaction.channel)
    
    else:
        # Ajouter à la queue
        SONG_QUEUES[guild_id].append((song, "youtube"))
        
        embed = create_embed("📋 Ajouté à la queue", f"**{song}**\nPosition: {len(SONG_QUEUES[guild_id])}")
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="spotify", description="🎧 Jouer depuis Spotify (converti en YouTube)")
@app_commands.describe(song="Nom de chanson à rechercher sur Spotify ou lien Spotify")
async def spotify_play(interaction: discord.Interaction, song: str):
    """Lecture Spotify via conversion YouTube"""
    await interaction.response.defer()
    
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.followup.send("❌ Vous devez être dans un canal vocal !", ephemeral=True)
        return
    
    search_query = song
    
    # Si c'est un lien Spotify, convertir
    if "spotify.com" in song:
        conversion_result = spotify_to_search_query(song)
        if conversion_result:
            search_query, track_info = conversion_result
            
            embed = create_embed("🎧 Spotify trouvé", f"**{track_info['name']}**")
            embed.add_field(name="🎤 Artiste", value=track_info['artists'][0]['name'], inline=True)
            embed.add_field(name="🔄 Conversion", value="YouTube yt-dlp", inline=True)
            await interaction.followup.send(embed=embed)
        else:
            embed = create_embed("❌ Erreur Spotify", "Impossible de lire ce lien Spotify", 0xff0000)
            await interaction.followup.send(embed=embed)
            return
    else:
        # Recherche métadonnées Spotify
        metadata = await search_spotify_metadata(song)
        if metadata:
            search_query = metadata['search_query']
            
            embed = create_embed("🎧 Spotify trouvé", f"**{metadata['title']}**")
            embed.add_field(name="🎤 Artiste", value=metadata['artist'], inline=True)
            embed.add_field(name="🔄 Conversion", value="YouTube yt-dlp", inline=True)
            
            if metadata['thumbnail']:
                embed.set_thumbnail(url=metadata['thumbnail'])
            
            await interaction.followup.send(embed=embed)
            EXTRACTION_STATS["spotify"] += 1
        else:
            embed = create_embed("❌ Erreur Spotify", "Chanson non trouvée sur Spotify", 0xff0000)
            await interaction.followup.send(embed=embed)
            return
    
    # Maintenant jouer avec la recherche convertie
    voice_channel = interaction.user.voice.channel
    
    # Se connecter au voice
    if not interaction.guild.voice_client:
        voice_client = await voice_channel.connect()
    else:
        voice_client = interaction.guild.voice_client
        if voice_client.channel != voice_channel:
            await voice_client.move_to(voice_channel)
    
    guild_id = str(interaction.guild_id)
    
    # Initialiser la queue si nécessaire
    if guild_id not in SONG_QUEUES:
        SONG_QUEUES[guild_id] = deque()
    
    # Si rien ne joue, jouer immédiatement
    if not voice_client.is_playing() and not voice_client.is_paused():
        # Extraire l'audio
        audio_info = await extract_with_ytdlp(search_query, "youtube")
        
        if audio_info:
            # Jouer immédiatement
            await play_extracted_audio(voice_client, audio_info, interaction.channel)
        else:
            # Radio fallback
            await play_radio_fallback(voice_client, interaction.channel)
    else:
        # Ajouter à la queue
        SONG_QUEUES[guild_id].append((search_query, "youtube"))
        
        embed = create_embed("📋 Spotify ajouté", f"**{search_query}**\nPosition: {len(SONG_QUEUES[guild_id])}")
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="soundcloud", description="🔊 Jouer depuis SoundCloud")
@app_commands.describe(song="Nom de la chanson ou URL SoundCloud")
async def soundcloud_play(interaction: discord.Interaction, song: str):
    """Lecture directe SoundCloud"""
    await interaction.response.defer()
    
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.followup.send("❌ Vous devez être dans un canal vocal !", ephemeral=True)
        return
    
    voice_channel = interaction.user.voice.channel
    
    # Se connecter au voice
    if not interaction.guild.voice_client:
        voice_client = await voice_channel.connect()
    else:
        voice_client = interaction.guild.voice_client
        if voice_client.channel != voice_channel:
            await voice_client.move_to(voice_channel)
    
    guild_id = str(interaction.guild_id)
    
    # Initialiser la queue si nécessaire
    if guild_id not in SONG_QUEUES:
        SONG_QUEUES[guild_id] = deque()
    
    # Si rien ne joue, jouer immédiatement
    if not voice_client.is_playing() and not voice_client.is_paused():
        # Message de progression
        embed = create_embed("🔍 Extraction SoundCloud...", f"Recherche: `{song}`", 0xffff00)
        progress_msg = await interaction.followup.send(embed=embed)
        
        # Extraire l'audio depuis SoundCloud
        audio_info = await extract_with_ytdlp(song, "soundcloud")
        
        # Supprimer le message de progression
        try:
            await progress_msg.delete()
        except:
            pass
        
        if audio_info:
            # Jouer immédiatement
            success = await play_extracted_audio(voice_client, audio_info, interaction.channel)
            if success:
                embed = create_embed("✅ SoundCloud", f"Chanson: `{song}`")
                await interaction.followup.send(embed=embed)
        else:
            embed = create_embed("❌ SoundCloud échoué", f"Impossible d'extraire: `{song}`\n\n📻 Radio à la place", 0xff9900)
            await interaction.followup.send(embed=embed)
            await play_radio_fallback(voice_client, interaction.channel)
    
    else:
        # Ajouter à la queue
        SONG_QUEUES[guild_id].append((song, "soundcloud"))
        
        embed = create_embed("📋 SoundCloud ajouté", f"**{song}**\nPosition: {len(SONG_QUEUES[guild_id])}")
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="radio", description="📻 Jouer une radio")
async def radio_command(interaction: discord.Interaction):
    """Lance une radio directement"""
    await interaction.response.defer()
    
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.followup.send("❌ Vous devez être dans un canal vocal !", ephemeral=True)
        return
    
    voice_channel = interaction.user.voice.channel
    
    # Se connecter au voice
    if not interaction.guild.voice_client:
        voice_client = await voice_channel.connect()
    else:
        voice_client = interaction.guild.voice_client
        if voice_client.channel != voice_channel:
            await voice_client.move_to(voice_channel)
    
    # Arrêter ce qui joue actuellement
    if voice_client.is_playing():
        voice_client.stop()
    
    # Lancer la radio
    success = await play_radio_fallback(voice_client, interaction.channel)
    
    if success:
        embed = create_embed("📻 Radio lancée", "Musique en continu activée")
        await interaction.followup.send(embed=embed)
    else:
        embed = create_embed("❌ Erreur radio", "Impossible de lancer la radio", 0xff0000)
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="queue", description="📋 Voir la queue")
async def queue_command(interaction: discord.Interaction):
    """Affiche la queue actuelle"""
    
    guild_id = str(interaction.guild_id)
    
    if guild_id not in SONG_QUEUES or not SONG_QUEUES[guild_id]:
        embed = create_embed("📋 Queue vide", "Aucune chanson en attente")
        await interaction.response.send_message(embed=embed)
        return
    
    queue = SONG_QUEUES[guild_id]
    embed = create_embed("📋 Queue actuelle", f"{len(queue)} chanson(s) en attente")
    
    # Afficher les prochaines chansons
    upcoming = []
    for i, (query, source) in enumerate(list(queue)[:10], 1):
        upcoming.append(f"`{i}.` **{query}** ({source})")
    
    embed.add_field(
        name="⏭️ À venir",
        value="\n".join(upcoming),
        inline=False
    )
    
    if len(queue) > 10:
        embed.add_field(name="➕", value=f"... et {len(queue) - 10} autres", inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="skip", description="⏭️ Passer à la chanson suivante")
async def skip(interaction: discord.Interaction):
    """Passer à la suivante"""
    
    voice_client = interaction.guild.voice_client
    
    if not voice_client or not voice_client.is_playing():
        await interaction.response.send_message("❌ Aucune chanson en cours.", ephemeral=True)
        return
    
    voice_client.stop()  # Cela déclenchera after_play qui lancera la suivante
    
    embed = create_embed("⏭️ Chanson passée", "Passage à la suivante...")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="stop", description="⏹️ Arrêter et vider la queue")
async def stop(interaction: discord.Interaction):
    """Arrêter complètement"""
    
    voice_client = interaction.guild.voice_client
    
    if not voice_client:
        await interaction.response.send_message("❌ Bot non connecté.", ephemeral=True)
        return
    
    # Vider la queue
    guild_id = str(interaction.guild_id)
    if guild_id in SONG_QUEUES:
        SONG_QUEUES[guild_id].clear()
    
    # Arrêter la lecture
    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()
    
    embed = create_embed("⏹️ Lecture arrêtée", "Queue vidée")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="disconnect", description="📞 Déconnecter le bot")
async def disconnect(interaction: discord.Interaction):
    """Déconnecter le bot du vocal"""
    
    if not interaction.guild.voice_client:
        await interaction.response.send_message("❌ Bot non connecté.", ephemeral=True)
        return
    
    await interaction.guild.voice_client.disconnect()
    
    embed = create_embed("📞 Déconnecté", "Bot déconnecté du vocal")
    await interaction.response.send_message(embed=embed)

# ============================
# COMMANDES DE MODÉRATION
# ============================

@bot.tree.command(name="ban", description="🔨 Bannir un utilisateur")
@app_commands.describe(
    user="Utilisateur à bannir",
    reason="Raison du bannissement",
    delete_messages="Supprimer les messages (en jours, 0-7)"
)
async def ban_user(interaction: discord.Interaction, user: discord.Member, reason: str = None, delete_messages: int = 0):
    """Bannir un utilisateur"""
    
    if not is_admin(interaction.user):
        await interaction.response.send_message("❌ Vous devez être administrateur !", ephemeral=True)
        return
    
    if user.id == interaction.user.id:
        await interaction.response.send_message("❌ Vous ne pouvez pas vous bannir vous-même !", ephemeral=True)
        return
    
    if user.id == OWNER_ID:
        await interaction.response.send_message("❌ Impossible de bannir le propriétaire du bot !", ephemeral=True)
        return
    
    if is_admin(user):
        await interaction.response.send_message("❌ Impossible de bannir un administrateur !", ephemeral=True)
        return
    
    delete_messages = max(0, min(7, delete_messages))
    
    try:
        await user.ban(reason=reason, delete_message_days=delete_messages)
        
        embed = create_embed("🔨 Utilisateur banni", f"**{user.display_name}** a été banni du serveur", 0xff6b6b)
        embed.add_field(name="👮 Modérateur", value=interaction.user.mention, inline=True)
        embed.add_field(name="📋 Raison", value=reason or "Aucune raison spécifiée", inline=True)
        embed.add_field(name="🗑️ Messages supprimés", value=f"{delete_messages} jour(s)", inline=True)
        
        await interaction.response.send_message(embed=embed)
        
        # Log l'action
        await log_action(interaction.guild, "ban", interaction.user, user, reason)
        
        logger.info(f"🔨 {interaction.user} a banni {user} - Raison: {reason}")
        
    except Exception as e:
        embed = create_embed("❌ Erreur", f"Impossible de bannir {user.display_name}: {str(e)}", 0xff0000)
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="kick", description="👢 Expulser un utilisateur")
@app_commands.describe(
    user="Utilisateur à expulser",
    reason="Raison de l'expulsion"
)
async def kick_user(interaction: discord.Interaction, user: discord.Member, reason: str = None):
    """Expulser un utilisateur"""
    
    if not is_admin(interaction.user):
        await interaction.response.send_message("❌ Vous devez être administrateur !", ephemeral=True)
        return
    
    if user.id == interaction.user.id:
        await interaction.response.send_message("❌ Vous ne pouvez pas vous expulser vous-même !", ephemeral=True)
        return
    
    if user.id == OWNER_ID:
        await interaction.response.send_message("❌ Impossible d'expulser le propriétaire du bot !", ephemeral=True)
        return
    
    if is_admin(user):
        await interaction.response.send_message("❌ Impossible d'expulser un administrateur !", ephemeral=True)
        return
    
    try:
        await user.kick(reason=reason)
        
        embed = create_embed("👢 Utilisateur expulsé", f"**{user.display_name}** a été expulsé du serveur", 0xffa726)
        embed.add_field(name="👮 Modérateur", value=interaction.user.mention, inline=True)
        embed.add_field(name="📋 Raison", value=reason or "Aucune raison spécifiée", inline=True)
        
        await interaction.response.send_message(embed=embed)
        
        # Log l'action
        await log_action(interaction.guild, "kick", interaction.user, user, reason)
        
        logger.info(f"👢 {interaction.user} a expulsé {user} - Raison: {reason}")
        
    except Exception as e:
        embed = create_embed("❌ Erreur", f"Impossible d'expulser {user.display_name}: {str(e)}", 0xff0000)
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="timeout", description="⏰ Timeout temporaire d'un utilisateur")
@app_commands.describe(
    user="Utilisateur à timeout",
    duration="Durée en minutes (1-1440)",
    reason="Raison du timeout"
)
async def timeout_user(interaction: discord.Interaction, user: discord.Member, duration: int, reason: str = None):
    """Timeout temporaire d'un utilisateur"""
    
    if not is_admin(interaction.user):
        await interaction.response.send_message("❌ Vous devez être administrateur !", ephemeral=True)
        return
    
    if user.id == interaction.user.id:
        await interaction.response.send_message("❌ Vous ne pouvez pas vous timeout vous-même !", ephemeral=True)
        return
    
    if user.id == OWNER_ID:
        await interaction.response.send_message("❌ Impossible de timeout le propriétaire du bot !", ephemeral=True)
        return
    
    if is_admin(user):
        await interaction.response.send_message("❌ Impossible de timeout un administrateur !", ephemeral=True)
        return
    
    duration = max(1, min(1440, duration))  # Entre 1 minute et 24 heures
    
    try:
        timeout_until = datetime.now() + timedelta(minutes=duration)
        await user.timeout(timeout_until, reason=reason)
        
        embed = create_embed("⏰ Utilisateur en timeout", f"**{user.display_name}** a été mis en timeout", 0xffa726)
        embed.add_field(name="👮 Modérateur", value=interaction.user.mention, inline=True)
        embed.add_field(name="⏱️ Durée", value=f"{duration} minute(s)", inline=True)
        embed.add_field(name="📋 Raison", value=reason or "Aucune raison spécifiée", inline=False)
        
        await interaction.response.send_message(embed=embed)
        
        # Log l'action
        await log_action(interaction.guild, "timeout", interaction.user, user, reason, duration*60)
        
        logger.info(f"⏰ {interaction.user} a timeout {user} pour {duration} minutes - Raison: {reason}")
        
    except Exception as e:
        embed = create_embed("❌ Erreur", f"Impossible de timeout {user.display_name}: {str(e)}", 0xff0000)
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="warn", description="⚠️ Avertir un utilisateur")
@app_commands.describe(
    user="Utilisateur à avertir",
    reason="Raison de l'avertissement"
)
async def warn_user(interaction: discord.Interaction, user: discord.Member, reason: str = None):
    """Avertir un utilisateur"""
    
    if not is_admin(interaction.user):
        await interaction.response.send_message("❌ Vous devez être administrateur !", ephemeral=True)
        return
    
    if user.id == interaction.user.id:
        await interaction.response.send_message("❌ Vous ne pouvez pas vous avertir vous-même !", ephemeral=True)
        return
    
    if user.id == OWNER_ID:
        await interaction.response.send_message("❌ Impossible d'avertir le propriétaire du bot !", ephemeral=True)
        return
    
    config = get_security_config(interaction.guild_id)
    
    # Ajouter l'avertissement
    warn_data = {
        'moderator': interaction.user.id,
        'reason': reason or "Aucune raison spécifiée",
        'timestamp': datetime.now()
    }
    
    WARNINGS[user.id].append(warn_data)
    warn_count = len(WARNINGS[user.id])
    
    embed = create_embed("⚠️ Utilisateur averti", f"**{user.display_name}** a reçu un avertissement", 0xffa726)
    embed.add_field(name="👮 Modérateur", value=interaction.user.mention, inline=True)
    embed.add_field(name="📊 Avertissements", value=f"{warn_count}/{config['max_warns']}", inline=True)
    embed.add_field(name="📋 Raison", value=reason or "Aucune raison spécifiée", inline=False)
    
    # Vérifier si l'utilisateur a atteint le maximum d'avertissements
    if warn_count >= config['max_warns']:
        try:
            timeout_until = datetime.now() + timedelta(seconds=config['timeout_duration'])
            await user.timeout(timeout_until, reason=f"Maximum d'avertissements atteint ({warn_count})")
            embed.add_field(name="🚨 Action automatique", value=f"Timeout de {config['timeout_duration']//60} minutes appliqué", inline=False)
            
            # Reset les avertissements après punition
            WARNINGS[user.id] = []
            
        except Exception as e:
            embed.add_field(name="❌ Erreur", value=f"Impossible d'appliquer le timeout automatique: {str(e)}", inline=False)
    
    await interaction.response.send_message(embed=embed)
    
    # Log l'action
    await log_action(interaction.guild, "warn", interaction.user, user, reason)
    
    logger.info(f"⚠️ {interaction.user} a averti {user} ({warn_count}/{config['max_warns']}) - Raison: {reason}")

@bot.tree.command(name="clear", description="🧹 Supprimer des messages")
@app_commands.describe(
    amount="Nombre de messages à supprimer (1-100)",
    user="Utilisateur spécifique (optionnel)"
)
async def clear_messages(interaction: discord.Interaction, amount: int, user: discord.Member = None):
    """Supprimer des messages"""
    
    if not is_admin(interaction.user):
        await interaction.response.send_message("❌ Vous devez être administrateur !", ephemeral=True)
        return
    
    if amount < 1 or amount > 100:
        await interaction.response.send_message("❌ Le nombre doit être entre 1 et 100 !", ephemeral=True)
        return
    
    # 🔥 DÉFÉRER IMMÉDIATEMENT (< 3 secondes)
    await interaction.response.defer(ephemeral=True)
    
    try:
        deleted = []
        
        if user:
            # Supprimer messages d'un utilisateur spécifique
            def check(message):
                return message.author == user
            deleted = await interaction.channel.purge(limit=amount, check=check)
        else:
            # Supprimer les X derniers messages
            deleted = await interaction.channel.purge(limit=amount)
        
        # Créer l'embed de confirmation
        embed = create_embed(
            "🧹 Messages supprimés", 
            f"**{len(deleted)} messages** supprimés avec succès !", 
            0x66bb6a
        )
        embed.add_field(name="👮 Modérateur", value=interaction.user.mention, inline=True)
        embed.add_field(name="📍 Canal", value=interaction.channel.mention, inline=True)
        if user:
            embed.add_field(name="👤 Utilisateur ciblé", value=user.mention, inline=True)
        
        # 🔥 UTILISER FOLLOWUP AU LIEU DE RESPONSE
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        # Log l'action
        target_info = f" de {user.display_name}" if user else ""
        await log_action(
            interaction.guild, 
            "clear", 
            interaction.user, 
            user or interaction.guild.me, 
            f"{len(deleted)} messages supprimés{target_info} dans {interaction.channel.name}"
        )
        
        logger.info(f"🧹 {interaction.user} a supprimé {len(deleted)} messages{target_info} dans {interaction.channel.name}")
        
    except discord.Forbidden:
        embed = create_embed("❌ Erreur de permissions", "Je n'ai pas les permissions pour supprimer les messages ici.", 0xff0000)
        await interaction.followup.send(embed=embed, ephemeral=True)
        
    except Exception as e:
        embed = create_embed("❌ Erreur", f"Une erreur est survenue: {str(e)}", 0xff0000)
        await interaction.followup.send(embed=embed, ephemeral=True)
        logger.error(f"❌ Erreur clear: {e}")


@bot.tree.command(name="message", description="📢 Envoyer un message en tant que bot")
@app_commands.describe(
    message="Le message à envoyer",
    channel="Canal où envoyer le message (optionnel)"
)
async def send_message_as_bot(interaction: discord.Interaction, message: str, channel: discord.TextChannel = None):
    """Envoyer un message en tant que bot avec division automatique"""
    
    if not is_admin(interaction.user):
        await interaction.response.send_message("❌ Vous devez être administrateur !", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    # Utiliser le canal actuel si aucun canal spécifié
    target_channel = channel or interaction.channel
    
    try:
        # Diviser le message en parties si nécessaire
        message_parts = split_long_message(message)
        
        # Envoyer chaque partie
        for i, part in enumerate(message_parts, 1):
            embed = create_embed("📢 Message du Bot", part, 0x5865f2)
            
            # Ajouter les infos seulement sur le premier embed
            if i == 1:
                embed.add_field(name="👮 Envoyé par", value=interaction.user.mention, inline=True)
                embed.add_field(name="📍 Canal", value=target_channel.mention, inline=True)
            
            # Footer avec numérotation si plusieurs parties
            if len(message_parts) > 1:
                embed.set_footer(text=f"Partie {i}/{len(message_parts)} • {datetime.now().strftime('%d/%m/%Y à %H:%M')}")
            else:
                embed.set_footer(text=f"Message envoyé le {datetime.now().strftime('%d/%m/%Y à %H:%M')}")
            
            await target_channel.send(embed=embed)
            
            # Petite pause entre les embeds pour éviter le rate limit
            if i < len(message_parts):
                await asyncio.sleep(0.5)
        
        # Confirmation à l'utilisateur
        if target_channel != interaction.channel:
            parts_text = f" en {len(message_parts)} partie(s)" if len(message_parts) > 1 else ""
            confirmation = create_embed("✅ Message envoyé", f"Message envoyé dans {target_channel.mention}{parts_text}", 0x66bb6a)
            await interaction.followup.send(embed=confirmation, ephemeral=True)
        else:
            parts_text = f" en {len(message_parts)} partie(s)" if len(message_parts) > 1 else ""
            await interaction.followup.send(f"✅ Message envoyé{parts_text} !", ephemeral=True)
        
        # Log l'action
        parts_info = f" ({len(message_parts)} parties)" if len(message_parts) > 1 else ""
        await log_action(interaction.guild, "message", interaction.user, interaction.guild.me, f"Message envoyé dans {target_channel.name}{parts_info}")
        
        logger.info(f"📢 {interaction.user} a envoyé un message bot dans {target_channel.name}: {len(message_parts)} partie(s)")
        
    except Exception as e:
        embed = create_embed("❌ Erreur", f"Impossible d'envoyer le message: {str(e)}", 0xff0000)
        await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="warns", description="📋 Voir les avertissements d'un utilisateur")
@app_commands.describe(user="Utilisateur à vérifier")
async def view_warns(interaction: discord.Interaction, user: discord.Member):
    """Voir les avertissements d'un utilisateur"""
    
    if not is_admin(interaction.user):
        await interaction.response.send_message("❌ Vous devez être administrateur !", ephemeral=True)
        return
    
    warnings = WARNINGS.get(user.id, [])
    
    if not warnings:
        embed = create_embed("📋 Avertissements", f"**{user.display_name}** n'a aucun avertissement", 0x66bb6a)
        await interaction.response.send_message(embed=embed)
        return
    
    embed = create_embed("📋 Avertissements", f"**{user.display_name}** - {len(warnings)} avertissement(s)", 0xffa726)
    
    for i, warn in enumerate(warnings[-10:], 1):  # Afficher les 10 derniers
        moderator = interaction.guild.get_member(warn['moderator'])
        moderator_name = moderator.display_name if moderator else "Modérateur inconnu"
        
        embed.add_field(
            name=f"⚠️ Avertissement {i}",
            value=f"**Modérateur:** {moderator_name}\n**Raison:** {warn['reason']}\n**Date:** {warn['timestamp'].strftime('%d/%m/%Y %H:%M')}",
            inline=False
        )
    
    if len(warnings) > 10:
        embed.add_field(name="➕", value=f"... et {len(warnings) - 10} autres", inline=False)
    
    await interaction.response.send_message(embed=embed)

# ============================
# CONFIGURATION DE SÉCURITÉ
# ============================

@bot.tree.command(name="config_security", description="🛡️ Configurer la sécurité anti-raid")
@app_commands.describe(
    setting="Paramètre à modifier",
    value="Nouvelle valeur"
)
@app_commands.choices(setting=[
    app_commands.Choice(name="🚨 Anti-raid activé", value="anti_raid_enabled"),
    app_commands.Choice(name="💬 Anti-spam activé", value="anti_spam_enabled"),
    app_commands.Choice(name="👥 Max joins/minute", value="max_joins_per_minute"),
    app_commands.Choice(name="📝 Max messages/minute", value="max_messages_per_minute"),
    app_commands.Choice(name="🔨 Auto-ban suspects", value="auto_ban_suspicious"),
    app_commands.Choice(name="⚠️ Max avertissements", value="max_warns"),
    app_commands.Choice(name="⏰ Durée timeout (min)", value="timeout_duration"),
    app_commands.Choice(name="🗑️ Supprimer spam", value="delete_spam_messages"),
    app_commands.Choice(name="👶 Seuil nouveau compte (jours)", value="new_account_threshold"),
    app_commands.Choice(name="⚖️ Type de punition", value="punishment_type")
])
async def config_security(interaction: discord.Interaction, setting: str, value: str):
    """Configurer la sécurité anti-raid"""
    
    if not is_admin(interaction.user):
        await interaction.response.send_message("❌ Vous devez être administrateur !", ephemeral=True)
        return
    
    config = get_security_config(interaction.guild_id)
    
    try:
        if setting in ["anti_raid_enabled", "anti_spam_enabled", "auto_ban_suspicious", "delete_spam_messages"]:
            config[setting] = value.lower() in ['true', '1', 'yes', 'oui', 'on']
            
        elif setting in ["max_joins_per_minute", "max_messages_per_minute", "max_warns", "new_account_threshold"]:
            config[setting] = max(1, int(value))
            
        elif setting == "timeout_duration":
            config[setting] = max(60, min(86400, int(value) * 60))  # Convert minutes to seconds
            
        elif setting == "punishment_type":
            if value.lower() in ["timeout", "kick", "ban"]:
                config[setting] = value.lower()
            else:
                await interaction.response.send_message("❌ Type de punition invalide ! Utilisez: timeout, kick, ou ban", ephemeral=True)
                return
        
        embed = create_embed("✅ Configuration mise à jour", f"**{setting}** = `{value}`", 0x66bb6a)
        embed.add_field(name="👮 Modérateur", value=interaction.user.mention, inline=True)
        
        await interaction.response.send_message(embed=embed)
        
        logger.info(f"⚙️ {interaction.user} a modifié {setting} = {value} sur {interaction.guild.name}")
        
    except ValueError:
        await interaction.response.send_message("❌ Valeur invalide ! Vérifiez le type de données requis.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur: {str(e)}", ephemeral=True)

@bot.tree.command(name="security_status", description="📊 Voir l'état de la sécurité")
async def security_status(interaction: discord.Interaction):
    """Afficher l'état de la sécurité"""
    
    if not is_admin(interaction.user):
        await interaction.response.send_message("❌ Vous devez être administrateur !", ephemeral=True)
        return
    
    config = get_security_config(interaction.guild_id)
    
    embed = create_embed("🛡️ État de la Sécurité", f"Configuration pour **{interaction.guild.name}**", 0x5865f2)
    
    # Protection anti-raid
    raid_status = "✅ Activée" if config["anti_raid_enabled"] else "❌ Désactivée"
    embed.add_field(name="🚨 Protection Anti-Raid", value=raid_status, inline=True)
    
    spam_status = "✅ Activée" if config["anti_spam_enabled"] else "❌ Désactivée"
    embed.add_field(name="💬 Protection Anti-Spam", value=spam_status, inline=True)
    
    mode_raid = "🔴 MODE RAID ACTIF" if config.get("raid_mode", False) else "🟢 Normal"
    embed.add_field(name="🚨 Mode Actuel", value=mode_raid, inline=True)
    
    # Limites
    embed.add_field(name="👥 Max joins/minute", value=str(config["max_joins_per_minute"]), inline=True)
    embed.add_field(name="📝 Max messages/minute", value=str(config["max_messages_per_minute"]), inline=True)
    embed.add_field(name="⚠️ Max avertissements", value=str(config["max_warns"]), inline=True)
    
    # Auto-actions
    auto_ban = "✅ Activé" if config["auto_ban_suspicious"] else "❌ Désactivé"
    embed.add_field(name="🔨 Auto-ban suspects", value=auto_ban, inline=True)
    
    delete_spam = "✅ Activé" if config["delete_spam_messages"] else "❌ Désactivé"
    embed.add_field(name="🗑️ Suppr. spam", value=delete_spam, inline=True)
    
    embed.add_field(name="⚖️ Type punition", value=config["punishment_type"].title(), inline=True)
    
    # Statistiques
    total_warns = sum(len(warns) for warns in WARNINGS.values())
    embed.add_field(name="📊 Avertissements total", value=str(total_warns), inline=True)
    
    recent_joins = len(JOIN_TRACKER.get(interaction.guild_id, []))
    embed.add_field(name="👥 Joins récents", value=str(recent_joins), inline=True)
    
    timeout_min = config["timeout_duration"] // 60
    embed.add_field(name="⏰ Timeout auto", value=f"{timeout_min} min", inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="set_log_channel", description="📝 Définir le salon de logs")
@app_commands.describe(channel="Salon où envoyer les logs de modération")
async def set_log_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    """Définir le salon de logs"""
    
    if not is_admin(interaction.user):
        await interaction.response.send_message("❌ Vous devez être administrateur !", ephemeral=True)
        return
    
    config = get_security_config(interaction.guild_id)
    config["log_channel_id"] = channel.id
    
    embed = create_embed("📝 Salon de logs configuré", f"Les logs seront envoyés dans {channel.mention}")
    await interaction.response.send_message(embed=embed)

# ============================
# COMMANDES SETUP SÉCURISÉES (OWNER ONLY)
# ============================

@bot.tree.command(name="setup", description="⚙️ [OWNER] Configurer le support vocal")
@app_commands.describe(enable="Activer ou désactiver le système de support")
async def setup_support(interaction: discord.Interaction, enable: bool = True):
    """Configuration du système de support vocal - OWNER ONLY"""
    
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Cette commande est réservée au propriétaire du bot !", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    guild = interaction.guild
    guild_id = guild.id
    
    if not enable:
        # Désactiver le support
        if guild_id in SUPPORT_CHANNELS:
            del SUPPORT_CHANNELS[guild_id]
            del SUPPORT_CONFIG[guild_id]
            embed = create_embed("⚙️ Support désactivé", "Système de support vocal désactivé")
            await interaction.followup.send(embed=embed)
            return
    
    try:
        # [Le reste du code setup identique à l'original]
        category = None
        for cat in guild.categories:
            if cat.name == "🎧 Support Vocal":
                category = cat
                break
        
        if not category:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=True, connect=True),
                guild.me: discord.PermissionOverwrite(view_channel=True, connect=True, manage_channels=True, move_members=True)
            }
            category = await guild.create_category("🎧 Support Vocal", overwrites=overwrites)
        
        waiting_channel_name = "⏳│Besoin d'aide"
        waiting_channel = None
        
        for channel in category.voice_channels:
            if channel.name == waiting_channel_name:
                waiting_channel = channel
                break
        
        if not waiting_channel:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=True, connect=True, speak=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, connect=True, manage_channels=True, move_members=True)
            }
            
            admin_role = None
            admin_role_id = None
            
            for role in guild.roles:
                role_name_lower = role.name.lower()
                if any(keyword in role_name_lower for keyword in ['admin', 'modér', 'staff', 'gérant', 'owner', 'fondateur']):
                    admin_role = role
                    admin_role_id = role.id
                    break
            
            if not admin_role:
                for role in guild.roles:
                    if role.permissions.administrator:
                        admin_role = role
                        admin_role_id = role.id
                        break
            
            if not admin_role_id:
                admin_role_id = guild.owner_id
                admin_role = guild.owner
            
            if admin_role and hasattr(admin_role, 'id'):
                overwrites[admin_role] = discord.PermissionOverwrite(
                    view_channel=True, connect=True, speak=True, move_members=True, manage_channels=True
                )
            
            waiting_channel = await category.create_voice_channel(waiting_channel_name, overwrites=overwrites, user_limit=0)
        
        SUPPORT_CONFIG[guild_id] = {"admin_role_id": admin_role_id, "category_id": category.id}
        SUPPORT_CHANNELS[guild_id] = {"waiting": waiting_channel.id, "active": []}
        
        embed = create_embed("✅ Système de Support Configuré", "Support vocal automatique activé avec succès !")
        embed.add_field(name="⏳ Channel d'attente", value=f"{waiting_channel.mention}", inline=True)
        embed.add_field(name="🏷️ Catégorie", value=f"{category.name}", inline=True)
        
        if admin_role and hasattr(admin_role, 'mention'):
            embed.add_field(name="👑 Rôle Admin détecté", value=f"{admin_role.mention}", inline=True)
        elif admin_role_id:
            embed.add_field(name="👑 Admin", value=f"<@{admin_role_id}>", inline=True)
        
        await interaction.followup.send(embed=embed)
        logger.info(f"✅ Support configuré pour {guild.name} par OWNER")
        
    except Exception as e:
        logger.error(f"❌ Erreur setup: {e}")
        embed = create_embed("❌ Erreur Configuration", f"Impossible de configurer le support:\n`{str(e)}`", 0xff0000)
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="setup_temp_vocal", description="🎤 [OWNER] Configurer les salons temporaires")
@app_commands.describe(enable="Activer ou désactiver le système de salons temporaires")
async def setup_temp_vocal(interaction: discord.Interaction, enable: bool = True):
    """Configuration des salons vocaux temporaires - OWNER ONLY"""
    
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Cette commande est réservée au propriétaire du bot !", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    guild = interaction.guild
    guild_id = guild.id
    
    if not enable:
        if guild_id in TEMP_VOCAL_CONFIG:
            del TEMP_VOCAL_CONFIG[guild_id]
            if guild_id in TEMP_VOCAL_CHANNELS:
                del TEMP_VOCAL_CHANNELS[guild_id]
            embed = create_embed("🎤 Salons temporaires désactivés", "Système désactivé")
            await interaction.followup.send(embed=embed)
            return
    
    try:
        # [Reste du code setup_temp_vocal identique]
        category = None
        for cat in guild.categories:
            if "vocal" in cat.name.lower():
                category = cat
                break
        
        if not category:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=True, connect=True),
                guild.me: discord.PermissionOverwrite(view_channel=True, connect=True, manage_channels=True, move_members=True)
            }
            category = await guild.create_category("🎤 Salons Vocaux", overwrites=overwrites)
        
        create_channel_name = "➕│Créer un salon vocal"
        create_channel = None
        
        for channel in category.voice_channels:
            if "créer" in channel.name.lower() and "salon" in channel.name.lower():
                create_channel = channel
                break
        
        if not create_channel:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=True, connect=True, speak=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, connect=True, manage_channels=True, move_members=True)
            }
            
            create_channel = await category.create_voice_channel(
                create_channel_name, 
                overwrites=overwrites, 
                user_limit=1
            )
        
        TEMP_VOCAL_CONFIG[guild_id] = {
            "category_id": category.id,
            "create_channel_id": create_channel.id
        }
        
        if guild_id not in TEMP_VOCAL_CHANNELS:
            TEMP_VOCAL_CHANNELS[guild_id] = []
        
        embed = create_embed("✅ Salons Vocaux Temporaires Configurés", "Système activé avec succès !")
        embed.add_field(name="➕ Channel de création", value=f"{create_channel.mention}", inline=True)
        embed.add_field(name="🏷️ Catégorie", value=f"{category.name}", inline=True)
        
        await interaction.followup.send(embed=embed)
        logger.info(f"✅ Salons temporaires configurés pour {guild.name} par OWNER")
        
    except Exception as e:
        logger.error(f"❌ Erreur setup salons temporaires: {e}")
        embed = create_embed("❌ Erreur Configuration", f"Erreur: {str(e)}", 0xff0000)
        await interaction.followup.send(embed=embed)

# ============================
# AIDE MISE À JOUR
# ============================

@bot.tree.command(name="help", description="❓ Aide complète")
async def help_command(interaction: discord.Interaction):
    """Affiche l'aide complète du bot"""
    
    embed = create_embed("🎵 Bot Musical Direct Pro + Modération Anti-Raid", "Système complet de musique, modération et support vocal")
    
    embed.add_field(
        name="🎶 Commandes Musicales",
        value=(
            "`/play <chanson>` - YouTube avec 8 méthodes d'extraction\n"
            "`/spotify <chanson/lien>` - Spotify → YouTube\n"
            "`/soundcloud <chanson/lien>` - SoundCloud direct\n"
            "`/radio` - Lancer une radio en continu\n"
            "`/queue` - Voir la liste d'attente\n"
            "`/skip` - Passer à la chanson suivante\n"
            "`/stop` - Arrêter et vider la queue\n"
            "`/disconnect` - Déconnecter le bot"
        ),
        inline=False
    )
    
    embed.add_field(
        name="⚖️ Commandes de Modération",
        value=(
            "`/ban <user> [raison]` - Bannir un utilisateur\n"
            "`/kick <user> [raison]` - Expulser un utilisateur\n"
            "`/timeout <user> <durée> [raison]` - Timeout temporaire\n"
            "`/warn <user> [raison]` - Avertir un utilisateur\n"
            "`/warns <user>` - Voir les avertissements\n"
            "`/clear <nombre> [user]` - Supprimer des messages"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🛡️ Système Anti-Raid",
        value=(
            "`/config_security` - Configurer la protection\n"
            "`/security_status` - Voir l'état de la sécurité\n\n"
            "**Protection automatique :**\n"
            "• Détection de raids (joins massifs)\n"
            "• Anti-spam intelligent\n"
            "• Auto-ban des comptes suspects\n"
            "• Logs détaillés des actions"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🎧 Support Vocal Automatique",
        value=(
            "**Fonctionnalités automatiques :**\n"
            "• Channel d'attente → Channels privés\n"
            "• Détection automatique des admins\n"
            "• Gestion des permissions\n"
            "• Nettoyage automatique des channels vides"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🎤 Salons Vocaux Temporaires",
        value=(
            "`/temp_vocal_list` - Voir les salons actifs\n\n"
            "**Fonctionnalités automatiques :**\n"
            "• Channel de création → Salons personnalisés\n"
            "• Permissions de gestion pour le créateur\n"
            "• Suppression automatique quand vide\n"
            "• Format: 🎤 [Nom utilisateur]"
        ),
        inline=False
    )
    
    embed.add_field(
        name="📊 Informations",
        value=(
            "`/stats` - Statistiques d'extraction\n"
            "`/help` - Cette aide\n\n"
            f"**Version :** 2025-07-01 avec Anti-Raid\n"
            f"**Développeur :** Mada\n"
            f"**Serveurs :** {len(bot.guilds)}"
        ),
        inline=False
    )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="stats", description="📊 Statistiques complètes du bot")
async def stats(interaction: discord.Interaction):
    """Affiche les statistiques complètes"""
    
    total = EXTRACTION_STATS["success"] + EXTRACTION_STATS["failed"]
    success_rate = (EXTRACTION_STATS["success"] / total * 100) if total > 0 else 0
    
    embed = create_embed("📊 Statistiques Bot Complet", f"Depuis le démarrage - {datetime.now().strftime('%H:%M:%S')}")
    
    # Stats musicales
    embed.add_field(name="✅ Extractions réussies", value=str(EXTRACTION_STATS["success"]), inline=True)
    embed.add_field(name="❌ Extractions échouées", value=str(EXTRACTION_STATS["failed"]), inline=True)
    embed.add_field(name="📈 Taux de réussite", value=f"{success_rate:.1f}%", inline=True)
    
    embed.add_field(name="🎥 YouTube", value=str(EXTRACTION_STATS["youtube"]), inline=True)
    embed.add_field(name="🔊 SoundCloud", value=str(EXTRACTION_STATS["soundcloud"]), inline=True)
    embed.add_field(name="🎧 Spotify", value=str(EXTRACTION_STATS["spotify"]), inline=True)
    
    # Stats modération
    total_warns = sum(len(warns) for warns in WARNINGS.values())
    guilds_with_security = len([g for g in SECURITY_CONFIG.values() if g.get("enabled", True)])
    
    embed.add_field(name="⚠️ Avertissements total", value=str(total_warns), inline=True)
    embed.add_field(name="🛡️ Serveurs protégés", value=str(guilds_with_security), inline=True)
    embed.add_field(name="🚨 Modes raid actifs", value=str(len([c for c in SECURITY_CONFIG.values() if c.get("raid_mode", False)])), inline=True)
    
    # Stats salons
    total_temp_channels = sum(len(channels) for channels in TEMP_VOCAL_CHANNELS.values())
    embed.add_field(name="🎤 Salons temporaires actifs", value=str(total_temp_channels), inline=True)
    embed.add_field(name="🏠 Serveurs avec salons temp", value=str(len(TEMP_VOCAL_CONFIG)), inline=True)
    embed.add_field(name="🎧 Serveurs avec support", value=str(len(SUPPORT_CHANNELS)), inline=True)
    
    embed.add_field(name="🔥 Technologie", value="yt-dlp direct (8 méthodes)\nFFmpeg optimisé\n5 radios fallback\nAnti-raid avancé", inline=False)
    embed.add_field(name="🎯 Fonctionnalités", value="Musique + Modération + Support + Salons + Anti-Raid", inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="temp_vocal_list", description="📋 Voir les salons vocaux temporaires actifs")
async def temp_vocal_list(interaction: discord.Interaction):
    """Liste les salons vocaux temporaires actifs"""
    
    guild_id = interaction.guild_id
    
    if guild_id not in TEMP_VOCAL_CHANNELS or not TEMP_VOCAL_CHANNELS[guild_id]:
        embed = create_embed("📋 Aucun salon temporaire", "Aucun salon vocal temporaire actuel")
        await interaction.response.send_message(embed=embed)
        return
    
    embed = create_embed("📋 Salons Vocaux Temporaires", f"{len(TEMP_VOCAL_CHANNELS[guild_id])} salon(s) actif(s)")
    
    for i, channel_info in enumerate(TEMP_VOCAL_CHANNELS[guild_id][:10], 1):
        channel = bot.get_channel(channel_info['channel_id'])
        if channel:
            creator = bot.get_user(channel_info['creator_id'])
            creator_name = creator.display_name if creator else "Utilisateur inconnu"
            member_count = len(channel.members)
            created_time = channel_info['created_at'].strftime("%H:%M")
            
            embed.add_field(
                name=f"🎤 {channel.name}",
                value=f"👤 Créateur: {creator_name}\n👥 Membres: {member_count}\n🕐 Créé: {created_time}",
                inline=True
            )
    
    if len(TEMP_VOCAL_CHANNELS[guild_id]) > 10:
        embed.add_field(name="➕", value=f"... et {len(TEMP_VOCAL_CHANNELS[guild_id]) - 10} autres", inline=False)
    
    await interaction.response.send_message(embed=embed)

# Commande de debug réservée au propriétaire
@bot.tree.command(name="debug", description="🔧 [OWNER] Debug système")
async def debug_command(interaction: discord.Interaction):
    """Commande de debug pour le propriétaire"""
    
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Réservé au propriétaire", ephemeral=True)
        return
    
    commands_list = []
    for cmd in bot.tree.get_commands():
        commands_list.append(f"• `/{cmd.name}` - {cmd.description}")
    
    embed = create_embed("🔧 Debug - Informations Système", f"État du bot à {datetime.now().strftime('%H:%M:%S')}")
    
    embed.add_field(name="📋 Commandes synchronisées", value=f"{len(commands_list)} commandes", inline=True)
    embed.add_field(name="🏠 Serveurs", value=str(len(bot.guilds)), inline=True)
    embed.add_field(name="👤 Développeur", value="Mada", inline=True)
    
    embed.add_field(name="📊 Stats extraction", value=f"Succès: {EXTRACTION_STATS['success']}\nÉchecs: {EXTRACTION_STATS['failed']}", inline=True)
    embed.add_field(name="🛡️ Sécurité active", value=str(len(SECURITY_CONFIG)), inline=True)
    embed.add_field(name="🎵 Queues actives", value=str(len(SONG_QUEUES)), inline=True)
    
    total_temp_channels = sum(len(channels) for channels in TEMP_VOCAL_CHANNELS.values())
    embed.add_field(name="🎤 Salons temp actifs", value=str(total_temp_channels), inline=True)
    embed.add_field(name="🎧 Support actif", value=str(len(SUPPORT_CHANNELS)), inline=True)
    embed.add_field(name="🎯 Intents", value="✅ Tous configurés", inline=True)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="sync", description="🔄 [OWNER] Forcer la synchronisation des commandes")
async def force_sync(interaction: discord.Interaction):
    """Forcer la synchronisation des commandes slash"""
    
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Réservé au propriétaire du bot !", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        # Synchronisation forcée
        synced = await bot.tree.sync()
        
        embed = create_embed("🔄 Synchronisation Forcée", f"**{len(synced)} commandes** synchronisées avec succès !", 0x66bb6a)
        
        # Lister les commandes synchronisées
        commands_list = []
        for cmd in synced:
            commands_list.append(f"• `/{cmd.name}` - {cmd.description[:50]}{'...' if len(cmd.description) > 50 else ''}")
        
        # Diviser en chunks si trop de commandes
        if len(commands_list) <= 10:
            embed.add_field(name="📋 Commandes synchronisées", value="\n".join(commands_list), inline=False)
        else:
            embed.add_field(name="📋 Premières commandes", value="\n".join(commands_list[:10]), inline=False)
            embed.add_field(name="➕ Et plus...", value=f"{len(commands_list) - 10} autres commandes", inline=False)
        
        embed.add_field(name="⏰ Synchronisé le", value=f"<t:{int(datetime.now().timestamp())}:F>", inline=False)
        embed.add_field(name="💡 Info", value="Les commandes peuvent prendre jusqu'à 1 heure pour apparaître sur tous les serveurs.", inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        logger.info(f"🔄 {interaction.user} a forcé la synchronisation: {len(synced)} commandes")
        
    except Exception as e:
        embed = create_embed("❌ Erreur Synchronisation", f"Erreur lors de la synchronisation:\n```{str(e)}```", 0xff0000)
        await interaction.followup.send(embed=embed, ephemeral=True)
        logger.error(f"❌ Erreur sync forcée: {e}")

# ============================
# LANCEMENT
# ============================

if __name__ == "__main__":
    print("🚀 Démarrage du BOT COMPLET AVEC MODÉRATION ET ANTI-RAID...")
    print("🔥 Technologie: yt-dlp direct (8 méthodes robustes)")
    print("🎯 Sources: YouTube + SoundCloud + Spotify + 5 Radios")
    print("🛡️ Modération: Ban/Kick/Timeout/Warn/Clear avec logs")
    print("🚨 Anti-Raid: Protection automatique intelligente")
    print("🎧 Support vocal: Système automatique intelligent")
    print("🎤 Salons temporaires: Création automatique personnalisée")
    print("📻 Fallback: Radio garantie si extraction échoue")
    print("🎵 Queue: Gestion intelligente avec retry automatique")
    print("👤 Développé pour: Mada")
    print("📅 Version: 2025-07-01 14:15:21 UTC - ÉDITION COMPLÈTE")
    print("🔐 Sécurité: Commandes setup réservées au propriétaire")
    
    try:
        bot.run(BOT_TOKEN)
    except Exception as e:
        logger.error(f"❌ Erreur critique: {e}")
        print("💡 Vérifiez que DISCORD_TOKEN est correct dans le fichier .env")
