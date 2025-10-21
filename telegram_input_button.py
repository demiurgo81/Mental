import json
import os
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, scrolledtext
from typing import Any
from urllib import error, parse, request


CONFIG_FILENAME = "telegram_comm.json"
DIRECT_CHAT_KEY = "bot_chat_id"
GROUP_CHAT_KEY = "chat_id"
USERNAME_KEY = "bot_username"


class TelegramAPIError(Exception):
    def __init__(self, description: str) -> None:
        super().__init__(description)
        self.description = description


class TelegramInputApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Telegram Bot Inbox")
        self.resizable(False, False)

        self.config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), CONFIG_FILENAME
        )
        self.config_data: dict[str, str] = {}
        self.last_update_id: int | None = None

        self._build_widgets()
        self._load_config()
        self._refresh_state()

    # UI ------------------------------------------------------------------ #
    def _build_widgets(self) -> None:
        self.columnconfigure(0, weight=1)

        # Config frame (hidden when data is complete)
        self.config_frame = tk.Frame(self, padx=12, pady=12)
        self.config_frame.columnconfigure(1, weight=1)

        tk.Label(self.config_frame, text="Token del bot:").grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )
        self.token_entry = tk.Entry(self.config_frame, width=45)
        self.token_entry.grid(row=0, column=1, sticky="ew", pady=(0, 6))

        tk.Label(self.config_frame, text="ID chat directo (bot_chat_id):").grid(
            row=1, column=0, sticky="w"
        )
        self.direct_chat_entry = tk.Entry(self.config_frame, width=45)
        self.direct_chat_entry.grid(row=1, column=1, sticky="ew", pady=(0, 6))

        tk.Label(self.config_frame, text="ID chat grupal (chat_id):").grid(
            row=2, column=0, sticky="w"
        )
        self.group_chat_entry = tk.Entry(self.config_frame, width=45)
        self.group_chat_entry.grid(row=2, column=1, sticky="ew", pady=(0, 6))

        tk.Label(self.config_frame, text="Usuario del bot (@...):").grid(
            row=3, column=0, sticky="w"
        )
        self.username_entry = tk.Entry(self.config_frame, width=45)
        self.username_entry.grid(row=3, column=1, sticky="ew")

        self.save_button = tk.Button(
            self.config_frame, text="Guardar configuración", command=self._save_config
        )
        self.save_button.grid(row=4, column=0, columnspan=2, pady=(10, 0))

        # Messages + controls
        self.message_frame = tk.Frame(self, padx=12, pady=12)
        self.message_frame.columnconfigure(0, weight=1)

        tk.Label(self.message_frame, text="Mensajes recientes:").grid(
            row=0, column=0, sticky="w"
        )
        self.messages_box = scrolledtext.ScrolledText(
            self.message_frame,
            width=70,
            height=18,
            wrap="word",
            state="disabled",
        )
        self.messages_box.grid(row=1, column=0, sticky="nsew", pady=(4, 8))
        self.message_frame.rowconfigure(1, weight=1)

        controls = tk.Frame(self.message_frame)
        controls.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        controls.columnconfigure(2, weight=1)

        self.fetch_button = tk.Button(
            controls, text="Actualizar mensajes", command=self._on_fetch
        )
        self.fetch_button.grid(row=0, column=0, padx=(0, 8))

        tk.Label(controls, text="Destino:").grid(row=0, column=1, sticky="w")
        self.destination_var = tk.StringVar(value=DIRECT_CHAT_KEY)
        tk.Radiobutton(
            controls,
            text="Bot",
            variable=self.destination_var,
            value=DIRECT_CHAT_KEY,
        ).grid(row=0, column=2, sticky="w")
        tk.Radiobutton(
            controls,
            text="Grupo",
            variable=self.destination_var,
            value=GROUP_CHAT_KEY,
        ).grid(row=0, column=3, sticky="w", padx=(8, 0))

        # Send area
        sender = tk.Frame(self.message_frame)
        sender.grid(row=3, column=0, sticky="ew")
        sender.columnconfigure(0, weight=1)

        tk.Label(sender, text="Mensaje a enviar:").grid(row=0, column=0, sticky="w")
        self.outgoing_text = tk.Text(sender, height=4, wrap="word")
        self.outgoing_text.grid(row=1, column=0, sticky="ew", pady=(4, 4))

        self.send_button = tk.Button(sender, text="Enviar", command=self._on_send)
        self.send_button.grid(row=2, column=0, sticky="e")

    # Config -------------------------------------------------------------- #
    def _load_config(self) -> None:
        if not os.path.exists(self.config_path):
            self.config_data = {}
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (json.JSONDecodeError, OSError) as exc:
            messagebox.showwarning(
                "Configuración no válida",
                f"No se pudo leer el archivo de configuración.\nDetalle: {exc}",
            )
            self.config_data = {}
            return

        token = str(data.get("bot_token", "")).strip()
        direct_chat = str(data.get(DIRECT_CHAT_KEY, "")).strip()
        group_chat = str(data.get(GROUP_CHAT_KEY, "")).strip()
        username = str(data.get(USERNAME_KEY, "")).strip()

        if token and direct_chat and group_chat:
            self.config_data = {
                "bot_token": token,
                DIRECT_CHAT_KEY: direct_chat,
                GROUP_CHAT_KEY: group_chat,
            }
            if username:
                self.config_data[USERNAME_KEY] = username
        else:
            self.config_data = {}

    def _save_config(self) -> None:
        token = self.token_entry.get().strip()
        direct_chat = self.direct_chat_entry.get().strip()
        group_chat = self.group_chat_entry.get().strip()
        username = self.username_entry.get().strip()

        if not token or not direct_chat or not group_chat:
            messagebox.showerror(
                "Datos incompletos",
                "Ingresa token, bot_chat_id y chat_id.",
            )
            return

        self.config_data = {
            "bot_token": token,
            DIRECT_CHAT_KEY: direct_chat,
            GROUP_CHAT_KEY: group_chat,
        }
        if username:
            self.config_data[USERNAME_KEY] = username

        try:
            with open(self.config_path, "w", encoding="utf-8") as handle:
                json.dump(self.config_data, handle, ensure_ascii=True, indent=2)
        except OSError as exc:
            messagebox.showerror(
                "Error al guardar",
                f"No se pudo escribir la configuración.\nDetalle: {exc}",
            )
            self.config_data = {}
            return

        self.last_update_id = None
        messagebox.showinfo(
            "Configuración guardada",
            "Los datos se guardaron correctamente.",
        )
        self._refresh_state()

    def _refresh_state(self) -> None:
        has_config = bool(self.config_data)
        if has_config:
            self.config_frame.pack_forget()
            self.fetch_button.configure(state="normal")
            self.send_button.configure(state="normal")
        else:
            self.token_entry.delete(0, tk.END)
            self.direct_chat_entry.delete(0, tk.END)
            self.group_chat_entry.delete(0, tk.END)
            self.username_entry.delete(0, tk.END)
            self.config_frame.pack(fill="x")
            self.fetch_button.configure(state="disabled")
            self.send_button.configure(state="disabled")

        if not self.message_frame.winfo_ismapped():
            self.message_frame.pack(fill="both", expand=True)

    # Actions ------------------------------------------------------------- #
    def _on_fetch(self) -> None:
        token = self.config_data.get("bot_token", "")
        direct_chat = self.config_data.get(DIRECT_CHAT_KEY, "")
        group_chat = self.config_data.get(GROUP_CHAT_KEY, "")
        if not (token and direct_chat and group_chat):
            messagebox.showerror(
                "Configuración faltante",
                "Configura token, bot_chat_id y chat_id antes de continuar.",
            )
            self._refresh_state()
            return

        self.fetch_button.configure(state="disabled")
        try:
            messages = self._get_recent_messages(token, direct_chat, group_chat)
        except TelegramAPIError as exc:
            messagebox.showerror("Error al consultar", exc.description)
        except OSError as exc:
            messagebox.showerror(
                "Error de red",
                f"No se pudo contactar con Telegram.\nDetalle: {exc}",
            )
        else:
            if messages:
                self._append_messages(messages)
            else:
                messagebox.showinfo("Sin novedades", "No hay mensajes nuevos.")
        finally:
            self.fetch_button.configure(state="normal")

    def _on_send(self) -> None:
        token = self.config_data.get("bot_token", "")
        direct_chat = self.config_data.get(DIRECT_CHAT_KEY, "")
        group_chat = self.config_data.get(GROUP_CHAT_KEY, "")
        if not (token and direct_chat and group_chat):
            messagebox.showerror(
                "Configuración faltante",
                "Configura token, bot_chat_id y chat_id antes de continuar.",
            )
            self._refresh_state()
            return

        message = self.outgoing_text.get("1.0", tk.END).strip()
        if not message:
            messagebox.showerror("Mensaje vacío", "Escribe un mensaje para enviarlo.")
            return

        target_key = self.destination_var.get()
        chat_id = direct_chat if target_key == DIRECT_CHAT_KEY else group_chat
        try:
            self._send_to_telegram(token, chat_id, message)
        except TelegramAPIError as exc:
            messagebox.showerror("Error al enviar", exc.description)
            return
        except OSError as exc:
            messagebox.showerror(
                "Error de red",
                f"No se pudo contactar con Telegram.\nDetalle: {exc}",
            )
            return

        self.outgoing_text.delete("1.0", tk.END)
        messagebox.showinfo("Enviado", "Mensaje enviado correctamente.")

    # Helpers ------------------------------------------------------------- #
    def _append_messages(self, messages: list[str]) -> None:
        self.messages_box.configure(state="normal")
        for entry in messages:
            self.messages_box.insert(tk.END, f"{entry}\n")
        self.messages_box.configure(state="disabled")
        self.messages_box.see(tk.END)

    def _get_recent_messages(
        self, token: str, direct_chat: str, group_chat: str
    ) -> list[str]:
        api_url = f"https://api.telegram.org/bot{token}/getUpdates"
        params: dict[str, str] = {"limit": "50"}
        if self.last_update_id is not None:
            params["offset"] = str(self.last_update_id + 1)
        query = parse.urlencode(params)
        url = f"{api_url}?{query}"

        req = request.Request(url)
        try:
            with request.urlopen(req, timeout=10) as response:
                body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            description = _extract_description(body) or f"HTTP {exc.code}"
            raise TelegramAPIError(description) from exc
        except error.URLError as exc:
            raise OSError(exc.reason) from exc

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise TelegramAPIError("Respuesta inesperada de Telegram.") from exc

        if not parsed.get("ok", False):
            detail = parsed.get("description") or "Error desconocido."
            raise TelegramAPIError(detail)

        updates = parsed.get("result", [])
        if not isinstance(updates, list):
            raise TelegramAPIError("Formato de respuesta inválido.")

        targets = {
            str(direct_chat): "Directo",
            str(group_chat): "Grupo",
        }
        entries: list[str] = []
        for update in updates:
            if not isinstance(update, dict):
                continue

            update_id = update.get("update_id")
            if isinstance(update_id, int):
                if self.last_update_id is None or update_id > self.last_update_id:
                    self.last_update_id = update_id

            message = self._extract_message_from_update(update)
            if not message:
                continue

            chat = message.get("chat", {})
            chat_id = str(chat.get("id", ""))
            if chat_id not in targets:
                continue

            text, content_type = self._extract_text(message)
            if not text:
                continue

            timestamp = self._format_timestamp(message.get("date"))
            author = self._format_author(message.get("from"))
            mention_tag = ""
            if self._is_mention(message):
                mention_tag = " [MENCION]"

            entries.append(
                f"[{timestamp}] [{targets[chat_id]}]{mention_tag} {author} ({content_type}): {text}"
            )

        return entries

    def _extract_message_from_update(self, update: dict[str, Any]) -> dict[str, Any] | None:
        for key in ("message", "edited_message", "channel_post", "edited_channel_post"):
            candidate = update.get(key)
            if isinstance(candidate, dict):
                return candidate
        callback = update.get("callback_query")
        if isinstance(callback, dict):
            message = callback.get("message")
            if isinstance(message, dict):
                message.setdefault("text", f"[Callback data: {callback.get('data', '')}]")
                return message
        return None

    def _extract_text(self, message: dict[str, Any]) -> tuple[str, str]:
        text_fields = (
            ("text", "texto"),
            ("caption", "media"),
            ("poll", "encuesta"),
        )
        for key, label in text_fields:
            value = message.get(key)
            if not value:
                continue
            if key == "poll" and isinstance(value, dict):
                question = value.get("question", "")
                return (f"[Encuesta] {question}", label)
            return (str(value), label)

        if "photo" in message or "document" in message:
            return ("[Archivo sin texto]", "archivo")

        return ("", "")

    def _format_timestamp(self, date_value: Any) -> str:
        try:
            return datetime.fromtimestamp(int(date_value)).strftime("%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError):
            return "sin fecha"

    def _format_author(self, data: Any) -> str:
        if not isinstance(data, dict):
            return "Desconocido"
        username = data.get("username") or ""
        first_name = data.get("first_name") or ""
        last_name = data.get("last_name") or ""
        full_name = " ".join(part for part in [first_name, last_name] if part).strip()
        return f"@{username}" if username else (full_name or "Desconocido")

    def _is_mention(self, message: dict[str, Any]) -> bool:
        username = self.config_data.get(USERNAME_KEY, "")
        text = message.get("text") or message.get("caption") or ""

        entities = message.get("entities") or message.get("caption_entities")
        if isinstance(entities, list):
            for entity in entities:
                if not isinstance(entity, dict):
                    continue
                entity_type = entity.get("type")
                if entity_type not in {"mention", "text_mention"}:
                    continue
                if entity_type == "mention" and username:
                    offset = entity.get("offset", 0)
                    length = entity.get("length", 0)
                    try:
                        mention = text[offset : offset + length]
                    except Exception:  # noqa: BLE001 - slicing safeguard
                        mention = ""
                    if mention.lower() == f"@{username}".lower():
                        return True
                else:
                    return True

        if username and f"@{username}".lower() in text.lower():
            return True

        return False

    def _send_to_telegram(self, token: str, chat_id: str, text: str) -> None:
        api_url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")

        req = request.Request(api_url, data=payload, method="POST")
        try:
            with request.urlopen(req, timeout=10) as response:
                body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            description = _extract_description(body) or f"HTTP {exc.code}"
            raise TelegramAPIError(description) from exc
        except error.URLError as exc:
            raise OSError(exc.reason) from exc

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise TelegramAPIError("Respuesta inesperada de Telegram.") from exc

        if not parsed.get("ok", False):
            detail = parsed.get("description") or "Error desconocido."
            raise TelegramAPIError(detail)


def _extract_description(payload: str) -> str:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return ""
    description = data.get("description")
    return str(description) if description else ""


def main() -> None:
    app = TelegramInputApp()
    app.mainloop()


if __name__ == "__main__":
    main()
