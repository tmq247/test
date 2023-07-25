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
import re
from contextlib import suppress
from time import time

from pyrogram import filters
from pyrogram.enums import ChatMembersFilter, ChatType
from pyrogram.errors import FloodWait
from pyrogram.types import (
    CallbackQuery,
    ChatMemberUpdated,
    ChatPermissions,
    ChatPrivileges,
    Message,
)

from wbb import BOT_ID, SUDOERS, app, log
from wbb.core.decorators.errors import capture_err
from wbb.core.keyboard import ikb
from wbb.utils.dbfunctions import (
    add_warn,
    get_warn,
    int_to_alpha,
    remove_warns,
    save_filter,
)
from wbb.utils.functions import (
    extract_user,
    extract_user_and_reason,
    time_converter,
)
from wbb import FMUTE_LOG_GROUP_ID
from wbb.utils.dbfunctions import (
    get_served_chats,
    add_fmute_user,
    is_fmuted_user,
    remove_fmute_user,
)

__MODULE__ = "Admin"
__HELP__ = """/ban - cấm người dùng
/db - Xóa tin nhắn đã trả lời cấm người gửi
/tb - Cấm người dùng trong thời gian cụ thể
/unb - Bỏ cấm người dùng
/listban - Cấm người dùng khỏi các nhóm được liệt kê trong một tin nhắn
/listunban - Bỏ cấm người dùng khỏi các nhóm được liệt kê trong thông báo
/w - Cảnh báo người dùng
/dw - Xóa tin nhắn đã trả lời cảnh báo người gửi
/uw - Xóa tất cả cảnh báo của người dùng
/ws - Hiển thị cảnh báo của người dùng
/k - Kick A User
/dk - Xóa tin nhắn đã trả lời đá người gửi của nó
/purge - Xóa tin nhắn
/purge [n] - Xóa số lượng tin nhắn "n" khỏi tin nhắn đã trả lời
/del - Xóa tin nhắn đã trả lời
/promote - Thăng cấp thành viên
/fullpromote - Thăng cấp thành viên có mọi quyền
/demote - giáng cấp một thành viên
/pin - Ghim tin nhắn
/mut - Cấm chat người dùng
/dmut - Xóa tin nhắn đã trả lời cấm chat người gửi
/tmut - Cấm chat người dùng trong thời gian cụ thể
/unmut - Mở chat người dùng
/ban_ghosts - Cấm các tài khoản đã xóa
/report | @admins | @admin - Báo cáo tin nhắn cho quản trị viên.
/invite - Gửi liên kết mời nhóm/siêu nhóm."""


async def member_permissions(chat_id: int, user_id: int):
    perms = []
    member = (await app.get_chat_member(chat_id, user_id)).privileges
    if not member:
        return []
    if member.can_post_messages:
        perms.append("can_post_messages")
    if member.can_edit_messages:
        perms.append("can_edit_messages")
    if member.can_delete_messages:
        perms.append("can_delete_messages")
    if member.can_restrict_members:
        perms.append("can_restrict_members")
    if member.can_promote_members:
        perms.append("can_promote_members")
    if member.can_change_info:
        perms.append("can_change_info")
    if member.can_invite_users:
        perms.append("can_invite_users")
    if member.can_pin_messages:
        perms.append("can_pin_messages")
    if member.can_manage_video_chats:
        perms.append("can_manage_video_chats")
    return perms


from wbb.core.decorators.permissions import adminsOnly

admins_in_chat = {}


async def list_admins(chat_id: int):
    global admins_in_chat
    if chat_id in admins_in_chat:
        interval = time() - admins_in_chat[chat_id]["last_updated_at"]
        if interval < 3600:
            return admins_in_chat[chat_id]["data"]

    admins_in_chat[chat_id] = {
        "last_updated_at": time(),
        "data": [
            member.user.id
            async for member in app.get_chat_members(
                chat_id, filter=ChatMembersFilter.ADMINISTRATORS
            )
        ],
    }
    return admins_in_chat[chat_id]["data"]


# Admin cache reload


@app.on_chat_member_updated()
async def admin_cache_func(_, cmu: ChatMemberUpdated):
    if cmu.old_chat_member and cmu.old_chat_member.promoted_by:
        admins_in_chat[cmu.chat.id] = {
            "last_updated_at": time(),
            "data": [
                member.user.id
                async for member in app.get_chat_members(
                    cmu.chat.id, filter=ChatMembersFilter.ADMINISTRATORS
                )
            ],
        }
        log.info(f"Đã cập nhật bộ đệm quản trị cho {cmu.chat.id} [{cmu.chat.title}]")


# Purge Messages


@app.on_message(filters.command("purge") & ~filters.private)
@adminsOnly("can_delete_messages")
async def purgeFunc(_, message: Message):
    repliedmsg = message.reply_to_message
    await message.delete()

    if not repliedmsg:
        return await message.reply_text("Trả lời tin nhắn để xóa khỏi.")

    cmd = message.command
    if len(cmd) > 1 and cmd[1].isdigit():
        purge_to = repliedmsg.id + int(cmd[1])
        if purge_to > message.id:
            purge_to = message.id
    else:
        purge_to = message.id

    chat_id = message.chat.id
    message_ids = []

    for message_id in range(
        repliedmsg.id,
        purge_to,
    ):
        message_ids.append(message_id)

        # Max message deletion limit is 100
        if len(message_ids) == 100:
            await app.delete_messages(
                chat_id=chat_id,
                message_ids=message_ids,
                revoke=True,  # For both sides
            )

            # To delete more than 100 messages, start again
            message_ids = []

    # Delete if any messages left
    if len(message_ids) > 0:
        await app.delete_messages(
            chat_id=chat_id,
            message_ids=message_ids,
            revoke=True,
        )


# Kick members


@app.on_message(filters.command(["k", "dk"]) & ~filters.private)
@adminsOnly("can_restrict_members")
async def kickFunc(_, message: Message):
    user_id, reason = await extract_user_and_reason(message)
    if not user_id:
        return await message.reply_text("Tôi không thể tìm thấy người dùng đó.")
    if user_id == BOT_ID:
        return await message.reply_text(
            "Tôi không thể đá chính mình, tôi có thể rời đi nếu bạn muốn."
        )
    if user_id in SUDOERS:
        return await message.reply_text("Bạn Muốn Đá Một Đấng?")
    if user_id in (await list_admins(message.chat.id)):
        return await message.reply_text(
            "Tôi không thể đá một quản trị viên, Bạn biết các quy tắc, tôi cũng vậy."
        )
    mention = (await app.get_users(user_id)).mention
    msg = f"""
**Người dùng bị đá:** {mention}
**Bị đá bởi:** {message.from_user.mention if message.from_user else 'Anon'}
**Lý do:** {reason or 'None.'}"""
    if message.command[0][0] == "d":
        await message.reply_to_message.delete()
    await message.chat.ban_member(user_id)
    await message.reply_text(msg)
    await asyncio.sleep(1)
    await message.chat.unban_member(user_id)


# Ban members


@app.on_message(filters.command(["ban", "db", "tb"]) & ~filters.private)
@adminsOnly("can_restrict_members")
async def banFunc(_, message: Message):
    user_id, reason = await extract_user_and_reason(message, sender_chat=True)

    if not user_id:
        return await message.reply_text("Tôi không thể tìm thấy người dùng đó.")
    if user_id == BOT_ID:
        return await message.reply_text(
            "Tôi không thể cấm bản thân mình, tôi có thể rời đi nếu bạn muốn."
        )
    if user_id in SUDOERS:
        return await message.reply_text(
            "Bạn muốn cấm MỘT ĐẤNG?, KHÔNG ĐƯỢC ĐÂU :P!"
        )
    if user_id in (await list_admins(message.chat.id)):
        return await message.reply_text(
            "Ban tau à? Mở đi cưng."
        )

    try:
        mention = (await app.get_users(user_id)).mention
    except IndexError:
        mention = (
            message.reply_to_message.sender_chat.title
            if message.reply_to_message
            else "Anon"
        )

    msg = (
        f"**Người dùng bị cấm:** {mention}\n"
        f"**Bị cấm bởi:** {message.from_user.mention if message.from_user else 'Anon'}\n"
    )
    if message.command[0][0] == "d":
        await message.reply_to_message.delete()
    if message.command[0] == "tb":
        split = reason.split(None, 1)
        time_value = split[0]
        temp_reason = split[1] if len(split) > 1 else ""
        temp_ban = await time_converter(message, time_value)
        msg += f"**Bị cấm trong:** {time_value}\n"
        if temp_reason:
            msg += f"**Lý do:** {temp_reason}"
        with suppress(AttributeError):
            if len(time_value[:-1]) < 3:
                await message.chat.ban_member(user_id, until_date=temp_ban)
                await message.reply_text(msg)
            else:
                await message.reply_text("Bạn không thể sử dụng nhiều hơn 99")
        return
    if reason:
        msg += f"**Lý do:** {reason}"
    await message.chat.ban_member(user_id)
    await message.reply_text(msg)


# Unban members


@app.on_message(filters.command("unb") & ~filters.private)
@adminsOnly("can_restrict_members")
async def unban_func(_, message: Message):
    # we don't need reasons for unban, also, we
    # don't need to get "text_mention" entity, because
    # normal users won't get text_mention if the user
    # they want to unban is not in the group.
    reply = message.reply_to_message

    if reply and reply.sender_chat and reply.sender_chat != message.chat.id:
        return await message.reply_text("Bạn không thể bỏ cấm kênh")

    if len(message.command) == 2:
        user = message.text.split(None, 1)[1]
    elif len(message.command) == 1 and reply:
        user = message.reply_to_message.from_user.id
    else:
        return await message.reply_text(
            "Cung cấp tên người dùng hoặc trả lời tin nhắn của người dùng để bỏ cấm."
        )
    await message.chat.unban_member(user)
    umention = (await app.get_users(user)).mention
    await message.reply_text(f"Unbanned! {umention}")


# Ban users listed in a message


@app.on_message(SUDOERS & filters.command("listban") & ~filters.private)
async def list_ban_(c, message: Message):
    userid, msglink_reason = await extract_user_and_reason(message)
    if not userid or not msglink_reason:
        return await message.reply_text(
            "Cung cấp userid/username cùng với liên kết tin nhắn và lý do cấm danh sách"
        )
    if (
        len(msglink_reason.split(" ")) == 1
    ):  # message link included with the reason
        return await message.reply_text(
            "Bạn phải cung cấp một lý do để cấm danh sách"
        )
    # seperate messge link from reason
    lreason = msglink_reason.split()
    messagelink, reason = lreason[0], " ".join(lreason[1:])

    if not re.search(
        r"(https?://)?t(elegram)?\.me/\w+/\d+", messagelink
    ):  # validate link
        return await message.reply_text("Liên kết tin nhắn không hợp lệ được cung cấp")

    if userid == BOT_ID:
        return await message.reply_text("Tôi không thể cấm bản thân mình.")
    if userid in SUDOERS:
        return await message.reply_text(
            "Bạn muốn cấm một Đấng? Ngáo à!"
        )
    splitted = messagelink.split("/")
    uname, mid = splitted[-2], int(splitted[-1])
    m = await message.reply_text(
        "`Cấm người dùng từ nhiều nhóm. \
         Quá trình này có thể mất chút thời gian`"
    )
    try:
        msgtext = (await app.get_messages(uname, mid)).text
        gusernames = re.findall("@\w+", msgtext)
    except:
        return await m.edit_text("Không thể lấy usernames nhóm")
    count = 0
    for username in gusernames:
        try:
            await app.ban_chat_member(username.strip("@"), userid)
            await asyncio.sleep(1)
        except FloodWait as e:
            await asyncio.sleep(e.x)
        except:
            continue
        count += 1
    mention = (await app.get_users(userid)).mention

    msg = f"""
**List-banned User:** {mention}
**ID người dùng bị cấm:** `{userid}`
**Quản trị viên:** {message.from_user.mention}
**Cuộc trò chuyện bị ảnh hưởng:** `{count}`
**Lý do:** {reason}
"""
    await m.edit_text(msg)


# Unban users listed in a message


@app.on_message(SUDOERS & filters.command("listunban") & ~filters.private)
async def list_unban_(c, message: Message):
    userid, msglink = await extract_user_and_reason(message)
    if not userid or not msglink:
        return await message.reply_text(
            "Cung cấp userid/username cùng với liên kết thông báo tới list-unban"
        )

    if not re.search(
        r"(https?://)?t(elegram)?\.me/\w+/\d+", msglink
    ):  # validate link
        return await message.reply_text("Liên kết tin nhắn không hợp lệ được cung cấp")

    splitted = msglink.split("/")
    uname, mid = splitted[-2], int(splitted[-1])
    m = await message.reply_text(
        "`Bỏ cấm người dùng khỏi nhiều nhóm. \
         Quá trình này có thể mất chút thời gian`"
    )
    try:
        msgtext = (await app.get_messages(uname, mid)).text
        gusernames = re.findall("@\w+", msgtext)
    except:
        return await m.edit_text("Không thể lấy usernames nhóm")
    count = 0
    for username in gusernames:
        try:
            await app.unban_chat_member(username.strip("@"), userid)
            await asyncio.sleep(1)
        except FloodWait as e:
            await asyncio.sleep(e.x)
        except:
            continue
        count += 1
    mention = (await app.get_users(userid)).mention
    msg = f"""
**List-Unbanned User:** {mention}
**Unbanned User ID:** `{userid}`
**Quản trị viên:** {message.from_user.mention}
**Số nhóm:** `{count}`
"""
    await m.edit_text(msg)


# Delete messages


@app.on_message(filters.command("del") & ~filters.private)
@adminsOnly("can_delete_messages")
async def deleteFunc(_, message: Message):
    if not message.reply_to_message:
        return await message.reply_text("Trả lời một tin nhắn để xóa nó")
    await message.reply_to_message.delete()
    await message.delete()


# Promote Members


@app.on_message(filters.command(["promote", "fullpromote"]) & ~filters.private)
@adminsOnly("can_promote_members")
async def promoteFunc(_, message: Message):
    user_id = await extract_user(message)
    if not user_id:
        return await message.reply_text("Tôi không thể tìm thấy người dùng đó.")
    
    bot = (await app.get_chat_member(message.chat.id, BOT_ID)).privileges
    if user_id == BOT_ID:
        return await message.reply_text("Tôi không thể thăng cấp bản thân mình.")
    if not bot:
        return await message.reply_text("Tôi không phải là quản trị viên trong cuộc trò chuyện này.")
    if not bot.can_promote_members:
        return await message.reply_text("Tôi không có đủ quyền")

    umention = (await app.get_users(user_id)).mention
    
    if message.command[0][0] == "f":
        await message.chat.promote_member(
            user_id=user_id,
            privileges=ChatPrivileges(
                can_change_info=bot.can_change_info,
                can_invite_users=bot.can_invite_users,
                can_delete_messages=bot.can_delete_messages,
                can_restrict_members=bot.can_restrict_members,
                can_pin_messages=bot.can_pin_messages,
                can_promote_members=bot.can_promote_members,
                can_manage_chat=bot.can_manage_chat,
                can_manage_video_chats=bot.can_manage_video_chats,
            ),
        )
        return await message.reply_text(f"Đã thăng cấp full quyền! {umention}")

    await message.chat.promote_member(
        user_id=user_id,
        privileges=ChatPrivileges(
            can_change_info=False,
            can_invite_users=bot.can_invite_users,
            can_delete_messages=bot.can_delete_messages,
            can_restrict_members=False,
            can_pin_messages=False,
            can_promote_members=False,
            can_manage_chat=bot.can_manage_chat,
            can_manage_video_chats=bot.can_manage_video_chats,
        ),
    )
    await message.reply_text(f"Đã thăng cấp! {umention}")


# Demote Member


@app.on_message(filters.command("demote") & ~filters.private)
@adminsOnly("can_promote_members")
async def demote(_, message: Message):
    user_id = await extract_user(message)
    if not user_id:
        return await message.reply_text("Tôi không thể tìm thấy người dùng đó.")
    if user_id == BOT_ID:
        return await message.reply_text("Tôi không thể hạ cấp bản thân mình.")
    if user_id in SUDOERS:
        return await message.reply_text(
            "Bạn muốn giáng cấp Một ĐẤNG? Không được đâu!"
        )
    await message.chat.promote_member(
        user_id=user_id,
        privileges=ChatPrivileges(
            can_change_info=False,
            can_invite_users=False,
            can_delete_messages=False,
            can_restrict_members=False,
            can_pin_messages=False,
            can_promote_members=False,
            can_manage_chat=False,
            can_manage_video_chats=False,
        ),
    )
    umention = (await app.get_users(user_id)).mention
    await message.reply_text(f"Đã giáng cấp! {umention}")


# Pin Messages


@app.on_message(filters.command(["pin", "unpin"]) & ~filters.private)
@adminsOnly("can_pin_messages")
async def pin(_, message: Message):
    if not message.reply_to_message:
        return await message.reply_text("Trả lời tin nhắn để ghim/bỏ ghim tin nhắn đó.")
    r = message.reply_to_message
    if message.command[0][0] == "u":
        await r.unpin()
        return await message.reply_text(
            f"**Đã bỏ ghim tin nhắn [this]({r.link}).**",
            disable_web_page_preview=True,
        )
    await r.pin(disable_notification=True)
    await message.reply(
        f"**Đã ghim tin nhắn [this]({r.link}).**",
        disable_web_page_preview=True,
    )
    msg = "Vui lòng kiểm tra tin nhắn đã ghim: ~ " + f"[Check, {r.link}]"
    filter_ = dict(type="text", data=msg)
    await save_filter(message.chat.id, "~pinned", filter_)


# Mute members


@app.on_message(filters.command(["mut", "tmut", "dmut"]) & ~filters.private)
@adminsOnly("can_restrict_members")
async def mute(_, message: Message):
    user_id, reason = await extract_user_and_reason(message)
    if not user_id:
        return await message.reply_text("Tôi không thể tìm thấy người dùng đó.")
    if user_id == BOT_ID:
        return await message.reply_text("Tôi không thể tự cấm chat mình.")
    if user_id in SUDOERS:
        return await message.reply_text(
            "Bạn muốn cấm chat Một Đấng?, Mơ đi cưng!"
        )
    if user_id in (await list_admins(message.chat.id)):
        return await message.reply_text(
            "Tôi không thể tắt tiếng quản trị viên, Bạn biết các quy tắc, tôi cũng vậy."
        )
    mention = (await app.get_users(user_id)).mention
    keyboard = ikb({"🚨  Mở chat  🚨": f"unmute_{user_id}"})
    msg = (
        f"**Người dùng bị cấm chat:** {mention}\n"
        f"**Bị cấm chat bởi:** {message.from_user.mention if message.from_user else 'Anon'}\n"
    )
    if message.command[0][0] == "d":
        await message.reply_to_message.delete()
    if message.command[0] == "tmut":
        split = reason.split(None, 1)
        time_value = split[0]
        temp_reason = split[1] if len(split) > 1 else ""
        temp_mute = await time_converter(message, time_value)
        msg += f"**Bị cấm chat trong:** {time_value}\n"
        if temp_reason:
            msg += f"**Lý do:** {temp_reason}"
        try:
            if len(time_value[:-1]) < 3:
                await message.chat.restrict_member(
                    user_id,
                    permissions=ChatPermissions(),
                    until_date=temp_mute,
                )
                await message.reply_text(msg, reply_markup=keyboard)
            else:
                await message.reply_text("Bạn không thể sử dụng nhiều hơn 99")
        except AttributeError:
            pass
        return
    if reason:
        msg += f"**Lý do:** {reason}"
    await message.chat.restrict_member(user_id, permissions=ChatPermissions())
    await message.reply_text(msg, reply_markup=keyboard)


# Unmute members


@app.on_message(filters.command("unmut") & ~filters.private)
@adminsOnly("can_restrict_members")
async def unmute(_, message: Message):
    user_id = await extract_user(message)
    if not user_id:
        return await message.reply_text("Tôi không thể tìm thấy người dùng đó.")
    await message.chat.unban_member(user_id)
    umention = (await app.get_users(user_id)).mention
    await message.reply_text(f"Đã mở chat cho {umention}")

# Fmute


@app.on_message(filters.command("m") & ~filters.private)
@adminsOnly("can_restrict_members")
#@capture_err
async def mute_globally(_, message):
    user_id, reason = await extract_user_and_reason(message)
    user = await app.get_users(user_id)
    from_user = message.from_user
    is_fmuted = await is_fmuted_user(user.id)

    if not user_id:
        return await message.reply_text("Tôi không thể tìm thấy người dùng đó.")
        
    #if not reason:
        #return await message.reply("No reason provided.")

    if user_id in [from_user.id, BOT_ID] or user_id in SUDOERS:
        return await message.reply_text("Tôi không thể tắt tiếng người dùng đó.")

    #if  is_fmuted:
        #await message.reply_text("Người này đã được xác nhận.")
        
    served_chats = await get_served_chats()
    m = await message.reply_text(
        f"**Đang cấm chat {user.mention} trên toàn hệ thống!**"
        + f" **Hành động này sẽ mất khoảng {len(served_chats)} giây.**"
    )
    await add_fmute_user(user_id)
    number_of_chats = 0
    for served_chat in served_chats:
        try:
            await app.restrict_chat_member(served_chat["chat_id"], user.id, permissions=ChatPermissions())
            number_of_chats += 1
            await asyncio.sleep(1)
        except FloodWait as e:
            await asyncio.sleep(int(e.value))
        except Exception:
            pass
    try:
        await app.send_message(
            user.id,
            f"Xin chào, Bạn đã bị cấm chat toàn hệ thống bởi {from_user.mention},"
            f" Bạn hãy nhắn tin cho admin {reason or from_user.mention} để mở chat.",
        )
    except Exception:
        pass
    await m.edit(f"Đã cấm chat {user.mention} toàn hệ thống!")
    mute_text = f"""
__**Người dùng bị cấm chat toàn hệ thống**__
**Tại nhóm :** {message.chat.title} [`{message.chat.id}`]
**Quản trị viên:** {from_user.mention}
**Người dùng bị cấm chat:** {user.mention}
**ID người dùng bị cấm chat:** `{user_id}`
**Lý do (admin) :** __{reason}__
**Số nhóm:** `{number_of_chats}`"""
    try:
        m2 = await app.send_message(
            FMUTE_LOG_GROUP_ID,
            text=mute_text,
            disable_web_page_preview=True,
        )
        await m.edit(
            f"""**Đã cấm chat {user.mention} trên toàn hệ thống!!!\n Gửi voice cho {reason or from_user.mention} để được mỡ chat  💬💬💬**""",
            disable_web_page_preview=True,
        )
    except Exception:
        await message.reply_text(
            "Người dùng bị cấm chat, nhưng hành động cấm chat này không được ghi lại, hãy thêm tôi vào nhóm quản lý"
        )


# Unfmute


@app.on_message(filters.command("um") & ~filters.private)
@adminsOnly("can_restrict_members")
#@capture_err
async def unmute_globally(_, message):
    user_id, reason = await extract_user_and_reason(message)
    from_user = message.from_user
    if not user_id:
        return await message.reply_text("Tôi không thể tìm thấy người dùng đó.")
    user = await app.get_users(user_id)

    is_fmuted = await is_fmuted_user(user.id)
    if not is_fmuted:
        await message.reply_text("Tôi không nhớ đã cấm chat họ.")
    else:
        #await remove_fmute_user(user.id)
        #await message.chat.unban_member(user_id)
        #await message.reply_text(f"{user.mention} unmuted.'")
        served_chats = await get_served_chats()
        m = await message.reply_text(
            f"**Đang xác nhận {user.mention} trong hệ thống!**"
            + f" **Hành động này sẽ mất khoảng {len(served_chats)} giây.**"
        )
        await remove_fmute_user(user.id)
        number_of_chats = 0
        for served_chat in served_chats:
            try:
                await app.unban_chat_member(served_chat["chat_id"], user.id)
                number_of_chats += 1
                await asyncio.sleep(1)
            except FloodWait as e:
                await asyncio.sleep(int(e.value))
            except Exception:
                pass
        try:
            await app.send_message(
                user.id,
                f"Xin chào, Bạn đã được {from_user.mention} bỏ cấm chat trên toàn hệ thống,"
                + " Hãy tham gia trò chuyện cùng chúng tôi tại @nguhanh69 .",
            )
        except Exception:
            pass
        await m.edit(f"Đã xác nhận {user.mention} trên toàn hệ thống!")
        mute_text = f"""
__**Người dùng được xác nhận**__
**Tại nhóm :** {message.chat.title} [`{message.chat.id}`]
**Quản trị viên:** {from_user.mention}
**Mở chat người dùng:** {user.mention}
**ID người dùng đã mở chat:** `{user_id}`
**Lúc:** __{reason or 'None.'}__
**Số nhóm:** `{number_of_chats}`"""
        try:
            m2 = await app.send_message(
                FMUTE_LOG_GROUP_ID,
                text=mute_text,
                disable_web_page_preview=True,
            )
            await m.edit(
                f"Đã xác nhận {user.mention} trên toàn hệ thống!\n Bởi: {from_user.mention}",
                disable_web_page_preview=True,
            )
        except Exception:
            await message.reply_text(
                "Người dùng đã bật tiếng, nhưng hành động bật tiếng này không được ghi lại, hãy thêm tôi vào nhóm quản lý"
            )



# Ban deleted accounts


@app.on_message(filters.command("ban_ghosts") & ~filters.private)
@adminsOnly("can_restrict_members")
async def ban_deleted_accounts(_, message: Message):
    chat_id = message.chat.id
    deleted_users = []
    banned_users = 0
    m = await message.reply("Finding ghosts...")

    async for i in app.get_chat_members(chat_id):
        if i.user.is_deleted:
            deleted_users.append(i.user.id)
    if len(deleted_users) > 0:
        for deleted_user in deleted_users:
            try:
                await message.chat.ban_member(deleted_user)
            except Exception:
                pass
            banned_users += 1
        await m.edit(f"Đã cấm {banned_users} Tài khoản đã xóa")
    else:
        await m.edit("Không có tài khoản nào bị xóa trong cuộc trò chuyện này")


@app.on_message(filters.command(["wa", "dw"]) & ~filters.private)
@adminsOnly("can_restrict_members")
async def warn_user(_, message: Message):
    user_id, reason = await extract_user_and_reason(message)
    chat_id = message.chat.id
    if not user_id:
        return await message.reply_text("Tôi không thể tìm thấy người dùng đó.")
    if user_id == BOT_ID:
        return await message.reply_text(
            "Tôi không thể cảnh báo bản thân mình, tôi có thể rời đi nếu bạn muốn."
        )
    if user_id in SUDOERS:
        return await message.reply_text(
            "Bạn Muốn Cảnh Báo Đấng Tối Cao?, HÃY XEM XÉT!"
        )
    if user_id in (await list_admins(chat_id)):
        return await message.reply_text(
            "Tôi không thể cảnh báo quản trị viên, Bạn biết các quy tắc, tôi cũng vậy."
        )
    user, warns = await asyncio.gather(
        app.get_users(user_id),
        get_warn(chat_id, await int_to_alpha(user_id)),
    )
    mention = user.mention
    keyboard = ikb({"🚨  Gỡ cảnh báo  🚨": f"unwarn_{user_id}"})
    if warns:
        warns = warns["warns"]
    else:
        warns = 0
    if message.command[0][0] == "d":
        await message.reply_to_message.delete()
    if warns >= 2:
        await message.chat.ban_member(user_id)
        await message.reply_text(
            f"Đã vượt quá số cảnh báo của {mention}, BỊ CẤM KHỎI NHÓM!"
        )
        await remove_warns(chat_id, await int_to_alpha(user_id))
    else:
        warn = {"warns": warns + 1}
        msg = f"""
**Người dùng bị cảnh báo:** {mention}
**Bị cảnh báo bởi:** {message.from_user.mention if message.from_user else 'Anon'}
**Lý do:** {reason or 'No Reason Provided.'}
**Số cảnh báo:** {warns + 1}/3"""
        await message.reply_text(msg, reply_markup=keyboard)
        await add_warn(chat_id, await int_to_alpha(user_id), warn)


@app.on_callback_query(filters.regex("unwarn_"))
async def remove_warning(_, cq: CallbackQuery):
    from_user = cq.from_user
    chat_id = cq.message.chat.id
    permissions = await member_permissions(chat_id, from_user.id)
    permission = "can_restrict_members"
    if permission not in permissions:
        return await cq.answer(
            "Bạn không có đủ quyền để thực hiện hành động này.\n"
            + f"Quyền cần thiết: {permission}",
            show_alert=True,
        )
    user_id = cq.data.split("_")[1]
    warns = await get_warn(chat_id, await int_to_alpha(user_id))
    if warns:
        warns = warns["warns"]
    if not warns or warns == 0:
        return await cq.answer("Người dùng không có cảnh báo.")
    warn = {"warns": warns - 1}
    await add_warn(chat_id, await int_to_alpha(user_id), warn)
    text = cq.message.text.markdown
    text = f"~~{text}~~\n\n"
    text += f"__Cảnh báo bị xóa bởi {from_user.mention}__"
    await cq.message.edit(text)


# Rmwarns


@app.on_message(filters.command("uw") & ~filters.private)
@adminsOnly("can_restrict_members")
async def remove_warnings(_, message: Message):
    if not message.reply_to_message:
        return await message.reply_text(
            "Trả lời tin nhắn để xóa cảnh báo của người dùng."
        )
    user_id = message.reply_to_message.from_user.id
    mention = message.reply_to_message.from_user.mention
    chat_id = message.chat.id
    warns = await get_warn(chat_id, await int_to_alpha(user_id))
    if warns:
        warns = warns["warns"]
    if warns == 0 or not warns:
        await message.reply_text(f"{mention} không có cảnh báo.")
    else:
        await remove_warns(chat_id, await int_to_alpha(user_id))
        await message.reply_text(f"Removed warnings of {mention}.")


# Warns


@app.on_message(filters.command("ws") & ~filters.private)
@capture_err
async def check_warns(_, message: Message):
    user_id = await extract_user(message)
    if not user_id:
        return await message.reply_text("Tôi không thể tìm thấy người dùng đó.")
    warns = await get_warn(message.chat.id, await int_to_alpha(user_id))
    mention = (await app.get_users(user_id)).mention
    if warns:
        warns = warns["warns"]
    else:
        return await message.reply_text(f"{mention} không có cảnh báo.")
    return await message.reply_text(f"{mention} có {warns}/3 warnings.")


# Report


@app.on_message(
    (
        filters.command("report")
        | filters.command(["admins", "admin"], prefixes="@")
    )
    & ~filters.private
)
@capture_err
async def report_user(_, message):
    if not message.reply_to_message:
        return await message.reply_text(
            "Trả lời tin nhắn để báo cáo người dùng đó."
        )

    reply = message.reply_to_message
    reply_id = reply.from_user.id if reply.from_user else reply.sender_chat.id
    user_id = (
        message.from_user.id if message.from_user else message.sender_chat.id
    )
    if reply_id == user_id:
        return await message.reply_text("Tại sao bạn báo cáo chính mình ?")

    list_of_admins = await list_admins(message.chat.id)
    linked_chat = (await app.get_chat(message.chat.id)).linked_chat
    if linked_chat is not None:
        if (
            reply_id in list_of_admins
            or reply_id == message.chat.id
            or reply_id == linked_chat.id
        ):
            return await message.reply_text(
                "Bạn có biết rằng người dùng mà bạn đang trả lời là quản trị viên không ?"
            )
    else:
        if reply_id in list_of_admins or reply_id == message.chat.id:
            return await message.reply_text(
                "Bạn có biết rằng người dùng mà bạn đang trả lời là quản trị viên không ?"
            )

    user_mention = (
        reply.from_user.mention if reply.from_user else reply.sender_chat.title
    )
    text = f"Đã báo cáo {user_mention} cho chú cảnh sát!"
    admin_data = [
        i
        async for i in app.get_chat_members(
            chat_id=message.chat.id, filter=ChatMembersFilter.ADMINISTRATORS
        )
    ]  # will it give floods ???
    for admin in admin_data:
        if admin.user.is_bot or admin.user.is_deleted:
            # return bots or deleted admins
            continue
        text += f"[\u2063](tg://user?id={admin.user.id})"

    await message.reply_to_message.reply_text(text)


@app.on_message(filters.command("invite"))
@adminsOnly("can_invite_users")
async def invite(_, message):
    if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        link = (await app.get_chat(message.chat.id)).invite_link
        if not link:
            link = await app.export_chat_invite_link(message.chat.id)
        text = f"Đây là liên kết mời nhóm này.\n\n{link}"
        if message.reply_to_message:
            await message.reply_to_message.reply_text(
                text, disable_web_page_preview=True
            )
        else:
            await message.reply_text(text, disable_web_page_preview=True)
