from pyrogram import enums
from config import OWNER_ID

async def is_admin_or_owner(chat, user_id):
    # ✅ OWNER bypass
    if user_id == OWNER_ID:
        return True

    # ✅ ADMIN check
    member = await chat.get_member(user_id)
    return (
        member.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]
        and member.privileges
        and member.privileges.can_restrict_members
    )


def admin_required(func):
    async def wrapper(client, message, *args, **kwargs):
        chat = message.chat

        if not await is_admin_or_owner(chat, message.from_user.id):
            return await message.reply_text("You don't have permission 😎")

        return await func(client, message, *args, **kwargs)

    return wrapper
