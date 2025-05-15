import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp as youtube_dl
import asyncio
from typing import Dict, List

ytdl_format_options = {
    "format": "251/bestaudio",
    "quiet": True,
    "no_warnings": True,
    "default_search": "auto",
    "source_address": "0.0.0.0",
    "noplaylist": True,
}

ffmpeg_options = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn -loglevel quiet",
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

queues: Dict[int, List[str]] = {}

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get("title")

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        except Exception:
            raise Exception("❌ Impossible de lire cette vidéo (peut-être privée, supprimée ou bloquée).")

        if "entries" in data:
            data = data["entries"][0]

        filename = data["url"] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

async def play_next(guild: discord.Guild, bot: commands.Bot):
    vc = guild.voice_client
    if guild.id in queues and queues[guild.id]:
        next_url = queues[guild.id].pop(0)
        try:
            player = await YTDLSource.from_url(next_url, loop=bot.loop, stream=True)
        except Exception as e:
            print(e)
            return

        def after_playing(error):
            fut = asyncio.run_coroutine_threadsafe(play_next(guild, bot), bot.loop)
            try:
                fut.result()
            except:
                pass

        vc.play(player, after=after_playing)

class MusicControls(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=None)
        self.guild = guild

    @discord.ui.button(label="⏸️ Pause", style=discord.ButtonStyle.grey)
    async def pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸️ Musique mise en pause.", ephemeral=True)

    @discord.ui.button(label="▶️ Reprendre", style=discord.ButtonStyle.grey)
    async def resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.guild.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️ Lecture reprise.", ephemeral=True)

    @discord.ui.button(label="⏭️ Skip", style=discord.ButtonStyle.grey)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await interaction.response.send_message("⏭️ Morceau sauté.", ephemeral=True)

def setup_commands(bot: commands.Bot):

    @bot.tree.command(name="join", description="Joindre un canal vocal")
    async def join(interaction: discord.Interaction):
        if interaction.user.voice:
            channel = interaction.user.voice.channel
            await channel.connect()
            await interaction.response.send_message("Connecté au canal vocal.")
        else:
            await interaction.response.send_message("Tu dois être dans un canal vocal.")

    @bot.tree.command(name="play", description="Jouer une musique")
    @app_commands.describe(url="Lien vers la vidéo YouTube")
    async def play(interaction: discord.Interaction, url: str):
        await interaction.response.defer()  # ✅ Appelé dès le début

        guild_id = interaction.guild.id
        if guild_id not in queues:
            queues[guild_id] = []

        if not interaction.guild.voice_client:
            if interaction.user.voice:
                await interaction.user.voice.channel.connect()
            else:
                await interaction.followup.send("❗ Tu dois être dans un canal vocal.")
                return

        vc = interaction.guild.voice_client
        queues[guild_id].append(url)

        try:
            if not vc.is_playing() and not vc.is_paused():
                await play_next(interaction.guild, bot)
                await interaction.followup.send(
                    f"🎵 Lecture commencée avec : {url}", view=MusicControls(interaction.guild)
                )
            else:
                await interaction.followup.send(f"🔗 Ajouté à la queue : {url}")
        except Exception as e:
            await interaction.followup.send(str(e))

    @bot.tree.command(name="queue", description="Afficher la file d'attente")
    async def queue(interaction: discord.Interaction):
        q = queues.get(interaction.guild.id, [])
        if not q:
            await interaction.response.send_message("La file est vide.")
        else:
            msg = "\n".join([f"{i+1}. {url}" for i, url in enumerate(q)])
            await interaction.response.send_message(f"🎶 File d'attente :\n{msg}")

    @bot.tree.command(name="leave", description="Quitter le vocal")
    async def leave(interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc:
            await vc.disconnect()
            queues.pop(interaction.guild.id, None)
            await interaction.response.send_message("Déconnecté.")
        else:
            await interaction.response.send_message("Je ne suis pas connecté à un canal vocal.")
