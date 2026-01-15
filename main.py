import os
from dotenv import load_dotenv
load_dotenv()

TOKEN = os.getenv("BETA_TOKEN")
DB_PASSWORD = os.getenv('DB_PASSWORD')
APP_ID = 1386436781330923753
GUILD_ID = 905167903224123473

from scurrypy import (
    Client,
    Interaction, InteractionEvent,
    MessagePart,
    EmbedPart, EmbedField, EmbedImage, EmbedFooter
)

client = Client(token=TOKEN)

from scurry_kit import (
    CommandsAddon, ComponentsAddon, BotEmojisCacheAddon, 
    EmbedBuilder as E, ActionRowBuilder as A, 
    setup_default_logger
)

logger = setup_default_logger()

commands = CommandsAddon(client, APP_ID, False)
components = ComponentsAddon(client)
bot_emojis = BotEmojisCacheAddon(client, APP_ID)

from game import PostgresDB,  Cards, Card, Player, CardEvent, OPTIONS_SIZE, MAX_HEALTH, RANKS, SUITS
db = PostgresDB(client, 'furmissile', 'squirrels', DB_PASSWORD)


# --- Common Message Formats ---
def build_player_options(p: Player):
    return A.row([
        A.primary(
            custom_id=format_custom_id('select', p.user_id, p.session_id, i), 
            label=p.options[i].rank,
            emoji=bot_emojis.get_emoji(p.options[i].emoji_name)
        )
        for i in range(3)
    ]) if p.hp > 0 else A.row(
        A.danger(format_custom_id('restart', p.user_id, p.session_id), 'Restart') 
    )

def format_custom_id(command: str, user_id: int, session_id: str, *args):
    return '_'.join([command, str(user_id), session_id] + [f"{n}" for n in args])

def build_game_embed(event: InteractionEvent, p: Player, add_pts: int = 0):
    space = bot_emojis.get_emoji('space').mention
    stash = bot_emojis.get_emoji('stash').mention
    highscore = bot_emojis.get_emoji('highscore').mention
    heart = bot_emojis.get_emoji('heart').mention
    empty_heart = bot_emojis.get_emoji('empty_heart').mention

    hp_bar = ' '.join([heart] * p.hp + [empty_heart] * (MAX_HEALTH - p.hp))

    return EmbedPart(
        title="Foraging...",
        author=E.user_author(event.member.user),
        fields=[
            EmbedField('Score',
                f"{space}{stash} **{p.score}**" 
                + (f' +**{add_pts}**' if add_pts else '')
                + (f" ({highscore} **{p.highscore}**)" if p.highscore > 0 else '')),

            EmbedField('Hearts', hp_bar),

            EmbedField(f'Hand ({Cards.sum_cards(p.hand)})',
                f'{space}'.join(
                    f"{bot_emojis.get_emoji(c.emoji_name).mention} **{c.rank}**" 
                    for c in p.hand) if p.hand else 'No cards.'
            )
        ]
    )

def get_suit_emoji(suit: str):
    return bot_emojis.get_emoji(suit).mention

def format_card(card: Card):
    return f"{get_suit_emoji(card.emoji_name)} **{card.rank}**"

def append_event(e: CardEvent):
    description = ""

    if e.is_stash and e.stash_suit:
        card_suit = get_suit_emoji(e.stash_suit)
        description += f"{card_suit} *Stash Bonus!* {card_suit} \n"

    if e.is_match and e.match_suit:
        card_suit = get_suit_emoji(e.match_suit)
        description += f"{card_suit} *Match Bonus!* {card_suit} \n"

    return description

# --- Bot Interactions ---
@commands.slash_command('play', 'Begin or resume your game!', guild_ids=GUILD_ID)
async def on_start(bot: Client, interaction: Interaction):
    event: InteractionEvent = interaction.context

    embed = EmbedPart(
        title=f'Welcome, {event.member.nick or event.member.user.username}!',
        image=EmbedImage('https://raw.githubusercontent.com/scurry-works/squirrel-stash/refs/heads/main/assets/welcome.gif')
    )

    import uuid

    row = A.row([
        A.success(format_custom_id('start', event.member.user.id, str(uuid.uuid4())), 'Start', bot_emojis.get_emoji('acorn'))
    ])

    await interaction.respond(
        MessagePart(
            embeds=[embed],
            components=[row]
        )
    )

@components.button('start_*')
async def on_forage(bot: Client, interaction: Interaction):
    event: InteractionEvent = interaction.context

    _, user_id, session_id = event.data.custom_id.split('_')

    if int(user_id) != event.member.user.id:
        await interaction.respond("This message belongs to someone else! Send `/forage` to initiate your own forage.", ephemeral=True)
        return

    conn = await db.get_connection()

    p = await Player(event.member.user.id).fetch(conn)

    throw_error = False

    try:
        p.session_id = session_id

        if p.guild_id != event.guild_id:
            p.guild_id = event.guild_id

        await p.save(conn)

    except Exception as e:
        await interaction.respond("An error occurred!", ephemeral=True)
        logger.error(e)
        throw_error = True
    finally:
        await conn.close()

    if throw_error:
        return

    embed = build_game_embed(event, p)

    row = build_player_options(p)

    await interaction.update(
        MessagePart(
            embeds=[embed],
            components=[row]
        )
    )

@components.button('select_*')
async def on_select(bot: Client, interaction: Interaction):
    event: InteractionEvent = interaction.context

    _, user_id, session_id, button_idx = event.data.custom_id.split('_')

    if int(user_id) != event.member.user.id:
        await interaction.respond("This message belongs to someone else! Send `/forage` to initiate your own forage.", ephemeral=True)
        return

    conn = await db.get_connection()

    p = await Player(event.member.user.id).fetch(conn)
    
    if session_id != p.session_id:
        await interaction.respond("This appears to be an old message! Try sending `/forage` to renew a session.", ephemeral=True)
        await conn.close()
        return

    select_card = p.options[int(button_idx)]
    throw_error = False

    add_pts = 0
    description = ""

    try:
        import random
        if select_card.suit == 'HP':
            p.hp += (1 if p.hp < MAX_HEALTH else 0)

        elif select_card.rank == 'B':
            rank_one, rank_two = tuple(random.sample(population=RANKS, k=2))
            suit_one, suit_two = tuple(random.choices(population=SUITS, k=2))

            card_one = Card(suit_one, rank_one)
            card_two = Card(suit_two, rank_two)

            description = f"Bookie drew: {format_card(card_one)} + {format_card(card_two)} \n"

            e_one = p.add_card(card_one)
            e_two = p.add_card(card_two)

            description += append_event(e_one)
            description += append_event(e_two)

            add_pts = e_one.points + e_two.points

        elif select_card.rank == 'P':
            # pull all targets with the same guild id and a non-empty hand
            records = await conn.fetch("select user_id from player where user_id != $1 and hand != '{}' and hp > 0 order by random()", p.user_id)

            if len(records) == 0:
                card_select = Card.random_rank()
                description += f"*No targets available.* \nPirate drew: {format_card(card_select)} \n"
            else:
                random_opponent = random.choice(records)
                opponent = await Player(random_opponent['user_id']).fetch(conn)
                card_select = opponent.hand.pop(random.randint(0, len(opponent.hand) -1))
                await opponent.save(conn)

                description += f"You stole a {format_card(card_select)}!"
                await bot.channel(event.channel_id).send(f"<@{opponent.user_id}>, **{event.member.nick or event.member.user.username}** has stolen your {format_card(card_select)}!")

            e = p.add_card(card_select)

            description += append_event(e)

            add_pts = e.points

        elif select_card.rank == 'W':
            highest_card = Cards.get_highest_card(p.hand)
            p.hand.remove(highest_card)

            e = CardEvent(points=2 * highest_card.value)
            p.hand = e.check_21(p.hand, highest_card)

            description += append_event(e)
            
            add_pts = e.points
        else: 
            e = p.add_card(select_card)

            description += append_event(e)

            add_pts = e.points

        if Cards.sum_cards(p.hand) > 21:
            p.hp -= 1
            description += f"*Busted!* \n-**1** {bot_emojis.get_emoji('broken_heart').mention} Heart"

        p.new_options()

        await p.save(conn)
    except Exception as e:
        await interaction.respond("An error occurred!", ephemeral=True)
        logger.error(e)
        throw_error = True
    finally:
        await conn.close()

    if throw_error:
        return

    embed = build_game_embed(event, p, add_pts)

    embed.description = description

    row = build_player_options(p)

    await interaction.update(
        MessagePart(
            embeds=[embed],
            components=[row]
        )
    )

@components.button('restart_*')
async def on_restart(bot: Client, interaction: Interaction):
    event: InteractionEvent = interaction.context

    _, user_id, session_id = event.data.custom_id.split('_')

    if int(user_id) != event.member.user.id:
        await interaction.respond("This message belongs to someone else! Send `/forage` to initiate your own forage.", ephemeral=True)
        return

    conn = await db.get_connection()

    p = await Player(event.member.user.id).fetch(conn)
    
    if session_id != p.session_id:
        await interaction.respond("This appears to be an old message! Try sending `/forage` to renew a session.", ephemeral=True)
        await conn.close()
        return
    
    throw_error = False

    try:
        reset_p = Player(
            event.member.user.id, 
            p.session_id, 
            highscore = p.score if p.score > p.highscore else p.highscore,
        )

        reset_p.new_options()

        await reset_p.save(conn)
    except Exception as e:
        await interaction.respond("An error occurred!", ephemeral=True)
        logger.error(e)
        throw_error = True
    finally:
        await conn.close()

    if throw_error:
        return
    
    embed = build_game_embed(event, reset_p)

    row = build_player_options(reset_p)

    await interaction.update(
        MessagePart(
            embeds=[embed],
            components=[row]
        )
    )

wrap_help_field = lambda name, values: EmbedField('{acorn} ' + name, '\n'.join(['{space}{bullet}' + v for v in values]))

GAME_HELP = {
    0: wrap_help_field('Gameplay', [
            "**GOAL**: Accumulate the highest score!",
            "Add to your hand by selecting from the given choices.",
            "Game ends when you run out of hearts."
        ]),
    1: wrap_help_field('Stashing', [
            "Stashing occurs automatically when there's a match to be made or your hand sums to 21.",
            "Hitting 21 is worth 100 points.",
            "Pairs of the same rank is worth *twice* the matching card's value.",
            "If matching a pair of the same suit, the match score is **doubled** (2×).",
            "If stashing 21 with all one suit, you earn **500 points** instead of 100 (5×)."
        ]),
    2: wrap_help_field('Busting', [
            "You hand is busted when its sum exceeds 21.",
            "Lose 1 heart for each bust.",
            "Hearts can be found to restore hearts."
        ]),
    3: wrap_help_field('Face Cards', [
            "**Ace (A)** is worth 1 point in hand.",
            "The Bookie, Pirate, and Wizard are all executed immediately upon selecting and do NOT go in hand.",
            "**Bookie (B)**: Draw 2 random cards.",
            "**Pirate (P)**: Steal a random card from a random player. If no targets available, draws a card instead.",
            "**Wizard (W)**: Stash the card of highest value + Wizard worth `(card value ×2) +10` points."
        ]),
    4: wrap_help_field('Support', [
            "Need more help or looking to report a bug? Join the [support server](https://discord.gg/D4SdHxcujM)!"
        ])
}

GAME_HELP_SIZE = len(GAME_HELP)

def build_help_message(event: InteractionEvent, page_num: int):
    acorn = bot_emojis.get_emoji('acorn').mention
    space = bot_emojis.get_emoji('space').mention
    bullet = bot_emojis.get_emoji('bullet').mention

    help_field = GAME_HELP.get(page_num)

    if not help_field:
        help_field = wrap_help_field("Uh oh!", ["Looks like you came across an error!"])

    help_field.name = help_field.name.format(acorn=acorn)
    help_field.value = help_field.value.format(space=space, bullet=bullet)

    embed = EmbedPart(
        title='Help Pages',
        author=E.user_author(event.member.user),
        fields=[help_field],
        footer=EmbedFooter(f"Page {page_num +1} of {GAME_HELP_SIZE}")
    )

    page_buttons = A.row([
        A.secondary(custom_id=f"help start_{event.member.user.id}_0", emoji='⏮️', disabled=True)
        if page_num == 0 else
        A.primary(custom_id=f"help start_{event.member.user.id}_0", emoji='⏮️'),

        A.secondary(custom_id=f"help back_{event.member.user.id}_{page_num -1}", emoji='⏪', disabled=True)
        if page_num -1 < 0 else
        A.primary(custom_id=f"help back_{event.member.user.id}_{page_num -1}", emoji='⏪'),

        A.secondary(custom_id=f"help next_{event.member.user.id}_{page_num +1}", emoji='⏩', disabled=True)
        if page_num +1 == GAME_HELP_SIZE else
        A.primary(custom_id=f"help next_{event.member.user.id}_{page_num +1}", emoji='⏩'),

        A.secondary(custom_id=f"help end_{event.member.user.id}_{GAME_HELP_SIZE -1}", emoji='⏭️', disabled=True)
        if page_num == GAME_HELP_SIZE -1 else
        A.primary(custom_id=f"help end_{event.member.user.id}_{GAME_HELP_SIZE -1}", emoji='⏭️')
    ])

    return MessagePart(
        embeds=[embed],
        components=[page_buttons]
    )

@commands.slash_command('help', 'Need some assistance?')
async def on_help(bot: Client, interaction: Interaction):
    event: InteractionEvent = interaction.context

    await interaction.respond(build_help_message(event, 0))

async def respond_help(interaction: Interaction):
    event: InteractionEvent = interaction.context

    _, user_id, page_num = event.data.custom_id.split('_')

    if int(user_id) != event.member.user.id:
        await interaction.respond("This message belongs to someone else! Send `/forage` to initiate your own forage.", ephemeral=True)
        return

    await interaction.update(build_help_message(event, int(page_num)))

@components.button('help start_*_0')
async def on_to_start(bot: Client, interaction: Interaction):
    await respond_help(interaction)

@components.button('help back_*')
async def on_back_page(bot: Client, interaction: Interaction):
    await respond_help(interaction)

@components.button('help next_*')
async def on_next_page(bot: Client, interaction: Interaction):
    await respond_help(interaction)

@components.button(f"help end_*_{GAME_HELP_SIZE -1}")
async def on_to_end(bot: Client, interaction: Interaction):
    await respond_help(interaction)


client.run()
