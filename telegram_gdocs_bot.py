#!/usr/bin/env python3
import time
import asyncio
import schedule
import logging
from telegram.ext import ExtBot
import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

DOC_SCOPES = ["https://www.googleapis.com/auth/documents.readonly"]
DOC_ID = "xxxxxx"  # Replace with your Google Doc ID
BOT_TOKEN = open("bot_token.json").read().strip()[1:-1]
BOT_CHAT_ID_TEST = "-1000"  # Replace with your Telegram chat ID for testing
BOT_CHAT_ID_PROD = "-1000"  # Replace with your Telegram chat ID for production
BOT_CHAT_ID = BOT_CHAT_ID_PROD
USER_MAP = {
    "Szymon": "🦜 @dsonyy",
}
BOT_MSG_MAX_LEN = 4096
DOC_HEADER_BLACKLIST = ["Backlog"]


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


def get_google_api_creds():
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", DOC_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Workaround: https://stackoverflow.com/questions/71318804/google-oauth-2-0-failing-with-error-400-invalid-request-for-some-client-id-but/71491500#71491500
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json",
                DOC_SCOPES,
                redirect_uri='http://localhost:1/',
            )
            auth_url, _ = creds = flow.authorization_url(prompt="consent")
            print("Please go to this URL and authorize the app:")
            print(auth_url)
            code = input("Enter the auth code: ")
            flow.fetch_token(code=code)

            creds = flow.credentials

        with open("token.json", "w") as token:
            token.write(creds.to_json())
            logger.info("Saving Google API creds...")

    return creds


def fetch_todo_list_doc():
    creds = get_google_api_creds()
    try:
        service = build("docs", "v1", credentials=creds)

        document = service.documents().get(documentId=DOC_ID).execute()

        return document.get("body").get("content")
    except HttpError as err:
        print(err)
        return None


def parse_todo_list_doc(doc):
    todo_list = {}

    user = ""
    cnt = 1
    for item in doc:
        try:
            if item["paragraph"]["paragraphStyle"]["namedStyleType"] == "HEADING_2":
                user = item["paragraph"]["elements"][0]["textRun"]["content"].strip()
                if user not in DOC_HEADER_BLACKLIST:
                    todo_list[user] = f"{USER_MAP[user]}\n"
                cnt = 1
                continue
        except KeyError:
            continue

        if user and user not in DOC_HEADER_BLACKLIST:
            todo_item = ""

            for element in item["paragraph"]["elements"]:
                try:
                    todo_item += element["textRun"]["content"]
                except KeyError:
                    continue

            if todo_item.strip():
                todo_item = f"{cnt}. " + todo_item.strip() + "\n"
                cnt += 1
                todo_list[user] += f"{todo_item}"

    return "\n".join(todo_list.values())


def build_todo_list_reminder_message():
    doc = fetch_todo_list_doc()
    todo_list = parse_todo_list_doc(doc)

    msg = "Hej, czy aby na pewno się nie opierdalasz? 👀\n" \
        "\n" \
        "Może zamiast klikać w ten telefon upewnisz się, że wszystkie taski są gotowe? " \
        "CleverHive potrzebuje Twojej pomocy w następujących sprawach:\n" \
        f"\n{todo_list}\n" \
        "Jazda do roboty 😎 Zyski same się nie zarobią 🔥\n"

    return msg


def fragment_todo_list_reminder_message(msg):
    splitted = msg.split("\n\n")

    msgs = [""]
    for s in splitted:
        if len(msgs[-1]) + len(s) < BOT_MSG_MAX_LEN:
            msgs[-1] += s + "\n\n"
        else:
            msgs.append(s + "\n\n")

    return msgs


def send_todo_list_reminder(bot):
    msg = build_todo_list_reminder_message()

    if len(msg) > BOT_MSG_MAX_LEN:
        msgs = fragment_todo_list_reminder_message(msg)
    else:
        msgs = [msg]

    loop = asyncio.get_event_loop()
    for msg in msgs:
        loop.run_until_complete(
            bot.send_message(
                chat_id=BOT_CHAT_ID,
                text=msg,
                disable_web_page_preview=True,
            ))


def send_hello_world(bot):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        bot.send_message(
            chat_id=BOT_CHAT_ID_TEST,
            text="Hello 🍎",
            disable_web_page_preview=True,
        ))


def main():
    logger.info("Starting bot...")
    bot = ExtBot(token=BOT_TOKEN)

    logger.info("Getting Google API creds...")
    get_google_api_creds()
    # schedule.every().minute.at(":00").do(send_todo_list_reminder, bot)
    schedule.every().saturday.at("21:37").do(send_todo_list_reminder, bot)

    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == '__main__':
    while True:
        try:
            main()
        except KeyboardInterrupt:
            logger.info("Stopping bot...")
            exit()
        except Exception as e:
            logger.exception(e)
            time.sleep(1)
            logger.info("Restarting bot...")
