import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import os
import logging
from collections import deque
import asyncio
import os

# Verificação de Opus
if not discord.opus.is_loaded():
    try:
        discord.opus.load_opus('libopus.so')  # Tentar carregar o Opus
    except Exception as e:
        logging.warning(f'Opus não foi carregado automaticamente. Erro: {e}')

TOKEN = os.getenv("DISCORD_TOKEN")

# Definir intents
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

# Prefixo de comando alterado para "/"
bot = commands.Bot(command_prefix='/', intents=intents)

# Configurações do yt-dlp com cookies
ytdl_format_options = {
    'format': 'bestaudio/best',
    'noplaylist': 'True',
    'default_search': 'ytsearch',
    'cookiefile': '/home/ubuntu/Bot-do-Jotaene/cookies.txt',  # Adicionando o arquivo de cookies
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

# Configuração de fila de reprodução
song_queue = deque()

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data['title']

    @classmethod
    async def from_url(cls, url, *, loop=None):
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))

        if 'entries' in data:
            data = data['entries'][0]  # Se for uma playlist, pegar o primeiro vídeo

        filename = data['url']
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

# Evento quando o bot está pronto
@bot.event
async def on_ready():
    print(f'{bot.user} está online e conectado ao Gateway!')
    logging.info(f'{bot.user} foi iniciado com sucesso.')

# Evento de quando um novo membro entra no servidor
@bot.event
async def on_member_join(member):
    nome_do_cargo = "🐒 Australopithecus"
    guild = member.guild
    role = discord.utils.get(guild.roles, name=nome_do_cargo)

    if role:
        try:
            await member.add_roles(role)
            logging.info(f"Cargo '{role.name}' adicionado a {member.name}.")
        except discord.Forbidden:
            logging.error(f"Permissões insuficientes para adicionar o cargo '{role.name}' ao {member.name}.")
        except Exception as e:
            logging.error(f"Erro ao adicionar o cargo '{role.name}' ao membro {member.name}: {e}")
    else:
        logging.error(f"Erro: O cargo '{nome_do_cargo}' não foi encontrado.")

# Função para tocar a próxima música na fila
async def play_next(ctx):
    if song_queue:
        next_song = song_queue.popleft()  # Retira a próxima música da fila
        player = await YTDLSource.from_url(next_song, loop=bot.loop)
        ctx.voice_client.play(player, after=lambda e: bot.loop.create_task(play_next(ctx)))
        await ctx.send(f'Tocando agora: {player.title}')
        logging.info(f'Tocando a próxima música: {player.title}')
    else:
        await ctx.send("A fila de músicas acabou.")
        logging.info('Fila de músicas vazia.')

# Comandos de música
@bot.command()
async def play(ctx, *, query):
    """Adiciona uma música à fila e começa a tocar se não houver música tocando."""
    if ctx.voice_client is None:
        if ctx.author.voice:
            channel = ctx.author.voice.channel
            await channel.connect()  # Faz o bot entrar no canal de voz
            logging.info(f"{ctx.author.name} solicitou que o bot entrasse no canal: {channel.name}")
        else:
            await ctx.send("Você precisa estar em um canal de voz para tocar músicas.")
            return

    try:
        # Busca a música usando o executor padrão de asyncio
        results = await bot.loop.run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch:{query}", download=False))

        if not results or 'entries' not in results:
            await ctx.send("Nenhuma música encontrada.")
            return

        # Exibe as opções para o usuário
        options = results['entries'][:5]  # Limite a 5 resultados
        if len(options) == 1:
            # Se só uma música for encontrada, tocamos diretamente
            song_url = options[0]['url']
            song_queue.append(song_url)
            await ctx.send(f'Tocando agora: {options[0]["title"]}')
        else:
            embed = discord.Embed(title="Escolha uma música", description="Digite o número da música que deseja tocar:")
            for i, entry in enumerate(options):
                embed.add_field(name=f"{i + 1}: {entry['title']}", value=f"Link: {entry['webpage_url']}", inline=False)
                embed.set_thumbnail(url=entry['thumbnail'])  # Mostra a imagem da música

            await ctx.send(embed=embed)

            # Função para verificar a escolha do usuário
            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel

            msg = await bot.wait_for('message', timeout=30.0, check=check)

            index = int(msg.content) - 1
            if index < 0 or index >= len(options):
                await ctx.send("Número inválido.")
                return

            # Pega a música escolhida
            song_url = options[index]['url']
            song_queue.append(song_url)
            await ctx.send(f'Música adicionada à fila: {options[index]["title"]}')

        if not ctx.voice_client.is_playing():
            await play_next(ctx)

    except Exception as e:
        await ctx.send(f"Ocorreu um erro: {str(e)}")
        logging.error(f"Erro ao buscar ou tocar a música: {str(e)}")

@bot.command()
async def skip(ctx):
    """Pula a música atual."""
    if ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("Música pulada.")
        logging.info('Música atual foi pulada.')
    else:
        await ctx.send("Nenhuma música está tocando no momento.")

@bot.command()
async def queue(ctx):
    """Mostra as músicas na fila."""
    if song_queue:
        await ctx.send("Músicas na fila:\n" + "\n".join(song_queue))
    else:
        await ctx.send("A fila está vazia.")
    logging.info(f"Fila exibida: {list(song_queue)}")

@bot.command()
async def nowplaying(ctx):
    """Exibe a música que está tocando no momento."""
    if ctx.voice_client and ctx.voice_client.is_playing():
        await ctx.send(f"Tocando agora: {ctx.voice_client.source.title}")
    else:
        await ctx.send("Nenhuma música está tocando no momento.")
    logging.info(f"Tocando agora: {ctx.voice_client.source.title if ctx.voice_client else 'Nenhuma'}")

@bot.command()
async def leave(ctx):
    """Faz o bot sair do canal de voz."""
    if ctx.voice_client:
        await ctx.guild.voice_client.disconnect()
        await ctx.send("Saí do canal de voz.")
    else:
        await ctx.send("Não estou em nenhum canal de voz.")

# Rodar o bot
bot.run(TOKEN)