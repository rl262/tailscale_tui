from textual.app import App, ComposeResult
from textual.widgets import Static, Header, Footer, DataTable, TabbedContent, TabPane
from textual.containers import VerticalScroll, Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from asyncio import create_task, sleep
from ts_backend import (
    get_peers, get_local_ip, get_exit_node_info, get_netcheck, ping,
    get_network_topology, generate_topology_map
)

class TopologyScreen(ModalScreen):
    """Modal screen showing network topology map"""
    
    def __init__(self):
        super().__init__()
        self.topology_data = None
        self.map_lines = []
    
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("🌐 Network Topology Map", id="topology-title")
            yield Static("Loading topology...", id="topology-map")
            yield Static("Legend: ⊙=You ⚡=Exit Node 📱=Mobile 🍎=Mac 🐧=Linux 🪟=Windows ●=Other", id="topology-legend")
            yield Static("Connection Quality: ═=Excellent ─=Good ┈=Fair ·=Poor", id="topology-quality")
            yield Static("Press any key to close", id="topology-help")
    
    async def on_mount(self):
        await self.update_topology()
    
    async def update_topology(self):
        """Update the topology map"""
        try:
            # Show loading message
            self.query_one("#topology-map").update("🔄 Scanning network topology...")
            
            # Get topology data (this may take a few seconds due to pings)
            self.topology_data = get_network_topology()
            
            # Generate ASCII map
            self.map_lines = generate_topology_map(self.topology_data, width=80, height=20)
            
            # Create info text
            nodes_count = len([n for n in self.topology_data["nodes"] if n["online"]])
            connections_count = len(self.topology_data["connections"])
            
            map_text = "\n".join(self.map_lines)
            info_text = f"\nNodes Online: {nodes_count} | Connections Tested: {connections_count}"
            
            self.query_one("#topology-map").update(map_text + info_text)
            
        except Exception as e:
            self.query_one("#topology-map").update(f"Error generating topology: {e}")
    
    def on_key(self, event):
        """Close on any key press"""
        self.dismiss()

class ConnectionDetailsScreen(ModalScreen):
    """Modal screen showing detailed connection information"""
    
    def __init__(self, topology_data: dict):
        super().__init__()
        self.topology_data = topology_data
    
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("🔗 Connection Details", id="details-title")
            yield Static("", id="details-content")
            yield Static("Press any key to close", id="details-help")
    
    def on_mount(self):
        """Generate detailed connection information"""
        details = []
        details.append("Network Connection Analysis:")
        details.append("=" * 50)
        
        # Group connections by quality
        by_quality = {}
        for conn_key, conn in self.topology_data["connections"].items():
            quality = conn["quality"]
            if quality not in by_quality:
                by_quality[quality] = []
            by_quality[quality].append(conn)
        
        # Display by quality groups
        quality_order = ["excellent", "good", "fair", "poor", "unknown"]
        for quality in quality_order:
            if quality in by_quality:
                connections = by_quality[quality]
                details.append(f"\n{quality.upper()} Connections ({len(connections)}):")
                for conn in connections:
                    latency_str = f"{conn['latency']:.1f}ms" if conn['latency'] else "N/A"
                    conn_type = conn['connection_type'].title()
                    details.append(f"  {conn['target']:15} | {latency_str:8} | {conn_type}")
        
        # Add summary statistics
        all_latencies = [c['latency'] for c in self.topology_data["connections"].values() if c['latency']]
        if all_latencies:
            avg_latency = sum(all_latencies) / len(all_latencies)
            min_latency = min(all_latencies)
            max_latency = max(all_latencies)
            details.append(f"\nLatency Statistics:")
            details.append(f"  Average: {avg_latency:.1f}ms")
            details.append(f"  Range: {min_latency:.1f}ms - {max_latency:.1f}ms")
        
        self.query_one("#details-content").update("\n".join(details))
    
    def on_key(self, event):
        self.dismiss()

class PingResultScreen(ModalScreen):
    def __init__(self, result_text: str):
        super().__init__()
        self.result_text = result_text
    
    def compose(self) -> ComposeResult:
        yield Static(self.result_text, id="ping-result")
    
    def on_key(self, event):
        self.dismiss()

class TailscaleDashboard(App):
    CSS_PATH = None
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh Now"),
        ("t", "show_topology", "Network Map"),
        ("d", "show_details", "Connection Details")
    ]
    
    netcheck_output = reactive("")
    local_ip = reactive("")
    exit_status = reactive("")
    topology_data = reactive({})

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        
        with TabbedContent(initial="overview"):
            with TabPane("Overview", id="overview"):
                with Vertical():
                    yield Static(id="ip-label")
                    yield Static(id="exit-label")
                    self.table = DataTable(zebra_stripes=True)
                    self.table.add_columns("Hostname", "IP", "Online", "Exit Node", "OS")
                    yield VerticalScroll(self.table)
            
            with TabPane("Network Map", id="topology"):
                with Vertical():
                    yield Static("🌐 Network Topology", id="topology-header")
                    yield Static("", id="topology-display")
                    with Horizontal():
                        yield Static("Press 't' for full-screen map | 'd' for connection details", id="topology-hints")
            
            with TabPane("Diagnostics", id="diagnostics"):
                with Vertical():
                    yield Static(id="netcheck")
                    yield Static("", id="connection-stats")
        
        yield Footer()

    async def on_mount(self):
        await self.refresh_data()
        create_task(self.refresh_loop())

    async def refresh_loop(self):
        while True:
            await self.refresh_data()
            await sleep(30)  # Slower refresh for topology due to ping tests

    async def refresh_data(self):
        """Refresh all dashboard data"""
        self.local_ip = get_local_ip()
        advertised, using = get_exit_node_info()
        self.exit_status = f"Exit Nodes: {', '.join(advertised) if advertised else 'None'}\n{using}"
        self.netcheck_output = get_netcheck()
        
        # Update basic data
        self.update_table()
        self.query_one("#ip-label", Static).update(f"Local IP: {self.local_ip}")
        self.query_one("#exit-label", Static).update(self.exit_status)
        self.query_one("#netcheck", Static).update(f"[Netcheck]\n{self.netcheck_output}")
        
        # Update topology in background (non-blocking)
        create_task(self.update_topology_async())

    async def update_topology_async(self):
        """Update topology data asynchronously"""
        try:
            # Get fresh topology data
            topology_data = get_network_topology()
            self.topology_data = topology_data
            
            # Generate compact topology map for the tab
            compact_map = generate_topology_map(topology_data, width=60, height=12)
            
            # Add connection summary
            total_connections = len(topology_data["connections"])
            online_nodes = len([n for n in topology_data["nodes"] if n["online"]])
            
            # Quality breakdown
            quality_counts = {}
            for conn in topology_data["connections"].values():
                quality = conn["quality"]
                quality_counts[quality] = quality_counts.get(quality, 0) + 1
            
            summary_lines = [
                f"Online Nodes: {online_nodes} | Connections: {total_connections}",
                f"Quality: Excellent:{quality_counts.get('excellent', 0)} Good:{quality_counts.get('good', 0)} Fair:{quality_counts.get('fair', 0)} Poor:{quality_counts.get('poor', 0)}",
                ""
            ]
            
            display_text = "\n".join(summary_lines + compact_map)
            
            # Update the topology display
            self.query_one("#topology-display").update(display_text)
            
            # Update connection stats
            if topology_data["connections"]:
                latencies = [c['latency'] for c in topology_data["connections"].values() if c['latency']]
                if latencies:
                    avg_latency = sum(latencies) / len(latencies)
                    stats_text = f"Average Latency: {avg_latency:.1f}ms | Range: {min(latencies):.1f}-{max(latencies):.1f}ms"
                    self.query_one("#connection-stats").update(stats_text)
                
        except Exception as e:
            self.query_one("#topology-display").update(f"Error loading topology: {e}")

    def update_table(self):
        self.table.clear()
        for peer in get_peers():
            self.table.add_row(
                peer["hostname"],
                peer["ip"],
                "✅" if peer["online"] else "❌",
                "🌐" if peer["exit_node"] else "",
                peer["os"]
            )

    async def on_data_table_row_selected(self, event: DataTable.RowSelected):
        ip = self.table.get_row_at(event.cursor_row)[1]
        result = ping(ip)
        await self.push_screen(
            PingResultScreen(f"📡 Ping result for {ip}:\n\n{result}")
        )

    async def action_refresh(self):
        """Manual refresh action"""
        await self.refresh_data()

    async def action_show_topology(self):
        """Show full-screen topology map"""
        await self.push_screen(TopologyScreen())

    async def action_show_details(self):
        """Show detailed connection information"""
        if self.topology_data:
            await self.push_screen(ConnectionDetailsScreen(self.topology_data))
        else:
            await self.push_screen(
                PingResultScreen("No topology data available yet.\nWait for the next refresh or press 'r' to refresh now.")
            )

if __name__ == "__main__":
    TailscaleDashboard().run()