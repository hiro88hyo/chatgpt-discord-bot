# Gemini Code Understanding

## Project Overview

This project is a Discord bot that integrates with OpenAI's ChatGPT and Google's Generative AI services. It's built as a serverless application running on Google Cloud Functions, with a separate frontend and backend.

## Architecture

The application is split into two main components:

*   **Frontend:** A Google Cloud Function triggered by HTTP requests. It's responsible for handling interactions from Discord, such as slash commands. It then publishes a message to a Pub/Sub topic to be processed by the backend.
*   **Backend:** A Google Cloud Function triggered by messages on a Pub/Sub topic. It processes the requests from the frontend, interacts with the OpenAI and Google Generative AI APIs, and likely sends the results back to the Discord channel.

## Technologies Used

### Frontend

*   **Python 3.11**
*   **Flask:** A lightweight web framework for Python.
*   **Google Cloud Functions:** To run the serverless frontend application.
*   **Google Cloud Pub/Sub:** To communicate with the backend.
*   **PyNaCl:** For Discord interaction security.

### Backend

*   **Python 3.11**
*   **Flask:** A lightweight web framework for Python.
*   **Google Cloud Functions:** To run the serverless backend application.
*   **Google Cloud Pub/Sub:** To receive messages from the frontend.
*   **OpenAI API:** To interact with ChatGPT.
*   **Google Generative AI API:** To interact with Google's generative models.

## Deployment

The application is deployed to Google Cloud using the `gcloud` command-line tool. The `README.md` file contains the specific commands for deploying both the frontend and backend functions.

### Frontend Deployment

The frontend is deployed as an HTTP-triggered Cloud Function.

### Backend Deployment

The backend is deployed as a Cloud Function triggered by a Pub/Sub topic named `openai_api_hook`.
