import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from collections import deque
import asyncio
import logging
import subprocess
from datetime import datetime
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

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ============================
# SPOTIFY API
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
# YT-DLP DIRECT - MÉTHODES ROBUSTES
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
# LECTURE AUDIO DIRECTE
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
# SYSTÈME DE SUPPORT COMPLET
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
# SYSTÈME DE SALONS VOCAUX TEMPORAIRES
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
    embed.set_footer(text="🎵 Bot Musical Direct Pro + Salons Vocaux - 2025-06-30")
    return embed

# ============================
# ÉVÉNEMENTS DISCORD
# ============================

@bot.event
async def on_ready():
    try:
        print("🔄 Synchronisation FORCÉE des commandes...")
        
        # Synchronisation simple sans clear_commands()
        synced = await bot.tree.sync()
        
        logger.info(f"🔄 {len(synced)} slash command(s) synchronisée(s) avec FORCE")
        
        # Lister toutes les commandes synchronisées
        print("📋 Commandes disponibles :")
        for cmd in synced:
            print(f"  ✅ /{cmd.name} - {cmd.description}")
        
    except Exception as e:
        logger.error(f"❌ Erreur synchronisation: {e}")
    
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
        activity=discord.Activity(type=discord.ActivityType.listening, name="/play - Musique + Salons vocaux !")
    )
    
    print("=" * 80)
    print(f"🎵 BOT MUSICAL DIRECT COMPLET + SALONS VOCAUX PRÊT !")
    print(f"👤 Connecté: {bot.user.name}")
    print(f"🏠 Serveurs: {len(bot.guilds)}")
    print(f"🎧 Spotify API: {'✅ Configurée' if spotify_client else '⚠️ Non configurée'}")
    print(f"🔥 yt-dlp: ✅ 8 méthodes d'extraction robustes")
    print(f"🎯 Sources: YouTube direct + SoundCloud + Spotify→YouTube")
    print(f"🎧 Support: Système vocal automatique")
    print(f"🎤 Salons vocaux: Création automatique temporaire")
    print(f"📻 Radio: 5 stations de fallback")
    print(f"📋 Commandes: /play, /spotify, /soundcloud, /queue, /skip, /setup, /setup_temp_vocal, /help")
    print("=" * 80)

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
# COMMANDES SLASH MUSICALES
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

@bot.tree.command(name="stats", description="📊 Statistiques du bot")
async def stats(interaction: discord.Interaction):
    """Affiche les statistiques"""
    
    total = EXTRACTION_STATS["success"] + EXTRACTION_STATS["failed"]
    success_rate = (EXTRACTION_STATS["success"] / total * 100) if total > 0 else 0
    
    embed = create_embed("📊 Statistiques Bot Musical Direct", f"Depuis le démarrage - {datetime.now().strftime('%H:%M:%S')}")
    
    embed.add_field(name="✅ Succès", value=str(EXTRACTION_STATS["success"]), inline=True)
    embed.add_field(name="❌ Échecs", value=str(EXTRACTION_STATS["failed"]), inline=True)
    embed.add_field(name="📈 Taux de réussite", value=f"{success_rate:.1f}%", inline=True)
    
    embed.add_field(name="🎥 YouTube", value=str(EXTRACTION_STATS["youtube"]), inline=True)
    embed.add_field(name="🔊 SoundCloud", value=str(EXTRACTION_STATS["soundcloud"]), inline=True)
    embed.add_field(name="🎧 Spotify", value=str(EXTRACTION_STATS["spotify"]), inline=True)
    
    # Statistiques des salons vocaux temporaires
    total_temp_channels = sum(len(channels) for channels in TEMP_VOCAL_CHANNELS.values())
    embed.add_field(name="🎤 Salons temporaires actifs", value=str(total_temp_channels), inline=True)
    embed.add_field(name="🏠 Serveurs avec salons temp", value=str(len(TEMP_VOCAL_CONFIG)), inline=True)
    embed.add_field(name="🎧 Serveurs avec support", value=str(len(SUPPORT_CHANNELS)), inline=True)
    
    embed.add_field(name="🔥 Technologie", value="yt-dlp direct (8 méthodes)\nFFmpeg optimisé\n5 radios fallback\nSalons vocaux automatiques", inline=False)
    embed.add_field(name="🎯 Sources", value="YouTube + SoundCloud + Spotify→YouTube + Radio", inline=False)
    
    # Informations système
    embed.add_field(name="🖥️ Système", value=f"Serveurs: {len(bot.guilds)}\nUtilisateur: adam-KUROPATWA-BUTTE", inline=False)
    
    await interaction.response.send_message(embed=embed)

# ============================
# COMMANDES SETUP AMÉLIORÉES
# ============================

@bot.tree.command(name="setup", description="⚙️ Configurer le support vocal automatique")
@app_commands.describe(enable="Activer ou désactiver le système de support")
async def setup_support(interaction: discord.Interaction, enable: bool = True):
    """Configuration du système de support vocal"""
    
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Vous devez être administrateur !", ephemeral=True)
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
        # Rechercher ou créer la catégorie de support
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
        
        # Rechercher ou créer le channel d'attente
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
            
            # Chercher le rôle admin automatiquement
            admin_role = None
            admin_role_id = None
            
            # Essayer de trouver un rôle admin par nom
            for role in guild.roles:
                role_name_lower = role.name.lower()
                if any(keyword in role_name_lower for keyword in ['admin', 'modér', 'staff', 'gérant', 'owner', 'fondateur']):
                    admin_role = role
                    admin_role_id = role.id
                    break
            
            # Si pas trouvé par nom, chercher par permissions
            if not admin_role:
                for role in guild.roles:
                    if role.permissions.administrator:
                        admin_role = role
                        admin_role_id = role.id
                        break
            
            # Dernier recours : propriétaire du serveur
            if not admin_role_id:
                admin_role_id = guild.owner_id
                admin_role = guild.owner
            
            # Ajouter les permissions pour les admins
            if admin_role and hasattr(admin_role, 'id'):
                overwrites[admin_role] = discord.PermissionOverwrite(
                    view_channel=True, connect=True, speak=True, move_members=True, manage_channels=True
                )
            
            waiting_channel = await category.create_voice_channel(waiting_channel_name, overwrites=overwrites, user_limit=0)
        
        # Configurer le système
        SUPPORT_CONFIG[guild_id] = {"admin_role_id": admin_role_id, "category_id": category.id}
        SUPPORT_CHANNELS[guild_id] = {"waiting": waiting_channel.id, "active": []}
        
        # Message de confirmation détaillé
        embed = create_embed("✅ Système de Support Configuré", "Support vocal automatique activé avec succès !")
        embed.add_field(name="⏳ Channel d'attente", value=f"{waiting_channel.mention}", inline=True)
        embed.add_field(name="🏷️ Catégorie", value=f"{category.name}", inline=True)
        
        if admin_role and hasattr(admin_role, 'mention'):
            embed.add_field(name="👑 Rôle Admin détecté", value=f"{admin_role.mention}", inline=True)
        elif admin_role_id:
            embed.add_field(name="👑 Admin", value=f"<@{admin_role_id}>", inline=True)
        
        embed.add_field(
            name="🔧 Fonctionnement",
            value=(
                "• **Étape 1 :** Les utilisateurs rejoignent le channel d'attente\n"
                "• **Étape 2 :** Ils sont automatiquement déplacés vers un channel privé\n"
                "• **Étape 3 :** Les admins peuvent les rejoindre pour aider\n"
                "• **Étape 4 :** Les channels vides sont supprimés automatiquement"
            ),
            inline=False
        )
        
        await interaction.followup.send(embed=embed)
        
        logger.info(f"✅ Support configuré pour {guild.name} (ID: {guild_id}) avec admin: {admin_role_id}")
        
    except Exception as e:
        logger.error(f"❌ Erreur setup: {e}")
        embed = create_embed("❌ Erreur Configuration", f"Impossible de configurer le support:\n`{str(e)}`", 0xff0000)
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="setup_temp_vocal", description="🎤 Configurer les salons vocaux temporaires")
@app_commands.describe(enable="Activer ou désactiver le système de salons temporaires")
async def setup_temp_vocal(interaction: discord.Interaction, enable: bool = True):
    """Configuration du système de salons vocaux temporaires"""
    
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Vous devez être administrateur !", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    guild = interaction.guild
    guild_id = guild.id
    
    if not enable:
        # Désactiver les salons temporaires
        if guild_id in TEMP_VOCAL_CONFIG:
            del TEMP_VOCAL_CONFIG[guild_id]
            if guild_id in TEMP_VOCAL_CHANNELS:
                del TEMP_VOCAL_CHANNELS[guild_id]
            embed = create_embed("🎤 Salons temporaires désactivés", "Système de salons vocaux temporaires désactivé")
            await interaction.followup.send(embed=embed)
            return
    
    try:
        # Rechercher ou créer la catégorie vocale
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
        
        # Rechercher ou créer le channel "Créer un salon vocal"
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
                user_limit=1  # Limite à 1 pour éviter l'encombrement
            )
        
        # Configurer le système
        TEMP_VOCAL_CONFIG[guild_id] = {
            "category_id": category.id,
            "create_channel_id": create_channel.id
        }
        
        if guild_id not in TEMP_VOCAL_CHANNELS:
            TEMP_VOCAL_CHANNELS[guild_id] = []
        
        # Message de confirmation détaillé
        embed = create_embed("✅ Salons Vocaux Temporaires Configurés", "Système de création automatique activé avec succès !")
        embed.add_field(name="➕ Channel de création", value=f"{create_channel.mention}", inline=True)
        embed.add_field(name="🏷️ Catégorie", value=f"{category.name}", inline=True)
        embed.add_field(name="🎤 Format des salons", value="🎤 [Nom utilisateur]", inline=True)
        
        embed.add_field(
            name="🔧 Fonctionnement",
            value=(
                "• **Étape 1 :** Rejoignez le channel de création\n"
                "• **Étape 2 :** Un salon personnel est créé automatiquement\n"
                "• **Étape 3 :** Vous êtes déplacé vers votre salon\n"
                "• **Étape 4 :** Le salon est supprimé quand il devient vide"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🎯 Avantages",
            value=(
                "• Salons personnalisés avec votre nom\n"
                "• Permissions de gestion pour le créateur\n"
                "• Nettoyage automatique\n"
                "• Limite de 10 utilisateurs par salon"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🛠️ Permissions du créateur",
            value=(
                "• Gérer le salon\n"
                "• Déplacer les membres\n"
                "• Modifier les paramètres\n"
                "• Contrôler l'accès"
            ),
            inline=False
        )
        
        await interaction.followup.send(embed=embed)
        
        logger.info(f"✅ Salons vocaux temporaires configurés pour {guild.name} (ID: {guild_id})")
        
    except Exception as e:
        logger.error(f"❌ Erreur setup salons temporaires: {e}")
        embed = create_embed("❌ Erreur Configuration", f"Impossible de configurer les salons temporaires:\n`{str(e)}`", 0xff0000)
        embed.add_field(
            name="🔧 Solutions possibles",
            value=(
                "• Vérifiez que le bot a les permissions `Gérer les channels`\n"
                "• Vérifiez que le bot a les permissions `Déplacer les membres`\n"
                "• Réessayez dans quelques secondes"
            ),
            inline=False
        )
        await interaction.followup.send(embed=embed)

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
        
