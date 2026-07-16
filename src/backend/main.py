import os
import base64
import logging
import requests
import json
from flask import request
from openai import OpenAI
from datetime import datetime
import dateutil.parser
from google import genai

logging.basicConfig(
        format = "[%(asctime)s][%(levelname)s] %(message)s",
        level = logging.DEBUG
    )
logger = logging.getLogger()

DISCORD_MAX_POST_LENGTH = 4000

def generate_chatbot_response_openai(messages):
    client = OpenAI(
      # This is the default and can be omitted
      api_key=os.environ.get("OPENAI_API_KEY"),
    )
    mode_name = os.environ["OPENAI_MODEL_NAME"]
    openai_response = client.chat.completions.create(
            model=mode_name,
            messages=messages
        )
    logger.info(f"API response={openai_response}")
    chatbot_message = openai_response.choices[0].message.content
    return {"content":chatbot_message, "timestamp": openai_response.created, "id": openai_response.id}

def generate_chatbot_response(messages):
  # Gemini
    client = genai.Client(
        api_key=os.environ.get("VERTEXAI_API_KEY")
    )
    response = client.models.generate_content(
        model='gemini-3.5-flash', contents=messages
    )
    logger.info(f"API response={response}")
    chatbot_message = response.text
    return {"content":chatbot_message, "timestamp": "", "id": ""}

def build_conversation(channel_id):
  token = os.environ["DISCORD_BOT_ACCESS_TOKEN"]
  url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
  headers = {
    "Authorization": f"Bot {token}"
  }

  r = requests.get(url, headers=headers)
  res = json.loads(r.text)

  conversation = []

  for message in res:
    if message["type"]==20 and not (int(message["flags"]) & (1 << 7)):
        conversation.append({
            'timestamp': dateutil.parser.parse(message['timestamp']),
            'prompt': message['embeds'][0]['description'],
            'response': message['embeds'][0]['fields'][0]['value']
        })

  ret = []
  for message in sorted(conversation, key=lambda k:k['timestamp']):
    ret.append({"role": "user", "content": message['prompt']})
    ret.append({"role": "assistant", "content": message['response']})

  return ret

def build_openai_messages(channel_id, channel_type, user_message):
  input_prompt = {
    "role": "system", "content": "あなたは優秀なアシスタントです。ユーザーからの質問に対し700から800文字程度で簡潔に回答します。",
    "role": "user", "content": f"{user_message}"
  }

  if channel_type==0: # default
    return [input_prompt]
  elif channel_type==11: # thread
    ret = build_conversation(channel_id)
    ret.append(input_prompt)
    return ret
  else:
    pass

def build_gemini_messages(channel_id, channel_type, user_message):

  if channel_type==0: # default
    return f"あなたは優秀なアシスタントです。ユーザーからの質問に対し700から800文字程度で簡潔に回答します。{user_message}"
  elif channel_type==11: # thread
    ret = build_conversation(channel_id)
    ret.append(user_message)
    return ret
  else:
    pass

def build_payload(prompt, response):
  payload = {
    "username": "お肉",
    "content": f"{prompt}",
    "embeds": [
      {
        "title"         : "回答",
        "description"   : response,
        "color"         : 5620992,
        "author": {
          "name"      : 'gemini-3.5-flash',
        },
#        "fields": [
#          {
#            "name"  : "回答",
#            "value" : response,
#          }
#        ]
      }
    ]
  }
  return json.dumps(payload, ensure_ascii=False)

def slice_by_byte_length(s: str, byte_length: int, encoding='utf-8') -> str:
    # Step 1: 文字列をバイト列に変換
    byte_data = s.encode(encoding)
    # Step 2: バイト列をスライス
    sliced_byte_data = byte_data[:byte_length]
    # Step 3: バイト列を再び文字列に変換
    # バイト列のスライスが途中で文字を切らないようにデコード可能な部分のみを取得
    try:
        decoded_string = sliced_byte_data.decode(encoding)
    except UnicodeDecodeError:
        # デコードエラーが発生した場合は、一つずつバイトを減らしてデコード可能な部分を取得
        for i in range(byte_length, 0, -1):
            try:
                decoded_string = sliced_byte_data[:i].decode(encoding)
                break
            except UnicodeDecodeError:
                continue


    logger.info(decoded_string)
    return decoded_string

def main(event, context):
  """Background Cloud Function to be triggered by Pub/Sub.
    Args:
      event (dict):  The dictionary with data specific to this type of
      event. The `data` field contains the PubsubMessage message. The
      `attributes` field will contain custom attributes if there are any.
      context (google.cloud.functions.Context): The Cloud Functions event
      metadata. The `event_id` field contains the Pub/Sub message ID. The
      `timestamp` field contains the publish time.
  """
  logger.info(f"Request={event}")

  if 'data' not in event:
    logger.error("No data in Pub/Sub message")
    return(False)

  message = json.loads(base64.b64decode(event['data']).decode('utf-8'))
  logger.info(f"Message={message}")

  user_message = message['message']
  chat_engine = message['engine']

  os.environ["OPENAI_MODEL_NAME"] = chat_engine

#  messages = build_openai_messages(message['channel_id'], message['channel_type'], user_message)
  messages = build_gemini_messages(message['channel_id'], message['channel_type'], user_message)
  logger.info(f"API input = {json.dumps(messages)}")
#  chatbot_response = generate_chatbot_response(messages)
  chatbot_response = generate_chatbot_response(messages)
  response = chatbot_response['content']
#  if len(response.encode('utf-8')) > DISCORD_MAX_POST_LENGTH:
  if len(response) > DISCORD_MAX_POST_LENGTH:
    logger.info(f"Message length exceeded: {len(response)}")
#    sliced_string = slice_by_byte_length(response, DISCORD_MAX_POST_LENGTH)
    sliced_string = response[::DISCORD_MAX_POST_LENGTH]
    response = sliced_string+"略"

  payload = {
    "payload_json" : build_payload(user_message, response)
  }

  application_id = message["application_id"]
  interaction_token = message["interaction_token"]
  discord_interaction_endpoint = f"https://discord.com/api/v10/webhooks/{application_id}/{interaction_token}"
  r = requests.post(discord_interaction_endpoint, data=payload)
  logger.info(r.text)
