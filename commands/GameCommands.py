from discord.ext.commands import Cog
from discord.ext import tasks
from discord import File, Embed, Colour
from utils.stat_util import *
from utils.plot_utils import *
from utils.utils import *
import logging
from mojang import MojangAPI
from asyncio import TimeoutError
from os import listdir
from random import choice, shuffle
from json import load
from difflib import get_close_matches


# Slash commands support
from discord_slash.cog_ext import cog_slash, manage_commands
from utils.config import SLASH_COMMANDS_GUILDS


class GameCommands(Cog, name="CTF Commands"):
    """
    A game where you guess the player from plots of the stats
    """
    def __init__(self, bot):
        self.bot = bot
        self.bot_channel = None
        self.general_chat = None
        self.in_progress = False
        self.maps_dir = "assets/map_closeups/"
        self.timeout = 300
        self.repost_guesses = 10

    @staticmethod
    async def comp_playtime_pie(ign):
        data = await get_lifetime_stats(ign)
        if data:
            mode = "competitive"
            if not len(data[mode].keys()) > 0:
                return False
            sizes = [int(data[mode][key]["playtime"]) for key in data[mode].keys()]
            avg_size = sum(sizes) / len(sizes)
            labels = [(key.title() if float(data[mode][key]["playtime"]) > avg_size else "") for key in data[mode].keys()]
            print(sizes, labels)

            ##Sorting lists as tuples
            list_of_tuples = list(zip(labels, sizes))
            shuffle(list_of_tuples)
            unzipped_list = list(zip(*list_of_tuples))
            new_labels, new_sizes = list(unzipped_list[0]), list(unzipped_list[1])

            # TODO: sort these lists to make the pie chart look better
            data_stream = pie_chart(new_labels, new_sizes, explode=[0.1 if label else 0 for label in labels],
                                    title="Playtime by class")
            data_stream.seek(0)
            chart_file = File(data_stream, filename="pie_chart.png")
            return chart_file
        else:
            return False

    @cog_slash(guild_ids=SLASH_COMMANDS_GUILDS)
    async def gameofmaps(self, ctx):
        """Compete with other players and show off your map knowledge!"""
        if self.in_progress:
            await error_embed(ctx, "There is already a game in progress")
            return

        def check(message):
            return message.content.startswith(">") and message.channel == ctx.channel

        with open("utils/maps.json") as file:
            maps = load(file)
        map_names = maps.keys()
        random_map_filename = choice(listdir(self.maps_dir))

        self.in_progress = True
        winners = []
        await ctx.send("Welcome to Game of Maps! Respond with `>[map_name]` to guess the map.")
        for round_num in range(1, 6):
            while True:
                random_map_filename = choice(listdir(self.maps_dir))
                path, map_id = self.maps_dir + random_map_filename, int(random_map_filename.split(" ")[0])
                file = File(path, filename="random_map.jpg")
                round_message = await ctx.send(content=f"Round {round_num}:", file=file)
                guessed = False
                n_guesses = 0
                while not guessed:
                    try:
                        response = await self.bot.wait_for("message", timeout=self.timeout, check=check)
                    except TimeoutError:
                        self.in_progress = False
                        await round_message.reply("Game timed out; you took too long to answer. "
                                                  "Start a new game to play again.")
                        return
                    content = response.content.lower()
                    if content.startswith(">"):
                        map_guess = get_close_matches(content.strip(">"), map_names)
                        if map_guess:
                            if maps[map_guess[0]] == map_id:
                                await response.add_reaction("✅")
                                await response.reply(f"You guessed correctly! ({map_guess[0]})")
                                winners.append(response.author)
                                guessed = True
                            else:
                                await response.add_reaction("❌")
                        else:
                            await response.add_reaction("❌")
                        if n_guesses >= self.repost_guesses:
                            await round_message.reply(content=round_message.attachments[0].url)
                            n_guesses = 0
                        n_guesses += 1
                break
        if winners:
            await ctx.send("Game finished! Congratulations to the winners - " +
                           " ".join(list(set(winner.mention for winner in winners))))
        else:
            await ctx.send("Game of Stats finished!")
        self.in_progress = False

    @cog_slash(guild_ids=SLASH_COMMANDS_GUILDS)
    async def gameofstats(self, ctx):
        """Compete with other members to guess the player from their stats"""
        if self.in_progress:
            await error_embed(ctx, "There is already a game in progress")
            return

        def check(message):
            return message.content.startswith(">") and message.channel == ctx.channel

        self.in_progress = True
        winners = []
        attempts = 0
        await ctx.send("Welcome to Game of Stats! Respond with `>[IGN]` to guess the player. Old names work too.")
        for round_num in range(1, 6):
            while True:
                random_player = Player.fetch_random_player()
                random_ign = random_player.minecraft_username
                uuid = random_player.minecraft_id
                names_dict = MojangAPI.get_name_history(uuid)
                all_names = [item["name"].lower() for item in names_dict]
                pie_file = await self.comp_playtime_pie(random_ign)
                if pie_file:
                    round_message = await ctx.send(content=f"Round {round_num}:", file=pie_file)
                    guessed = False
                    n_guesses = 0
                    while not guessed:
                        try:
                            response = await self.bot.wait_for("message", timeout=self.timeout, check=check)
                        except TimeoutError:
                            self.in_progress = False
                            await round_message.reply("Game timed out; you took too long to answer. "
                                                      "Start a new game to play again.")
                            return
                        content = response.content.lower()
                        if content.startswith(">"):
                            if content.strip(">") in all_names:
                                await response.add_reaction("✅")
                                await response.reply(f"You guessed correctly! ({random_ign})")
                                winners.append(response.author)
                                guessed = True
                            else:
                                await response.add_reaction("❌")
                            if n_guesses >= self.repost_guesses:
                                await round_message.reply(content=round_message.attachments[0].url)
                                n_guesses = 0
                            n_guesses += 1
                    break
                else:
                    if attempts > 5:
                        ctx.send("There were errors getting stats or generating pie charts")
                        return
                    attempts += 1
                    continue
        if winners:
            await ctx.send("Game finished! Congratulations to the winners - " +
                           " ".join(list(set(winner.mention for winner in winners))))
        else:
            await ctx.send("Game of Stats finished!")
        self.in_progress = False


