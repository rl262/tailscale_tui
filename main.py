from textual.app import App, ComposeResult
from textual.widgets import Static, Header, Footer, DataTable, Input, Button, ProgressBar
from textual.containers import VerticalScroll, Horizontal, Vertical, Container
from textual.reactive import reactive
from textual.screen import ModalScreen
from asyncio import create_task, sleep
import time
from collections import Counter
from ts_backend import (
    get_peers, get_local_ip, get_exit_node_info, get_netcheck, ping,
    get_network_topology, generate_topology_map, get_bandwidth_data, 
    generate_bandwidth_display, ping_host_advanced, get_ping_history,
    get_ping_statistics, generate_ping_graph, get_multi_ping_comparison
)

class GeographicAnalyzer:
    @staticmethod
    def process_nodes(nodes):
        regions, countries, cities = {}, {}, {}
        for node in nodes:
            if node["online"]:
                location = node.get("location", {})
                region = location.get("region", "Unknown")
                country = location.get("country", "Unknown")
                city = location.get("city", "Unknown")
                
                regions[region] = regions.get(region, 0) + 1
                countries[country] = countries.get(country, 0) + 1
                if city != "Unknown":
                    cities[city] = cities.get(city, 0) + 1
        return regions, countries, cities
    
    @staticmethod
    def get_location_sets(nodes):
        countries, regions = set(), set()
        for node in nodes:
            if node["online"]:
                location = node.get("location", {})
                country = location.get("country", "Unknown")
                region = location.get("region", "Unknown")
                if country != "Unknown":
                    countries.add(country)
                if region != "Unknown":
                    regions.add(region)
        return countries, regions

class HelpScreen(ModalScreen):
    """Modal screen showing keyboard shortcuts and help"""
    
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("🆘 Tailscale Dashboard Help", id="help-title")
            
            help_content = [
                "📋 NAVIGATION:",
                "  1, 2, 3, 4    Switch between Overview, Topology, Diagnostics, Bandwidth",
                "  q             Quit application",
                "  r             Refresh data now",
                "  h             Show this help screen",
                "  /             Search/filter peers",
                "",
                "🌐 NETWORK TOOLS:",
                "  t             Open full-screen network topology map",
                "  m             Open visual network map with connection topology",
                "  d             Show detailed connection analysis",
                "  p             Open advanced ping tools",
                "",
                "🗺️ NETWORK MAP (when open):",
                "  g             Switch to geographic view",
                "  s             Switch to standard hub-and-spoke view",
                "  r             Refresh network topology",
                "",
                "📡 PING TOOLS (when open):",
                "  s             Single ping test",
                "  p             Multi-ping comparison",
                "  c             Continuous ping mode",
                "  h             Show ping history",
                "",
                "💡 TIPS:",
                "  • Click on any peer in the table to ping them",
                "  • Use Ctrl+C to force quit if needed",
                "  • Data refreshes automatically every 30 seconds",
                "  • Bandwidth tab updates every 2 seconds",
                "",
                "Press any key to close this help screen"
            ]
            
            yield Static("\n".join(help_content), id="help-content")
    
    def on_key(self, event):
        self.dismiss()

class SearchScreen(ModalScreen):
    """Modal screen for searching/filtering peers"""
    
    def __init__(self, peers_data):
        super().__init__()
        self.peers_data = peers_data
        self.filtered_results = []
    
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("🔍 Search Peers", id="search-title")
            yield Input(placeholder="Type hostname, IP, or OS to search...", id="search-input")
            yield Static("", id="search-results")
            yield Static("Press Enter to search, Esc to close", id="search-help")
    
    def on_mount(self):
        self.query_one("#search-input").focus()
    
    def on_input_changed(self, event):
        query = event.value.lower().strip()
        if not query:
            self.query_one("#search-results").update("")
            return
        
        self.filtered_results = []
        for peer in self.peers_data:
            if (query in peer["hostname"].lower() or 
                query in peer["ip"].lower() or 
                query in peer["os"].lower()):
                self.filtered_results.append(peer)
        
        if self.filtered_results:
            results = ["📋 Search Results:"]
            for peer in self.filtered_results[:10]:  # Limit to 10 results
                status = "🟢" if peer["online"] else "🔴"
                exit_node = "🌐" if peer["exit_node"] else "  "
                results.append(f"  {status} {peer['hostname']:15} {peer['ip']:15} {exit_node} {peer['os']}")
            
            if len(self.filtered_results) > 10:
                results.append(f"  ... and {len(self.filtered_results) - 10} more")
        else:
            results = ["No peers found matching your search."]
        
        self.query_one("#search-results").update("\n".join(results))
    
    def on_key(self, event):
        if event.key == "escape":
            self.dismiss()
        elif event.key == "enter" and self.filtered_results:
            # Return the first result for quick access
            self.dismiss(self.filtered_results[0])

class StatusIndicator:
    """Helper class for consistent status indicators"""
    
    @staticmethod
    def get_connection_status(online: bool) -> str:
        return "🟢 Online" if online else "🔴 Offline"
    
    @staticmethod
    def get_quality_indicator(quality: str) -> str:
        indicators = {
            "excellent": "🟢 Excellent",
            "good": "🟡 Good", 
            "fair": "🟠 Fair",
            "poor": "🔴 Poor",
            "unknown": "⚪ Unknown"
        }
        return indicators.get(quality, "⚪ Unknown")
    
    @staticmethod
    def get_tailscale_status(exit_status: str) -> str:
        if "stopped" in exit_status.lower():
            return "🔴 Tailscale Stopped"
        elif "not logged in" in exit_status.lower():
            return "🟡 Not Logged In"
        else:
            return "🟢 Connected"

class LatencyStatsHelper:
    @staticmethod
    def calculate_stats(connections):
        latencies = [c['latency'] for c in connections.values() if c['latency']]
        if not latencies:
            return None
        
        return {
            'avg': sum(latencies) / len(latencies),
            'min': min(latencies),
            'max': max(latencies),
            'count': len(latencies),
            'latencies': latencies
        }

class NetworkOverviewScreen(ModalScreen):
    """Modal screen showing clear network overview"""
    
    def __init__(self):
        super().__init__()
        self.topology_data = None
    
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("🌐 Network Overview", id="network-title")
            yield Static("Loading network information...", id="network-content")
            yield Static("Press any key to close", id="network-help")
    
    async def on_mount(self):
        await self.update_network_overview()
    
    async def update_network_overview(self):
        try:
            self.query_one("#network-content").update("🔄 Gathering network information...")
            self.topology_data = get_network_topology()
            
            content_lines = []
            content_lines.append("📋 YOUR TAILSCALE NETWORK")
            content_lines.append("=" * 50)
            content_lines.append("")
            
            # Network Summary
            nodes = self.topology_data["nodes"]
            connections = self.topology_data["connections"]
            online_nodes = [n for n in nodes if n["online"]]
            offline_nodes = [n for n in nodes if not n["online"]]
            
            content_lines.append(f"📊 NETWORK SUMMARY:")
            content_lines.append(f"  🟢 Online Devices: {len(online_nodes)}")
            content_lines.append(f"  🔴 Offline Devices: {len(offline_nodes)}")
            content_lines.append(f"  🔗 Active Connections: {len(connections)}")
            content_lines.append("")
            
            # Connection Quality Summary
            if connections:
                quality_counts = Counter(conn["quality"] for conn in connections.values())
                content_lines.append(f"📈 CONNECTION QUALITY:")
                for quality in ["excellent", "good", "fair", "poor", "unknown"]:
                    count = quality_counts.get(quality, 0)
                    if count > 0:
                        emoji = {
                            "excellent": "🟢",
                            "good": "🟡", 
                            "fair": "🟠",
                            "poor": "🔴",
                            "unknown": "⚪"
                        }.get(quality, "⚪")
                        content_lines.append(f"  {emoji} {quality.title()}: {count} connections")
                content_lines.append("")
            
            # Geographic Distribution
            regions, countries, _ = GeographicAnalyzer.process_nodes(nodes)
            if countries and len([c for c in countries.keys() if c != "Unknown"]) > 0:
                content_lines.append(f"🌍 GEOGRAPHIC DISTRIBUTION:")
                valid_countries = {k: v for k, v in countries.items() if k != "Unknown"}
                for country, count in sorted(valid_countries.items()):
                    content_lines.append(f"  🌍 {country}: {count} devices")
                content_lines.append("")
            
            # Online Devices List
            content_lines.append(f"🟢 ONLINE DEVICES ({len(online_nodes)}):")
            content_lines.append("-" * 45)
            
            for node in online_nodes:
                hostname = node["hostname"][:15]
                ip = node["ip"]
                os_name = node["os"][:10]
                location = node.get("location", {})
                country = location.get("country", "Unknown")
                
                # Get connection info for this node
                connection_info = ""
                for conn_key, conn in connections.items():
                    if conn["target"] == node["hostname"]:
                        latency = conn.get("latency")
                        if latency:
                            connection_info = f" | {latency:.0f}ms"
                        quality = conn.get("quality", "unknown")
                        quality_emoji = {
                            "excellent": "🟢",
                            "good": "🟡", 
                            "fair": "🟠",
                            "poor": "🔴",
                            "unknown": "⚪"
                        }.get(quality, "⚪")
                        connection_info = f" {quality_emoji}{connection_info}"
                        break
                
                exit_indicator = " 🌐" if node.get("exit_node") else ""
                location_info = f" ({country})" if country != "Unknown" else ""
                
                content_lines.append(f"  💻 {hostname:<15} {ip:<15} {os_name:<10}{location_info}{connection_info}{exit_indicator}")
            
            # Offline Devices (if any)
            if offline_nodes:
                content_lines.append("")
                content_lines.append(f"🔴 OFFLINE DEVICES ({len(offline_nodes)}):")
                content_lines.append("-" * 45)
                
                for node in offline_nodes[:5]:  # Show max 5 offline devices
                    hostname = node["hostname"][:15]
                    ip = node["ip"]
                    os_name = node["os"][:10]
                    location = node.get("location", {})
                    country = location.get("country", "Unknown")
                    location_info = f" ({country})" if country != "Unknown" else ""
                    
                    content_lines.append(f"  💻 {hostname:<15} {ip:<15} {os_name:<10}{location_info}")
                
                if len(offline_nodes) > 5:
                    content_lines.append(f"  ... and {len(offline_nodes) - 5} more offline devices")
            
            # Latency Statistics
            if connections:
                latency_stats = LatencyStatsHelper.calculate_stats(connections)
                if latency_stats:
                    content_lines.append("")
                    content_lines.append(f"📈 LATENCY STATISTICS:")
                    content_lines.append(f"  Average: {latency_stats['avg']:.1f}ms")
                    content_lines.append(f"  Range: {latency_stats['min']:.1f}ms - {latency_stats['max']:.1f}ms")
                    content_lines.append(f"  Total Measurements: {latency_stats['count']}")
            
            self.query_one("#network-content").update("\n".join(content_lines))
            
        except Exception as e:
            self.query_one("#network-content").update(f"❌ Error loading network overview: {e}")
    
    def on_key(self, event):
        self.dismiss()

class NetworkAnalysisScreen(ModalScreen):
    def __init__(self, topology_data: dict):
        super().__init__()
        self.topology_data = topology_data
    
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("📊 Network Analysis", id="analysis-title")
            yield Static("", id="analysis-content")
            yield Static("Press any key to close", id="analysis-help")
    
    def on_mount(self):
        details = []
        details.append("📈 TAILSCALE NETWORK ANALYSIS")
        details.append("=" * 50)
        details.append("")
        
        # Basic network stats
        nodes = self.topology_data["nodes"]
        connections = self.topology_data["connections"]
        online_nodes = [n for n in nodes if n["online"]]
        
        details.append("🌐 NETWORK SUMMARY:")
        details.append(f"  Total Devices: {len(nodes)}")
        details.append(f"  Online: {len(online_nodes)}")
        details.append(f"  Offline: {len(nodes) - len(online_nodes)}")
        details.append(f"  Active Connections: {len(connections)}")
        details.append("")
        
        # Geographic distribution
        regions, countries, cities = GeographicAnalyzer.process_nodes(nodes)
        valid_countries = {k: v for k, v in countries.items() if k != "Unknown"}
        
        if valid_countries:
            details.append("🌍 GEOGRAPHIC SPREAD:")
            for country, count in sorted(valid_countries.items()):
                details.append(f"  📍 {country}: {count} devices")
            details.append("")
        
        # Connection quality summary
        if connections:
            quality_counts = Counter(conn["quality"] for conn in connections.values())
            details.append("🔗 CONNECTION QUALITY:")
            
            for quality in ["excellent", "good", "fair", "poor"]:
                count = quality_counts.get(quality, 0)
                if count > 0:
                    emoji = {
                        "excellent": "🟢",
                        "good": "🟡", 
                        "fair": "🟠",
                        "poor": "🔴"
                    }.get(quality, "⚪")
                    percentage = (count / len(connections)) * 100
                    details.append(f"  {emoji} {quality.title()}: {count} connections ({percentage:.0f}%)")
            details.append("")
        
        # Performance statistics
        latency_stats = LatencyStatsHelper.calculate_stats(connections)
        if latency_stats:
            details.append("⚡ PERFORMANCE METRICS:")
            details.append(f"  Average Latency: {latency_stats['avg']:.1f}ms")
            details.append(f"  Best Connection: {latency_stats['min']:.1f}ms")
            details.append(f"  Worst Connection: {latency_stats['max']:.1f}ms")
            
            # Performance rating
            avg_latency = latency_stats['avg']
            if avg_latency < 20:
                rating = "🟢 Excellent"
            elif avg_latency < 50:
                rating = "🟡 Good"
            elif avg_latency < 100:
                rating = "🟠 Fair"
            else:
                rating = "🔴 Needs Improvement"
            
            details.append(f"  Network Rating: {rating}")
            details.append("")
        
        # Top connections by performance
        if connections:
            details.append("🏆 TOP PERFORMING CONNECTIONS:")
            sorted_connections = sorted(
                connections.items(),
                key=lambda x: x[1]['latency'] if x[1]['latency'] else float('inf')
            )
            
            for i, (conn_key, conn) in enumerate(sorted_connections[:5]):
                target = conn["target"]
                latency = f"{conn['latency']:.0f}ms" if conn['latency'] else "N/A"
                quality_emoji = {
                    "excellent": "🟢",
                    "good": "🟡", 
                    "fair": "🟠",
                    "poor": "🔴",
                    "unknown": "⚪"
                }.get(conn['quality'], "⚪")
                
                details.append(f"  {i+1}. {quality_emoji} {target} - {latency}")
        
        self.query_one("#analysis-content").update("\n".join(details))
    
    def on_key(self, event):
        self.dismiss()

class SimplePingScreen(ModalScreen):
    def __init__(self, hostname: str, ip: str):
        super().__init__()
        self.hostname = hostname
        self.ip = ip
        self.is_pinging = False
    
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("📡 Ping Tool", id="simple-ping-title")
            yield Static(f"Target: {self.hostname} ({self.ip})", id="simple-ping-target")
            yield Static("🔄 Starting ping...", id="simple-ping-result")
            yield Static("Press any key to close", id="simple-ping-help")
    
    async def on_mount(self):
        await self.perform_ping()
    
    async def perform_ping(self):
        if self.is_pinging:
            return
        
        self.is_pinging = True
        try:
            self.query_one("#simple-ping-result").update(f"🔄 Pinging {self.hostname} ({self.ip})...\n\nPlease wait...")
            
            # Use the ping function from ts_backend
            ping_result = ping(self.ip)
            
            # Format the result nicely
            if "pong" in ping_result.lower() or "time=" in ping_result.lower():
                status = "✅ Success"
                # Try to extract latency
                import re
                latency_match = re.search(r'time[=\s]+(\d+\.?\d*)\s*ms', ping_result, re.IGNORECASE)
                if latency_match:
                    latency = f" ({latency_match.group(1)}ms)"
                else:
                    latency = ""
                
                result_text = f"{status}{latency}\n\n{ping_result}\n\n💡 Use Advanced Ping Tools (press 'p') for more options"
            else:
                status = "❌ Failed"
                result_text = f"{status}\n\n{ping_result}\n\n💡 Troubleshooting:\n  • Check if {self.hostname} is online\n  • Verify network connectivity\n  • Try Advanced Ping Tools (press 'p')"
            
            self.query_one("#simple-ping-result").update(result_text)
            
        except Exception as e:
            error_text = f"❌ Ping Error\n\nError: {e}\n\n💡 Try Advanced Ping Tools (press 'p') for more options"
            self.query_one("#simple-ping-result").update(error_text)
        finally:
            self.is_pinging = False
    
    def on_key(self, event):
        self.dismiss()

class NetworkMapScreen(ModalScreen):
    def __init__(self):
        super().__init__()
        self.view_mode = "standard"  # "standard" or "geographic"
        self.topology_data = None
        
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("🗺️ Network Topology Map", id="map-title")
            yield Static("", id="map-display")
            yield Static("", id="map-stats")
            yield Static("Controls: s=Standard View | g=Geographic View | r=Refresh | q=Close", id="map-controls")
    
    async def on_mount(self):
        await self.update_network_map()
    
    async def update_network_map(self):
        try:
            from ts_backend import get_network_topology, generate_topology_map
            
            # Show loading message
            self.query_one("#map-display").update("🔄 Loading network topology...\n\nPlease wait while we scan your tailnet...")
            
            # Get topology data
            self.topology_data = get_network_topology()
            
            if not self.topology_data.get("nodes"):
                self.query_one("#map-display").update("⚠️ No network data available\n\n💡 Try:\n  • Check Tailscale is running\n  • Verify network connectivity\n  • Press 'r' to refresh")
                return
            
            # Generate map based on current view mode
            map_lines = generate_topology_map(
                self.topology_data, 
                width=76, 
                height=20, 
                view_mode=self.view_mode
            )
            
            map_text = "\n".join(map_lines)
            self.query_one("#map-display").update(map_text)
            
            # Update statistics
            await self.update_map_stats()
            
        except Exception as e:
            self.query_one("#map-display").update(f"❌ Error loading network map: {e}\n\n💡 Troubleshooting:\n  • Ensure Tailscale is running\n  • Check network permissions\n  • Try refreshing with 'r'")
    
    async def update_map_stats(self):
        if not self.topology_data:
            return
            
        nodes = self.topology_data.get("nodes", [])
        connections = self.topology_data.get("connections", {})
        
        online_nodes = [n for n in nodes if n.get("online", False)]
        offline_nodes = [n for n in nodes if not n.get("online", False)]
        
        # Connection quality breakdown
        quality_counts = {"excellent": 0, "good": 0, "fair": 0, "poor": 0, "unknown": 0}
        connection_types = {"direct": 0, "relay": 0, "unknown": 0}
        
        for conn in connections.values():
            quality = conn.get("quality", "unknown")
            conn_type = conn.get("connection_type", "unknown")
            quality_counts[quality] = quality_counts.get(quality, 0) + 1
            connection_types[conn_type] = connection_types.get(conn_type, 0) + 1
        
        # Geographic distribution
        countries = set()
        regions = set()
        for node in nodes:
            location = node.get("location", {})
            country = location.get("country", "Unknown")
            region = location.get("region", "Unknown")
            if country != "Unknown":
                countries.add(country)
            if region != "Unknown":
                regions.add(region)
        
        stats_lines = []
        stats_lines.append(f"📊 Network Overview ({self.view_mode.title()} View)")
        stats_lines.append("─" * 50)
        stats_lines.append(f"🟢 Online: {len(online_nodes)} devices | 🔴 Offline: {len(offline_nodes)} devices")
        stats_lines.append(f"🌍 Geographic: {len(countries)} countries, {len(regions)} regions")
        
        if connections:
            stats_lines.append("")
            stats_lines.append("🔗 Connection Quality:")
            for quality, emoji in [("excellent", "🟢"), ("good", "🟡"), ("fair", "🟠"), ("poor", "🔴")]:
                count = quality_counts.get(quality, 0)
                if count > 0:
                    stats_lines.append(f"  {emoji} {quality.title()}: {count}")
            
            stats_lines.append("")
            stats_lines.append("📡 Connection Types:")
            if connection_types["direct"] > 0:
                stats_lines.append(f"  🔗 Direct: {connection_types['direct']}")
            if connection_types["relay"] > 0:
                stats_lines.append(f"  🌐 Relay: {connection_types['relay']}")
        
        self.query_one("#map-stats").update("\n".join(stats_lines))
    
    def on_key(self, event):
        if event.key == "s":
            # Switch to standard view
            if self.view_mode != "standard":
                self.view_mode = "standard"
                create_task(self.update_network_map())
        elif event.key == "g":
            # Switch to geographic view
            if self.view_mode != "geographic":
                self.view_mode = "geographic"  
                create_task(self.update_network_map())
        elif event.key == "r":
            # Refresh map
            create_task(self.update_network_map())
        elif event.key == "q" or event.key == "escape":
            self.dismiss()

class AdvancedPingScreen(ModalScreen):
    def __init__(self):
        super().__init__()
        self.selected_target = None
        self.mode = "select"  # select, ping, continuous
        self.continuous_running = False
        self.ping_count = 0
        
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("🔧 Advanced Ping Tools", id="advanced-ping-title")
            yield Static("Choose a target device or enter IP:", id="ping-instructions")
            yield Static("", id="device-list")
            yield Input(placeholder="Press 'i' then type IP address/hostname", id="manual-input", disabled=True)
            yield Static("", id="ping-results")
            yield Static("Controls: 1-9=Select Device | i=Input Mode | c=Continuous | q=Quit", id="ping-controls")
    
    async def on_mount(self):
        await self.update_device_list()
        # Ensure input field is disabled and doesn't have focus
        input_field = self.query_one("#manual-input")
        input_field.disabled = True
        input_field.blur()
        self.focus()
        self.query_one("#ping-results").update("🎯 Ready! Press 1-9 to select device, 'i' for manual input, or 'q' to quit")
    
    async def update_device_list(self):
        try:
            from ts_backend import get_peers
            peers = get_peers()
            
            if not peers:
                self.query_one("#device-list").update("⚠️ No devices found. Make sure Tailscale is running.")
                return
            
            device_lines = []
            device_lines.append("📋 Available Devices (Press number to select):")
            device_lines.append("-" * 50)
            
            online_devices = [p for p in peers if p["online"]]
            offline_devices = [p for p in peers if not p["online"]]
            
            # Show online devices first
            for i, peer in enumerate(online_devices):
                status = "🟢" if peer["online"] else "🔴"
                location = peer.get("location", {}).get("country", "Unknown")
                location_text = f" ({location})" if location != "Unknown" else ""
                device_lines.append(f"  {i+1:2d}. {status} {peer['hostname']:<15} {peer['ip']:<15} {peer['os']:<10}{location_text}")
            
            # Show offline devices
            if offline_devices:
                device_lines.append("")
                device_lines.append("🔴 Offline Devices:")
                for i, peer in enumerate(offline_devices[:5]):
                    device_lines.append(f"     🔴 {peer['hostname']:<15} {peer['ip']:<15} {peer['os']:<10}")
                
                if len(offline_devices) > 5:
                    device_lines.append(f"     ... and {len(offline_devices) - 5} more offline")
            
            self.query_one("#device-list").update("\n".join(device_lines))
            
        except Exception as e:
            self.query_one("#device-list").update(f"❌ Error loading devices: {e}")
    
    def on_input_submitted(self, event):
        target = event.value.strip()
        if target:
            self.selected_target = target
            
            # Show immediate feedback
            self.query_one("#ping-results").update(f"🚀 Selected: {target}\n🔄 Starting ping...")
            
            # Disable and unfocus input after submission
            input_field = self.query_one("#manual-input")
            input_field.disabled = True
            input_field.blur()
            input_field.value = ""  # Clear the input
            self.focus()
            
            # Start ping asynchronously
            create_task(self.start_ping(target))
    
    def on_key(self, event):
        # Check if input field is enabled and has focus
        input_field = self.query_one("#manual-input")
        input_focused = not input_field.disabled and input_field.has_focus
        
        # Handle global shortcuts (work unless actively typing in input)
        if not input_focused:
            if event.key.isdigit():
                # User pressed a number to select a device
                try:
                    from ts_backend import get_peers
                    peers = get_peers()
                    online_peers = [p for p in peers if p["online"]]
                    
                    device_num = int(event.key) - 1
                    if 0 <= device_num < len(online_peers):
                        selected_peer = online_peers[device_num]
                        self.selected_target = selected_peer["ip"]
                        target_name = f"{selected_peer['hostname']} ({selected_peer['ip']})"
                        
                        # Show immediate feedback
                        self.query_one("#ping-results").update(f"🚀 Selected: {target_name}\n🔄 Starting ping...")
                        
                        # Ensure input is disabled and unfocused
                        input_field.disabled = True
                        input_field.blur()
                        self.focus()
                        
                        # Start ping asynchronously
                        create_task(self.start_ping(target_name))
                    else:
                        self.query_one("#ping-results").update(f"❌ Invalid selection: {event.key}")
                except Exception as e:
                    self.query_one("#ping-results").update(f"❌ Error selecting device: {e}")
            
            elif event.key == "i":
                # Enable and focus input field for manual entry
                input_field.disabled = False
                input_field.focus()
                self.query_one("#ping-results").update("📝 Input Mode: Type IP address or hostname and press Enter (ESC to cancel)\n\n💡 Examples: 192.168.1.1, hostname.local, 8.8.8.8")
            
            elif event.key == "c":
                if self.selected_target and not self.continuous_running:
                    create_task(self.start_continuous_ping())
                elif self.continuous_running:
                    self.stop_continuous_ping()
                else:
                    self.query_one("#ping-results").update("⚠️ Select a device first (1-9) or enter IP (press 'i')")
            
            elif event.key == "r":
                # Refresh device list
                create_task(self.update_device_list())
                self.query_one("#ping-results").update("🔄 Refreshing device list...")
            
            elif event.key == "q" or event.key == "escape":
                self.stop_continuous_ping()
                self.dismiss()
        
        # Handle input field specific keys when it's focused
        elif input_focused and event.key == "escape":
            # Escape from input field - disable and unfocus
            input_field.disabled = True
            input_field.blur()
            input_field.value = ""  # Clear the input
            self.focus()
            self.query_one("#ping-results").update("🎯 Ready for device selection (1-9) or commands (c, r, q)")
    
    async def start_ping(self, target_display_name: str):
        if not self.selected_target:
            self.query_one("#ping-results").update("⚠️ No target specified\n\nSelect a device number or enter IP manually")
            return
        
        self.mode = "ping"
        
        try:
            # Extract IP from target if it's in "hostname (ip)" format
            target_ip = self.selected_target
            if "(" in target_ip and ")" in target_ip:
                target_ip = target_ip.split("(")[1].split(")")[0]
            
            # Update UI to show we're pinging (if not already shown)
            current_text = self.query_one("#ping-results").renderable
            if "Starting ping" not in str(current_text):
                self.query_one("#ping-results").update(f"📡 Pinging {target_display_name}...\n\n🔄 Please wait, this may take a few seconds...")
            
            # Run ping in a separate thread to avoid blocking UI
            import asyncio
            import concurrent.futures
            from ts_backend import ping
            
            # Use thread pool to run blocking ping operation
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as executor:
                ping_result = await loop.run_in_executor(executor, ping, target_ip)
            
            lines = []
            lines.append(f"📡 Ping Results for {target_display_name}:")
            lines.append("─" * 50)
            
            if "pong" in ping_result.lower() or "time=" in ping_result.lower():
                lines.append("✅ Ping successful!")
                
                # Try to extract latency
                import re
                latency_match = re.search(r'time[=\s]+(\d+\.?\d*)\s*ms', ping_result, re.IGNORECASE)
                if latency_match:
                    latency = float(latency_match.group(1))
                    lines.append(f"🚀 Latency: {latency:.1f}ms")
                    
                    # Quality assessment
                    if latency < 20:
                        quality = "🟢 Excellent"
                    elif latency < 50:
                        quality = "🟡 Good"
                    elif latency < 100:
                        quality = "🟠 Fair"
                    else:
                        quality = "🔴 Poor"
                    lines.append(f"📈 Quality: {quality}")
                
                lines.append("\n💡 Options:")
                lines.append("  • Press 'c' for continuous ping")
                lines.append("  • Select another device (1-9)")
                lines.append("  • Press 'i' then type new IP")
                lines.append("  • Press 'r' to refresh device list")
            else:
                lines.append("❌ Ping failed")
                lines.append("\n💡 Troubleshooting:")
                lines.append("  • Check if target device is online")
                lines.append("  • Verify IP address is correct")
                lines.append("  • Check network connectivity")
            
            lines.append(f"\n🕰️ Time: {time.strftime('%H:%M:%S')}")
            lines.append("\nRaw output:")
            lines.append(ping_result)
            
            self.query_one("#ping-results").update("\n".join(lines))
            
        except Exception as e:
            error_lines = [
                "❌ Ping Error",
                "─" * 30,
                f"Error: {e}",
                "\n💡 Try:",
                "  • Check if Tailscale is running",
                "  • Verify the IP address",
                "  • Select a different device"
            ]
            self.query_one("#ping-results").update("\n".join(error_lines))
    
    async def start_continuous_ping(self):
        if not self.selected_target or self.continuous_running:
            return
        
        self.continuous_running = True
        self.ping_count = 0
        self.query_one("#ping-controls").update("Continuous Mode: Press 'c' to stop | ESC/q to quit")
        
        try:
            import concurrent.futures
            from ts_backend import ping
            
            while self.continuous_running:
                self.ping_count += 1
                
                # Extract IP from target
                target_ip = self.selected_target
                if "(" in target_ip and ")" in target_ip:
                    target_ip = target_ip.split("(")[1].split(")")[0]
                
                # Show we're pinging this round
                timestamp = time.strftime('%H:%M:%S')
                self.query_one("#ping-results").update(f"🔄 Continuous Ping #{self.ping_count}\n\nTarget: {self.selected_target}\nTime: {timestamp}\nStatus: 🔄 Pinging...")
                
                # Run ping in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    ping_result = await loop.run_in_executor(executor, ping, target_ip)
                
                timestamp = time.strftime('%H:%M:%S')
                
                if "pong" in ping_result.lower() or "time=" in ping_result.lower():
                    # Extract latency
                    import re
                    latency_match = re.search(r'time[=\s]+(\d+\.?\d*)\s*ms', ping_result, re.IGNORECASE)
                    if latency_match:
                        latency = f"{latency_match.group(1)}ms"
                    else:
                        latency = "Success"
                    status = f"✅ {latency}"
                else:
                    status = "❌ Failed"
                
                result_text = f"🔄 Continuous Ping #{self.ping_count}\n\nTarget: {self.selected_target}\nTime: {timestamp}\nResult: {status}\n\nPress 'c' to stop | ESC/q to quit"
                self.query_one("#ping-results").update(result_text)
                
                await sleep(2)
                
        except Exception as e:
            self.query_one("#ping-results").update(f"❌ Continuous ping error: {e}")
        finally:
            self.continuous_running = False
            self.query_one("#ping-controls").update("Controls: c=Continuous q=Quit ESC=Back")
    
    def stop_continuous_ping(self):
        self.continuous_running = False

class PingResultScreen(ModalScreen):
    def __init__(self, result_text: str):
        super().__init__()
        self.result_text = result_text
    
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("📡 Ping Results", id="ping-title")
            yield Static(self.result_text, id="ping-result")
            yield Static("Press any key to close", id="ping-help")
    
    def on_key(self, event):
        self.dismiss()

class TailscaleDashboard(App):
    CSS_PATH = None
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh Now"),
        ("t", "show_topology", "Network Map"),
        ("d", "show_details", "Connection Details"),
        ("m", "show_network_map", "Network Map"),
        ("p", "show_ping_tools", "Advanced Ping"),
        ("h", "show_help", "Help"),
        ("/", "show_search", "Search"),
        ("1", "show_overview", "Overview"),
        ("2", "show_topology_tab", "Topology Tab"),
        ("3", "show_diagnostics", "Diagnostics"),
        ("4", "show_bandwidth", "Bandwidth Monitor")
    ]
    
    netcheck_output = reactive("")
    local_ip = reactive("")
    exit_status = reactive("")
    topology_data = reactive({})
    current_view = reactive("overview")
    
    def __init__(self):
        super().__init__()
        self._topology_cache = None
        self._topology_cache_time = 0
        self.CACHE_TTL = 10
        self._peers_data = []
        self._last_refresh_time = 0
    
    def get_cached_topology(self):
        current_time = time.time()
        if (self._topology_cache is None or 
            current_time - self._topology_cache_time > self.CACHE_TTL):
            self._topology_cache = get_network_topology()
            self._topology_cache_time = current_time
        return self._topology_cache

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        
        with Vertical():
            with Horizontal(id="status-bar"):
                yield Static("🟢 Connected", id="connection-status")
                yield Static("Last refresh: Never", id="refresh-status")
                yield Static("Press 'h' for help", id="help-hint")
            yield Static("Current View: Overview | Press 1=Overview 2=Topology 3=Diagnostics 4=Bandwidth p=Ping Tools", id="tab-indicator")
            
            with Vertical(id="overview-section"):
                with Horizontal():
                    yield Static(id="ip-label")
                    yield Static(id="exit-label")
                yield Static("📋 Network Peers (Click any row to ping that device)", id="peers-header")
                self.table = DataTable(zebra_stripes=True)
                self.table.add_columns("💻 Hostname", "🌐 IP Address", "🔌 Status", "🌐 Exit Node", "💾 OS")
                yield VerticalScroll(self.table)
            
            with Vertical(id="topology-section", classes="hidden"):
                yield Static("🌐 Network Overview", id="topology-header")
                yield Static("", id="topology-display")
                with Horizontal():
                    yield Static("💡 Press 't' for full network overview | 'd' for network analysis", id="topology-hints")
            
            with Vertical(id="diagnostics-section", classes="hidden"):
                yield Static("🔧 Network Diagnostics", id="diagnostics-header")
                yield Static(id="netcheck")
                yield Static("", id="connection-stats")
            
            with Vertical(id="bandwidth-section", classes="hidden"):
                yield Static("📈 Bandwidth Monitor", id="bandwidth-header")
                yield Static("", id="bandwidth-display")
        
        yield Footer()

    async def on_mount(self):
        await self.refresh_data()
        create_task(self.refresh_loop())

    async def refresh_loop(self):
        while True:
            await self.refresh_data()
            if self.current_view == "bandwidth":
                await sleep(2)
            else:
                await sleep(30)

    async def refresh_data(self):
        try:
            # Gather all data first
            data = {
                'local_ip': get_local_ip(),
                'exit_info': get_exit_node_info(),
                'netcheck': get_netcheck()
            }
            
            # Batch update UI
            self.update_ui_batch(data)
            
            advertised, using = data['exit_info']
            if "stopped" not in using.lower():
                create_task(self.update_topology_async())
                if self.current_view == "bandwidth":
                    self.update_bandwidth_display()
            else:
                self.handle_tailscale_stopped()
        
        except Exception as e:
            self.handle_refresh_error(e)
    
    def update_ui_batch(self, data):
        self.local_ip = data['local_ip']
        advertised, using = data['exit_info']
        self.exit_status = f"Exit Nodes: {', '.join(advertised) if advertised else 'None'}\n{using}"
        self.netcheck_output = data['netcheck']
        
        # Update status indicators
        connection_status = StatusIndicator.get_tailscale_status(using)
        self.query_one("#connection-status").update(connection_status)
        
        current_time = time.strftime("%H:%M:%S")
        self.query_one("#refresh-status").update(f"Last refresh: {current_time}")
        self._last_refresh_time = time.time()
        
        self.update_table()
        self.query_one("#ip-label", Static).update(f"💻 Local IP: {self.local_ip}")
        self.query_one("#exit-label", Static).update(f"🌐 {self.exit_status}")
        self.query_one("#netcheck", Static).update(f"🔍 Network Check:\n{self.netcheck_output}")
    
    def handle_tailscale_stopped(self):
        self.query_one("#topology-display").update("🛑 Tailscale is not running\n\n💡 To start Tailscale:\n  • Run: sudo tailscale up\n  • Or check your system service manager\n  • Ensure you're logged in to your tailnet")
        self.query_one("#connection-stats").update("⚠️ Connection statistics unavailable - Tailscale stopped")
        self.query_one("#bandwidth-display").update("⚠️ Bandwidth monitoring unavailable - Tailscale stopped")
    
    def handle_refresh_error(self, error):
        error_msg = f"Error refreshing data: {error}"
        self.query_one("#connection-status").update("🔴 Connection Error")
        self.query_one("#ip-label", Static).update(f"💻 Local IP: ❌ Error - {error_msg}")
        self.query_one("#exit-label", Static).update("🌐 Exit Nodes: ❌ Error")
        
        detailed_error = f"❌ Network Error\n\n💡 Troubleshooting steps:\n  • Check if Tailscale is running: tailscale status\n  • Verify network connectivity\n  • Try refreshing with 'r' key\n  • Restart Tailscale if needed\n\nError details: {error}"
        self.query_one("#topology-display").update(detailed_error)
        self.query_one("#connection-stats").update("⚠️ Connection statistics unavailable")
        self.query_one("#bandwidth-display").update(f"⚠️ Bandwidth monitoring error: {error_msg}")

    def update_bandwidth_display(self):
        try:
            bandwidth_data = get_bandwidth_data()
            bandwidth_lines = generate_bandwidth_display(bandwidth_data, width=80)
            bandwidth_text = "\n".join(bandwidth_lines)
            self.query_one("#bandwidth-display").update(bandwidth_text)
        except Exception as e:
            error_msg = f"❌ Bandwidth Error\n\n💡 Common solutions:\n  • Install psutil: pip install psutil\n  • Check network interface permissions\n  • Verify Tailscale is running\n\nError: {e}"
            self.query_one("#bandwidth-display").update(error_msg)

    async def update_topology_async(self):
        try:
            topology_data = self.get_cached_topology()
            self.topology_data = topology_data
            
            # Create a simple, readable network overview
            nodes = topology_data["nodes"]
            connections = topology_data["connections"]
            online_nodes = [n for n in nodes if n["online"]]
            
            display_lines = []
            
            # Summary stats
            total_connections = len(connections)
            quality_counts = Counter(conn["quality"] for conn in connections.values())
            countries, regions = GeographicAnalyzer.get_location_sets(nodes)
            
            display_lines.append(f"📊 Network: {len(online_nodes)} online | {total_connections} connections | {len(countries)} countries")
            
            # Quality breakdown in a simple format
            quality_summary = []
            for quality, emoji in [("excellent", "🟢"), ("good", "🟡"), ("fair", "🟠"), ("poor", "🔴")]:
                count = quality_counts.get(quality, 0)
                if count > 0:
                    quality_summary.append(f"{emoji}{count}")
            
            if quality_summary:
                display_lines.append(f"🔗 Quality: {' '.join(quality_summary)}")
            
            display_lines.append("")
            
            # Show top connections with simple format
            if connections:
                display_lines.append("🗺️ Active Connections:")
                display_lines.append("-" * 40)
                
                # Sort connections by latency (best first)
                sorted_connections = sorted(
                    connections.items(), 
                    key=lambda x: x[1]['latency'] if x[1]['latency'] else float('inf')
                )
                
                for i, (conn_key, conn) in enumerate(sorted_connections[:8]):  # Show top 8
                    target = conn["target"][:12]
                    latency = f"{conn['latency']:.0f}ms" if conn['latency'] else "N/A"
                    quality = conn['quality']
                    
                    quality_emoji = {
                        "excellent": "🟢",
                        "good": "🟡", 
                        "fair": "🟠",
                        "poor": "🔴",
                        "unknown": "⚪"
                    }.get(quality, "⚪")
                    
                    # Get location info for target
                    target_node = next((n for n in nodes if n["hostname"] == conn["target"]), None)
                    location_info = ""
                    if target_node:
                        location = target_node.get("location", {})
                        country = location.get("country", "Unknown")
                        if country != "Unknown":
                            location_info = f" ({country})"
                    
                    display_lines.append(f"  {quality_emoji} {target:<12} {latency:>8}{location_info}")
                
                if len(connections) > 8:
                    display_lines.append(f"  ... and {len(connections) - 8} more connections")
            
            display_text = "\n".join(display_lines)
            self.query_one("#topology-display").update(display_text)
            
            # Update connection stats with simple summary
            if connections:
                latency_stats = LatencyStatsHelper.calculate_stats(connections)
                if latency_stats:
                    best_conn = min(connections.values(), key=lambda c: c['latency'] if c['latency'] else float('inf'))
                    worst_conn = max(connections.values(), key=lambda c: c['latency'] if c['latency'] else 0)
                    
                    stats_text = f"📈 Latency: Avg {latency_stats['avg']:.0f}ms | Best {best_conn['latency']:.0f}ms ({best_conn['target']}) | Worst {worst_conn['latency']:.0f}ms ({worst_conn['target']})"
                    self.query_one("#connection-stats").update(stats_text)
                
        except Exception as e:
            error_display = f"❌ Network Error\n\n💡 Try these steps:\n  • Press 'r' to refresh\n  • Check Tailscale status\n  • Verify network connectivity\n\nError: {e}"
            self.query_one("#topology-display").update(error_display)

    def update_table(self):
        self.table.clear()
        self._peers_data = get_peers()
        for peer in self._peers_data:
            status_icon = "🟢" if peer["online"] else "🔴"
            self.table.add_row(
                peer["hostname"],
                peer["ip"],
                f"{status_icon} {'Online' if peer['online'] else 'Offline'}",
                "🌐 Exit" if peer["exit_node"] else "",
                peer["os"]
            )

    async def on_data_table_row_selected(self, event: DataTable.RowSelected):
        try:
            # Get the row data from the table
            row_data = self.table.get_row_at(event.cursor_row)
            hostname = row_data[0]  # Should be the hostname
            ip = row_data[1]        # Should be the IP address
            
            # Create and show result screen with loading message first
            result_screen = PingResultScreen(f"🔄 Pinging {hostname} ({ip})...\n\nPlease wait...")
            result_screen_task = create_task(self.push_screen(result_screen))
            await result_screen_task
            
            # Perform the ping
            ping_result = ping(ip)
            
            # Update the result screen with actual results
            enhanced_result = f"📡 Quick Ping Result for {hostname} ({ip}):\n\n{ping_result}\n\n"
            enhanced_result += "💡 Press 'p' for Advanced Ping Tools with this host"
            
            # Update the existing screen content
            result_screen.result_text = enhanced_result
            result_screen.query_one("#ping-result").update(enhanced_result)
            
        except IndexError as e:
            error_message = f"❌ Table Selection Error\n\n💡 Debug info:\n  • Row data: {row_data if 'row_data' in locals() else 'Not available'}\n  • Event cursor row: {event.cursor_row}\n  • Table has data: {len(self._peers_data) if hasattr(self, '_peers_data') else 'Unknown'}\n\nError: {e}"
            await self.push_screen(PingResultScreen(error_message))
        except Exception as e:
            error_message = f"❌ Ping Error\n\n💡 Possible causes:\n  • Peer is offline or unreachable\n  • Network connectivity issues\n  • Tailscale routing problems\n\nError details: {e}\n\nTry using the Advanced Ping Tools (press 'p') for more options."
            await self.push_screen(PingResultScreen(error_message))

    def switch_view(self, view_name: str):
        self.current_view = view_name
        
        view_configs = {
            "overview": ("🏠 Overview", "#overview-section"),
            "topology": ("🌐 Network Topology", "#topology-section"),
            "diagnostics": ("🔧 Diagnostics", "#diagnostics-section"),
            "bandwidth": ("📈 Bandwidth Monitor", "#bandwidth-section")
        }
        
        # Hide all sections
        for _, section_id in view_configs.values():
            self.query_one(section_id).add_class("hidden")
        
        # Show current section
        view_title, section_id = view_configs[view_name]
        self.query_one(section_id).remove_class("hidden")
        self.query_one("#tab-indicator").update(
            f"Current View: {view_title} | 1=Overview 2=Network 3=Diagnostics 4=Bandwidth | h=Help /=Search p=Ping t=Details"
        )
        
        if view_name == "bandwidth":
            self.update_bandwidth_display()

    async def action_refresh(self):
        await self.refresh_data()

    async def action_show_topology(self):
        await self.push_screen(NetworkOverviewScreen())

    async def action_show_details(self):
        if self.topology_data:
            await self.push_screen(NetworkAnalysisScreen(self.topology_data))
        else:
            await self.push_screen(PingResultScreen("🔄 No network data available yet\n\n💡 Solutions:\n  • Wait for automatic refresh (30 seconds)\n  • Press 'r' to refresh now\n  • Check that Tailscale is running\n  • Ensure you have network connectivity"))

    async def action_show_overview(self):
        self.switch_view("overview")

    async def action_show_topology_tab(self):
        self.switch_view("topology")

    async def action_show_diagnostics(self):
        self.switch_view("diagnostics")

    async def action_show_bandwidth(self):
        self.switch_view("bandwidth")

    async def action_show_help(self):
        await self.push_screen(HelpScreen())
    
    async def action_show_search(self):
        await self.push_screen(SearchScreen(self._peers_data))
    
    async def action_show_ping_tools(self):
        await self.push_screen(AdvancedPingScreen())
    
    async def action_show_network_map(self):
        await self.push_screen(NetworkMapScreen())

if __name__ == "__main__":
    try:
        app = TailscaleDashboard()
        app.CSS = """
        .hidden {
            display: none;
        }
        
        #status-bar {
            height: 1;
            background: $surface;
            border-bottom: solid $primary;
        }
        
        #connection-status {
            width: 20;
            text-align: left;
        }
        
        #refresh-status {
            width: 25;
            text-align: center;
        }
        
        #help-hint {
            width: 1fr;
            text-align: right;
            color: $text-muted;
        }
        
        #tab-indicator {
            background: $primary;
            color: $text;
            padding: 0 1;
        }
        
        #help-title {
            text-align: center;
            text-style: bold;
            color: $accent;
            margin: 1;
        }
        
        #help-content {
            margin: 1;
            padding: 1;
            background: $surface;
            border: solid $primary;
        }
        
        #search-title {
            text-align: center;
            text-style: bold;
            color: $accent;
            margin: 1;
        }
        
        #search-input {
            margin: 1;
        }
        
        #search-results {
            margin: 1;
            padding: 1;
            background: $surface;
            min-height: 10;
        }
        
        #ping-title {
            text-align: center;
            text-style: bold;
            color: $accent;
            margin: 1;
        }
        
        #ping-result {
            margin: 1;
            padding: 1;
            background: $surface;
            border: solid $primary;
            min-height: 10;
        }
        
        #ping-help {
            text-align: center;
            color: $text-muted;
            margin: 1;
        }
        
        #map-title {
            text-align: center;
            text-style: bold;
            color: $accent;
            margin: 1;
        }
        
        #map-display {
            margin: 1;
            padding: 1;
            background: $surface;
            border: solid $primary;
            min-height: 20;
        }
        
        #map-stats {
            margin: 1;
            padding: 1;
            background: $panel;
            border: solid $secondary;
            min-height: 8;
        }
        
        #map-controls {
            text-align: center;
            color: $text-muted;
            margin: 1;
        }
        
        #simple-ping-title, #advanced-ping-title {
            text-align: center;
            text-style: bold;
            color: $accent;
            margin: 1;
        }
        
        #simple-ping-result, #device-list {
            margin: 1;
            padding: 1;
            background: $surface;
            border: solid $primary;
            min-height: 10;
        }
        
        #manual-input {
            margin: 1;
        }
        
        #ping-instructions, #ping-controls {
            text-align: center;
            color: $text-muted;
            margin: 1;
        }
        
        DataTable {
            background: $surface;
        }
        
        DataTable > .datatable--header {
            background: $primary;
            color: $text;
        }
        
        DataTable > .datatable--odd-row {
            background: $surface;
        }
        
        DataTable > .datatable--even-row {
            background: $panel;
        }
        
        DataTable > .datatable--cursor {
            background: $accent;
            color: $text;
        }
        """
        print("🚀 Starting Tailscale Dashboard...")
        print("💡 Press 'h' for help once the dashboard loads")
        app.run()
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("\n💡 Fix by installing required dependencies:")
        print("   pip install textual psutil")
        print("\n📚 Documentation: https://github.com/tailscale/tailscale")
    except KeyboardInterrupt:
        print("\n👋 Dashboard closed by user")
    except Exception as e:
        print(f"❌ Error starting dashboard: {e}")
        print("\n💡 Troubleshooting:")
        print("   • Ensure Tailscale is installed and running")
        print("   • Check that you have proper permissions")
        print("   • Verify Python dependencies are installed")
        print("\n📝 Full error details:")
        import traceback
        traceback.print_exc()