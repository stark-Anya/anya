import asyncio
from pyrogram import filters, enums
from pyrogram.errors import FloodWait
from SANYAMUSIC import app
from SANYAMUSIC.misc import SUDOERS
from SANYAMUSIC.utils.database import (
    get_client,
    get_served_chats,
    get_served_users,
)
from SANYAMUSIC.utils.decorators.language import language
from config import OWNER_ID

IS_BROADCASTING = False


@app.on_message(filters.command("broadcast") & SUDOERS)
@language
async def broadcast_message(client, message, _):
    global IS_BROADCASTING

    # Clone bot me broadcast allowed nahi — sirf main owner kar sakta hai main bot se
    is_clone = getattr(client, "is_clone", False)
    if is_clone:
        return await message.reply_text(
            "❌ Broadcast is not available in clone bots.\n"
            "Use the <b>main bot</b> to broadcast to all groups.",
            parse_mode=enums.ParseMode.HTML,
        )

    # Sirf main owner broadcast kar sakta hai
    if message.from_user.id != OWNER_ID:
        return await message.reply_text(
            "❌ Only the <b>main owner</b> can use broadcast.",
            parse_mode=enums.ParseMode.HTML,
        )

    if message.reply_to_message:
        x = message.reply_to_message.id
        y = message.chat.id
    else:
        if len(message.command) < 2:
            return await message.reply_text(_["broad_2"])
        query = message.text.split(None, 1)[1]
        for flag in ["-pin", "-nobot", "-pinloud", "-assistant", "-user"]:
            query = query.replace(flag, "")
        if not query.strip():
            return await message.reply_text(_["broad_8"])

    IS_BROADCASTING = True
    await message.reply_text(_["broad_1"])

    if "-nobot" not in message.text:
        sent = 0
        pin = 0
        schats = await get_served_chats()
        chats = [int(c["chat_id"]) for c in schats]
        for i in chats:
            try:
                m = (
                    await app.forward_messages(i, y, x)
                    if message.reply_to_message
                    else await app.send_message(i, text=query)
                )
                if "-pin" in message.text:
                    try:
                        await m.pin(disable_notification=True)
                        pin += 1
                    except:
                        pass
                elif "-pinloud" in message.text:
                    try:
                        await m.pin(disable_notification=False)
                        pin += 1
                    except:
                        pass
                sent += 1
                await asyncio.sleep(0.2)
            except FloodWait as fw:
                flood_time = int(fw.value)
                if flood_time > 200:
                    continue
                await asyncio.sleep(flood_time)
            except:
                continue
        try:
            await message.reply_text(_["broad_3"].format(sent, pin))
        except:
            pass

    if "-user" in message.text:
        susr = 0
        susers = await get_served_users()
        served_users = [int(u["user_id"]) for u in susers]
        for i in served_users:
            try:
                (
                    await app.forward_messages(i, y, x)
                    if message.reply_to_message
                    else await app.send_message(i, text=query)
                )
                susr += 1
                await asyncio.sleep(0.2)
            except FloodWait as fw:
                flood_time = int(fw.value)
                if flood_time > 200:
                    continue
                await asyncio.sleep(flood_time)
            except:
                pass
        try:
            await message.reply_text(_["broad_4"].format(susr))
        except:
            pass

    if "-assistant" in message.text:
        aw = await message.reply_text(_["broad_5"])
        text = _["broad_6"]
        from SANYAMUSIC.core.userbot import assistants
        for num in assistants:
            sent = 0
            assist_client = await get_client(num)
            async for dialog in assist_client.get_dialogs():
                try:
                    (
                        await assist_client.forward_messages(dialog.chat.id, y, x)
                        if message.reply_to_message
                        else await assist_client.send_message(dialog.chat.id, text=query)
                    )
                    sent += 1
                    await asyncio.sleep(3)
                except FloodWait as fw:
                    flood_time = int(fw.value)
                    if flood_time > 200:
                        continue
                    await asyncio.sleep(flood_time)
                except:
                    continue
            text += _["broad_7"].format(num, sent)
        try:
            await aw.edit_text(text)
        except:
            pass

    IS_BROADCASTING = False
