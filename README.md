# 🖥️ Remote Mouse Desktop Server

## 📦 Prerequisites

- **Python 3.8+**
- **uv** package manager → [Install uv](https://github.com/astral-sh/uv)

---

## ⚙️ Installation & Setup

### 1. Clone the Repository

```bash
git clone https://github.com/waniathar/remote_mouse_server.git
cd remote-mouse-desktop
```

### 2. Install Dependencies

Use **uv** to sync and install all required dependencies:

```bash
uv sync
```

This automatically creates a virtual environment and installs all necessary packages.

### 3. Start the Server

Run the application:

```bash
python app.py
```

This will:
- Launch a GUI window
- Start the server
- Display a QR code for connection

---

## 📱 Connecting the Mobile App

1. **Scan the QR Code**
   - Open the **Remote Mouse mobile app** on your smartphone.
   - Tap the **QR code icon** (top-left corner).
   - Scan the QR code displayed in the desktop app window.

2. **Wait for “Connected” Status**
   - Once connected, the app will show a “Connected” message.

3. **Close Desktop Window**
   - After connection, you can close the desktop app window.
   - ✅ The server will continue running in the background.

---

## 🧠 Managing the Server

### Check Server Status
The server continues running as a **background process** after setup.

### Stop the Server
To stop the server:

1. Run the app again:

   ```bash
   python app.py
   ```

2. Click **“Stop Server”** in the GUI.
   The server will shut down gracefully.

---

## 🧩 Troubleshooting

### 🛑 Server Won’t Start

```bash
# Check if port 8080 is already in use
netstat -ano | findstr :8080   # Windows
lsof -i :8080                  # macOS/Linux

# Kill the process using that port if needed
```

### ❌ QR Code Not Displaying
- Ensure your **firewall allows the app**
- Confirm you’re **connected to a network**
- Try **restarting the app**

### 📶 Connection Issues
- Ensure both devices are on the **same Wi-Fi network**
- Check firewall settings
- Verify antivirus isn’t interfering

---


When you close the main window, the server continues running in the background

Right-click the tray icon for quick options:
- Show Window
- Stop Server
- Exit

---

## ⚡ Auto-Start (Optional)

### Windows
Add to Startup folder:

```bash
Win + R → shell:startup
# Copy shortcut to app.py here
```

### macOS
Add to Login Items in **System Preferences** or create a **launch agent**.

### Linux
Add to **autostart applications** or create a **systemd service**.



## 📦 Requirements

The `uv sync` command will install the required modules


## 🔒 Security Notes

⚠️ **Important Security Information:**

- The server only accepts connections from your **local network**
- No internet connection is required or used
- All communication is **unencrypted** (use on trusted networks only)
- The server binds to `0.0.0.0` to accept local connections

---

## 🛠️ Support

If you encounter issues:
- Check the **Troubleshooting** section
- Review **GitHub Issues**
- Open a **new issue** with detailed information

---

## 🚀 Quick Start Card

```bash
# 1. Clone & Navigate
git clone https://github.com/waniathar/remote_mouse_server.git
cd remote_mouse_server

# 2. Install Dependencies
uv sync

# 3. Start Server
python app.py

# 4. Scan QR code with mobile app

# 5. Close window (server runs in background)

# 6. To stop: Run app.py again and click "Stop Server"
```

That’s it! You’re ready to control your computer. 🎉
