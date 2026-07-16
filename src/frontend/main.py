import os
import json
from flask import request, abort, jsonify
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError
import logging
import functions_framework
from google.cloud import pubsub_v1
from urllib.parse import urlparse

logging.basicConfig(
        format = "[%(asctime)s][%(levelname)s] %(message)s",
        level = logging.DEBUG
    )
logger = logging.getLogger()

def publish_pubsub_topic_chat(application_id, interaction_token, channel_id, channel_type, message, engine):
  publisher = pubsub_v1.PublisherClient()
  project_id = os.environ.get('GCP_PROJECT_ID')
  topic_name = os.environ.get('PUBSUB_TOPIC_CHAT')

  topic_path = publisher.topic_path(project_id,topic_name)

  data = {
    "application_id": application_id,
    "interaction_token": interaction_token,
    "channel_id": channel_id,
    "channel_type": channel_type,
    "message": message,
    "engine": engine
  }

  publisher.publish(topic_path, json.dumps(data).encode("utf-8"))

  return True

def publish_pubsub_topic_summary(application_id, interaction_token, channel_id, channel_type, url):
  publisher = pubsub_v1.PublisherClient()
  project_id = os.environ.get('GCP_PROJECT_ID')
  topic_name = os.environ.get('PUBSUB_TOPIC_SUMMARY')

  topic_path = publisher.topic_path(project_id,topic_name)

  data = {
    "application_id": application_id,
    "interaction_token": interaction_token,
    "channel_id": channel_id,
    "channel_type": channel_type,
    "url": url,
  }

  publisher.publish(topic_path, json.dumps(data).encode("utf-8"))

  return True

def validate_request(request):
    verify_key = VerifyKey(bytes.fromhex(os.environ.get('DISCORD_BOT_PUBLIC_KEY')))
    signature = request.headers["X-Signature-Ed25519"]
    timestamp = request.headers["X-Signature-Timestamp"]
    body = request.data.decode("utf-8")
    try:
        verify_key.verify(f"{timestamp}{body}".encode(), bytes.fromhex(signature))
    except BadSignatureError:
        return False
    return True

def is_url(text):
  try:
    result = urlparse(text)
    return all([result.scheme, result.netloc])  # scheme（http, httpsなど）とnetloc（ドメイン名）が存在するかチェック
  except ValueError:
    return False

@functions_framework.http
def main(request):

  if request.method == 'GET':
    return jsonify({"type": 1}), 200

  is_valid = validate_request(request)
  if not is_valid:
    return abort(401, "invalid request signature")

  body = json.loads(request.get_data(as_text=True))
  if body["type"] == 1: # PING
    return jsonify({"type": 1}), 200
  elif body["type"] == 2: # InteractionType.ApplicationCommand
    # command options list -> dict
    opts = {v["name"]: v['value'] for v in body["data"]["options"]} if "options" in body["data"] else {}

    response_type = 5 # InteractionResponseType.DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE
    bot_name = body["data"]["name"]

    if bot_name=="chat":
      if "prompt" in opts:
        response = opts["prompt"]
      else:
        response = "プロンプト入れてね"
      logger.info(f"body={body}")
      engine = opts["engine"] if "engine" in opts else "gpt-4o"
      is_publish = publish_pubsub_topic_chat(
        body["application_id"],
        body["token"],
        body["channel"]["id"],
        body["channel"]["type"],
        opts["prompt"],
        engine
      )
      response = "Invoke chat"
      if not is_publish:
        return abort(503, "Pub/Sub publish error")
      return {
        "type": response_type, # InteractionResponseType.DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE
        "data": {
          "content": response
          }
        }
    elif bot_name=="summary":
      if "url" in opts:
        text = opts["url"]
        if is_url(text):
          is_publish = publish_pubsub_topic_summary(
            body["application_id"],
            body["token"],
            body["channel"]["id"],
            body["channel"]["type"],
            text
          )
          response = "Invoke summary"
          if not is_publish:
            return abort(503, "Pub/Sub publish error")
        else:
          response_type = 4 # InteractionResponseType.CHANNEL_MESSAGE_WITH_SOURCE
          response = "URL入れてないでしょ"
      else:
        response_type = 4 # InteractionResponseType.CHANNEL_MESSAGE_WITH_SOURCE
        response = "URL入れてね"

      return {
        "type": response_type,
        "data": {
          "content": response
          }
        }

logger.info("Finished.")
