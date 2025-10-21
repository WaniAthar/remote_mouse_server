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
import signal
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
            )
            
            time.sleep(2)
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
            self.is_running = False
            self._clear_state()
            return False, f"Error stopping server: {str(e)}"

    def get_uptime(self) -> str:
        """Get server uptime as a formatted string"""
        if not self.start_time:
            return "00:00:00"
        delta = datetime.now() - self.start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


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
        
        return ft.Image(src_base64=src_base64, width=250, height=250, border_radius=12), ws_url
    except Exception as e:
        logger.error(f"Failed to generate QR code: {e}")
        raise


def main(page: ft.Page):
    page.title = "Remote Mouse Server"
    page.window_width = 700
    page.window_height = 500
    page.window_min_width = 600
    page.window_min_height = 450
    page.padding = 0
    page.spacing = 0
    
    # Initialize managers
    settings = Settings()
    server = ServerManager()
    shutdown_event = threading.Event()
    
    # Apply theme mode
    if settings.theme == "dark":
        page.theme_mode = ft.ThemeMode.DARK
    elif settings.theme == "light":
        page.theme_mode = ft.ThemeMode.LIGHT
    else:
        page.theme_mode = ft.ThemeMode.SYSTEM

    # UI References
    status_indicator = ft.Icon("circle", size=12, color="red")
    status_text = ft.Text("Offline", size=11)
    
    ip_text = ft.Text("---.---.---.---", size=13, weight=ft.FontWeight.W_500)
    port_text = ft.Text("----", size=13, weight=ft.FontWeight.W_500)
    uptime_text = ft.Text("00:00:00", size=28, weight=ft.FontWeight.W_600)
    qr_container = ft.Container(alignment=ft.alignment.center, expand=True)
    status_bar_text = ft.Text("Ready", size=11)
    
    # Main button reference
    start_btn = ft.Ref[ft.FilledButton]()
    stop_btn = ft.Ref[ft.OutlinedButton]()

    def update_uptime():
        """Background thread to update uptime"""
        while not shutdown_event.is_set():
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
            content=ft.Text(message),
            action="OK",
        )
        page.snack_bar.open = True
        page.update()

    # Dialogs
    about_dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("About Remote Mouse Server"),
        content=ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon("mouse", size=48),
                    ft.Column([
                        ft.Text("Remote Mouse Server", size=18, weight=ft.FontWeight.BOLD),
                        ft.Text(f"Version {APP_VERSION}", size=12),
                    ], spacing=4),
                ], spacing=16),
                ft.Divider(height=20),
                ft.Text("Control your computer remotely using your smartphone as a mouse and keyboard.", size=13),
                ft.Divider(height=10),
                ft.Text("Features:", size=14, weight=ft.FontWeight.BOLD),
                ft.Text("• Real-time WebSocket communication", size=12),
                ft.Text("• Gyroscope-based motion tracking", size=12),
                ft.Text("• Secure QR code pairing", size=12),
                ft.Text("• Cross-platform support", size=12),
                ft.Divider(height=20),
                ft.Text("Built with Flet & FastAPI", size=11, italic=True),
            ], tight=True, spacing=4),
            width=450,
        ),
        actions=[
            ft.TextButton("Close", on_click=lambda e: page.close(about_dlg)),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    # Settings dialog
    port_field = ft.TextField(
        label="Server Port",
        value=str(settings.preferred_port),
        keyboard_type=ft.KeyboardType.NUMBER,
        width=200,
    )
    
    theme_dropdown = ft.Dropdown(
        label="Theme",
        value=settings.theme,
        options=[
            ft.dropdown.Option("light", "Light"),
            ft.dropdown.Option("dark", "Dark"),
            ft.dropdown.Option("system", "System"),
        ],
        width=200,
    )

    auto_start_switch = ft.Switch(
        label="Auto-start server on launch",
        value=settings.auto_start,
    )

    logging_switch = ft.Switch(
        label="Enable detailed logging",
        value=settings.enable_logging,
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

            if settings.theme == "dark":
                page.theme_mode = ft.ThemeMode.DARK
            elif settings.theme == "light":
                page.theme_mode = ft.ThemeMode.LIGHT
            else:
                page.theme_mode = ft.ThemeMode.SYSTEM
            
            page.close(settings_dlg)
            show_snackbar("Settings saved successfully")
            
        except ValueError:
            port_field.error_text = "Invalid port number"
            page.update()

    settings_dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Settings"),
        content=ft.Container(
            content=ft.Column([
                ft.Text("Network Configuration", weight=ft.FontWeight.BOLD, size=14),
                port_field,
                ft.Divider(height=20),
                ft.Text("Appearance", weight=ft.FontWeight.BOLD, size=14),
                theme_dropdown,
                ft.Divider(height=20),
                ft.Text("Behavior", weight=ft.FontWeight.BOLD, size=14),
                auto_start_switch,
                logging_switch,
            ], tight=True, spacing=10),
            width=400,
        ),
        actions=[
            ft.TextButton("Cancel", on_click=lambda e: page.close(settings_dlg)),
            ft.FilledButton("Save", on_click=save_settings),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    # Logs dialog
    logs_text = ft.Text("", size=10, selectable=True)
    
    def refresh_logs():
        try:
            if os.path.exists(LOG_FILE):
                with open(LOG_FILE, 'r') as f:
                    logs = f.read()
                    log_lines = logs.split('\n')[-100:]
                    logs_text.value = '\n'.join(log_lines)
                    page.update()
            else:
                logs_text.value = "No logs available"
                page.update()
        except Exception as ex:
            logs_text.value = f"Error reading logs: {ex}"
            page.update()

    def clear_logs(e):
        try:
            with open(LOG_FILE, 'w') as f:
                f.write('')
            logs_text.value = ""
            page.update()
            show_snackbar("Logs cleared")
        except Exception as ex:
            show_snackbar(f"Error: {ex}", True)

    logs_dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Server Logs"),
        content=ft.Container(
            content=ft.Column([
                ft.Container(
                    content=logs_text,
                    padding=10,
                )
            ], scroll=ft.ScrollMode.AUTO),
            width=650,
            height=400,
        ),
        actions=[
            ft.TextButton("Refresh", on_click=lambda e: refresh_logs()),
            ft.TextButton("Clear", on_click=clear_logs),
            ft.TextButton("Close", on_click=lambda e: page.close(logs_dlg)),
        ],
        actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )

    def update_ui_for_server_state():
        """Updates the UI based on the current server state."""
        if server.is_running:
            status_indicator.color = "green"
            status_text.value = "Running"
            ip_text.value = server.ip
            port_text.value = str(server.port)
            status_bar_text.value = f"Server running on {server.ip}:{server.port} | PID: {server.pid}"
            
            start_btn.current.visible = False
            stop_btn.current.visible = True
            
            try:
                qr_image, ws_url = generate_qr(server.ip, server.port)
                qr_container.content = ft.Column([
                    ft.Container(
                        content=qr_image,
                        bgcolor="white",
                        border_radius=12,
                        padding=12,
                    ),
                    ft.Container(height=12),
                    ft.Text("Scan with mobile app", size=13, weight=ft.FontWeight.W_500),
                    ft.Container(
                        content=ft.SelectionArea(
                            content=ft.Text(
                                ws_url,
                                size=10,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ),
                        border_radius=6,
                        padding=ft.padding.symmetric(horizontal=12, vertical=6),
                    ),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER)
                
            except Exception as ex:
                logger.error(f"Failed to generate QR: {ex}")
                
        else:
            status_indicator.color = "red"
            status_text.value = "Offline"
            ip_text.value = "---.---.---.---"
            port_text.value = "----"
            uptime_text.value = "00:00:00"
            status_bar_text.value = "Ready"
            
            start_btn.current.visible = True
            stop_btn.current.visible = False
            
            qr_container.content = ft.Container(
                content=ft.Column([
                    ft.Icon("qr_code_2", size=100),
                    ft.Container(height=12),
                    ft.Text("QR Code will appear here", size=13, weight=ft.FontWeight.W_500),
                    ft.Text("Start the server to generate", size=11),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                alignment=ft.alignment.center,
            )
        
        page.update()

    def start_server(e):
        """Start the server"""
        start_btn.current.disabled = True
        page.update()

        success, message = server.start(settings.preferred_port)
        if success:
            show_snackbar("Server started successfully!")
        else:
            show_snackbar(message, True)
        
        start_btn.current.disabled = False
        update_ui_for_server_state()

    def stop_server(e):
        """Stop the server"""
        stop_btn.current.disabled = True
        page.update()

        success, message = server.stop()
        if success:
            show_snackbar("Server stopped")
        else:
            show_snackbar(message, True)
        
        stop_btn.current.disabled = False
        update_ui_for_server_state()

    # Toolbar with clear action buttons
    toolbar = ft.Container(
        content=ft.Row([
            ft.IconButton(
                icon="settings",
                tooltip="Settings",
                on_click=lambda e: page.open(settings_dlg),
            ),
            ft.IconButton(
                icon="description",
                tooltip="View Logs",
                on_click=lambda e: (refresh_logs(), page.open(logs_dlg)),
            ),
            ft.IconButton(
                icon="refresh",
                tooltip="Refresh",
                on_click=lambda e: update_ui_for_server_state(),
            ),
            ft.IconButton(
                icon="info",
                tooltip="About",
                on_click=lambda e: page.open(about_dlg),
            ),
        ], alignment=ft.MainAxisAlignment.END),
        padding=ft.padding.only(right=8, top=8, bottom=8),
        border=ft.border.only(bottom=ft.BorderSide(1, "outline")),
    )

    # Left Panel - Server Info
    left_panel = ft.Container(
        content=ft.Column([
            # Header
            ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon("mouse", size=24),
                        ft.Text("Remote Mouse", size=16, weight=ft.FontWeight.BOLD),
                    ], spacing=8),
                    ft.Container(height=8),
                    ft.Row([
                        status_indicator,
                        status_text,
                    ], spacing=8),
                ]),
                padding=16,
            ),
            
            ft.Divider(height=1),
            
            # Server Info
            ft.Container(
                content=ft.Column([
                    ft.ListTile(
                        leading=ft.Icon("router", size=20),
                        title=ft.Text("IP Address", size=11),
                        subtitle=ip_text,
                        dense=True,
                    ),
                    ft.ListTile(
                        leading=ft.Icon("settings_ethernet", size=20),
                        title=ft.Text("Port", size=11),
                        subtitle=port_text,
                        dense=True,
                    ),
                ], spacing=0),
            ),
            
            ft.Divider(height=1),
            
            # Uptime
            ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon("schedule", size=18),
                        ft.Text("Uptime", size=11, weight=ft.FontWeight.BOLD),
                    ], spacing=8),
                    ft.Container(height=8),
                    uptime_text,
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=16,
            ),
            
            ft.Container(expand=True),
            
            # Control Buttons
            ft.Container(
                content=ft.Column([
                    ft.FilledButton(
                        ref=start_btn,
                        text="Start Server",
                        icon="play_arrow",
                        on_click=start_server,
                        width=float("inf"),
                        height=45,
                    ),
                    ft.OutlinedButton(
                        ref=stop_btn,
                        text="Stop Server",
                        icon="stop",
                        on_click=stop_server,
                        width=float("inf"),
                        height=45,
                        visible=False,
                    ),
                ], spacing=8),
                padding=16,
            ),
        ]),
        width=260,
        border=ft.border.only(right=ft.BorderSide(1, "outline")),
    )

    # Right Panel - QR Code
    right_panel = ft.Container(
        content=qr_container,
        padding=16,
        expand=True,
    )

    # Status Bar
    status_bar = ft.Container(
        content=ft.Row([
            ft.Icon("circle", size=8, color="green" if server.is_running else "red"),
            status_bar_text,
        ], spacing=8),
        padding=ft.padding.symmetric(horizontal=12, vertical=6),
        border=ft.border.only(top=ft.BorderSide(1, "outline")),
    )

    # Main Layout
    main_content = ft.Column([
        toolbar,
        ft.Container(
            content=ft.Row([
                left_panel,
                right_panel,
            ], spacing=0, expand=True),
            expand=True,
        ),
        status_bar,
    ], spacing=0, expand=True)

    page.add(main_content)
    
    # Initial UI update
    update_ui_for_server_state()

    # Auto-start if enabled
    if settings.auto_start and not server.is_running:
        logger.info("Auto-starting server")
        time.sleep(0.5)
        start_server(None)

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