import flet as ft
import subprocess
import socket
import base64
import qrcode
import io
import json
import os
import sys
import logging
import threading
import time
from typing import Optional
from datetime import datetime
import contextlib
from pathlib import Path
from subprocess import TimeoutExpired
import signal

# App constants
APP_VERSION = "2.0.0"
DEFAULT_PORT = 8000
CONFIG_FILE = "config.json"
LOG_FILE = "server.log"
STATE_FILE = "server.state.json"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class Settings:
    """Application settings manager with persistent storage"""
    
    def __init__(self):
        self.preferred_port = DEFAULT_PORT
        self.auto_start = False
        self.theme = "dark"
        self.sensitivity = 1.0
        self.enable_logging = True
        self.load()

    def load(self):
        """Load settings from config file"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    self.preferred_port = data.get('preferred_port', DEFAULT_PORT)
                    self.auto_start = data.get('auto_start', False)
                    self.theme = data.get('theme', 'dark')
                    self.sensitivity = data.get('sensitivity', 1.0)
                    self.enable_logging = data.get('enable_logging', True)
                logger.info("Settings loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load settings: {e}")

    def save(self):
        """Save settings to config file"""
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump({
                    'preferred_port': self.preferred_port,
                    'auto_start': self.auto_start,
                    'theme': self.theme,
                    'sensitivity': self.sensitivity,
                    'enable_logging': self.enable_logging
                }, f, indent=2)
            logger.info("Settings saved successfully")
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")


class ServerManager:
    """Manages the FastAPI server lifecycle"""
    
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.port: Optional[int] = None
        self.ip: Optional[str] = None
        self.start_time: Optional[datetime] = None
        self.pid: Optional[int] = None
        self.is_running = False
        self._check_and_load_state()

    def _check_and_load_state(self):
        """Check for a running server from a previous session."""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    state = json.load(f)
                
                pid = state.get('pid')
                port = state.get('port')
                if pid and port and self._is_server_process_running(pid, port):
                    logger.info(f"Found running server with PID {pid} on port {port}")
                    self.is_running = True
                    self.pid = pid
                    self.ip = state.get('ip')
                    self.port = port
                    self.start_time = datetime.fromisoformat(state.get('start_time'))
                else:
                    logger.info("Stale state file found. Cleaning up.")
                    self._clear_state()
            except (json.JSONDecodeError, KeyError, OSError) as e:
                logger.error(f"Error loading state file, cleaning up: {e}")
                self._clear_state()

    def _is_server_process_running(self, pid: int, port: int) -> bool:
        """Check if a process with the given PID is running and listening on the port."""
        # 1. Check if the port is in use
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                logger.debug(f"Port {port} is not open.")
                return False  # Port is not open

        # 2. Check if the PID is running
        if sys.platform == "win32":
            result = subprocess.run(['tasklist', '/FI', f'PID eq {pid}'], capture_output=True, text=True)
            is_running = str(pid) in result.stdout
        else:
            try:
                os.kill(pid, 0)
                is_running = True
            except OSError:
                is_running = False
        
        if not is_running:
            logger.debug(f"PID {pid} is not running.")

        return is_running

    def _save_state(self):
        """Save server state to a file."""
        if not self.pid: return
        state = {
            'pid': self.pid,
            'ip': self.ip,
            'port': self.port,
            'start_time': self.start_time.isoformat() if self.start_time else None
        }
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(state, f)
            logger.info(f"Server state saved for PID {self.pid}")
        except Exception as e:
            logger.error(f"Failed to save server state: {e}")

    def _clear_state(self):
        """Clear the server state file."""
        if os.path.exists(STATE_FILE):
            with contextlib.suppress(OSError):
                os.remove(STATE_FILE)
        logger.info("Server state file cleared.")

    def get_local_ip(self) -> str:
        """Get the local IP address"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return socket.gethostbyname(socket.gethostname())

    def find_free_port(self, start=8000, end=8100) -> int:
        """Find an available port in the given range"""
        for port in range(start, end):
            with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
                try:
                    s.bind(("", port))
                    return port
                except OSError:
                    continue
        raise RuntimeError("No free ports available in range")

    def start(self, preferred_port: int) -> tuple[bool, str]:
        """Start the server"""
        if self.is_running:
            return False, "Server is already running"

        try:
            self.ip = self.get_local_ip()
            self.port = self.find_free_port(preferred_port)
            
            if not os.path.exists("main.py"):
                return False, "main.py not found. Please ensure the FastAPI server file exists."

            # Platform-specific process creation for detached process
            creation_flags = 0
            preexec_fn = None
            if sys.platform == "win32":
                creation_flags = subprocess.CREATE_NO_WINDOW
            else:
                preexec_fn = os.setsid

            self.process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "main:app", 
                 "--host", "0.0.0.0", "--port", str(self.port)],
                creationflags=creation_flags,
                preexec_fn=preexec_fn,
                # stdout and stderr are not piped to allow detachment
            )
            
            time.sleep(2) # Give server time to start
            if self.process.poll() is not None:
                return False, "Server failed to start. Check logs for details."
            
            self.is_running = True
            self.start_time = datetime.now()
            self.pid = self.process.pid
            self._save_state()
            logger.info(f"Server started on {self.ip}:{self.port} with PID {self.pid}")
            return True, f"Server started successfully on {self.ip}:{self.port}"
            
        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            return False, f"Error starting server: {str(e)}"

    def stop(self) -> tuple[bool, str]:
        """Stop the server"""
        if not self.is_running and not self.pid:
            self._check_and_load_state()
            if not self.is_running:
                return False, "Server is not running"

        try:
            pid_to_stop = self.pid
            if pid_to_stop:
                logger.info(f"Stopping server process with PID: {pid_to_stop}")
                if sys.platform == "win32":
                    # Use taskkill for a more robust termination on Windows
                    subprocess.run(["taskkill", "/F", "/PID", str(pid_to_stop)], check=True, capture_output=True)
                else:
                    os.kill(pid_to_stop, signal.SIGTERM)
                logger.info(f"Termination signal sent to PID {pid_to_stop}")
            
            self.is_running = False
            self._clear_state()
            uptime = self.get_uptime()
            logger.info(f"Server stopped. Uptime was {uptime}")
            return True, f"Server stopped. Uptime: {uptime}"
            
        except Exception as e:
            logger.error(f"Failed to stop server: {e}")
            # If stopping failed, the state might be inconsistent. Clear it.
            self.is_running = False
            self._clear_state()
            return False, f"Error stopping server: {str(e)}"

    def get_uptime(self) -> str:
        """Get server uptime as a formatted string"""
        if not self.start_time:
            return "N/A"
        delta = datetime.now() - self.start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}h {minutes}m {seconds}s"


def generate_qr(ip: str, port: int) -> tuple[ft.Image, str]:
    """Generate QR code for WebSocket connection"""
    try:
        ws_url = f"ws://{ip}:{port}/ws"
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(ws_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        src_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        
        return ft.Image(src_base64=src_base64, width=280, height=280, border_radius=15), ws_url
    except Exception as e:
        logger.error(f"Failed to generate QR code: {e}")
        raise


def main(page: ft.Page):
    page.title = "Remote Mouse Server"
    page.window.width = 900
    page.window.height = 700
    page.window.min_width = 400
    page.window.min_height = 500
    page.padding = 0
    page.spacing = 0
    settings = Settings()
    server = ServerManager()
    shutdown_event = threading.Event()
    
    # Apply theme
    page.theme_mode = ft.ThemeMode.DARK if settings.theme == "dark" else ft.ThemeMode.LIGHT
    page.bgcolor = "#000000" if settings.theme == "dark" else "#f5f7fa"

    # Status indicator ref
    status_indicator = ft.Container(
        width=12,
        height=12,
        border_radius=6,
        bgcolor="#ef4444",
        shadow=ft.BoxShadow(
            spread_radius=0,
            blur_radius=8,
            color="#ef444440",
        )
    )

    def update_uptime():
        """Background thread to update uptime"""
        while True:
            time.sleep(1)
            if server.is_running:
                try:
                    uptime_text.value = server.get_uptime()
                    page.update()
                except:
                    pass

    threading.Thread(target=update_uptime, daemon=True).start()

    def show_snackbar(message: str, is_error: bool = False):
        """Show a snackbar notification"""
        page.snack_bar = ft.SnackBar(
            content=ft.Text(message, color="white"),
            bgcolor="#ef4444" if is_error else "#10b981"
        )
        page.snack_bar.open = True
        page.update()

    def show_info_dialog(e):
        """Show about dialog"""
        def close_dlg(e):
            dialog.open = False
            page.update()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("About Remote Mouse", size=24, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column([
                    ft.Text(f"Version {APP_VERSION}", size=16, color="#6b7280"),
                    ft.Divider(height=20, color="transparent"),
                    ft.Text("Control your desktop mouse using your smartphone's gyroscope and touch sensors.", 
                           size=14, color="#9ca3af"),
                    ft.Divider(height=10, color="transparent"),
                    ft.Text("Features:", size=16, weight=ft.FontWeight.BOLD),
                    ft.Text("• Real-time WebSocket connection", size=13, color="#9ca3af"),
                    ft.Text("• Gyroscope motion tracking", size=13, color="#9ca3af"),
                    ft.Text("• Touch gesture controls", size=13, color="#9ca3af"),
                    ft.Text("• Secure QR code pairing", size=13, color="#9ca3af"),
                    ft.Divider(height=20, color="transparent"),
                    ft.Text("Built with Flet & FastAPI", size=12, italic=True, color="#6b7280"),
                ], tight=True, spacing=5),
                width=400,
            ),
            actions=[
                ft.TextButton("Close", on_click=close_dlg),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        page.dialog = dialog
        dialog.open = True
        page.update()

    def show_settings_dialog(e):
        """Show settings dialog"""
        def close_dlg(e):
            dialog.open = False
            page.update()

        port_field = ft.TextField(
            label="Preferred Port",
            value=str(settings.preferred_port),
            hint_text="1024-65535",
            border_color="#3b82f6",
            focused_border_color="#2563eb",
            expand=True
        )

      

        theme_dropdown = ft.Dropdown(
            label="Theme",
            value=settings.theme,
            options=[
                ft.dropdown.Option("light", "Light"),
                ft.dropdown.Option("dark", "Dark"),
            ],
            border_color="#3b82f6",
            focused_border_color="#2563eb",
            expand=True
        )

        auto_start_switch = ft.Switch(
            label="Auto-start server on launch",
            value=settings.auto_start,
            active_color="#3b82f6"
        )

        logging_switch = ft.Switch(
            label="Enable logging",
            value=settings.enable_logging,
            active_color="#3b82f6"
        )

        def save_settings(e):
            try:
                new_port = int(port_field.value)
                if not (1024 <= new_port <= 65535):
                    port_field.error_text = "Port must be between 1024 and 65535"
                    page.update()
                    return

                settings.preferred_port = new_port
                settings.theme = theme_dropdown.value
                settings.auto_start = auto_start_switch.value
                settings.enable_logging = logging_switch.value
                settings.save()

                page.theme_mode = ft.ThemeMode.DARK if settings.theme == "dark" else ft.ThemeMode.LIGHT
                page.bgcolor = "#000000" if settings.theme == "dark" else "#f5f7fa"
                
                # Update card backgrounds
                status_card.bgcolor = "#1a1a1a" if settings.theme == "dark" else "white"
                qr_section.bgcolor = "#1a1a1a" if settings.theme == "dark" else "white"
                
                dialog.open = False
                page.update()
                show_snackbar("Settings saved successfully")
            except ValueError:
                port_field.error_text = "Please enter a valid port number"
                page.update()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Settings", size=24, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column([
                    port_field,
                    ft.Divider(height=10, color="transparent"),
                    ft.Text("Mouse Sensitivity", size=14, weight=ft.FontWeight.W_500),
                    ft.Divider(height=10, color="transparent"),
                    theme_dropdown,
                    ft.Divider(height=20, color="#e5e7eb"),
                    auto_start_switch,
                    logging_switch,
                ], tight=True, spacing=10),
                width=400,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=close_dlg),
                ft.ElevatedButton("Save", on_click=save_settings, bgcolor="#3b82f6", color="white"),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        page.dialog = dialog
        dialog.open = True
        page.update()

    def show_logs_dialog(e):
        """Show logs dialog"""
        def close_dlg(e):
            dialog.open = False
            page.update()

        try:
            if os.path.exists(LOG_FILE):
                with open(LOG_FILE, 'r') as f:
                    logs = f.read()
                    log_lines = logs.split('\n')[-100:]
                    log_content = '\n'.join(log_lines)
            else:
                log_content = "No logs available"
        except Exception as ex:
            log_content = f"Error reading logs: {ex}"

        def clear_logs(e):
            try:
                with open(LOG_FILE, 'w') as f:
                    f.write('')
                show_snackbar("Logs cleared")
                dialog.open = False
                page.update()
            except Exception as ex:
                show_snackbar(f"Error clearing logs: {ex}", True)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Server Logs", size=24, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Text(log_content, size=11, selectable=True, font_family="Courier"),
                width=700,
                height=400,
                padding=15,
                bgcolor="#1a1a1a" if settings.theme == "dark" else "#f8fafc",
                border_radius=8,
            ),
            actions=[
                ft.TextButton("Clear Logs", on_click=clear_logs),
                ft.TextButton("Close", on_click=close_dlg),
            ],
            actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
        
        page.dialog = dialog
        dialog.open = True
        page.update()

    # Status texts
    server_status_text = ft.Text("Offline", size=16, weight=ft.FontWeight.BOLD, color="#ef4444")
    ip_text = ft.Text("", size=13, color="#6b7280")
    port_text = ft.Text("", size=13, color="#6b7280")
    uptime_text = ft.Text("--:--:--", size=13, color="#6b7280")
    qr_container = ft.Container(alignment=ft.alignment.center, height=300)
    url_container = ft.Container()

    def update_ui_for_server_state():
        """Updates the UI based on the current server state."""
        if server.is_running:
            server_status_text.value = "Online"
            server_status_text.color = "#10b981"
            status_indicator.bgcolor = "#10b981"
            status_indicator.shadow = ft.BoxShadow(spread_radius=0, blur_radius=8, color="#10b98140")
            
            ip_text.value = f"IP: {server.ip}"
            port_text.value = f"Port: {server.port}"
            
            start_button.content.controls[1].value = "Stop Server"
            start_button.content.controls[0].name = "stop_circle"
            start_button.bgcolor = "#ef4444"
            
            try:
                qr_image, ws_url = generate_qr(server.ip, server.port)
                qr_container.content = ft.Container(
                    content=qr_image,
                    bgcolor="white",
                    border_radius=15,
                    padding=15,
                    shadow=ft.BoxShadow(
                        spread_radius=1,
                        blur_radius=15,
                        color="#00000020",
                        offset=ft.Offset(0, 4),
                    )
                )
                
                url_container.content = ft.Container(
                    content=ft.Text(
                        ws_url,
                        size=12,
                        color="#6b7280",
                        selectable=True,
                        text_align=ft.TextAlign.CENTER,
                        weight=ft.FontWeight.W_500
                    ),
                    padding=ft.padding.symmetric(horizontal=20, vertical=10),
                    bgcolor="#2a2a2a" if settings.theme == "dark" else "#f1f5f9",
                    border_radius=8,
                    margin=ft.margin.only(top=15),
                )
            except Exception as ex:
                logger.error(f"Failed to generate QR: {ex}")
            
            if qr_section not in content_column.controls:
                content_column.controls.append(qr_section)
        else:
            server_status_text.value = "Offline"
            server_status_text.color = "#ef4444"
            status_indicator.bgcolor = "#ef4444"
            status_indicator.shadow = ft.BoxShadow(spread_radius=0, blur_radius=8, color="#ef444440")
            
            ip_text.value = ""
            port_text.value = ""
            uptime_text.value = "--:--:--"
            
            start_button.content.controls[1].value = "Start Server"
            start_button.content.controls[0].name = "play_circle"
            start_button.bgcolor = "#10b981"
            
            qr_container.content = None
            url_container.content = None
            
            if qr_section in content_column.controls:
                content_column.controls.remove(qr_section)
        
        page.update()

    def toggle_server(e):
        """Start or stop the server"""
        start_button.disabled = True
        page.update()

        if not server.is_running:
            success, message = server.start(settings.preferred_port)
            if success:
                show_snackbar("Server started successfully!")
            else:
                show_snackbar(message, True)
        else:
            success, message = server.stop()
            if success:
                show_snackbar("Server stopped")
            else:
                show_snackbar(message, True)
        
        start_button.disabled = False
        update_ui_for_server_state()

    # Header with gradient
    header = ft.Container(
        content=ft.Row([
            ft.Row([
                ft.Icon("mouse", size=32, color="white"),
                ft.Text("Remote Mouse", size=24, weight=ft.FontWeight.BOLD, color="white"),
            ], spacing=12),
            ft.Row([
                ft.IconButton(
                    icon="description",
                    icon_size=22,
                    icon_color="white",
                    tooltip="View Logs",
                    on_click=show_logs_dialog,
                ),
                ft.IconButton(
                    icon="settings",
                    icon_size=22,
                    icon_color="white",
                    tooltip="Settings",
                    on_click=show_settings_dialog
                ),
                ft.IconButton(
                    icon="info",
                    icon_size=22,
                    icon_color="white",
                    tooltip="About",
                    on_click=show_info_dialog
                ),
            ], spacing=5),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        padding=ft.padding.symmetric(horizontal=30, vertical=20),
        gradient=ft.LinearGradient(
            begin=ft.alignment.center_left,
            end=ft.alignment.center_right,
            colors=["#1a1a1a", "#000000"],
        ),
    )

    # Status card
    status_card = ft.Container(
        content=ft.Column([
            ft.Row([
                status_indicator,
                server_status_text,
            ], spacing=10),
            ft.Divider(height=10, color="transparent"),
            ft.Row([
                ft.Icon("router", size=16, color="#6b7280"),
                ip_text,
            ], spacing=8),
            ft.Row([
                ft.Icon("settings_ethernet", size=16, color="#6b7280"),
                port_text,
            ], spacing=8),
            ft.Row([
                ft.Icon("schedule", size=16, color="#6b7280"),
                uptime_text,
            ], spacing=8),
        ], spacing=8),
        padding=25,
        border_radius=15,
        bgcolor="#1a1a1a" if settings.theme == "dark" else "white",
        shadow=ft.BoxShadow(
            spread_radius=1,
            blur_radius=15,
            color="#00000015",
            offset=ft.Offset(0, 4),
        ),
        width=400,
    )

    # Start button
    start_button = ft.ElevatedButton(
        content=ft.Row([
            ft.Icon("play_circle", size=24, color="white"),
            ft.Text("Start Server", size=16, weight=ft.FontWeight.BOLD, color="white"),
        ], alignment=ft.MainAxisAlignment.CENTER, spacing=10),
        on_click=toggle_server,
        height=60,
        width=400,
        bgcolor="#10b981",
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=12),
            elevation=4,
        )
    )

    # QR section
    qr_section = ft.Container(
        content=ft.Column([
            ft.Text("Scan to Connect", size=18, weight=ft.FontWeight.BOLD, 
                   color="#e5e7eb" if settings.theme == "dark" else "#1f2937"),
            ft.Text("Open the mobile app and scan this QR code", 
                   size=13, color="#6b7280", text_align=ft.TextAlign.CENTER),
            qr_container,
            url_container,
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
        padding=25,
        border_radius=15,
        bgcolor="#1a1a1a" if settings.theme == "dark" else "white",
        shadow=ft.BoxShadow(
            spread_radius=1,
            blur_radius=15,
            color="#00000015",
            offset=ft.Offset(0, 4),
        ),
        margin=ft.margin.only(top=20),
        width=400,
    )

    # Responsive content container
    content_column = ft.Column([
        status_card,
        start_button,
    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=20, scroll=ft.ScrollMode.AUTO)

    # Wrap in responsive container
    responsive_content = ft.Container(
        content=content_column,
        padding=30,
        alignment=ft.alignment.top_center,
    )

    # Main layout
    main_content = ft.Column([
        header,
        ft.Container(
            content=responsive_content,
            expand=True,
        ),
    ], spacing=0, expand=True)

    page.add(main_content)

    # Initial UI setup
    update_ui_for_server_state()

    # Handle window resize
    def on_resize(e):
        # Adjust content width based on window width
        if page.window.width < 600:
            responsive_content.padding = 15
            content_column.spacing = 15
        else:
            responsive_content.padding = 30
            content_column.spacing = 20
        page.update()

    page.on_resize = on_resize

    # Auto-start if enabled and server not already running
    if settings.auto_start and not server.is_running:
        logger.info("Auto-starting server")
        time.sleep(0.5)
        toggle_server(None)

    def shutdown_app():
        """Gracefully shutdown the application."""
        logger.info("Application closed")
        shutdown_event.set()
        page.window_destroy()

    def on_window_event(e):
        if e.data == "close":
            if not shutdown_event.is_set():
                shutdown_app()

    page.window_prevent_close = True
    page.on_window_event = on_window_event


if __name__ == "__main__":
    ft.app(target=main)