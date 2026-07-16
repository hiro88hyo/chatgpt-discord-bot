# project

# deploy command
## frontend
gcloud functions deploy chatgpt-api-discord --runtime=python311 --trigger-http --entry-point=main --env-vars-file=.env --allow-unauthenticated

gcloud functions deploy chatgpt-api-discord \
--gen2 \
--trigger-http \
--allow-unauthenticated \
--region=asia-northeast1 \
--runtime=python311 \
--source=. \
--entry-point=main \
--env-vars-file=.env

## backend
gcloud functions deploy chatgpt-api-discord-backend --trigger-topic openai_api_hook --runtime=python311 --entry-point=main --env-vars-file=.env

gcloud functions deploy chatgpt-api-discord-backend \
--gen2 \
--trigger-topic openai_api_hook \
--region=asia-northeast1 \
--runtime=python311 \
--source=. \
--entry-point=main \
--env-vars-file=.env


gcloud projects add-iam-policy-binding chatgpt-line-bot-382200 --member=serviceAccount:service-340388323004@gcp-sa-pubsub.iam.gserviceaccount.com --role=roles/iam.serviceAccountTokenCreator

gcloud beta services identity create --project chatgpt-line-bot-382200 --service pubsub