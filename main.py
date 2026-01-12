import os
from dotenv import load_dotenv
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
DB_PASSWORD = os.getenv('DB_PASSWORD')
APP_ID = 1386436781330923753
GUILD_ID = 905167903224123473

from scurrypy import (
    Client,
    Interaction, InteractionEvent, UserModel,
    MessagePart, Attachment,
    EmbedPart, EmbedField, EmbedImage, EmbedFooter,
    StringSelect, SelectOption
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

from game import PostgresDB, Card, Player, OPTIONS_SIZE, MAX_HEALTH, STANDARD_SUITS, STANDARD_RANKS
db = PostgresDB(client, 'furmissile', 'squirrels', DB_PASSWORD)


# --- Various Utils ---
def sum_cards(cards: list[Card]):
    from functools import reduce
    return reduce(lambda x, y: x + y, [c.value for c in cards], 0)

def all_one_suit(cards: list[Card]):
    return len(set([c.suit for c in cards])) == 1

def format_custom_id(command: str, user_id: int, session_id: str, *args):
    return '_'.join([command, str(user_id), session_id] + [f"{n}" for n in args])


# --- Common Message Formats ---
def build_util_buttons(p: Player):
    has_matches = any(p.matches())
    has_b = p.has_rank('B')
    has_p = p.has_rank('P')
    has_w = p.has_rank('W')
    has_21 = sum_cards(p.hand) == 21

    return A.row([
        A.success(format_custom_id('match', p.user_id, p.session_id), 'Match', bot_emojis.get_emoji('match')) 
        if has_matches 
        else A.secondary(format_custom_id('match', p.user_id, p.session_id), 'Match', bot_emojis.get_emoji('match'), True),

        A.success(format_custom_id('stash', p.user_id, p.session_id), 'Stash 21', bot_emojis.get_emoji('stash'))
        if has_21 
        else A.secondary(format_custom_id('stash', p.user_id, p.session_id), 'Stash 21', bot_emojis.get_emoji('stash'), True),

        A.success(format_custom_id('bookie', p.user_id, p.session_id), 'Use Bookie', bot_emojis.get_emoji('bookie')) 
        if has_b
        else A.secondary(format_custom_id('bookie', p.user_id, p.session_id), 'Use Bookie', bot_emojis.get_emoji('bookie'), True),

        A.success(format_custom_id('pirate', p.user_id, p.session_id), 'Use Pirate', bot_emojis.get_emoji('pirate'))
        if has_p 
        else A.secondary(format_custom_id('pirate', p.user_id, p.session_id), 'Use Pirate', bot_emojis.get_emoji('pirate'), True),

        A.success(format_custom_id('wizard', p.user_id, p.session_id), 'Use Wizard', bot_emojis.get_emoji('wizard'))
        if has_w 
        else A.secondary(format_custom_id('wizard', p.user_id, p.session_id), 'Use Wizard', bot_emojis.get_emoji('wizard'), True)
    ])

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

def build_game_embed(author: UserModel, p: Player, add_pts: int = 0):
    space = bot_emojis.get_emoji('space').mention
    stash = bot_emojis.get_emoji('stash').mention
    highscore = bot_emojis.get_emoji('highscore').mention
    heart = bot_emojis.get_emoji('heart').mention
    empty_heart = bot_emojis.get_emoji('empty_heart').mention

    hp_bar = ' '.join([heart] * p.hp + [empty_heart] * (MAX_HEALTH - p.hp))

    return EmbedPart(
        title="Foraging...",
        author=E.user_author(author),
        fields=[
            EmbedField('Score',
                f"{space}{stash} **{p.score}**" 
                + (f' +**{add_pts}**' if add_pts else '')
                + (f" ({highscore} **{p.highscore}**)" if p.highscore > 0 else '')),

            EmbedField('Hearts' + (' (LAST STAND)' if p.hp == 0 else ''), hp_bar),

            EmbedField(f'Hand ({sum_cards(p.hand)})',
                f'{space}'.join(
                    f"{bot_emojis.get_emoji(c.emoji_name).mention} **{c.rank}**" 
                    for c in p.hand) if p.hand else 'No cards.'
            )
        ]
    )


# --- Bot Interactions ---
@commands.slash_command('play', 'Begin or resume your game!', guild_ids=GUILD_ID)
async def on_start(bot: Client, interaction: Interaction):
    event: InteractionEvent = interaction.context

    embed = EmbedPart(
        title=f'Welcome, {event.member.nick or event.member.user.username}!',
        image=EmbedImage('attachment://welcome.gif')
    )

    attachments = [
        Attachment('assets/welcome.gif', 'welcome!')
    ]

    import uuid

    row = A.row([
        A.success(format_custom_id('start', event.member.user.id, str(uuid.uuid4())), 'Start', bot_emojis.get_emoji('acorn'))
    ])

    await interaction.respond(
        MessagePart(
            embeds=[embed],
            components=[row],
            attachments=attachments
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

    embed = build_game_embed(event.member.user, p)

    row = build_player_options(p)

    util_row = build_util_buttons(p)

    await interaction.update(
        MessagePart(
            embeds=[embed],
            components=[row, util_row]
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

    throw_error = False

    try:
        hp_loss = False

        button_idx = int(button_idx)

        if p.options[button_idx].suit == 'HP':
            p.hp += (1 if p.hp < MAX_HEALTH else 0)
        else:
            p.hand.append(p.options[button_idx])

            # check if hand is already busted
            if sum_cards(p.hand) > 21 and p.hp > 0:
                p.hp -= 1
                hp_loss = True

        import random
        ranks = random.sample(population=STANDARD_RANKS, k=OPTIONS_SIZE)
        suits = random.choices(population=STANDARD_SUITS, k=OPTIONS_SIZE)

        new_options = [Card(s, r) for s, r in zip(suits, ranks)]

        if random.randint(0, 100) > 80:
            new_options[random.randint(0, OPTIONS_SIZE -1)] = Card('HP', '+1')

        p.options = new_options

        await p.save(conn)
    except Exception as e:
        await interaction.respond("An error occurred!", ephemeral=True)
        logger.error(e)
        throw_error = True
    finally:
        await conn.close()

    if throw_error:
        return

    embed = build_game_embed(event.member.user, p)

    if hp_loss:
        embed.description = f"*Busted!* \n-**1** {bot_emojis.get_emoji('broken_heart').mention} Heart"

    row = build_player_options(p)

    util_row = build_util_buttons(p)

    await interaction.update(
        MessagePart(
            embeds=[embed],
            components=[row, util_row]
        )
    )


@components.button('match_*')
async def on_match(bot: Client, interaction: Interaction):
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

    create_select_menu = False
    points = 0
    throw_error = False

    try:
        matches = p.matches() # len can only be 1 or greater (0 is filtered by disabling this interaction)

        if len(matches) == 1:
            only_match = list(matches.keys())[0]
            pair = p.pop_match(only_match)
            points = 2 * Card(None, only_match).value # make popped rank a card for the value prop
            if all_one_suit(pair):
                points *= 2 # EASTER EGG: double if all one suit!
            p.score += points 
            await p.save(conn)
        else:
            create_select_menu = True

        await p.save(conn)
    except Exception as e:
        await interaction.respond("An error occurred!", ephemeral=True)
        logger.error(e)
        throw_error = True
    finally:
        await conn.close()

    if throw_error:
        return
    
    embed = build_game_embed(event.member.user, p, points)
    
    if create_select_menu:
        select_menu = A.row([
            StringSelect(
                custom_id=format_custom_id('select match', p.user_id, p.session_id), 
                options=[
                    SelectOption(label=r, value=r) 
                    for r in list(matches.keys())
                ],
                placeholder='Select match...'
            )
        ])

        back = A.row([
            A.danger(format_custom_id('start', p.user_id, p.session_id), 'Back')
        ])

        await interaction.update(
            MessagePart(
                embeds=[embed],
                components=[select_menu, back]
            )
        )
    else:
        row = build_player_options(p)

        util_row = build_util_buttons(p)

        await interaction.update(
            MessagePart(
                embeds=[embed],
                components=[row, util_row]
            )
        )

@components.select('select match_*')
async def on_select_match(bot: Client, interaction: Interaction):
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
        pair = p.pop_match(event.data.values[0])
        points = 2 * Card(None, event.data.values[0]).value # make popped rank a card for the value prop
        if all_one_suit(pair):
            points *= 2 # EASTER EGG: double if all one suit!
        p.score += points 

        await p.save(conn)
    except Exception as e:
        await interaction.respond("An error occurred!", ephemeral=True)
        logger.error(e)
        throw_error = True
    finally:
        await conn.close()

    if throw_error:
        return

    embed = build_game_embed(event.member.user, p, points)

    row = build_player_options(p)

    util_row = build_util_buttons(p)

    await interaction.update(
        MessagePart(
            embeds=[embed],
            components=[row, util_row]
        )
    )


@components.button('bookie_*')
async def on_bookie(bot: Client, interaction: Interaction):
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
    
    if len(p.hand) == 1: # bookie is the ONLY card in hand
        await interaction.respond("Bookie needs another card in hand to be used!", ephemeral=True)
        await conn.close()
        return
    
    embed = build_game_embed(event.member.user, p)

    select_menu = A.row([
        StringSelect(
            format_custom_id('use bookie', p.user_id, p.session_id),
            options=[SelectOption(r, r) for r in list(dict.fromkeys([c.rank for c in p.hand if c.rank != 'B']))],
            placeholder='Pick a card to replace...'
        )
    ])

    special_options = A.row([
        A.danger(format_custom_id('start', p.user_id, p.session_id), 'Back')
    ])

    await interaction.update(
        MessagePart(
            embeds=[embed],
            components=[select_menu, special_options]
        )
    )

    await conn.close()

@components.button('use bookie_*')
async def on_use_bookie(bot: Client, interaction: Interaction):
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

    bookie_success = False
    throw_error = False
    card_select = None
    add_pts = 0

    try:
        p.pop_rank(event.data.values[0])
        card_select = Card.random()

        if not sum_cards(p.hand + [card_select]) > 21:
            bookie_success = True
            add_pts = 20
            p.hand.append(card_select)

        p.score += add_pts
        p.pop_rank('B')

        await p.save(conn)
    except Exception as e:
        await interaction.respond("An error occurred!", ephemeral=True)
        logger.error(e)
        throw_error = True
    finally:
        await conn.close()

    if throw_error:
        return
    
    embed = build_game_embed(event.member.user, p, add_pts)

    select_card_fmt = f"{bot_emojis.get_emoji(card_select.emoji_name).mention} **{card_select.rank}**"
    embed.description = f"Bookie drew: {select_card_fmt} \n" + ("*Bookie Stashed!*" if bookie_success else "*Bookie Lost!*")

    row = build_player_options(p)

    util_row = build_util_buttons(p)

    await interaction.update(
        MessagePart(
            embeds=[embed],
            components=[row, util_row]
        )
    )


@components.button('pirate_*')
async def on_pirate(bot: Client, interaction: Interaction):
    event: InteractionEvent = interaction.context

    _, user_id, session_id = event.data.custom_id.split('_')

    if int(user_id) != event.member.user.id:
        await interaction.respond("This message belongs to someone else! Send `/forage` to initiate your own forage.", ephemeral=True)
        return

    conn = await db.get_connection()

    p = await Player(event.member.user.id).fetch(conn)

    if session_id != p.session_id:
        await interaction.respond("This appears to be an old message! Try sending `/forage` to renew a session.", ephemeral=True)
        return

    throw_error = False
    pirate_success = False

    try:
        import random

        # pull all targets with the same guild id and a non-empty hand
        records = await conn.fetch("select user_id from player where user_id != $1 and hand != '{}' and hp > 0 order by random()", p.user_id)

        if len(records) == 0:
            card_select = Card.random()
        else:
            pirate_success = True

            random_opponent = random.choice(records)

            opponent = await Player(random_opponent['user_id']).fetch(conn)

            card_select = opponent.hand.pop(random.randint(0, len(opponent.hand) -1))

            await opponent.save(conn)

        p.pop_rank('P')
        p.hand.append(card_select)

        await p.save(conn)
    except Exception as e:
        await interaction.respond("An error occurred!", ephemeral=True)
        logger.error(e)
        throw_error = True
    finally:
        await conn.close()

    if throw_error:
        return
    
    embed = build_game_embed(event.member.user, p)

    select_card_fmt = f"{bot_emojis.get_emoji(card_select.emoji_name).mention} **{card_select.rank}**"

    if pirate_success:
        embed.description = f"You stole a {select_card_fmt}!"

        await bot.channel(event.channel_id).send(f"<@{opponent.user_id}>, **{event.member.nick or event.member.user.username}** has stolen your {select_card_fmt}!")
    else:
        embed.description = f"*No targets available.* \nPirate drew: {select_card_fmt}"

    row = build_player_options(p)

    util_row = build_util_buttons(p)

    await interaction.update(
        MessagePart(
            embeds=[embed],
            components=[row, util_row]
        )
    )


@components.button('wizard_*')
async def on_wizard(bot: Client, interaction: Interaction):
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

    embed = build_game_embed(event.member.user, p)

    select_menu = A.row([
        StringSelect(
            format_custom_id('use wizard', p.user_id, p.session_id),
            options=[SelectOption(r, r) for r in list(dict.fromkeys([c.rank for c in p.hand if c.rank != 'W']))],
            placeholder='Pick a card to discard...'
        )
    ])

    special_options = A.row([
        A.danger(format_custom_id('start', p.user_id, p.session_id), 'Back')
    ])

    await interaction.update(
        MessagePart(
            embeds=[embed],
            components=[select_menu, special_options]
        )
    )

    await conn.close()

@components.select('use wizard_*')
async def on_use_wizard(bot: Client, interaction: Interaction):
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
    add_pts = 0

    try:
        p.pop_rank('W')

        discarded = p.pop_rank(event.data.values[0])

        add_pts = (discarded.value *2) + 10 # includes W value + match

        p.score += add_pts

        await p.save(conn)
    except Exception as e:
        await interaction.respond("An error occurred!", ephemeral=True)
        logger.error(e)
        throw_error = True
    finally:
        await conn.close()

    if throw_error:
        return
    
    embed = build_game_embed(event.member.user, p, add_pts)

    row = build_player_options(p)

    util_row = build_util_buttons(p)

    await interaction.update(
        MessagePart(
            embeds=[embed],
            components=[row, util_row]
        )
    )


@components.button('stash_*')
async def on_stash(bot: Client, interaction: Interaction):
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
    
    score = 0

    throw_error = False
    
    try:
        if all_one_suit(p.hand):
            score = 200 # EASTER EGG: double if all one suit!
        else:
            score = 100 # STASH 21 value

        p.score += score 

        p.hand.clear()

        await p.save(conn)
    except Exception as e:
        await interaction.respond("An error occurred!", ephemeral=True)
        logger.error(e)
        throw_error = True
    finally:
        await conn.close()

    if throw_error:
        return
    
    embed = build_game_embed(event.member.user, p, score)

    row = build_player_options(p)

    util_row = build_util_buttons(p)

    await interaction.update(
        MessagePart(
            embeds=[embed],
            components=[row, util_row]
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
            options=[Card.random() for _ in range(OPTIONS_SIZE)]
        )

        await reset_p.save(conn)
    except Exception as e:
        await interaction.respond("An error occurred!", ephemeral=True)
        logger.error(e)
        throw_error = True
    finally:
        await conn.close()

    if throw_error:
        return
    
    embed = build_game_embed(event.member.user, reset_p)

    row = build_player_options(reset_p)

    util_row = build_util_buttons(reset_p)

    await interaction.update(
        MessagePart(
            embeds=[embed],
            components=[row, util_row]
        )
    )


def wrap_help_field(name: str, values: list[str]):
    return EmbedField('{acorn} ' + name, 
        '\n'.join(['{space}{bullet}' + v for v in values])
    )

GAME_HELP = {
    0: wrap_help_field('Gameplay', 
        [
            "**GOAL**: Accumulate the highest score!",
            "Add to your hand by selecting from the given choices.",
            "Game ends when you run out of hearts."
        ]),
    1: wrap_help_field('Stashing',
        [
            "Stash when the sum of your hand is exactly **21** (worth 100 points).",
            "Or stash matching pairs of the same rank (worth *twice* the matching card's value)."
        ]),
    2: wrap_help_field('Busting',
        [
            "You hand is busted when its sum exceeds 21.",
            "Lose 1 heart for each bust.",
            "Hearts can be found to restore hearts."
        ]),
    3: wrap_help_field('Face Cards',
        [
            "Face cards are Ace (A), Bookie (B), Pirate (P), and Wizard (W).",
            "Ace is worth 1 point in hand.",
            "The Bookie, Pirate, and Wizard are all worth 10 points in hand.",
            "**Bookie**: Replace a card with a card of the Bookie's choosing. If your resulting hand is a bust: lose both the bookie and card, otherwise stash bookie (worth 20 points) and keep the card.",
            "**Pirate**: Steal a random card from a random player in the same guild. If there is nothing to steal, the pirate will make a random draw. \n"
            "**Wizard**: Discard one of your cards and the Wizard itself for the value of the Wizard + double the rank's value."
        ]),
    4: wrap_help_field('Support',
        [
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
