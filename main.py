
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import subprocess
import platform
import json
import os
import time
import smtplib

from datetime import datetime
from email.message import EmailMessage
from concurrent.futures import ThreadPoolExecutor, as_completed


# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

CONFIG_FILE = "config.json"

# Intervalo entre ciclos completos de monitoreo
PING_INTERVAL = 4

# Número de fallos consecutivos antes de declarar DOWN
MAX_FAILURES = 3

# Configuración SMTP Microsoft 365
SMTP_SERVER = "smtp.office365.com"
SMTP_PORT = 587

# Cantidad máxima de pings simultáneos
MAX_WORKERS = 14


# ============================================================
# AGENCIAS PREDETERMINADAS
# ============================================================

DEFAULT_AGENCIES = [
    {
        "name": "Agencia Central",
        "links": [
            {
                "name": "Enlace Tigo",
                "ip": "192.0.2.11"
            },
            {
                "name": "Enlace Claro",
                "ip": "198.51.100.11"
            }
        ]
    },
    {
        "name": "Agencia Mercados",
        "links": [
            {
                "name": "Enlace Tigo",
                "ip": "192.0.2.12"
            },
            {
                "name": "Enlace Claro",
                "ip": "198.51.100.12"
            }
        ]
    },
    {
        "name": "Agencia Gotera",
        "links": [
            {
                "name": "Enlace Tigo",
                "ip": "192.0.2.13"
            },
            {
                "name": "Enlace Claro",
                "ip": "198.51.100.13"
            }
        ]
    },
    {
        "name": "Agencia Usulutan",
        "links": [
            {
                "name": "Enlace Tigo",
                "ip": "192.0.2.14"
            },
            {
                "name": "Enlace Claro",
                "ip": "198.51.100.14"
            }
        ]
    },
    {
        "name": "Agencia La Union",
        "links": [
            {
                "name": "Enlace Tigo",
                "ip": "192.0.2.15"
            },
            {
                "name": "Enlace Claro",
                "ip": "198.51.100.15"
            }
        ]
    },
    {
        "name": "Agencia San Vicente",
        "links": [
            {
                "name": "Enlace Tigo",
                "ip": "192.0.2.16"
            },
            {
                "name": "Enlace Claro",
                "ip": "198.51.100.16"
            }
        ]
    },
    {
        "name": "Agencia San Salvador",
        "links": [
            {
                "name": "Enlace Tigo",
                "ip": "192.0.2.17"
            },
            {
                "name": "Enlace Claro",
                "ip": "198.51.100.17"
            }
        ]
    }
]


# ============================================================
# VARIABLES GLOBALES
# ============================================================

root = None

running = False
monitor_thread = None

# Correo
email_account = ""
email_password = ""
alert_recipient = ""

# Estados
link_states = {}
failure_counts = {}
down_since = {}
last_latency = {}

# Simulación
simulation_mode = False
simulation_down = set()

# Interfaz
tree = None
log_text = None
start_button = None
stop_button = None
monitor_label = None
simulation_button = None
simulation_info = None

# Identificador de cada fila
row_items = {}

# Lock para variables compartidas
state_lock = threading.Lock()


# ============================================================
# FECHA/HORA
# ============================================================

def current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ============================================================
# CONFIGURACIÓN
# ============================================================

def load_config():

    global email_account
    global alert_recipient
    global DEFAULT_AGENCIES

    if not os.path.exists(CONFIG_FILE):
        return

    try:

        with open(
            CONFIG_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        email_account = data.get(
            "email_account",
            ""
        )

        alert_recipient = data.get(
            "alert_recipient",
            ""
        )

        saved_agencies = data.get(
            "agencies"
        )

        if saved_agencies:

            for i, saved_agency in enumerate(
                saved_agencies
            ):

                if i >= len(DEFAULT_AGENCIES):
                    break

                DEFAULT_AGENCIES[i]["name"] = (
                    saved_agency.get(
                        "name",
                        DEFAULT_AGENCIES[i]["name"]
                    )
                )

                saved_links = saved_agency.get(
                    "links",
                    []
                )

                for j, saved_link in enumerate(
                    saved_links
                ):

                    if j >= 2:
                        break

                    DEFAULT_AGENCIES[i]["links"][j][
                        "name"
                    ] = saved_link.get(
                        "name",
                        DEFAULT_AGENCIES[i]["links"][j]["name"]
                    )

                    DEFAULT_AGENCIES[i]["links"][j][
                        "ip"
                    ] = saved_link.get(
                        "ip",
                        DEFAULT_AGENCIES[i]["links"][j]["ip"]
                    )

    except Exception as e:

        print(
            f"Error leyendo configuración: {e}"
        )


def save_config():

    data = {
        "email_account": email_account,
        "alert_recipient": alert_recipient,
        "agencies": DEFAULT_AGENCIES
    }

    try:

        with open(
            CONFIG_FILE,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                data,
                file,
                indent=4,
                ensure_ascii=False
            )

        return True

    except Exception as e:

        messagebox.showerror(
            "Error",
            f"No fue posible guardar la configuración:\n\n{e}"
        )

        return False


# ============================================================
# PING
# ============================================================

def ping_ip(ip):
    """
    Hace un ping a una IP.

    Windows:
        ping -n 1 -w 1500 IP

    Linux/macOS:
        ping -c 1 -W 1 IP

    Devuelve:
        (True/False, latencia_ms)
    """

    try:

        system = platform.system().lower()

        start = time.perf_counter()

        if system == "windows":

            command = [
                "ping",
                "-n",
                "1",
                "-w",
                "1500",
                ip
            ]

        elif system == "darwin":

            command = [
                "ping",
                "-c",
                "1",
                "-W",
                "1500",
                ip
            ]

        else:

            command = [
                "ping",
                "-c",
                "1",
                "-W",
                "1",
                ip
            ]

        result = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3
        )

        elapsed = (
            time.perf_counter() - start
        ) * 1000

        if result.returncode == 0:

            return True, round(
                elapsed,
                1
            )

        return False, None

    except Exception:

        return False, None


# ============================================================
# LOG
# ============================================================

def log_event(message):

    text = (
        f"[{current_time()}] "
        f"{message}"
    )

    print(text)

    try:

        if root is not None:

            root.after(
                0,
                lambda t=text: add_log_to_gui(t)
            )

    except Exception:
        pass


def add_log_to_gui(message):

    try:

        log_text.configure(
            state="normal"
        )

        log_text.insert(
            "end",
            message + "\n"
        )

        log_text.see(
            "end"
        )

        log_text.configure(
            state="disabled"
        )

    except Exception:
        pass


# ============================================================
# EMAIL
# ============================================================

def send_email(
    subject,
    body
):

    global email_account
    global email_password
    global alert_recipient

    if not email_account:

        log_event(
            "ERROR: No hay correo remitente configurado."
        )

        return False

    if not email_password:

        log_event(
            "ERROR: No hay contraseña configurada."
        )

        return False

    if not alert_recipient:

        log_event(
            "ERROR: No hay destinatario configurado."
        )

        return False

    try:

        message = EmailMessage()

        message["From"] = email_account

        message["To"] = alert_recipient

        message["Subject"] = subject

        message.set_content(
            body
        )

        log_event(
            f"Conectando a {SMTP_SERVER}:{SMTP_PORT}..."
        )

        with smtplib.SMTP(
            SMTP_SERVER,
            SMTP_PORT,
            timeout=20
        ) as server:

            server.ehlo()

            server.starttls()

            server.ehlo()

            server.login(
                email_account,
                email_password
            )

            server.send_message(
                message
            )

        log_event(
            f"Correo enviado correctamente: {subject}"
        )

        return True

    except smtplib.SMTPAuthenticationError:

        log_event(
            "ERROR SMTP: Microsoft 365 rechazó "
            "las credenciales o SMTP AUTH está deshabilitado."
        )

        return False

    except smtplib.SMTPConnectError:

        log_event(
            "ERROR SMTP: No fue posible conectar "
            "con smtp.office365.com."
        )

        return False

    except smtplib.SMTPException as e:

        log_event(
            f"ERROR SMTP: {e}"
        )

        return False

    except Exception as e:

        log_event(
            f"ERROR enviando correo: {e}"
        )

        return False


# ============================================================
# ALERTA DE ENLACE CAÍDO
# ============================================================

def send_down_alert(
    agency,
    link,
    ip
):

    subject = (
        f"[ALERTA RED] "
        f"{agency} - {link} CAÍDO"
    )

    body = f"""
ALERTA DE RED

Agencia:
{agency}

Enlace:
{link}

IP pública:
{ip}

Estado:
CAÍDO

Hora de detección:
{current_time()}

El enlace no respondió durante
{MAX_FAILURES} comprobaciones consecutivas.

Intervalo de monitoreo:
{PING_INTERVAL} segundos.

Este mensaje fue generado automáticamente
por el Monitor de Enlaces de Red.
"""

    threading.Thread(
        target=send_email,
        args=(
            subject,
            body
        ),
        daemon=True
    ).start()


# ============================================================
# ALERTA DE RECUPERACIÓN
# ============================================================

def send_recovery_alert(
    agency,
    link,
    ip,
    duration
):

    subject = (
        f"[RECUPERACIÓN RED] "
        f"{agency} - {link}"
    )

    body = f"""
RECUPERACIÓN DE RED

Agencia:
{agency}

Enlace:
{link}

IP pública:
{ip}

Estado:
RECUPERADO

Hora de recuperación:
{current_time()}

Tiempo aproximado de interrupción:
{duration}

El enlace volvió a responder correctamente.

Este mensaje fue generado automáticamente
por el Monitor de Enlaces de Red.
"""

    threading.Thread(
        target=send_email,
        args=(
            subject,
            body
        ),
        daemon=True
    ).start()


# ============================================================
# DURACIÓN DE UNA CAÍDA
# ============================================================

def calculate_duration(start_timestamp):

    if not start_timestamp:
        return "Desconocido"

    seconds = int(
        time.time() - start_timestamp
    )

    hours, remainder = divmod(
        seconds,
        3600
    )

    minutes, seconds = divmod(
        remainder,
        60
    )

    return (
        f"{hours:02d}:"
        f"{minutes:02d}:"
        f"{seconds:02d}"
    )


# ============================================================
# ACTUALIZAR FILA
# ============================================================

def refresh_tree():

    if tree is None:
        return

    try:

        for agency in DEFAULT_AGENCIES:

            for link in agency["links"]:

                key = (
                    f"{agency['name']}|"
                    f"{link['name']}"
                )

                if key not in row_items:
                    continue

                with state_lock:

                    state = link_states.get(
                        key,
                        "UNKNOWN"
                    )

                    failures = failure_counts.get(
                        key,
                        0
                    )

                    latency = last_latency.get(
                        key
                    )

                if state == "UP":

                    status_text = "● ACTIVO"

                    latency_text = (
                        f"{latency} ms"
                        if latency is not None
                        else "---"
                    )

                    tag = "up"

                elif state == "DOWN":

                    status_text = "● CAÍDO"

                    latency_text = "---"

                    tag = "down"

                elif state == "CHECKING":

                    status_text = "● COMPROBANDO"

                    latency_text = "---"

                    tag = "checking"

                else:

                    status_text = "● DESCONOCIDO"

                    latency_text = "---"

                    tag = "unknown"

                action_text = (
                    "Restaurar"
                    if key in simulation_down
                    else "Simular caída"
                )

                tree.item(
                    row_items[key],
                    values=(
                        agency["name"],
                        link["name"],
                        link["ip"],
                        status_text,
                        failures,
                        latency_text,
                        action_text
                    ),
                    tags=(tag,)
                )

        root.after(
            500,
            refresh_tree
        )

    except Exception:
        pass


# ============================================================
# MONITOREO DE UN ENLACE
# ============================================================

def process_ping_result(
    agency,
    link,
    result,
    latency
):

    agency_name = agency["name"]
    link_name = link["name"]
    ip = link["ip"]

    key = (
        f"{agency_name}|"
        f"{link_name}"
    )

    with state_lock:

        previous_state = link_states.get(
            key,
            "UNKNOWN"
        )

        if result:

            failure_counts[key] = 0

            last_latency[key] = latency

            link_states[key] = "UP"

            # --------------------------------------------
            # RECUPERACIÓN
            # --------------------------------------------

            if previous_state == "DOWN":

                started = down_since.get(
                    key
                )

                duration = calculate_duration(
                    started
                )

                down_since.pop(
                    key,
                    None
                )

                log_event(
                    f"{agency_name} - "
                    f"{link_name} "
                    f"({ip}) RECUPERADO "
                    f"({latency} ms)"
                )

                send_recovery_alert(
                    agency_name,
                    link_name,
                    ip,
                    duration
                )

            else:

                log_event(
                    f"{agency_name} - "
                    f"{link_name} "
                    f"({ip}) ACTIVO "
                    f"({latency} ms)"
                )

        else:

            failure_counts[key] = (
                failure_counts.get(
                    key,
                    0
                ) + 1
            )

            last_latency[key] = None

            failures = failure_counts[key]

            log_event(
                f"{agency_name} - "
                f"{link_name} "
                f"({ip}) SIN RESPUESTA "
                f"({failures}/{MAX_FAILURES})"
            )

            # --------------------------------------------
            # DECLARAR DOWN
            # --------------------------------------------

            if failures >= MAX_FAILURES:

                if previous_state != "DOWN":

                    link_states[key] = "DOWN"

                    down_since[key] = time.time()

                    log_event(
                        f"ALERTA: "
                        f"{agency_name} - "
                        f"{link_name} "
                        f"({ip}) CAÍDO"
                    )

                    send_down_alert(
                        agency_name,
                        link_name,
                        ip
                    )


# ============================================================
# MONITOR
# ============================================================

def monitor_loop():

    global running

    log_event(
        "Monitor iniciado."
    )

    log_event(
        f"Intervalo: {PING_INTERVAL} segundos."
    )

    log_event(
        f"Fallos necesarios para DOWN: "
        f"{MAX_FAILURES}."
    )

    executor = ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    )

    try:

        while running:

            cycle_start = time.time()

            tasks = {}

            # --------------------------------------------
            # PREPARAR LOS 14 ENLACES
            # --------------------------------------------

            for agency in DEFAULT_AGENCIES:

                for link in agency["links"]:

                    agency_name = agency["name"]
                    link_name = link["name"]
                    ip = link["ip"]

                    key = (
                        f"{agency_name}|"
                        f"{link_name}"
                    )

                    with state_lock:

                        link_states[key] = (
                            link_states.get(
                                key,
                                "UNKNOWN"
                            )
                        )

                    # ------------------------------------
                    # SIMULACIÓN
                    # ------------------------------------

                    if (
                        simulation_mode
                        and key in simulation_down
                    ):

                        future = executor.submit(
                            lambda: (
                                False,
                                None
                            )
                        )

                    else:

                        future = executor.submit(
                            ping_ip,
                            ip
                        )

                    tasks[future] = (
                        agency,
                        link
                    )

            # --------------------------------------------
            # RECIBIR RESULTADOS
            # --------------------------------------------

            for future in as_completed(tasks):

                if not running:
                    break

                agency, link = tasks[future]

                try:

                    result, latency = future.result()

                except Exception:

                    result = False
                    latency = None

                process_ping_result(
                    agency,
                    link,
                    result,
                    latency
                )

            # --------------------------------------------
            # ESPERAR HASTA EL SIGUIENTE CICLO
            # --------------------------------------------

            elapsed = (
                time.time() -
                cycle_start
            )

            remaining = max(
                0,
                PING_INTERVAL - elapsed
            )

            end_time = (
                time.time() +
                remaining
            )

            while (
                running
                and time.time() < end_time
            ):

                time.sleep(
                    0.1
                )

    finally:

        executor.shutdown(
            wait=False
        )

        log_event(
            "Monitor detenido."
        )


# ============================================================
# INICIAR MONITOR
# ============================================================

def start_monitor():

    global running
    global monitor_thread

    if running:

        messagebox.showinfo(
            "Monitor",
            "El monitor ya está ejecutándose."
        )

        return

    running = True

    start_button.configure(
        state="disabled"
    )

    stop_button.configure(
        state="normal"
    )

    monitor_label.configure(
        text="● MONITOREO ACTIVO",
        foreground="#00a651"
    )

    monitor_thread = threading.Thread(
        target=monitor_loop,
        daemon=True
    )

    monitor_thread.start()


# ============================================================
# DETENER MONITOR
# ============================================================

def stop_monitor():

    global running

    running = False

    start_button.configure(
        state="normal"
    )

    stop_button.configure(
        state="disabled"
    )

    monitor_label.configure(
        text="● MONITOREO DETENIDO",
        foreground="#e00000"
    )

    log_event(
        "Solicitud de detención recibida."
    )


# ============================================================
# SIMULACIÓN
# ============================================================

def toggle_simulation():

    global simulation_mode

    simulation_mode = not simulation_mode

    if simulation_mode:

        simulation_button.configure(
            text="SIMULACIÓN: ACTIVADA",
            background="#f39c12"
        )

        simulation_info.configure(
            text=(
                "Modo simulación activo. "
                "Haga doble clic sobre un enlace "
                "para simular una caída."
            )
        )

        log_event(
            "Modo simulación ACTIVADO."
        )

    else:

        simulation_button.configure(
            text="SIMULACIÓN: DESACTIVADA",
            background="#555555"
        )

        simulation_info.configure(
            text=""
        )

        simulation_down.clear()

        log_event(
            "Modo simulación DESACTIVADO."
        )


def simulate_link_down(key):

    if not simulation_mode:

        messagebox.showwarning(
            "Simulación",
            "Primero active el modo simulación."
        )

        return

    if key in simulation_down:

        simulation_down.remove(
            key
        )

        log_event(
            f"Simulación restaurada: {key}"
        )

    else:

        simulation_down.add(
            key
        )

        log_event(
            f"Simulando caída: {key}"
        )


# ============================================================
# CONFIGURACIÓN DE CORREO
# ============================================================

def open_email_config():

    window = tk.Toplevel(
        root
    )

    window.title(
        "Configuración de correo Microsoft 365"
    )

    window.geometry(
        "600x500"
    )

    window.resizable(
        False,
        False
    )

    # --------------------------------------------------------
    # REMITENTE
    # --------------------------------------------------------

    ttk.Label(
        window,
        text="Correo remitente Microsoft 365:",
        font=("Arial", 10, "bold")
    ).pack(
        padx=20,
        pady=(20, 5),
        anchor="w"
    )

    sender_entry = ttk.Entry(
        window,
        width=70
    )

    sender_entry.pack(
        padx=20
    )

    sender_entry.insert(
        0,
        email_account
    )

    # --------------------------------------------------------
    # PASSWORD
    # --------------------------------------------------------

    ttk.Label(
        window,
        text="Contraseña:",
        font=("Arial", 10, "bold")
    ).pack(
        padx=20,
        pady=(20, 5),
        anchor="w"
    )

    password_entry = ttk.Entry(
        window,
        width=70,
        show="*"
    )

    password_entry.pack(
        padx=20
    )

    # --------------------------------------------------------
    # MOSTRAR PASSWORD
    # --------------------------------------------------------

    show_password_var = tk.BooleanVar(
        value=False
    )

    def toggle_password():

        if show_password_var.get():

            password_entry.configure(
                show=""
            )

        else:

            password_entry.configure(
                show="*"
            )

    ttk.Checkbutton(
        window,
        text="Mostrar contraseña",
        variable=show_password_var,
        command=toggle_password
    ).pack(
        padx=20,
        pady=5,
        anchor="w"
    )

    # --------------------------------------------------------
    # DESTINATARIO
    # --------------------------------------------------------

    ttk.Label(
        window,
        text="Correo destinatario de alertas:",
        font=("Arial", 10, "bold")
    ).pack(
        padx=20,
        pady=(15, 5),
        anchor="w"
    )

    recipient_entry = ttk.Entry(
        window,
        width=70
    )

    recipient_entry.pack(
        padx=20
    )

    recipient_entry.insert(
        0,
        alert_recipient
    )

    # --------------------------------------------------------
    # SMTP
    # --------------------------------------------------------

    info_frame = ttk.LabelFrame(
        window,
        text="Configuración Microsoft 365"
    )

    info_frame.pack(
        fill="x",
        padx=20,
        pady=20
    )

    ttk.Label(
        info_frame,
        text="Servidor SMTP: smtp.office365.com"
    ).pack(
        anchor="w",
        padx=10,
        pady=3
    )

    ttk.Label(
        info_frame,
        text="Puerto: 587"
    ).pack(
        anchor="w",
        padx=10,
        pady=3
    )

    ttk.Label(
        info_frame,
        text="Seguridad: STARTTLS"
    ).pack(
        anchor="w",
        padx=10,
        pady=3
    )

    ttk.Label(
        info_frame,
        text=(
            "La contraseña no se guarda en config.json."
        ),
        foreground="#555555"
    ).pack(
        anchor="w",
        padx=10,
        pady=5
    )

    # --------------------------------------------------------
    # GUARDAR
    # --------------------------------------------------------

    def save_email_config():

        global email_account
        global email_password
        global alert_recipient

        new_email = (
            sender_entry.get().strip()
        )

        new_password = (
            password_entry.get()
        )

        new_recipient = (
            recipient_entry.get().strip()
        )

        if not new_email:

            messagebox.showwarning(
                "Configuración",
                "Ingrese el correo remitente."
            )

            return

        if not new_password:

            messagebox.showwarning(
                "Configuración",
                "Ingrese la contraseña."
            )

            return

        if not new_recipient:

            messagebox.showwarning(
                "Configuración",
                "Ingrese el destinatario."
            )

            return

        email_account = new_email

        email_password = new_password

        alert_recipient = new_recipient

        if save_config():

            messagebox.showinfo(
                "Configuración",
                "Configuración guardada correctamente.\n\n"
                "La contraseña permanecerá únicamente "
                "en memoria."
            )

    ttk.Button(
        window,
        text="GUARDAR CONFIGURACIÓN",
        command=save_email_config
    ).pack(
        pady=5
    )

    # --------------------------------------------------------
    # PRUEBA DE CORREO
    # --------------------------------------------------------

    def test_from_window():

        global email_account
        global email_password
        global alert_recipient

        new_email = (
            sender_entry.get().strip()
        )

        new_password = (
            password_entry.get()
        )

        new_recipient = (
            recipient_entry.get().strip()
        )

        if not new_email:

            messagebox.showwarning(
                "Prueba",
                "Ingrese el correo remitente."
            )

            return

        if not new_password:

            messagebox.showwarning(
                "Prueba",
                "Ingrese la contraseña."
            )

            return

        if not new_recipient:

            messagebox.showwarning(
                "Prueba",
                "Ingrese el destinatario."
            )

            return

        email_account = new_email

        email_password = new_password

        alert_recipient = new_recipient

        def worker():

            success = send_email(
                "[MONITOR RED] Correo de prueba",
                f"""
CORREO DE PRUEBA

El sistema Monitor de Enlaces de Red
está correctamente configurado.

Correo remitente:
{email_account}

Servidor SMTP:
{SMTP_SERVER}

Puerto:
{SMTP_PORT}

Fecha:
{current_time()}

Este mensaje fue generado automáticamente.
"""
            )

            root.after(
                0,
                lambda: messagebox.showinfo(
                    "Prueba de correo",
                    (
                        "Correo enviado correctamente."
                        if success
                        else
                        "No fue posible enviar el correo.\n\n"
                        "Revise el registro de eventos."
                    )
                )
            )

        threading.Thread(
            target=worker,
            daemon=True
        ).start()

    ttk.Button(
        window,
        text="PROBAR CORREO",
        command=test_from_window
    ).pack(
        pady=5
    )


# ============================================================
# CONFIGURACIÓN DE AGENCIAS
# ============================================================

def open_agency_config():

    window = tk.Toplevel(
        root
    )

    window.title(
        "Configuración de agencias"
    )

    window.geometry(
        "760x600"
    )

    window.resizable(
        False,
        False
    )

    main_frame = ttk.Frame(
        window
    )

    main_frame.pack(
        fill="both",
        expand=True,
        padx=20,
        pady=20
    )

    # --------------------------------------------------------
    # ENCABEZADOS
    # --------------------------------------------------------

    ttk.Label(
        main_frame,
        text="Agencia",
        font=("Arial", 10, "bold")
    ).grid(
        row=0,
        column=0,
        padx=10,
        pady=8
    )

    ttk.Label(
        main_frame,
        text="Enlace",
        font=("Arial", 10, "bold")
    ).grid(
        row=0,
        column=1,
        padx=10,
        pady=8
    )

    ttk.Label(
        main_frame,
        text="IP pública",
        font=("Arial", 10, "bold")
    ).grid(
        row=0,
        column=2,
        padx=10,
        pady=8
    )

    entries = []

    row = 1

    for agency in DEFAULT_AGENCIES:

        for link in agency["links"]:

            ttk.Label(
                main_frame,
                text=agency["name"]
            ).grid(
                row=row,
                column=0,
                padx=10,
                pady=6
            )

            ttk.Label(
                main_frame,
                text=link["name"]
            ).grid(
                row=row,
                column=1,
                padx=10,
                pady=6
            )

            entry = ttk.Entry(
                main_frame,
                width=35
            )

            entry.insert(
                0,
                link["ip"]
            )

            entry.grid(
                row=row,
                column=2,
                padx=10,
                pady=6
            )

            entries.append(
                (
                    link,
                    entry
                )
            )

            row += 1

    # --------------------------------------------------------
    # GUARDAR
    # --------------------------------------------------------

    def save_agencies():

        for link, entry in entries:

            new_ip = (
                entry.get().strip()
            )

            if not new_ip:

                messagebox.showwarning(
                    "IP",
                    f"La IP de {link['name']} "
                    "no puede estar vacía."
                )

                return

            link["ip"] = new_ip

        save_config()

        rebuild_table()

        messagebox.showinfo(
            "Agencias",
            "Configuración guardada correctamente."
        )

        window.destroy()

    ttk.Button(
        main_frame,
        text="GUARDAR CONFIGURACIÓN",
        command=save_agencies
    ).grid(
        row=row,
        column=2,
        pady=20
    )


# ============================================================
# RECONSTRUIR TABLA
# ============================================================

def rebuild_table():

    global row_items

    row_items.clear()

    for item in tree.get_children():

        tree.delete(
            item
        )

    with state_lock:

        link_states.clear()
        failure_counts.clear()
        down_since.clear()
        last_latency.clear()

    for agency in DEFAULT_AGENCIES:

        for link in agency["links"]:

            key = (
                f"{agency['name']}|"
                f"{link['name']}"
            )

            with state_lock:

                link_states[key] = "UNKNOWN"

                failure_counts[key] = 0

                last_latency[key] = None

            item = tree.insert(
                "",
                "end",
                values=(
                    agency["name"],
                    link["name"],
                    link["ip"],
                    "● DESCONOCIDO",
                    "0",
                    "---",
                    "Simular caída"
                ),
                tags=("unknown",)
            )

            row_items[key] = item


# ============================================================
# DOBLE CLICK EN TABLA
# ============================================================

def on_tree_double_click(event):

    item_id = tree.identify_row(
        event.y
    )

    if not item_id:
        return

    values = tree.item(
        item_id,
        "values"
    )

    if not values:
        return

    agency = values[0]

    link = values[1]

    key = (
        f"{agency}|{link}"
    )

    simulate_link_down(
        key
    )


# ============================================================
# CREAR INTERFAZ PRINCIPAL
# ============================================================

def build_main_interface():

    global root
    global tree
    global log_text
    global start_button
    global stop_button
    global monitor_label
    global simulation_button
    global simulation_info

    root = tk.Tk()

    root.title(
        "Monitor de Enlaces de Red"
    )

    root.geometry(
        "1250x850"
    )

    root.minsize(
        1100,
        750
    )

    # --------------------------------------------------------
    # ESTILO
    # --------------------------------------------------------

    style = ttk.Style()

    try:

        style.theme_use(
            "clam"
        )

    except Exception:
        pass

    style.configure(
        "Treeview",
        rowheight=30,
        font=("Arial", 10)
    )

    style.configure(
        "Treeview.Heading",
        font=(
            "Arial",
            10,
            "bold"
        )
    )

    # --------------------------------------------------------
    # ENCABEZADO
    # --------------------------------------------------------

    header = ttk.Frame(
        root
    )

    header.pack(
        fill="x",
        padx=20,
        pady=15
    )

    ttk.Label(
        header,
        text="MONITOR DE ENLACES DE RED",
        font=(
            "Arial",
            22,
            "bold"
        )
    ).pack(
        side="left"
    )

    monitor_label = ttk.Label(
        header,
        text="● MONITOREO DETENIDO",
        foreground="#e00000",
        font=(
            "Arial",
            11,
            "bold"
        )
    )

    monitor_label.pack(
        side="right"
    )

    # --------------------------------------------------------
    # BOTONES PRINCIPALES
    # --------------------------------------------------------

    button_frame = ttk.Frame(
        root
    )

    button_frame.pack(
        fill="x",
        padx=20,
        pady=5
    )

    start_button = ttk.Button(
        button_frame,
        text="▶ INICIAR MONITOREO",
        command=start_monitor
    )

    start_button.pack(
        side="left",
        padx=4
    )

    stop_button = ttk.Button(
        button_frame,
        text="■ DETENER",
        command=stop_monitor,
        state="disabled"
    )

    stop_button.pack(
        side="left",
        padx=4
    )

    ttk.Button(
        button_frame,
        text="Configuración correo",
        command=open_email_config
    ).pack(
        side="left",
        padx=4
    )

    ttk.Button(
        button_frame,
        text="Configuración agencias",
        command=open_agency_config
    ).pack(
        side="left",
        padx=4
    )

    simulation_button = tk.Button(
        button_frame,
        text="SIMULACIÓN: DESACTIVADA",
        background="#555555",
        foreground="white",
        activebackground="#777777",
        activeforeground="white",
        command=toggle_simulation
    )

    simulation_button.pack(
        side="right",
        padx=4
    )

    # --------------------------------------------------------
    # INFORMACIÓN
    # --------------------------------------------------------

    info_frame = ttk.Frame(
        root
    )

    info_frame.pack(
        fill="x",
        padx=20,
        pady=5
    )

    ttk.Label(
        info_frame,
        text=(
            f"Intervalo: {PING_INTERVAL} segundos    |    "
            f"Fallos para DOWN: {MAX_FAILURES}    |    "
            f"Enlaces monitoreados: 14"
        ),
        foreground="#555555"
    ).pack(
        side="left"
    )

    simulation_info = ttk.Label(
        info_frame,
        text="",
        foreground="#c77700"
    )

    simulation_info.pack(
        side="right"
    )

    # --------------------------------------------------------
    # TABLA
    # --------------------------------------------------------

    table_frame = ttk.Frame(
        root
    )

    table_frame.pack(
        fill="both",
        expand=True,
        padx=20,
        pady=10
    )

    columns = (
        "agency",
        "link",
        "ip",
        "status",
        "failures",
        "latency",
        "action"
    )

    tree = ttk.Treeview(
        table_frame,
        columns=columns,
        show="headings",
        selectmode="browse"
    )

    tree.heading(
        "agency",
        text="AGENCIA"
    )

    tree.heading(
        "link",
        text="ENLACE"
    )

    tree.heading(
        "ip",
        text="IP PÚBLICA"
    )

    tree.heading(
        "status",
        text="ESTADO"
    )

    tree.heading(
        "failures",
        text="FALLOS"
    )

    tree.heading(
        "latency",
        text="LATENCIA"
    )

    tree.heading(
        "action",
        text="SIMULACIÓN"
    )

    tree.column(
        "agency",
        width=160,
        anchor="center"
    )

    tree.column(
        "link",
        width=130,
        anchor="center"
    )

    tree.column(
        "ip",
        width=170,
        anchor="center"
    )

    tree.column(
        "status",
        width=170,
        anchor="center"
    )

    tree.column(
        "failures",
        width=80,
        anchor="center"
    )

    tree.column(
        "latency",
        width=100,
        anchor="center"
    )

    tree.column(
        "action",
        width=160,
        anchor="center"
    )

    # Scrollbar
    scrollbar = ttk.Scrollbar(
        table_frame,
        orient="vertical",
        command=tree.yview
    )

    tree.configure(
        yscrollcommand=scrollbar.set
    )

    tree.pack(
        side="left",
        fill="both",
        expand=True
    )

    scrollbar.pack(
        side="right",
        fill="y"
    )

    # Colores
    tree.tag_configure(
        "up",
        foreground="#008000"
    )

    tree.tag_configure(
        "down",
        foreground="#d00000"
    )

    tree.tag_configure(
        "checking",
        foreground="#c77700"
    )

    tree.tag_configure(
        "unknown",
        foreground="#777777"
    )

    tree.bind(
        "<Double-1>",
        on_tree_double_click
    )

    # --------------------------------------------------------
    # CARGAR FILAS
    # --------------------------------------------------------

    rebuild_table()

    # --------------------------------------------------------
    # REGISTRO
    # --------------------------------------------------------

    ttk.Label(
        root,
        text="REGISTRO DE EVENTOS",
        font=(
            "Arial",
            11,
            "bold"
        )
    ).pack(
        padx=20,
        anchor="w"
    )

    log_frame = ttk.Frame(
        root
    )

    log_frame.pack(
        fill="both",
        padx=20,
        pady=5
    )

    log_scroll = ttk.Scrollbar(
        log_frame,
        orient="vertical"
    )

    log_text = tk.Text(
        log_frame,
        height=9,
        state="disabled",
        background="#101010",
        foreground="#00ff66",
        insertbackground="white",
        font=(
            "Consolas",
            9
        ),
        yscrollcommand=log_scroll.set
    )

    log_scroll.configure(
        command=log_text.yview
    )

    log_text.pack(
        side="left",
        fill="both",
        expand=True
    )

    log_scroll.pack(
        side="right",
        fill="y"
    )

    # --------------------------------------------------------
    # LOG INICIAL
    # --------------------------------------------------------

    log_event(
        "======================================"
    )

    log_event(
        "MONITOR DE ENLACES DE RED"
    )

    log_event(
        "Aplicación iniciada."
    )

    log_event(
        f"Agencias configuradas: "
        f"{len(DEFAULT_AGENCIES)}"
    )

    log_event(
        "Enlaces configurados: 14"
    )

    log_event(
        f"Intervalo de ping: "
        f"{PING_INTERVAL} segundos."
    )

    log_event(
        f"Fallos consecutivos para DOWN: "
        f"{MAX_FAILURES}"
    )

    log_event(
        "======================================"
    )

    root.protocol(
        "WM_DELETE_WINDOW",
        on_close
    )

    # Actualización periódica de tabla
    root.after(
        500,
        refresh_tree
    )

    root.mainloop()


# ============================================================
# CERRAR APLICACIÓN
# ============================================================

def on_close():

    global running

    if running:

        answer = messagebox.askyesno(
            "Salir",
            "El monitoreo está activo.\n\n"
            "¿Desea detener el monitoreo y salir?"
        )

        if not answer:
            return

    running = False

    try:

        root.destroy()

    except Exception:
        pass


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

if __name__ == "__main__":

    load_config()

    build_main_interface()