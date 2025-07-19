import subprocess
import json
import platform

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
            "hostname": peer.get("HostName", "?"),
            "ip": peer.get("TailscaleIPs", ["?"])[0],
            "online": peer.get("Online", False),
            "exit_node": peer.get("ExitNode", False),  # Added missing key
            "os": peer.get("OS", "Unknown")  # Added missing key
        })
    return peers

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