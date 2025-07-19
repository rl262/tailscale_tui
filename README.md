# Tailscale Dashboard

A powerful, real-time terminal-based dashboard for monitoring and managing your Tailscale VPN network. Built with Python and the Textual framework, this tool provides an intuitive interface for viewing network status, peer connections, and performing network diagnostics.

## ✨ Features

- **Real-time Network Monitoring** - Live updates every 10 seconds showing current network status
- **Interactive Peer Management** - View all connected devices with hostname, IP, online status, and OS information
- **Network Diagnostics** - Integrated `tailscale netcheck` output for connectivity troubleshooting
- **Exit Node Management** - Monitor available exit nodes and current usage status
- **Ping Testing** - Click on any peer to test connectivity with interactive ping results
- **Cross-platform Clipboard** - Copy network information to clipboard (macOS/Linux)
- **Keyboard Shortcuts** - Quick refresh and navigation controls

## 🖥️ Screenshots

The dashboard displays:
- Your local Tailscale IP address
- Available and currently used exit nodes
- A comprehensive peer table with real-time status
- Network diagnostics information
- Interactive ping results in modal dialogs

## 📋 Requirements

### System Requirements
- **Operating System**: macOS or Linux
- **Python**: 3.8 or higher
- **Tailscale**: Must be installed and authenticated

### Python Dependencies
- `textual` - Modern terminal UI framework

### System Dependencies
- `tailscale` CLI tool (must be in PATH)
- `xclip` (Linux only, for clipboard functionality)

## 🚀 Installation

1. **Clone or download the project files**:
   ```bash
   # Ensure you have both files:
   # - ts_backend.py
   # - main.py
   ```

2. **Install Python dependencies**:
   ```bash
   pip install textual
   ```

3. **Verify Tailscale installation**:
   ```bash
   tailscale version
   tailscale status
   ```

4. **Install system dependencies** (Linux only):
   ```bash
   # Ubuntu/Debian
   sudo apt install xclip
   
   # Fedora/RHEL
   sudo dnf install xclip
   
   # Arch Linux
   sudo pacman -S xclip
   ```

## 🎮 Usage

### Starting the Dashboard
```bash
python main.py
```

### Keyboard Controls
- **`q`** - Quit the application
- **`r`** - Manually refresh all data
- **`↑/↓`** - Navigate through the peer table
- **`Enter`** - Ping the selected peer
- **`Esc`** - Close ping result dialogs

### Interface Elements

**Header**: Shows current time and application title

**Network Info Section**:
- **Local IP**: Your Tailscale IP address
- **Exit Nodes**: Lists available exit nodes and current usage status

**Peer Table**: Interactive table showing:
- **Hostname**: Device name
- **IP**: Tailscale IP address
- **Online**: Connection status (✅/❌)
- **Exit Node**: Shows 🌐 if device can act as exit node
- **OS**: Operating system of the peer

**Network Check**: Output from `tailscale netcheck` for diagnostics

**Footer**: Shows available keyboard shortcuts

## 🔧 Configuration

The application uses default settings but can be customized by modifying the source code:

- **Refresh interval**: Change the `sleep(10)` value in `refresh_loop()` (main.py)
- **Table styling**: Modify the `DataTable` configuration
- **UI colors/theme**: Add custom CSS to the `CSS_PATH` variable

## 📁 File Structure

```
tailscale-dashboard/
├── ts_backend.py      # Backend API for Tailscale operations
├── main.py           # Main TUI application
└── README.md         # This file
```

### ts_backend.py
Backend module containing functions for:
- Executing Tailscale CLI commands safely
- Retrieving network and peer information
- Managing exit nodes
- Network diagnostics
- Cross-platform utilities

### main.py
Main application featuring:
- Textual-based terminal user interface
- Reactive data updates
- Interactive peer table
- Modal dialog system for ping results
- Keyboard shortcut handling

## 🛠️ Troubleshooting

### Common Issues

**"Command not found: tailscale"**
- Ensure Tailscale is installed and in your PATH
- Try running `which tailscale` to verify installation

**"No peers showing"**
- Verify Tailscale is connected: `tailscale status`
- Check if you're logged in: `tailscale login`

**"Clipboard error"**
- On Linux: Install `xclip` package
- On unsupported systems: Clipboard features will be disabled

**"Permission denied"**
- Ensure your user has permission to run `tailscale` commands
- Some operations may require sudo privileges

### Debug Mode
For troubleshooting, you can run individual backend functions:
```python
python3 -c "from ts_backend import get_peers; print(get_peers())"
```

## 🤝 Contributing

Contributions are welcome! Areas for improvement:
- Windows support for clipboard functionality
- Additional Tailscale management features
- UI themes and customization options
- Export functionality for network reports
- Integration with Tailscale ACL management

## 📄 License

This project is provided as-is. Feel free to modify and distribute according to your needs.

## 🔗 Related Links

- [Tailscale Documentation](https://tailscale.com/docs/)
- [Textual Framework](https://textual.textualize.io/)
- [Python Subprocess Documentation](https://docs.python.org/3/library/subprocess.html)

## 📞 Support

For issues related to:
- **Tailscale connectivity**: Check Tailscale documentation and support
- **Python/Textual issues**: Refer to respective project documentation
- **Application bugs**: Review the code and modify as needed

---