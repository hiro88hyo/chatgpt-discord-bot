import os

import requests
import json
from datetime import datetime
import dateutil.parser

channel_id = os.environ["DISCORD_CHANNEL_ID"]
token = os.environ["DISCORD_BOT_ACCESS_TOKEN"]
url = f"https://discord.com/api/v10/channels/{channel_id}/messages"

# For authorization, you can use either your bot token
headers = {
    "Authorization": f"Bot {token}"
}

r = requests.get(url, headers=headers)
res = json.loads(r.text)

conversation = []

for message in res:
    if message["type"]==20 and not (int(message["flags"]) & (1 << 7)):
        print(message)
        conversation.append({
            'timestamp': dateutil.parser.parse(message['timestamp']),
            'prompt': message['embeds'][0]['description'],
            'response': message['embeds'][0]['fields'][0]['value']
        })

for message in sorted(conversation, key=lambda k:k['timestamp']):
        print(f"timestamp: {message['timestamp']}")
        print(f"prompt: {message['prompt']}")
        print(f"response: {message['response']}")
        print("----------")
