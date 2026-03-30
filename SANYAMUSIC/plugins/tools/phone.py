from pyrogram import Client, filters
import requests
import json
from SANYAMUSIC import app

def send_message(message, text):
    message.reply_text(text)


@app.on_message(filters.command("phone"))
def check_phone(client, message):
    try:
        args = message.text.split(None, 1)
        number = args[1]

        api = f"http://encorexapi.vercel.app/FREEAPI?ARUSHONDRUGS={number}"

        response = requests.get(api)
        data = response.json()

        name = data.get("name", "N/A")
        mobile = data.get("mobile", "N/A")
        alt_mobile = data.get("alternative mobile", "N/A")
        father = data.get("father name", "N/A")
        address = data.get("address", "N/A")
        sim = data.get("circle/sim", "N/A")
        id_number = data.get("id number", "N/A")
        mail = data.get("mail", "N/A")

        result = f"""
📱 Phone Lookup Result

👤 Name: {name}
📞 Mobile: {mobile}
📞 Alt Mobile: {alt_mobile}
👨 Father Name: {father}
🆔 ID Number: {id_number}
📡 SIM Circle: {sim}
📧 Email: {mail}
🏠 Address: {address}
"""

        send_message(message, result)

    except Exception as e:
        send_message(message, f"Error: {str(e)}")
