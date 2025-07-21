import subprocess
import json
import platform
import re
import time
import socket
from typing import Dict, List, Tuple, Optional

# Try to import psutil, provide fallback if not available
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("Warning: psutil not installed. Bandwidth monitoring will be disabled.")
    print("Install with: pip install psutil")

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
        peer_data = {
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
        }
        
        # Add geographic information
        peer_data["location"] = get_peer_location(peer)
        
        peers.append(peer_data)
    return peers

def get_self_info() -> dict:
    """Get information about the local node"""
    raw = run_cmd(["tailscale", "status", "--json"])
    try:
        data = json.loads(raw)
        self_data = data.get("Self", {})
        
        # Check if Tailscale is running
        backend_state = data.get("BackendState", "Unknown")
        if backend_state == "Stopped":
            result = {
                "id": "self",
                "hostname": "localhost (Tailscale stopped)", 
                "ip": "Not connected",
                "online": False,
                "exit_node": False,
                "os": platform.system(),
                "relay": "",
                "rx_bytes": 0,
                "tx_bytes": 0,
                "endpoints": []
            }
        else:
            result = {
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
        result = {
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
    
    # Add location information for self
    result["location"] = get_local_location()
    return result

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

def get_peer_location(peer: dict) -> dict:
    """Extract location information from peer data"""
    location_info = {
        "city": "Unknown",
        "country": "Unknown", 
        "country_code": "??",
        "region": "Unknown",
        "latitude": None,
        "longitude": None,
        "timezone": "Unknown"
    }
    
    # Try to extract location from relay information
    relay = peer.get("Relay", "")
    if relay:
        location_info.update(parse_relay_location(relay))
    
    # Try to extract location from endpoints (IP geolocation)
    endpoints = peer.get("Endpoints", [])
    if endpoints and not relay:
        # Use the first endpoint for geolocation
        first_endpoint = endpoints[0]
        if ":" in first_endpoint:
            ip = first_endpoint.split(":")[0]
            location_info.update(geolocate_ip(ip))
    
    # Try to extract location from hostname patterns
    hostname = peer.get("HostName", "")
    hostname_location = parse_hostname_location(hostname)
    if hostname_location["country"] != "Unknown":
        location_info.update(hostname_location)
    
    return location_info

def get_local_location() -> dict:
    """Get location information for the local node"""
    location_info = {
        "city": "Unknown",
        "country": "Unknown", 
        "country_code": "??",
        "region": "Unknown",
        "latitude": None,
        "longitude": None,
        "timezone": "Unknown"
    }
    
    # Try to get location from netcheck output
    netcheck = get_netcheck()
    netcheck_location = parse_netcheck_location(netcheck)
    if netcheck_location["country"] != "Unknown":
        location_info.update(netcheck_location)
    
    # Fallback: try to detect from system timezone
    try:
        import time
        timezone = time.tzname[0] if hasattr(time, 'tzname') else "Unknown"
        location_info["timezone"] = timezone
        
        # Try to infer region from timezone
        if "/" in timezone:
            parts = timezone.split("/")
            if len(parts) >= 2:
                location_info["region"] = parts[1].replace("_", " ")
    except:
        pass
    
    return location_info

def parse_relay_location(relay: str) -> dict:
    """Parse location from Tailscale relay server names"""
    location_mapping = {
        # North America
        "nyc": {"city": "New York", "country": "United States", "country_code": "US", "region": "North America"},
        "sfo": {"city": "San Francisco", "country": "United States", "country_code": "US", "region": "North America"},
        "sea": {"city": "Seattle", "country": "United States", "country_code": "US", "region": "North America"},
        "dal": {"city": "Dallas", "country": "United States", "country_code": "US", "region": "North America"},
        "chi": {"city": "Chicago", "country": "United States", "country_code": "US", "region": "North America"},
        "mia": {"city": "Miami", "country": "United States", "country_code": "US", "region": "North America"},
        "den": {"city": "Denver", "country": "United States", "country_code": "US", "region": "North America"},
        "tor": {"city": "Toronto", "country": "Canada", "country_code": "CA", "region": "North America"},
        
        # Europe
        "lhr": {"city": "London", "country": "United Kingdom", "country_code": "GB", "region": "Europe"},
        "fra": {"city": "Frankfurt", "country": "Germany", "country_code": "DE", "region": "Europe"},
        "ams": {"city": "Amsterdam", "country": "Netherlands", "country_code": "NL", "region": "Europe"},
        "par": {"city": "Paris", "country": "France", "country_code": "FR", "region": "Europe"},
        "mad": {"city": "Madrid", "country": "Spain", "country_code": "ES", "region": "Europe"},
        "mil": {"city": "Milan", "country": "Italy", "country_code": "IT", "region": "Europe"},
        "sto": {"city": "Stockholm", "country": "Sweden", "country_code": "SE", "region": "Europe"},
        "war": {"city": "Warsaw", "country": "Poland", "country_code": "PL", "region": "Europe"},
        
        # Asia Pacific
        "nrt": {"city": "Tokyo", "country": "Japan", "country_code": "JP", "region": "Asia Pacific"},
        "hkg": {"city": "Hong Kong", "country": "Hong Kong", "country_code": "HK", "region": "Asia Pacific"},
        "sin": {"city": "Singapore", "country": "Singapore", "country_code": "SG", "region": "Asia Pacific"},
        "syd": {"city": "Sydney", "country": "Australia", "country_code": "AU", "region": "Asia Pacific"},
        "blr": {"city": "Bangalore", "country": "India", "country_code": "IN", "region": "Asia Pacific"},
        "icn": {"city": "Seoul", "country": "South Korea", "country_code": "KR", "region": "Asia Pacific"},
        
        # South America
        "sao": {"city": "São Paulo", "country": "Brazil", "country_code": "BR", "region": "South America"},
        
        # Africa & Middle East
        "jnb": {"city": "Johannesburg", "country": "South Africa", "country_code": "ZA", "region": "Africa"},
        "dxb": {"city": "Dubai", "country": "UAE", "country_code": "AE", "region": "Middle East"},
    }
    
    relay_lower = relay.lower()
    for code, location in location_mapping.items():
        if code in relay_lower:
            return {
                "city": location["city"],
                "country": location["country"], 
                "country_code": location["country_code"],
                "region": location["region"],
                "latitude": None,
                "longitude": None,
                "timezone": "Unknown"
            }
    
    return {"city": "Unknown", "country": "Unknown", "country_code": "??", "region": "Unknown", "latitude": None, "longitude": None, "timezone": "Unknown"}

def parse_netcheck_location(netcheck: str) -> dict:
    """Parse location information from netcheck output"""
    location_info = {"city": "Unknown", "country": "Unknown", "country_code": "??", "region": "Unknown", "latitude": None, "longitude": None, "timezone": "Unknown"}
    
    try:
        # Look for location information in netcheck output
        lines = netcheck.split('\n')
        for line in lines:
            line = line.strip()
            if 'Region:' in line:
                region = line.split('Region:')[1].strip()
                location_info["region"] = region
            elif 'Country:' in line:
                country = line.split('Country:')[1].strip()
                location_info["country"] = country
            elif 'City:' in line:
                city = line.split('City:')[1].strip()
                location_info["city"] = city
    except:
        pass
    
    return location_info

def parse_hostname_location(hostname: str) -> dict:
    """Try to infer location from hostname patterns"""
    location_info = {"city": "Unknown", "country": "Unknown", "country_code": "??", "region": "Unknown", "latitude": None, "longitude": None, "timezone": "Unknown"}
    
    hostname_lower = hostname.lower()
    
    # Common hostname patterns that indicate location
    location_patterns = {
        # Cities
        "nyc": {"city": "New York", "country": "United States", "country_code": "US"},
        "sf": {"city": "San Francisco", "country": "United States", "country_code": "US"},
        "la": {"city": "Los Angeles", "country": "United States", "country_code": "US"},
        "london": {"city": "London", "country": "United Kingdom", "country_code": "GB"},
        "paris": {"city": "Paris", "country": "France", "country_code": "FR"},
        "tokyo": {"city": "Tokyo", "country": "Japan", "country_code": "JP"},
        "sydney": {"city": "Sydney", "country": "Australia", "country_code": "AU"},
        
        # Countries
        "usa": {"country": "United States", "country_code": "US", "region": "North America"},
        "canada": {"country": "Canada", "country_code": "CA", "region": "North America"},
        "uk": {"country": "United Kingdom", "country_code": "GB", "region": "Europe"},
        "germany": {"country": "Germany", "country_code": "DE", "region": "Europe"},
        "france": {"country": "France", "country_code": "FR", "region": "Europe"},
        "japan": {"country": "Japan", "country_code": "JP", "region": "Asia Pacific"},
        "australia": {"country": "Australia", "country_code": "AU", "region": "Asia Pacific"},
    }
    
    for pattern, location in location_patterns.items():
        if pattern in hostname_lower:
            location_info.update(location)
            break
    
    return location_info

def geolocate_ip(ip: str) -> dict:
    """Basic IP geolocation (simplified version)"""
    location_info = {"city": "Unknown", "country": "Unknown", "country_code": "??", "region": "Unknown", "latitude": None, "longitude": None, "timezone": "Unknown"}
    
    # This is a simplified version. In a real implementation, you might want to:
    # 1. Use a geolocation API service
    # 2. Use a local GeoIP database
    # 3. Cache results to avoid repeated lookups
    
    # For now, we'll just detect some obvious patterns
    if ip.startswith("192.168.") or ip.startswith("10.") or ip.startswith("172."):
        location_info.update({
            "city": "Local Network",
            "country": "Private",
            "country_code": "LAN",
            "region": "Local"
        })
    
    return location_info
    """Determine connection type based on peer info"""
    if peer.get("relay"):
        return "relay"
    elif peer.get("endpoints"):
        return "direct"
    else:
        return "unknown"

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

def generate_topology_map(topology: Dict, width: int = 80, height: int = 20, view_mode: str = "standard") -> List[str]:
    """Generate ASCII art representation of the network topology"""
    nodes = topology["nodes"]
    connections = topology["connections"]
    center_node = topology["center_node"]
    
    if view_mode == "geographic":
        return generate_geographic_map(topology, width, height)
    else:
        return generate_standard_map(topology, width, height)

def generate_geographic_map(topology: Dict, width: int = 80, height: int = 20) -> List[str]:
    """Generate a geography-based topology map"""
    nodes = topology["nodes"]
    connections = topology["connections"]
    center_node = topology["center_node"]
    
    # Create the map canvas
    canvas = [[' ' for _ in range(width)] for _ in range(height)]
    
    # Group nodes by region/country
    regions = {}
    for node in nodes:
        if node["online"] or node["hostname"] == center_node:
            location = node.get("location", {})
            region = location.get("region", "Unknown")
            country = location.get("country", "Unknown")
            
            region_key = f"{region}"
            if region_key not in regions:
                regions[region_key] = []
            regions[region_key].append(node)
    
    # Position regions across the map
    region_positions = {}
    region_keys = list(regions.keys())
    
    if region_keys:
        # Define rough geographic positions (simplified world map)
        geographic_layout = {
            "North America": (width // 4, height // 3),
            "Europe": (width // 2, height // 4),
            "Asia Pacific": (3 * width // 4, height // 3),
            "South America": (width // 3, 2 * height // 3),
            "Africa": (width // 2, 2 * height // 3),
            "Middle East": (2 * width // 3, height // 2),
            "Unknown": (width // 2, height // 2)
        }
        
        for i, region in enumerate(region_keys):
            if region in geographic_layout:
                region_positions[region] = geographic_layout[region]
            else:
                # Distribute unknown regions
                angle = (i * 2 * 3.14159) / len(region_keys)
                x = int(width // 2 + (width // 4) * (angle / 3.14159))
                y = int(height // 2 + (height // 4) * (angle / 3.14159))
                region_positions[region] = (max(5, min(width - 5, x)), max(2, min(height - 2, y)))
    
    # Place nodes within regions
    node_positions = {}
    center_pos = None
    
    for region, region_nodes in regions.items():
        if region not in region_positions:
            continue
            
        base_x, base_y = region_positions[region]
        
        # Place nodes in a small cluster around the region center
        for i, node in enumerate(region_nodes):
            offset_x = (i % 3 - 1) * 3  # -3, 0, 3
            offset_y = (i // 3 - 1) * 2  # -2, 0, 2
            
            x = max(2, min(width - 3, base_x + offset_x))
            y = max(1, min(height - 2, base_y + offset_y))
            
            node_positions[node["hostname"]] = (x, y)
            
            if node["hostname"] == center_node:
                center_pos = (x, y)
            
            # Place node on canvas
            symbol = get_node_symbol(node)
            place_node_on_canvas(canvas, x, y, node["hostname"], symbol, width, height)
            
            # Add location label
            location = node.get("location", {})
            country_code = location.get("country_code", "??")
            if country_code != "??":
                label_y = y - 2 if y > 2 else y + 2
                if 0 <= label_y < height:
                    for j, char in enumerate(country_code):
                        if x + j < width:
                            canvas[label_y][x + j] = char
    
    # Draw connections from center to other nodes
    if center_pos:
        center_x, center_y = center_pos
        for connection_key, conn in connections.items():
            target_hostname = conn["target"]
            if target_hostname in node_positions:
                target_x, target_y = node_positions[target_hostname]
                line_char = get_connection_char(conn["quality"])
                draw_line(canvas, center_x, center_y, target_x, target_y, line_char, width, height)
    
    # Add region labels
    for region, (x, y) in region_positions.items():
        if region != "Unknown" and region in regions:
            label = region[:12]  # Truncate long region names
            label_y = max(0, y - 3)
            label_x = max(0, x - len(label) // 2)
            
            if label_y < height:
                for i, char in enumerate(label):
                    if label_x + i < width:
                        canvas[label_y][label_x + i] = char
    
    return [''.join(row) for row in canvas]

def generate_standard_map(topology: Dict, width: int = 80, height: int = 20) -> List[str]:
    """Generate standard hub-and-spoke topology map"""
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
            
            # Add location info below hostname
            location = peer.get("location", {})
            country_code = location.get("country_code", "")
            city = location.get("city", "")
            
            if country_code and country_code != "??":
                location_label = f"{country_code}"
                if city and city != "Unknown":
                    location_label = f"{city[:8]},{country_code}"
                
                label_y = y + 2
                label_x = max(0, x - len(location_label) // 2)
                if label_y < height:
                    for j, char in enumerate(location_label):
                        if label_x + j < width:
                            canvas[label_y][label_x + j] = char
            
            # Draw connection line
            connection_key = f"{center_node}->{peer['hostname']}"
            if connection_key in connections:
                conn = connections[connection_key]
                line_char = get_connection_char(conn["quality"])
                draw_line(canvas, center_x, center_y, x, y, line_char, width, height)
    
    # Add offline nodes at bottom with location info
    offline_peers = [n for n in nodes if n["hostname"] != center_node and not n["online"]]
    if offline_peers:
        y_pos = height - 3
        x_start = 2
        for i, peer in enumerate(offline_peers[:8]):  # Limit to 8 offline nodes
            x_pos = x_start + i * 10
            if x_pos < width - 2:
                place_node_on_canvas(canvas, x_pos, y_pos, peer["hostname"], "○", width, height, offline=True)
                
                # Add location for offline nodes too
                location = peer.get("location", {})
                country_code = location.get("country_code", "")
                if country_code and country_code != "??":
                    label_y = y_pos + 1
                    if label_y < height:
                        for j, char in enumerate(country_code):
                            if x_pos + j < width:
                                canvas[label_y][x_pos + j] = char
    
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
        return [], "Error parsing status"
    
    # Check if Tailscale is running
    backend_state = data.get("BackendState", "Unknown")
    if backend_state == "Stopped":
        return [], "Tailscale is stopped"
    
    advertised = []
    current_exit = None
    
    # Handle case where Peer data might be None or missing
    peers = data.get("Peer", {})
    if peers is None:
        peers = {}
    
    for peer in peers.values():
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

# Bandwidth monitoring functionality
class BandwidthMonitor:
    def __init__(self):
        self.previous_stats = {}
        self.bandwidth_history = {}
        self.max_history_points = 50
        self.psutil_available = PSUTIL_AVAILABLE
        
    def get_tailscale_interface(self) -> Optional[str]:
        """Find the Tailscale network interface"""
        if not self.psutil_available:
            return None
            
        try:
            # Common Tailscale interface names
            possible_interfaces = ["tailscale0", "utun", "tun"]
            
            # Get all network interfaces
            interfaces = psutil.net_if_addrs()
            
            # First, try to find interface with Tailscale IP
            tailscale_ip = get_local_ip()
            if tailscale_ip and tailscale_ip != "Error":
                for interface, addrs in interfaces.items():
                    for addr in addrs:
                        if hasattr(addr, 'address') and addr.address == tailscale_ip:
                            return interface
            
            # Fallback: look for common Tailscale interface patterns
            for interface in interfaces.keys():
                interface_lower = interface.lower()
                if any(pattern in interface_lower for pattern in possible_interfaces):
                    return interface
                    
            return None
        except Exception:
            return None
    
    def get_interface_stats(self, interface: str) -> Dict:
        """Get network statistics for a specific interface"""
        if not self.psutil_available:
            return {}
            
        try:
            stats = psutil.net_io_counters(pernic=True)
            if interface in stats:
                stat = stats[interface]
                return {
                    "bytes_sent": stat.bytes_sent,
                    "bytes_recv": stat.bytes_recv,
                    "packets_sent": stat.packets_sent,
                    "packets_recv": stat.packets_recv,
                    "timestamp": time.time()
                }
        except Exception:
            pass
        return {}
    
    def calculate_bandwidth(self, interface: str) -> Dict:
        """Calculate current bandwidth usage"""
        if not self.psutil_available:
            return {"upload_bps": 0, "download_bps": 0, "error": "psutil not available"}
            
        current_stats = self.get_interface_stats(interface)
        
        if not current_stats:
            return {"upload_bps": 0, "download_bps": 0, "error": "No interface stats"}
        
        current_time = current_stats["timestamp"]
        
        if interface in self.previous_stats:
            prev_stats = self.previous_stats[interface]
            time_diff = current_time - prev_stats["timestamp"]
            
            if time_diff > 0:
                # Calculate bytes per second
                upload_bps = (current_stats["bytes_sent"] - prev_stats["bytes_sent"]) / time_diff
                download_bps = (current_stats["bytes_recv"] - prev_stats["bytes_recv"]) / time_diff
                
                # Store current stats for next calculation
                self.previous_stats[interface] = current_stats
                
                # Update history
                if interface not in self.bandwidth_history:
                    self.bandwidth_history[interface] = {"upload": [], "download": [], "timestamps": []}
                
                history = self.bandwidth_history[interface]
                history["upload"].append(max(0, upload_bps))
                history["download"].append(max(0, download_bps))
                history["timestamps"].append(current_time)
                
                # Keep only recent history
                if len(history["upload"]) > self.max_history_points:
                    history["upload"] = history["upload"][-self.max_history_points:]
                    history["download"] = history["download"][-self.max_history_points:]
                    history["timestamps"] = history["timestamps"][-self.max_history_points:]
                
                return {
                    "upload_bps": upload_bps,
                    "download_bps": download_bps,
                    "upload_history": history["upload"],
                    "download_history": history["download"],
                    "interface": interface
                }
        
        # First measurement - store but return zero
        self.previous_stats[interface] = current_stats
        return {"upload_bps": 0, "download_bps": 0, "interface": interface}
    
    def get_bandwidth_data(self) -> Dict:
        """Get current bandwidth data for Tailscale interface"""
        if not self.psutil_available:
            return {
                "error": "psutil library not installed. Run: pip install psutil",
                "upload_bps": 0,
                "download_bps": 0,
                "interface": "unavailable"
            }
            
        interface = self.get_tailscale_interface()
        
        if not interface:
            return {
                "error": "Tailscale interface not found",
                "upload_bps": 0,
                "download_bps": 0,
                "interface": "unknown"
            }
        
        return self.calculate_bandwidth(interface)

def format_bytes(bytes_value: float) -> str:
    """Format bytes into human readable format"""
    if bytes_value == 0:
        return "0 B/s"
    
    units = ["B/s", "KB/s", "MB/s", "GB/s"]
    unit_index = 0
    
    while bytes_value >= 1024 and unit_index < len(units) - 1:
        bytes_value /= 1024
        unit_index += 1
    
    if bytes_value >= 100:
        return f"{bytes_value:.0f} {units[unit_index]}"
    elif bytes_value >= 10:
        return f"{bytes_value:.1f} {units[unit_index]}"
    else:
        return f"{bytes_value:.2f} {units[unit_index]}"

def generate_ascii_graph(data: List[float], width: int = 40, height: int = 8, title: str = "") -> List[str]:
    """Generate ASCII graph from data points"""
    if not data or all(x == 0 for x in data):
        empty_graph = [" " * width for _ in range(height)]
        if title:
            empty_graph[0] = title[:width].ljust(width)
        empty_graph[height // 2] = "No data".center(width)
        return empty_graph
    
    # Normalize data to fit in graph height
    max_value = max(data)
    if max_value == 0:
        max_value = 1
    
    # Create graph
    graph = [[" " for _ in range(width)] for _ in range(height)]
    
    # Add title
    if title:
        title_text = title[:width]
        for i, char in enumerate(title_text):
            if i < width:
                graph[0][i] = char
    
    # Plot data points
    data_width = width - 1 if title else width
    step = len(data) / data_width if len(data) > data_width else 1
    
    for x in range(data_width):
        data_index = int(x * step)
        if data_index < len(data):
            # Calculate height position
            normalized_value = data[data_index] / max_value
            y_pos = int((height - 2) * (1 - normalized_value)) + 1
            y_pos = max(1, min(height - 1, y_pos))
            
            # Use different characters for different heights
            if normalized_value > 0.8:
                char = "█"
            elif normalized_value > 0.6:
                char = "▆"
            elif normalized_value > 0.4:
                char = "▄"
            elif normalized_value > 0.2:
                char = "▂"
            else:
                char = "."
            
            graph[y_pos][x] = char
    
    # Add max value indicator
    max_text = format_bytes(max_value)
    if len(max_text) < width:
        for i, char in enumerate(max_text):
            if i < width:
                graph[1][width - len(max_text) + i] = char
    
    return [''.join(row) for row in graph]

def generate_bandwidth_display(bandwidth_data: Dict, width: int = 80) -> List[str]:
    """Generate complete bandwidth display with graphs"""
    lines = []
    
    if "error" in bandwidth_data:
        lines.append(f"Bandwidth Monitoring: {bandwidth_data['error']}")
        return lines
    
    upload_bps = bandwidth_data.get("upload_bps", 0)
    download_bps = bandwidth_data.get("download_bps", 0)
    interface = bandwidth_data.get("interface", "unknown")
    
    # Header with current speeds
    upload_str = format_bytes(upload_bps)
    download_str = format_bytes(download_bps)
    header = f"📊 Bandwidth Monitor ({interface}) | ↑ {upload_str} | ↓ {download_str}"
    lines.append(header)
    lines.append("─" * min(len(header), width))
    
    # Get history data for graphs
    upload_history = bandwidth_data.get("upload_history", [])
    download_history = bandwidth_data.get("download_history", [])
    
    if upload_history or download_history:
        graph_width = min(width - 2, 50)
        graph_height = 6
        
        # Generate upload graph
        upload_graph = generate_ascii_graph(
            upload_history[-graph_width:], 
            graph_width, 
            graph_height, 
            "Upload"
        )
        
        # Generate download graph
        download_graph = generate_ascii_graph(
            download_history[-graph_width:], 
            graph_width, 
            graph_height, 
            "Download"
        )
        
        # Add graphs
        lines.extend(upload_graph)
        lines.append("")
        lines.extend(download_graph)
        
        # Add statistics
        if upload_history:
            avg_upload = sum(upload_history) / len(upload_history)
            max_upload = max(upload_history)
            lines.append(f"Upload Stats: Avg {format_bytes(avg_upload)} | Peak {format_bytes(max_upload)}")
        
        if download_history:
            avg_download = sum(download_history) / len(download_history)
            max_download = max(download_history)
            lines.append(f"Download Stats: Avg {format_bytes(avg_download)} | Peak {format_bytes(max_download)}")
    else:
        lines.append("Collecting bandwidth data...")
        lines.append("Graphs will appear after a few measurements")
    
    return lines

# Global bandwidth monitor instance
_bandwidth_monitor = BandwidthMonitor()

def get_bandwidth_data() -> Dict:
    """Get current bandwidth data"""
    return _bandwidth_monitor.get_bandwidth_data()

# Advanced Ping Tools
class PingMonitor:
    def __init__(self):
        self.ping_history = {}  # hostname -> list of ping results
        self.continuous_pings = {}  # hostname -> ping task info
        self.max_history_points = 100
        self.ping_intervals = {}  # hostname -> interval in seconds
        
    def ping_host_with_stats(self, hostname: str, count: int = 1, timeout: int = 5) -> Dict:
        """Enhanced ping with detailed statistics"""
        try:
            # Use tailscale ping with specific count
            cmd = ["tailscale", "ping", "-c", str(count), hostname]
            result = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                text=True, timeout=timeout
            )
            
            output = result.stdout + result.stderr
            
            # Parse ping results
            ping_data = {
                "hostname": hostname,
                "timestamp": time.time(),
                "success": False,
                "latencies": [],
                "packet_loss": 0,
                "avg_latency": None,
                "min_latency": None,
                "max_latency": None,
                "raw_output": output
            }
            
            if result.returncode == 0:
                ping_data["success"] = True
                
                # Extract latency values
                latency_matches = re.findall(r'time[=\s]+(\d+\.?\d*)\s*ms', output, re.IGNORECASE)
                if latency_matches:
                    latencies = [float(l) for l in latency_matches]
                    ping_data["latencies"] = latencies
                    ping_data["avg_latency"] = sum(latencies) / len(latencies)
                    ping_data["min_latency"] = min(latencies)
                    ping_data["max_latency"] = max(latencies)
                
                # Extract packet loss
                loss_match = re.search(r'(\d+)%\s+packet\s+loss', output, re.IGNORECASE)
                if loss_match:
                    ping_data["packet_loss"] = int(loss_match.group(1))
            
            # Store in history
            if hostname not in self.ping_history:
                self.ping_history[hostname] = []
            
            self.ping_history[hostname].append(ping_data)
            
            # Keep only recent history
            if len(self.ping_history[hostname]) > self.max_history_points:
                self.ping_history[hostname] = self.ping_history[hostname][-self.max_history_points:]
            
            return ping_data
            
        except subprocess.TimeoutExpired:
            ping_data = {
                "hostname": hostname,
                "timestamp": time.time(),
                "success": False,
                "latencies": [],
                "packet_loss": 100,
                "avg_latency": None,
                "min_latency": None,
                "max_latency": None,
                "raw_output": "Ping timed out"
            }
            
            if hostname not in self.ping_history:
                self.ping_history[hostname] = []
            self.ping_history[hostname].append(ping_data)
            
            return ping_data
            
        except Exception as e:
            return {
                "hostname": hostname,
                "timestamp": time.time(),
                "success": False,
                "latencies": [],
                "packet_loss": 100,
                "avg_latency": None,
                "min_latency": None,
                "max_latency": None,
                "raw_output": f"Error: {e}"
            }
    
    def get_ping_history(self, hostname: str, limit: int = None) -> List[Dict]:
        """Get ping history for a specific host"""
        history = self.ping_history.get(hostname, [])
        if limit:
            return history[-limit:]
        return history
    
    def get_ping_statistics(self, hostname: str) -> Dict:
        """Calculate comprehensive ping statistics"""
        history = self.ping_history.get(hostname, [])
        
        if not history:
            return {"error": "No ping data available"}
        
        # Gather all successful pings
        successful_pings = [p for p in history if p["success"] and p["avg_latency"] is not None]
        all_latencies = []
        
        for ping in successful_pings:
            if ping["latencies"]:
                all_latencies.extend(ping["latencies"])
        
        total_pings = len(history)
        successful_count = len(successful_pings)
        failed_count = total_pings - successful_count
        
        stats = {
            "hostname": hostname,
            "total_pings": total_pings,
            "successful_pings": successful_count,
            "failed_pings": failed_count,
            "success_rate": (successful_count / total_pings * 100) if total_pings > 0 else 0,
            "packet_loss_rate": (failed_count / total_pings * 100) if total_pings > 0 else 0
        }
        
        if all_latencies:
            stats.update({
                "avg_latency": sum(all_latencies) / len(all_latencies),
                "min_latency": min(all_latencies),
                "max_latency": max(all_latencies),
                "latency_stddev": calculate_stddev(all_latencies),
                "recent_trend": calculate_trend(all_latencies[-10:]) if len(all_latencies) >= 5 else "insufficient_data"
            })
        
        # Calculate availability over time periods
        now = time.time()
        for period_name, seconds in [("1_hour", 3600), ("24_hours", 86400), ("7_days", 604800)]:
            period_pings = [p for p in history if now - p["timestamp"] <= seconds]
            if period_pings:
                period_successful = len([p for p in period_pings if p["success"]])
                stats[f"availability_{period_name}"] = (period_successful / len(period_pings) * 100)
        
        return stats
    
    def generate_ping_graph(self, hostname: str, width: int = 60, height: int = 10) -> List[str]:
        """Generate ASCII graph of ping latencies"""
        history = self.get_ping_history(hostname, width)
        
        if not history:
            return [f"No ping data for {hostname}"] + [" " * width for _ in range(height - 1)]
        
        # Extract latencies for graphing
        latencies = []
        for ping in history:
            if ping["success"] and ping["avg_latency"] is not None:
                latencies.append(ping["avg_latency"])
            else:
                latencies.append(None)  # Failed ping
        
        # Create graph
        graph = [[" " for _ in range(width)] for _ in range(height)]
        
        # Add title
        title = f"Ping: {hostname} (last {len(latencies)} tests)"
        for i, char in enumerate(title[:width]):
            graph[0][i] = char
        
        if not any(l for l in latencies if l is not None):
            # All pings failed
            fail_msg = "All pings failed"
            start_pos = (width - len(fail_msg)) // 2
            for i, char in enumerate(fail_msg):
                if start_pos + i < width:
                    graph[height // 2][start_pos + i] = char
            return [''.join(row) for row in graph]
        
        # Find min/max for scaling
        valid_latencies = [l for l in latencies if l is not None]
        if valid_latencies:
            min_lat = min(valid_latencies)
            max_lat = max(valid_latencies)
            lat_range = max_lat - min_lat if max_lat > min_lat else 1
            
            # Plot points
            for x, latency in enumerate(latencies):
                if x >= width:
                    break
                    
                if latency is not None:
                    # Calculate y position
                    normalized = (latency - min_lat) / lat_range
                    y_pos = int((height - 3) * (1 - normalized)) + 1
                    y_pos = max(1, min(height - 1, y_pos))
                    
                    # Choose character based on latency level
                    if latency < 20:
                        char = "●"  # Excellent
                    elif latency < 50:
                        char = "○"  # Good
                    elif latency < 100:
                        char = "◐"  # Fair
                    else:
                        char = "◯"  # Poor
                        
                    graph[y_pos][x] = char
                else:
                    # Failed ping
                    graph[height - 1][x] = "✗"
            
            # Add scale
            scale_text = f"{min_lat:.1f}ms - {max_lat:.1f}ms"
            for i, char in enumerate(scale_text):
                if width - len(scale_text) + i < width:
                    graph[1][width - len(scale_text) + i] = char
        
        return [''.join(row) for row in graph]

def calculate_stddev(values: List[float]) -> float:
    """Calculate standard deviation"""
    if len(values) < 2:
        return 0
    
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    return variance ** 0.5

def calculate_trend(values: List[float]) -> str:
    """Calculate trend direction from recent values"""
    if len(values) < 3:
        return "insufficient_data"
    
    # Simple trend calculation
    first_half = sum(values[:len(values)//2]) / (len(values)//2)
    second_half = sum(values[len(values)//2:]) / (len(values) - len(values)//2)
    
    diff_percent = ((second_half - first_half) / first_half) * 100 if first_half > 0 else 0
    
    if diff_percent > 10:
        return "worsening"
    elif diff_percent < -10:
        return "improving"
    else:
        return "stable"

def format_ping_duration(seconds: float) -> str:
    """Format duration in human readable format"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    elif seconds < 86400:
        return f"{seconds/3600:.1f}h"
    else:
        return f"{seconds/86400:.1f}d"

# Global ping monitor instance
_ping_monitor = PingMonitor()

def ping_host_advanced(hostname: str, count: int = 1) -> Dict:
    """Advanced ping with statistics tracking"""
    return _ping_monitor.ping_host_with_stats(hostname, count)

def get_ping_history(hostname: str, limit: int = None) -> List[Dict]:
    """Get ping history for a host"""
    return _ping_monitor.get_ping_history(hostname, limit)

def get_ping_statistics(hostname: str) -> Dict:
    """Get comprehensive ping statistics"""
    return _ping_monitor.get_ping_statistics(hostname)

def generate_ping_graph(hostname: str, width: int = 60, height: int = 10) -> List[str]:
    """Generate ping latency graph"""
    return _ping_monitor.generate_ping_graph(hostname, width, height)

def get_multi_ping_comparison(hostnames: List[str], count: int = 3) -> Dict:
    """Ping multiple hosts and compare results"""
    results = {}
    
    for hostname in hostnames:
        results[hostname] = ping_host_advanced(hostname, count)
    
    # Calculate comparison metrics
    successful_hosts = {h: r for h, r in results.items() if r["success"]}
    
    comparison = {
        "results": results,
        "summary": {
            "total_hosts": len(hostnames),
            "successful_hosts": len(successful_hosts),
            "failed_hosts": len(hostnames) - len(successful_hosts)
        }
    }
    
    if successful_hosts:
        latencies = [r["avg_latency"] for r in successful_hosts.values() if r["avg_latency"]]
        if latencies:
            comparison["summary"].update({
                "fastest_host": min(successful_hosts.keys(), key=lambda h: successful_hosts[h]["avg_latency"]),
                "slowest_host": max(successful_hosts.keys(), key=lambda h: successful_hosts[h]["avg_latency"]),
                "avg_latency_all": sum(latencies) / len(latencies),
                "latency_range": max(latencies) - min(latencies)
            })
    
    return comparison