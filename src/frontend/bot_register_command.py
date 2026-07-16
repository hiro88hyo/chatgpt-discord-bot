import os

import requests

application_id = os.environ["DISCORD_APPLICATION_ID"]
token = os.environ["DISCORD_BOT_ACCESS_TOKEN"]
url = f"https://discord.com/api/v10/applications/{application_id}/commands"

json = {
    "name": "chat",
    "type": 1,
    "description": "ChatGPTに話しかける",
    "options": [
        {
            "name": "prompt",
            "description": "プロンプト",
            "type": 3,
            "required": True,
        },
        {
            "name": "engine",
            "description": "LLM Engine",
            "type": 3,
            "required": False,
            "choices": [
                {
                    "name": "gpt-4o",
                    "value": "gpt-4o"
                },
                {
                    "name": "gpt-3.5-turbo",
                    "value": "agpt-3.5-turbo"
                }
            ]
        }
    ]
}

# For authorization, you can use either your bot token
headers = {
    "Authorization": f"Bot {token}"
}

r = requests.post(url, headers=headers, json=json)
print(r)
