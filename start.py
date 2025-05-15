import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from commands_slash import setup_commands
from keep_alive import keep_alive

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

OWNER_ID = 804607777410514944

@bot.command(name="arretetoi", hidden=True)
async def shutdown(ctx):
    if ctx.author.id == OWNER_ID:
        await ctx.send("🔌 Je m'éteins... à bientôt.")
        await bot.close()
    else:
        await ctx.send("❌ Tu n'as pas la permission d'exécuter cette commande.")


@bot.event
async def on_ready():
    await bot.wait_until_ready()
    try:
        synced = await bot.tree.sync()
        print(f"{len(synced)} slash commands synchronisées.")
    except Exception as e:
        print(f"Erreur sync: {e}")
    await bot.change_presence(activity=discord.Game(name="musique avec /play 🎶"))
    print(f"{bot.user} est prêt.")

setup_commands(bot)
keep_alive()
bot.run(os.getenv("DISCORD_TOKEN"))
