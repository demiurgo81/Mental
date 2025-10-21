import json
import os
import tkinter as tk
from tkinter import messagebox
from urllib import error, parse, request


CONFIG_FILENAME = "telegram_comm.json"


class TelegramAPIError(Exception):
    """Raised when Telegram returns an error response."""

    def __init__(self, description: str) -> None:
        super().__init__(description)
        self.description = description


class TelegramApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Telegram Bot Sender")
        self.resizable(False, False)

        self.config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), CONFIG_FILENAME
        )
        self.config_data: dict[str, str] = {}

        self._build_widgets()
        self._load_config()
        self._refresh_state()

    def _build_widgets(self) -> None:
        self.columnconfigure(0, weight=1)

        self.config_frame = tk.Frame(self, padx=12, pady=12)
        self.config_frame.columnconfigure(1, weight=1)

        tk.Label(self.config_frame, text="Token del bot:").grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )
        self.token_entry = tk.Entry(self.config_frame, width=40)
        self.token_entry.grid(row=0, column=1, sticky="ew", pady=(0, 6))

        tk.Label(self.config_frame, text="ID del chat:").grid(
            row=1, column=0, sticky="w"
        )
        self.chat_entry = tk.Entry(self.config_frame, width=40)
        self.chat_entry.grid(row=1, column=1, sticky="ew")

        self.save_button = tk.Button(
            self.config_frame, text="Guardar configuración", command=self._save_config
        )
        self.save_button.grid(row=2, column=0, columnspan=2, pady=(10, 0))

        self.message_frame = tk.Frame(self, padx=12, pady=12)
        tk.Label(self.message_frame, text="Mensaje:").grid(
            row=0, column=0, sticky="w"
        )
        self.message_text = tk.Text(self.message_frame, width=50, height=10, wrap="word")
        self.message_text.grid(row=1, column=0, sticky="nsew", pady=(4, 8))
        self.message_frame.rowconfigure(1, weight=1)

        self.send_button = tk.Button(
            self.message_frame, text="Enviar", command=self._on_send
        )
        self.send_button.grid(row=2, column=0, sticky="e")

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
        chat_id = str(data.get("chat_id", "")).strip()
        if token and chat_id:
            self.config_data = {"bot_token": token, "chat_id": chat_id}
        else:
            self.config_data = {}

    def _save_config(self) -> None:
        token = self.token_entry.get().strip()
        chat_id = self.chat_entry.get().strip()
        if not token or not chat_id:
            messagebox.showerror(
                "Datos incompletos",
                "Por favor ingresa el token del bot y el ID del chat.",
            )
            return

        self.config_data = {"bot_token": token, "chat_id": chat_id}
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

        messagebox.showinfo(
            "Configuración guardada",
            "Los datos del bot se guardaron correctamente.",
        )
        self._refresh_state()

    def _refresh_state(self) -> None:
        has_config = bool(self.config_data)
        if has_config:
            self.config_frame.pack_forget()
            self.send_button.configure(state="normal")
        else:
            self.token_entry.delete(0, tk.END)
            self.chat_entry.delete(0, tk.END)
            self.config_frame.pack(fill="x")
            self.send_button.configure(state="disabled")

        if not self.message_frame.winfo_ismapped():
            self.message_frame.pack(fill="both", expand=True)

    def _on_send(self) -> None:
        message = self.message_text.get("1.0", tk.END).strip()
        if not message:
            messagebox.showerror(
                "Mensaje vacío", "Escribe un mensaje antes de enviarlo."
            )
            return

        token = self.config_data.get("bot_token", "")
        chat_id = self.config_data.get("chat_id", "")
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

        messagebox.showinfo("Enviado", "Mensaje enviado correctamente.")
        self.message_text.delete("1.0", tk.END)

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

        description = _extract_description(body)
        if not description:
            description = ""

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise TelegramAPIError(
                "Respuesta inesperada de Telegram."
            ) from exc

        if not parsed.get("ok", False):
            detail = parsed.get("description") or description or "Error desconocido."
            raise TelegramAPIError(detail)


def _extract_description(payload: str) -> str:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return ""
    description = data.get("description")
    return str(description) if description else ""


def main() -> None:
    app = TelegramApp()
    app.mainloop()


if __name__ == "__main__":
    main()
