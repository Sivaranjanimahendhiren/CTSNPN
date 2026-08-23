"""
Adaptive AI Nurse - Telegram Bot Runner (MVC Entrypoint).
Listens to Telegram updates, delegates business logic to BotController,
and renders responses via TelegramView and ConsoleTraceView.
"""

import os
import sys
import time
import re
from typing import Optional
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from adaptive_postcare.controllers.bot_controller import BotController
from adaptive_postcare.views.telegram_view import TelegramView
from adaptive_postcare.views.console_view import ConsoleTraceView, safe_console_print


class TelegramBotRunner:
    """
    Main Runner connecting Telegram API events to MVC Controllers and Views.
    """

    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.controller = BotController()

    def send_chat_action(self, chat_id: int, action: str = "typing"):
        """Sends typing status indicator to Telegram."""
        url = f"{self.base_url}/sendChatAction"
        try:
            requests.post(url, json={"chat_id": chat_id, "action": action}, timeout=5)
        except Exception:
            pass

    def send_message(self, chat_id: int, text: str, parse_mode: Optional[str] = "Markdown"):
        """Dispatches message to Telegram user."""
        url = f"{self.base_url}/sendMessage"
        payload = {"chat_id": chat_id, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode

        try:
            r = requests.post(url, json=payload, timeout=10)
            res_json = r.json()
            if not res_json.get("ok"):
                # Fallback to plain text if Markdown format encounters unescaped characters
                if parse_mode:
                    payload.pop("parse_mode", None)
                    requests.post(url, json=payload, timeout=10)
                else:
                    safe_console_print(f"[Telegram API Error]: {res_json.get('description')}")
        except Exception as e:
            safe_console_print(f"[Send Error]: {e}")

    def start(self):
        """Starts real-time long polling on Telegram."""
        ConsoleTraceView.print_startup_banner(
            llm_count=len(self.controller.llm_pool),
            patient_count=10,
        )

        offset = 0
        while True:
            try:
                url = f"{self.base_url}/getUpdates?offset={offset}&timeout=15"
                resp = requests.get(url, timeout=20).json()

                if not resp.get("ok"):
                    time.sleep(1)
                    continue

                for update in resp.get("result", []):
                    offset = update["update_id"] + 1
                    msg = update.get("message")
                    if not msg or "text" not in msg:
                        continue

                    chat_id = msg["chat"]["id"]
                    user_name = msg["from"].get("first_name", "Patient")
                    user_text = msg["text"].strip()

                    safe_console_print(f"\n[Telegram Incoming] {user_name} ({chat_id}): {user_text}")

                    # 1. COMMAND: /start or /help
                    if user_text.lower() in ["/start", "start", "/help", "help"]:
                        active_pid = self.controller.get_patient_for_chat(chat_id)
                        self.controller.ensure_patient_activated(active_pid)
                        welcome_msg = TelegramView.format_welcome_message(user_name, active_pid)
                        self.send_message(chat_id, welcome_msg)
                        self.controller.save_conversation(chat_id, "assistant", welcome_msg, active_pid)
                        continue

                    # 1b. MORNING CHECK-IN GREETING: hi, hey, hello, good morning, good morning elena, etc.
                    clean_lower = re.sub(r"[^\w\s]", "", user_text.lower()).strip()
                    is_greeting = (
                        clean_lower in ["hi", "hey", "hello", "good morning", "morning", "checkin", "check in"]
                        or any(clean_lower.startswith(g) for g in ["good morning", "morning", "hi el", "hello el", "hey el"])
                        or clean_lower in ["good morning elena", "good morning elna", "hi elena", "hello elena", "hey elena"]
                    )
                    if is_greeting and len(user_text.split()) <= 4:
                        self.send_chat_action(chat_id, "typing")
                        morning_greeting = self.controller.get_morning_greeting(chat_id, user_name)
                        safe_console_print(f"[AI Nurse -> {user_name} (Morning Check-in)]: {morning_greeting}\n")
                        self.send_message(chat_id, morning_greeting)
                        continue

                    # 2. COMMAND: /patient <id>
                    if user_text.lower().startswith("/patient ") or user_text.lower().startswith("/select "):
                        parts = user_text.split()
                        if len(parts) > 1:
                            new_pid = parts[1].strip().upper()
                            self.controller.set_patient_for_chat(chat_id, new_pid)
                            switch_msg = TelegramView.format_patient_switch(new_pid)
                            self.send_message(chat_id, switch_msg)
                        else:
                            self.send_message(chat_id, "Usage: `/patient P001` or `/patient P005`")
                        continue

                    # 3. COMMAND: /status
                    if user_text.lower() in ["/status", "status"]:
                        status_card = self.controller.get_status_view(chat_id)
                        self.send_message(chat_id, status_card)
                        continue

                    # 4. COMMAND: /history
                    if user_text.lower() in ["/history", "history"]:
                        history_summary = self.controller.get_history_view(chat_id)
                        self.send_message(chat_id, history_summary)
                        continue

                    # 5. COMMAND: /plan
                    if user_text.lower() in ["/plan", "plan"]:
                        plan_details = self.controller.get_care_plan_view(chat_id)
                        self.send_message(chat_id, plan_details)
                        continue

                    # 6. COMMAND: /reset
                    if user_text.lower() in ["/reset", "reset"]:
                        active_pid = self.controller.get_patient_for_chat(chat_id)
                        self.controller.sessions.pop(chat_id, None)
                        reset_msg = f"🔄 Conversation reset for Patient `{active_pid}`. How are you feeling today?"
                        self.send_message(chat_id, reset_msg)
                        continue

                    # 7. CLINICAL RECOVERY UPDATE -> 7-Node LangGraph State Machine
                    self.send_chat_action(chat_id, "typing")
                    nurse_reply = self.controller.process_incoming_message(chat_id, user_text)
                    safe_console_print(f"[AI Nurse -> {user_name}]: {nurse_reply}\n")
                    self.send_message(chat_id, nurse_reply)

            except KeyboardInterrupt:
                safe_console_print("\n[*] Stopping Telegram Bot...")
                break
            except Exception as e:
                safe_console_print(f"[Polling Loop Exception]: {e}")
                time.sleep(2)


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token or token == "YOUR_TELEGRAM_BOT_TOKEN":
        safe_console_print("\n[?] Enter your Telegram Bot Token from @BotFather:")
        token = input("Token: ").strip()

    if not token:
        safe_console_print("Error: No Telegram bot token provided.")
        sys.exit(1)

    runner = TelegramBotRunner(token)
    runner.start()


if __name__ == "__main__":
    main()
