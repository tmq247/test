"""
MIT License

Copyright (c) 2023 TheHamkerCat

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import asyncio
import os
import subprocess
import time

import psutil
from pyrogram import filters, types
from pyrogram.errors import FloodWait
from pyrogram.types import ChatPermissions, InlineKeyboardMarkup

from wbb import (
    BOT_ID,
    GBAN_LOG_GROUP_ID,
    FMUTE_LOG_GROUP_ID,
    SUDOERS,
    USERBOT_USERNAME,
    app,
    bot_start_time,
)
from wbb.core.decorators.errors import capture_err
from wbb.utils import formatter
from wbb.utils.dbfunctions import (
    add_gban_user,
    get_served_chats,
    is_gbanned_user,
    remove_gban_user,
    get_served_users,
    add_fmute_user,
    is_fmuted_user,
    remove_fmute_user,
)
from wbb.utils.functions import extract_user, extract_user_and_reason, restart

__MODULE__ = "Sudoers"
__HELP__ = """
/stats - To Check System Status.

/gstats - To Check Bot's Global Stats.

/gban - To Ban A User Globally.

/m - To Ban A User Globally.

/clean_db - Clean database.

/broadcast - To Broadcast A Message To All Groups.

/ubroadcast - To Broadcast A Message To All Users.

/update - To Update And Restart The Bot

/eval - Execute Python Code

/sh - Execute Shell Code
"""


# Stats Module


async def bot_sys_stats():
    bot_uptime = int(time.time() - bot_start_time)
    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory().percent
    disk = psutil.disk_usage("/").percent
    process = psutil.Process(os.getpid())
    stats = f"""
{USERBOT_USERNAME}@William
------------------
UPTIME: {formatter.get_readable_time(bot_uptime)}
BOT: {round(process.memory_info()[0] / 1024 ** 2)} MB
CPU: {cpu}%
RAM: {mem}%
DISK: {disk}%
"""
    return stats


# Gban


@app.on_message(filters.command("gban") & SUDOERS)
@capture_err
async def ban_globally(_, message):
    user_id, reason = await extract_user_and_reason(message)
    user = await app.get_users(user_id)
    from_user = message.from_user

    if not user_id:
        return await message.reply_text("I can't find that user.")
    if not reason:
        return await message.reply("No reason provided.")

    if user_id in [from_user.id, BOT_ID] or user_id in SUDOERS:
        return await message.reply_text("I can't ban that user.")

    served_chats = await get_served_chats()
    m = await message.reply_text(
        f"**Banning {user.mention} Globally!**"
        + f" **This Action Should Take About {len(served_chats)} Seconds.**"
    )
    await add_gban_user(user_id)
    number_of_chats = 0
    for served_chat in served_chats:
        try:
            await app.ban_chat_member(served_chat["chat_id"], user.id)
            number_of_chats += 1
            await asyncio.sleep(1)
        except FloodWait as e:
            await asyncio.sleep(int(e.value))
        except Exception:
            pass
    try:
        await app.send_message(
            user.id,
            f"Hello, You have been globally banned by {from_user.mention},"
            + " You can appeal for this ban by talking to him.",
        )
    except Exception:
        pass
    await m.edit(f"Banned {user.mention} Globally!")
    ban_text = f"""
__**New Global Ban**__
**Origin:** {message.chat.title} [`{message.chat.id}`]
**Admin:** {from_user.mention}
**Banned User:** {user.mention}
**Banned User ID:** `{user_id}`
**Reason:** __{reason}__
**Chats:** `{number_of_chats}`"""
    try:
        m2 = await app.send_message(
            GBAN_LOG_GROUP_ID,
            text=ban_text,
            disable_web_page_preview=True,
        )
        await m.edit(
            f"Banned {user.mention} Globally!\nAction Log: {m2.link}",
            disable_web_page_preview=True,
        )
    except Exception:
        await message.reply_text(
            "User Gbanned, But This Gban Action Wasn't Logged, Add Me In GBAN_LOG_GROUP"
        )


# Ungban


@app.on_message(filters.command("ungban") & SUDOERS)
@capture_err
async def unban_globally(_, message):
    user_id = await extract_user(message)
    if not user_id:
        return await message.reply_text("I can't find that user.")
    user = await app.get_users(user_id)

    is_gbanned = await is_gbanned_user(user.id)
    if not is_gbanned:
        await message.reply_text("I don't remember Gbanning him.")
    else:
        await remove_gban_user(user.id)
        await message.chat.unban_member(user_id)
        await message.reply_text(f"Lifted {user.mention}'s Global Ban.'")


# Fmute


@app.on_message(filters.command("m") & ~filters.private)
@capture_err
async def mute_globally(_, message):
    user_id, reason = await extract_user_and_reason(message)
    user = await app.get_users(user_id)
    from_user = message.from_user

    if not user_id:
        return await message.reply_text("I can't find that user.")
    if not reason:
        return await message.reply("No reason provided.")

    if user_id in [from_user.id, BOT_ID] or user_id in SUDOERS:
        return await message.reply_text("I can't mute that user.")

    served_chats = await get_served_chats()
    m = await message.reply_text(
        f"**Muting {user.mention} Globally!**"
        + f" **This Action Should Take About {len(served_chats)} Seconds.**"
    )
    await add_fmute_user(user_id)
    number_of_chats = 0
    for served_chat in served_chats:
        try:
            await app.restrict_chat_member(served_chat["chat_id"], user_id, permissions=ChatPermissions())
            number_of_chats += 1
            await asyncio.sleep(1)
        except FloodWait as e:
            await asyncio.sleep(int(e.value))
        except Exception:
            pass
    try:
        await app.send_message(
            user.id,
            f"Hello, You have been globally muted by {from_user.mention},"
            + " You can appeal for this mute by talking to him.",
        )
    except Exception:
        pass
    await m.edit(f"Muted {user.mention} Globally!")
    mute_text = f"""
__**New Global Mute**__
**Origin:** {message.chat.title} [`{message.chat.id}`]
**Admin:** {from_user.mention}
**Muted User:** {user.mention}
**Muted User ID:** `{user_id}`
**Reason:** __{reason}__
**Chats:** `{number_of_chats}`"""
    try:
        m2 = await app.send_message(
            FMUTE_LOG_GROUP_ID,
            text=mute_text,
            disable_web_page_preview=True,
        )
        await m.edit(
            f"Muted {user.mention} Globally!\nAction Log: {m2.link}",
            disable_web_page_preview=True,
        )
    except Exception:
        await message.reply_text(
            "User Fmuted, But This Fmute Action Wasn't Logged, Add Me In FMUTE_LOG_GROUP"
        )


# Unfmute


@app.on_message(filters.command("um") & ~filters.private)
@capture_err
async def unmute_globally(_, message):
    user_id = await extract_user(message)
    if not user_id:
        return await message.reply_text("I can't find that user.")
    user = await app.get_users(user_id)

    is_fmuted = await is_fmuted_user(user.id)
    if not is_fmuted:
        await message.reply_text("I don't remember Fmuting him.")
    else:
        served_chats = await get_served_chats()
        m = await message.reply_text(
        f"**Muting {user.mention} Globally!**"
        + f" **This Action Should Take About {len(served_chats)} Seconds.**"
    )
        await remove_fmute_user(user.id)
        for served_chat in served_chats:
            try:
                await app.chat.unban_member(served_chat["chat_id"], user_id)
                number_of_chats += 1
                await asyncio.sleep(1)
            except FloodWait as e:
                await asyncio.sleep(int(e.value))
            except Exception:
                pass
            try:
            #await message.chat.unban_member(user_id)
            await message.reply_text(f"{user.mention}'s unmuted.'")




# Broadcast


@app.on_message(filters.command("broadcast") & SUDOERS)
@capture_err
async def broadcast_message(_, message):
    sleep_time = 0.1
    text = message.reply_to_message.text.markdown
    reply_message = message.reply_to_message

    reply_markup = None
    if reply_message.reply_markup:
        reply_markup = InlineKeyboardMarkup(reply_message.reply_markup.inline_keyboard)
    sent = 0
    schats = await get_served_chats()
    chats = [int(chat["chat_id"]) for chat in schats]
    m = await message.reply_text(
        f"Broadcast in progress, will take {len(chats) * sleep_time} seconds."
    )
    for i in chats:
        try:
            await app.send_message(
                i,
                text=text,
                reply_markup=reply_markup,
            )
            await asyncio.sleep(sleep_time)
            sent += 1
        except FloodWait as e:
            await asyncio.sleep(int(e.value))
        except Exception:
            pass
    await m.edit(f"**Broadcasted Message In {sent} Chats.**")


# Update


@app.on_message(filters.command("update") & SUDOERS)
async def update_restart(_, message):
    try:
        out = subprocess.check_output(["git", "pull"]).decode("UTF-8")
        if "Already up to date." in str(out):
            return await message.reply_text("Its already up-to date!")
        await message.reply_text(f"```{out}```")
    except Exception as e:
        return await message.reply_text(str(e))
    m = await message.reply_text("**Updated with default branch, restarting now.**")
    await restart(m)


@app.on_message(filters.command("ubroadcast") & SUDOERS)
@capture_err
async def broadcast_message(_, message):
    sleep_time = 0.1
    sent = 0
    schats = await get_served_users()
    chats = [int(chat["user_id"]) for chat in schats]
    text = message.reply_to_message.text.markdown
    reply_message = message.reply_to_message

    reply_markup = None
    if reply_message.reply_markup:
        reply_markup = InlineKeyboardMarkup(reply_message.reply_markup.inline_keyboard)

    m = await message.reply_text(
        f"Broadcast in progress, will take {len(chats) * sleep_time} seconds."
    )

    for i in chats:
        try:
            await app.send_message(
                i,
                text=text,
                reply_markup=reply_markup,
            )
            await asyncio.sleep(sleep_time)
            sent += 1
        except FloodWait as e:
            await asyncio.sleep(int(e.value))
        except Exception:
            pass
    await m.edit(f"**Broadcasted Message to {sent} Users.**")
