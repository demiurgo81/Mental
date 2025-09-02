import tkinter as tk
from tkinter import filedialog, messagebox
from threading import Thread, Event
import time
from datetime import datetime, timedelta
import subprocess
import sys

class SchedulerApp:
    def __init__(self, master):
        self.master = master
        master.title("Programador de Scripts")

        # Variables para controlar la ejecución
        self.stop_event = Event()
        self.scheduler_thread = None

        # Configuración de la interfaz
        self.create_widgets()

    def create_widgets(self):
        # Campo para la hora
        tk.Label(self.master, text="Hora (formato 24h HH:MM):").pack(pady=5)
        self.time_entry = tk.Entry(self.master, width=25)
        self.time_entry.pack(pady=5)

        # Campo para el script
        tk.Label(self.master, text="Script Python:").pack(pady=5)
        self.script_entry = tk.Entry(self.master, width=25)
        self.script_entry.pack(pady=5)
        tk.Button(self.master, text="Examinar", command=self.browse_script).pack(pady=5)

        # Botones de control
        self.start_btn = tk.Button(self.master, text="Iniciar", command=self.start_scheduling)
        self.start_btn.pack(pady=10)
        self.stop_btn = tk.Button(self.master, text="Detener", command=self.stop_scheduling, state=tk.DISABLED)
        self.stop_btn.pack(pady=10)

        # Manejar cierre de ventana
        self.master.protocol("WM_DELETE_WINDOW", self.on_close)

    def browse_script(self):
        filepath = filedialog.askopenfilename(filetypes=[("Python Files", "*.py")])
        if filepath:
            self.script_entry.delete(0, tk.END)
            self.script_entry.insert(0, filepath)

    def validate_inputs(self):
        # Validar formato de hora
        try:
            datetime.strptime(self.time_entry.get(), "%H:%M")
        except ValueError:
            messagebox.showerror("Error", "Formato de hora inválido. Use HH:MM (24h)")
            return False

        # Validar archivo Python
        if not self.script_entry.get().endswith('.py'):
            messagebox.showerror("Error", "Seleccione un archivo .py válido")
            return False

        return True

    def start_scheduling(self):
        if not self.validate_inputs():
            return

        self.stop_event.clear()
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)

        # Obtener parámetros
        target_time = datetime.strptime(self.time_entry.get(), "%H:%M").time()
        script_path = self.script_entry.get()

        # Iniciar hilo programador
        self.scheduler_thread = Thread(
            target=self.schedule_task,
            args=(target_time, script_path),
            daemon=True
        )
        self.scheduler_thread.start()

    def stop_scheduling(self):
        self.stop_event.set()
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

    def schedule_task(self, target_time, script_path):
        while not self.stop_event.is_set():
            now = datetime.now()
            target = datetime.combine(now.date(), target_time)

            # Si la hora ya pasó hoy, programar para mañana
            if target < now:
                target += timedelta(days=1)

            # Calcular segundos restantes
            wait_seconds = (target - now).total_seconds()

            # Esperar en intervalos cortos para permitir parada
            while wait_seconds > 0 and not self.stop_event.is_set():
                time.sleep(1)
                wait_seconds -= 1

            # Ejecutar script si no se ha detenido
            if not self.stop_event.is_set():
                try:
                    subprocess.run([sys.executable, script_path], check=True)
                except Exception as e:
                    messagebox.showerror("Error", f"Error al ejecutar script: {str(e)}")

                # Programar próxima ejecución
                target += timedelta(days=1)

    def on_close(self):
        self.stop_scheduling()
        self.master.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = SchedulerApp(root)
    root.mainloop()