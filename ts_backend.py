import subprocess
import json
import platform
import re
import time
from typing import Dict, List, Tuple, Optional

def run_cmd(cmd: list[str]) -> str:
    try:
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
        )
        return result.stdout.strip()
    except Exception as e:
        return f"Error: {e}"

def get_local_ip() -> str:
    return run_cmd(["tailscale", "ip"])

def get_peers() -> list[dict]:
    raw = run_cmd(["tailscale", "status", "--json"])
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    
    peers = []
    for peer_id, peer in data.get("Peer", {}).items():
        peers.append({
            "id": peer_id,
            "hostname": peer.get("HostName", "?"),
            "ip": peer.get("TailscaleIPs", ["?"])[0],
            "online": peer.get("Online", False),
            "exit_node": peer.get("ExitNode", False),
            "os": peer.get("OS", "Unknown"),
            "relay": peer.get("Relay", ""),
            "rx_bytes": peer.get("RxBytes", 0),
            "tx_bytes": peer.get("TxBytes", 0),
            "last_seen": peer.get("LastSeen", ""),
            "endpoints": peer.get("Endpoints", [])
        })
    return peers

def get_self_info() -> dict:
    """Get information about the local node"""
    raw = run_cmd(["tailscale", "status", "--json"])
    try:
        data = json.loads(raw)
        self_data = data.get("Self", {})
        return {
            "id": self_data.get("PublicKey", ""),
            "hostname": self_data.get("HostName", "localhost"),
            "ip": self_data.get("TailscaleIPs", ["?"])[0] if self_data.get("TailscaleIPs") else "?",
            "online": True,
            "exit_node": self_data.get("ExitNode", False),
            "os": self_data.get("OS", platform.system()),
            "relay": "",
            "rx_bytes": 0,
            "tx_bytes": 0,
            "endpoints": []
        }
    except json.JSONDecodeError:
        return {
            "id": "self",
            "hostname": "localhost", 
            "ip": get_local_ip(),
            "online": True,
            "exit_node": False,
            "os": platform.system(),
            "relay": "",
            "rx_bytes": 0,
            "tx_bytes": 0,
            "endpoints": []
        }

def ping_with_latency(hostname: str) -> Tuple[bool, Optional[float]]:
    """Ping a host and return success status and latency in ms"""
    result = run_cmd(["tailscale", "ping", "-c", "1", hostname])
    
    if "pong" not in result.lower():
        return False, None
    
    # Try to extract latency from ping result
    # Look for patterns like "time=123.4ms" or "123.4ms"
    latency_match = re.search(r'time[=\s]+(\d+\.?\d*)\s*ms', result, re.IGNORECASE)
    if not latency_match:
        latency_match = re.search(r'(\d+\.?\d*)\s*ms', result)
    
    if latency_match:
        try:
            return True, float(latency_match.group(1))
        except ValueError:
            pass
    
    return True, None

def get_network_topology() -> Dict:
    """Build network topology with connection quality"""
    peers = get_peers()
    self_info = get_self_info()
    all_nodes = [self_info] + peers
    
    # Create connections map
    connections = {}
    
    # Test connections from self to all peers
    for peer in peers:
        if peer["online"]:
            success, latency = ping_with_latency(peer["hostname"])
            connections[f"{self_info['hostname']}->{peer['hostname']}"] = {
                "source": self_info["hostname"],
                "target": peer["hostname"],
                "status": "connected" if success else "unreachable",
                "latency": latency,
                "connection_type": get_connection_type(peer),
                "quality": get_connection_quality(latency) if latency else "unknown"
            }
    
    return {
        "nodes": all_nodes,
        "connections": connections,
        "center_node": self_info["hostname"]
    }

def get_connection_type(peer: dict) -> str:
    """Determine connection type based on peer info"""
    if peer.get("relay"):
        return "relay"
    elif peer.get("endpoints"):
        return "direct"
    else:
        return "unknown"

def get_connection_quality(latency: Optional[float]) -> str:
    """Categorize connection quality based on latency"""
    if latency is None:
        return "unknown"
    elif latency < 20:
        return "excellent"
    elif latency < 50:
        return "good"
    elif latency < 100:
        return "fair"
    else:
        return "poor"

def generate_topology_map(topology: Dict, width: int = 80, height: int = 20) -> List[str]:
    """Generate ASCII art representation of the network topology"""
    nodes = topology["nodes"]
    connections = topology["connections"]
    center_node = topology["center_node"]
    
    # Create the map canvas
    canvas = [[' ' for _ in range(width)] for _ in range(height)]
    
    # Position nodes
    center_x, center_y = width // 2, height // 2
    node_positions = {}
    
    # Place center node (self)
    center_info = next((n for n in nodes if n["hostname"] == center_node), None)
    if center_info:
        node_positions[center_node] = (center_x, center_y)
        place_node_on_canvas(canvas, center_x, center_y, center_node, "⊙", width, height)
    
    # Place other nodes in a circle around center
    online_peers = [n for n in nodes if n["hostname"] != center_node and n["online"]]
    if online_peers:
        import math
        angle_step = 2 * math.pi / len(online_peers)
        radius_x = min(width // 3, 20)
        radius_y = min(height // 3, 8)
        
        for i, peer in enumerate(online_peers):
            angle = i * angle_step
            x = int(center_x + radius_x * math.cos(angle))
            y = int(center_y + radius_y * math.sin(angle))
            
            # Ensure within bounds
            x = max(2, min(width - 3, x))
            y = max(1, min(height - 2, y))
            
            node_positions[peer["hostname"]] = (x, y)
            
            # Choose symbol based on node type
            symbol = get_node_symbol(peer)
            place_node_on_canvas(canvas, x, y, peer["hostname"], symbol, width, height)
            
            # Draw connection line
            connection_key = f"{center_node}->{peer['hostname']}"
            if connection_key in connections:
                conn = connections[connection_key]
                line_char = get_connection_char(conn["quality"])
                draw_line(canvas, center_x, center_y, x, y, line_char, width, height)
    
    # Add offline nodes at bottom
    offline_peers = [n for n in nodes if n["hostname"] != center_node and not n["online"]]
    if offline_peers:
        y_pos = height - 2
        x_start = 2
        for i, peer in enumerate(offline_peers[:10]):  # Limit to 10 offline nodes
            x_pos = x_start + i * 8
            if x_pos < width - 2:
                place_node_on_canvas(canvas, x_pos, y_pos, peer["hostname"], "○", width, height, offline=True)
    
    return [''.join(row) for row in canvas]

def place_node_on_canvas(canvas, x, y, hostname, symbol, width, height, offline=False):
    """Place a node symbol and label on the canvas"""
    if 0 <= y < height and 0 <= x < width:
        canvas[y][x] = symbol
        
        # Add hostname label
        label = hostname[:8]  # Truncate long names
        label_start = max(0, x - len(label) // 2)
        label_end = min(width, label_start + len(label))
        label = label[:label_end - label_start]
        
        # Place label below the node
        label_y = y + 1 if not offline else y - 1
        if 0 <= label_y < height:
            for i, char in enumerate(label):
                if label_start + i < width:
                    canvas[label_y][label_start + i] = char

def get_node_symbol(peer: dict) -> str:
    """Get appropriate symbol for a peer based on its properties"""
    if peer.get("exit_node"):
        return "⚡"  # Exit node
    elif peer.get("os", "").lower() in ["android", "ios"]:
        return "📱"  # Mobile device
    elif peer.get("os", "").lower() in ["darwin", "macos"]:
        return "🍎"  # Mac
    elif peer.get("os", "").lower() in ["windows"]:
        return "🪟"  # Windows
    elif peer.get("os", "").lower() in ["linux"]:
        return "🐧"  # Linux
    else:
        return "●"   # Generic device

def get_connection_char(quality: str) -> str:
    """Get line character based on connection quality"""
    quality_chars = {
        "excellent": "═",
        "good": "─",
        "fair": "┈",
        "poor": "·",
        "unknown": "?"
    }
    return quality_chars.get(quality, "─")

def draw_line(canvas, x1, y1, x2, y2, char, width, height):
    """Draw a line between two points using Bresenham's algorithm"""
    dx = abs(x2 - x1)
    dy = abs(y2 - y1)
    x, y = x1, y1
    sx = 1 if x1 < x2 else -1
    sy = 1 if y1 < y2 else -1
    
    if dx > dy:
        err = dx / 2
        while x != x2:
            if 0 <= x < width and 0 <= y < height and canvas[y][x] == ' ':
                canvas[y][x] = char
            err -= dy
            if err < 0:
                y += sy
                err += dx
            x += sx
    else:
        err = dy / 2
        while y != y2:
            if 0 <= x < width and 0 <= y < height and canvas[y][x] == ' ':
                canvas[y][x] = char
            err -= dx
            if err < 0:
                x += sx
                err += dy
            y += sy

def get_exit_node_info() -> tuple[list[str], str]:
    raw = run_cmd(["tailscale", "status", "--json"])
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return [], "Error"
    
    advertised = []
    current_exit = None
    
    for peer in data.get("Peer", {}).values():
        if peer.get("ExitNode", False):
            advertised.append(peer.get("HostName", "unknown"))
    
    current_exit = data.get("CurrentExit", None)
    current_node = data.get("Self", {}).get("ExitNode", False)
    using_exit = current_exit or current_node
    
    return advertised, "Using Exit Node: ✅" if using_exit else "Not using Exit Node"

def get_netcheck() -> str:
    return run_cmd(["tailscale", "netcheck"])

def ping(hostname: str) -> str:
    return run_cmd(["tailscale", "ping", hostname])

def set_exit_node(node_name: str) -> str:
    return run_cmd(["tailscale", "up", f"--exit-node={node_name}"])

def copy_to_clipboard(text: str):
    system = platform.system()
    try:
        if system == "Darwin":  # macOS
            subprocess.run("pbcopy", input=text, text=True)
        elif system == "Linux":
            subprocess.run("xclip -selection clipboard", input=text, shell=True, text=True)
        else:
            raise NotImplementedError("Clipboard copy not supported on this OS")
    except Exception as e:
        print(f"Clipboard error: {e}")