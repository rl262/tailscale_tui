from textual.app import App, ComposeResult
from textual.widgets import Static, Header, Footer, DataTable
from textual.containers import VerticalScroll, Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from asyncio import create_task, sleep
from ts_backend import (
    get_peers, get_local_ip, get_exit_node_info, get_netcheck, ping,
    get_network_topology, generate_topology_map, get_bandwidth_data, 
    generate_bandwidth_display
)

class TopologyScreen(ModalScreen):
    """Modal screen showing network topology map"""
    
    def __init__(self):
        super().__init__()
        self.topology_data = None
        self.map_lines = []
        self.view_mode = "standard"  # "standard" or "geographic"
    
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("🌐 Network Topology Map", id="topology-title")
            yield Static("Loading topology...", id="topology-map")
            yield Static("Legend: ⊙=You ⚡=Exit Node 📱=Mobile 🍎=Mac 🐧=Linux 🪟=Windows ●=Other", id="topology-legend")
            yield Static("Connection Quality: ═=Excellent ─=Good ┈=Fair ·=Poor", id="topology-quality")
            yield Static("Press 'g' for geographic view, 's' for standard view, any other key to close", id="topology-help")
    
    async def on_mount(self):
        await self.update_topology()
    
    async def update_topology(self):
        """Update the topology map"""
        try:
            # Show loading message
            self.query_one("#topology-map").update("🔄 Scanning network topology and locations...")
            
            # Get topology data (this may take a few seconds due to pings)
            self.topology_data = get_network_topology()
            
            # Generate ASCII map based on current view mode
            self.map_lines = generate_topology_map(
                self.topology_data, 
                width=80, 
                height=20, 
                view_mode=self.view_mode
            )
            
            # Create info text with geographic details
            nodes_count = len([n for n in self.topology_data["nodes"] if n["online"]])
            connections_count = len(self.topology_data["connections"])
            
            # Add geographic summary
            regions = {}
            countries = {}
            for node in self.topology_data["nodes"]:
                if node["online"]:
                    location = node.get("location", {})
                    region = location.get("region", "Unknown")
                    country = location.get("country", "Unknown")
                    
                    regions[region] = regions.get(region, 0) + 1
                    countries[country] = countries.get(country, 0) + 1
            
            map_text = "\n".join(self.map_lines)
            
            # Geographic summary
            geo_summary = []
            if regions:
                region_list = [f"{region}({count})" for region, count in sorted(regions.items()) if region != "Unknown"]
                if region_list:
                    geo_summary.append(f"Regions: {', '.join(region_list[:4])}")  # Show top 4 regions
            
            if countries and len(countries) > 1:
                country_list = [f"{country}({count})" for country, count in sorted(countries.items()) if country != "Unknown"]
                if country_list:
                    geo_summary.append(f"Countries: {', '.join(country_list[:6])}")  # Show top 6 countries
            
            info_lines = [f"Nodes Online: {nodes_count} | Connections: {connections_count}"]
            if geo_summary:
                info_lines.extend(geo_summary)
            
            view_mode_text = f"View: {self.view_mode.title()}"
            info_lines.append(view_mode_text)
            
            info_text = "\n" + "\n".join(info_lines)
            
            self.query_one("#topology-map").update(map_text + info_text)
            
        except Exception as e:
            self.query_one("#topology-map").update(f"Error generating topology: {e}")
    
    def on_key(self, event):
        """Handle key presses for view switching"""
        if event.key == "g":
            # Switch to geographic view
            self.view_mode = "geographic"
            create_task(self.update_topology())
        elif event.key == "s":
            # Switch to standard view
            self.view_mode = "standard"
            create_task(self.update_topology())
        else:
            # Close on any other key
            self.dismiss()

class ConnectionDetailsScreen(ModalScreen):
    """Modal screen showing detailed connection information"""
    
    def __init__(self, topology_data: dict):
        super().__init__()
        self.topology_data = topology_data
    
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("🔗 Connection & Location Details", id="details-title")
            yield Static("", id="details-content")
            yield Static("Press any key to close", id="details-help")
    
    def on_mount(self):
        """Generate detailed connection and location information"""
        details = []
        details.append("Network Connection & Geographic Analysis:")
        details.append("=" * 60)
        
        # Geographic distribution
        details.append("\n📍 GEOGRAPHIC DISTRIBUTION:")
        regions = {}
        countries = {}
        cities = {}
        
        for node in self.topology_data["nodes"]:
            if node["online"]:
                location = node.get("location", {})
                region = location.get("region", "Unknown")
                country = location.get("country", "Unknown")
                city = location.get("city", "Unknown")
                
                regions[region] = regions.get(region, 0) + 1
                countries[country] = countries.get(country, 0) + 1
                if city != "Unknown":
                    cities[city] = cities.get(city, 0) + 1
        
        if regions:
            details.append("  Regions:")
            for region, count in sorted(regions.items()):
                if region != "Unknown":
                    details.append(f"    {region:20} | {count} nodes")
        
        if countries and len(countries) > 1:
            details.append("  Countries:")
            for country, count in sorted(countries.items()):
                if country != "Unknown":
                    details.append(f"    {country:20} | {count} nodes")
        
        if cities:
            details.append("  Cities:")
            for city, count in sorted(cities.items()):
                details.append(f"    {city:20} | {count} nodes")
        
        # Connection quality by geography
        details.append(f"\n🌐 CONNECTION QUALITY BY LOCATION:")
        location_performance = {}
        
        for conn_key, conn in self.topology_data["connections"].items():
            target = conn["target"]
            target_node = next((n for n in self.topology_data["nodes"] if n["hostname"] == target), None)
            
            if target_node:
                location = target_node.get("location", {})
                country = location.get("country", "Unknown")
                
                if country not in location_performance:
                    location_performance[country] = {"latencies": [], "qualities": {}}
                
                if conn["latency"]:
                    location_performance[country]["latencies"].append(conn["latency"])
                
                quality = conn["quality"]
                location_performance[country]["qualities"][quality] = location_performance[country]["qualities"].get(quality, 0) + 1
        
        for country, perf in location_performance.items():
            if country != "Unknown" and perf["latencies"]:
                avg_latency = sum(perf["latencies"]) / len(perf["latencies"])
                min_latency = min(perf["latencies"])
                max_latency = max(perf["latencies"])
                
                quality_summary = ", ".join([f"{q}:{c}" for q, c in perf["qualities"].items()])
                
                details.append(f"  {country:20} | Avg: {avg_latency:5.1f}ms | Range: {min_latency:.1f}-{max_latency:.1f}ms | {quality_summary}")
        
        # Group connections by quality
        details.append(f"\n⚡ CONNECTION QUALITY BREAKDOWN:")
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
                details.append(f"\n  {quality.upper()} Connections ({len(connections)}):")
                for conn in connections:
                    target_node = next((n for n in self.topology_data["nodes"] if n["hostname"] == conn["target"]), None)
                    location_str = "Unknown"
                    if target_node:
                        location = target_node.get("location", {})
                        city = location.get("city", "")
                        country = location.get("country", "")
                        if city != "Unknown" and country != "Unknown":
                            location_str = f"{city}, {country}"
                        elif country != "Unknown":
                            location_str = country
                    
                    latency_str = f"{conn['latency']:.1f}ms" if conn['latency'] else "N/A"
                    conn_type = conn['connection_type'].title()
                    details.append(f"    {conn['target']:15} | {latency_str:8} | {conn_type:8} | {location_str}")
        
        # Add summary statistics
        all_latencies = [c['latency'] for c in self.topology_data["connections"].values() if c['latency']]
        if all_latencies:
            avg_latency = sum(all_latencies) / len(all_latencies)
            min_latency = min(all_latencies)
            max_latency = max(all_latencies)
            details.append(f"\n📊 OVERALL STATISTICS:")
            details.append(f"  Average Latency: {avg_latency:.1f}ms")
            details.append(f"  Latency Range: {min_latency:.1f}ms - {max_latency:.1f}ms")
            details.append(f"  Total Countries: {len([c for c in countries.keys() if c != 'Unknown'])}")
            details.append(f"  Total Regions: {len([r for r in regions.keys() if r != 'Unknown'])}")
        
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
        ("d", "show_details", "Connection Details"),
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

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        
        with Vertical():
            # Tab indicator
            yield Static("Current View: Overview | Press 1=Overview 2=Topology 3=Diagnostics 4=Bandwidth", id="tab-indicator")
            
            # Overview section
            with Vertical(id="overview-section"):
                yield Static(id="ip-label")
                yield Static(id="exit-label")
                self.table = DataTable(zebra_stripes=True)
                self.table.add_columns("Hostname", "IP", "Online", "Exit Node", "OS")
                yield VerticalScroll(self.table)
            
            # Topology section (initially hidden)
            with Vertical(id="topology-section", classes="hidden"):
                yield Static("🌐 Network Topology", id="topology-header")
                yield Static("", id="topology-display")
                with Horizontal():
                    yield Static("Press 't' for full-screen map | 'd' for connection details", id="topology-hints")
            
            # Diagnostics section (initially hidden)
            with Vertical(id="diagnostics-section", classes="hidden"):
                yield Static(id="netcheck")
                yield Static("", id="connection-stats")
            
            # Bandwidth section (initially hidden)
            with Vertical(id="bandwidth-section", classes="hidden"):
                yield Static("", id="bandwidth-display")
        
        yield Footer()

    async def on_mount(self):
        await self.refresh_data()
        create_task(self.refresh_loop())

    async def refresh_loop(self):
        while True:
            await self.refresh_data()
            # More frequent updates for bandwidth monitoring
            if self.current_view == "bandwidth":
                await sleep(2)  # Fast updates for bandwidth graphs
            else:
                await sleep(30)  # Normal updates for other views

    async def refresh_data(self):
        """Refresh all dashboard data"""
        try:
            self.local_ip = get_local_ip()
            advertised, using = get_exit_node_info()
            self.exit_status = f"Exit Nodes: {', '.join(advertised) if advertised else 'None'}\n{using}"
            self.netcheck_output = get_netcheck()
            
            # Update basic data
            self.update_table()
            self.query_one("#ip-label", Static).update(f"Local IP: {self.local_ip}")
            self.query_one("#exit-label", Static).update(self.exit_status)
            self.query_one("#netcheck", Static).update(f"[Netcheck]\n{self.netcheck_output}")
            
            # Update topology in background (non-blocking) only if Tailscale is running
            if "stopped" not in using.lower():
                create_task(self.update_topology_async())
                
                # Update bandwidth data if in bandwidth view
                if self.current_view == "bandwidth":
                    self.update_bandwidth_display()
            else:
                # Clear topology data if Tailscale is stopped
                self.query_one("#topology-display").update("Tailscale is not running. Please start Tailscale to view network topology.")
                self.query_one("#connection-stats").update("Connection statistics unavailable - Tailscale stopped")
                self.query_one("#bandwidth-display").update("Bandwidth monitoring unavailable - Tailscale stopped")
        
        except Exception as e:
            # Handle any other errors gracefully
            error_msg = f"Error refreshing data: {e}"
            self.query_one("#ip-label", Static).update(f"Local IP: Error - {error_msg}")
            self.query_one("#exit-label", Static).update("Exit Nodes: Error")
            self.query_one("#topology-display").update(f"Error: {error_msg}")
            self.query_one("#connection-stats").update("Connection statistics unavailable")
            self.query_one("#bandwidth-display").update(f"Bandwidth monitoring error: {error_msg}")
            print(f"Dashboard error: {e}")  # For debugging

    def update_bandwidth_display(self):
        """Update the bandwidth monitoring display"""
        try:
            bandwidth_data = get_bandwidth_data()
            bandwidth_lines = generate_bandwidth_display(bandwidth_data, width=80)
            bandwidth_text = "\n".join(bandwidth_lines)
            self.query_one("#bandwidth-display").update(bandwidth_text)
        except Exception as e:
            self.query_one("#bandwidth-display").update(f"Error updating bandwidth: {e}")

    async def update_topology_async(self):
        """Update topology data asynchronously"""
        try:
            # Get fresh topology data
            topology_data = get_network_topology()
            self.topology_data = topology_data
            
            # Generate compact topology map for the tab (standard view)
            compact_map = generate_topology_map(topology_data, width=60, height=12, view_mode="standard")
            
            # Add connection and geographic summary
            total_connections = len(topology_data["connections"])
            online_nodes = len([n for n in topology_data["nodes"] if n["online"]])
            
            # Quality breakdown
            quality_counts = {}
            for conn in topology_data["connections"].values():
                quality = conn["quality"]
                quality_counts[quality] = quality_counts.get(quality, 0) + 1
            
            # Geographic summary
            countries = set()
            regions = set()
            for node in topology_data["nodes"]:
                if node["online"]:
                    location = node.get("location", {})
                    country = location.get("country", "Unknown")
                    region = location.get("region", "Unknown")
                    if country != "Unknown":
                        countries.add(country)
                    if region != "Unknown":
                        regions.add(region)
            
            summary_lines = [
                f"Online Nodes: {online_nodes} | Connections: {total_connections} | Countries: {len(countries)} | Regions: {len(regions)}",
                f"Quality: Excellent:{quality_counts.get('excellent', 0)} Good:{quality_counts.get('good', 0)} Fair:{quality_counts.get('fair', 0)} Poor:{quality_counts.get('poor', 0)}",
                ""
            ]
            
            display_text = "\n".join(summary_lines + compact_map)
            
            # Update the topology display
            self.query_one("#topology-display").update(display_text)
            
            # Update connection stats with geographic info
            if topology_data["connections"]:
                latencies = [c['latency'] for c in topology_data["connections"].values() if c['latency']]
                if latencies:
                    avg_latency = sum(latencies) / len(latencies)
                    
                    # Find most distant connection
                    max_latency_conn = max(topology_data["connections"].values(), key=lambda c: c['latency'] if c['latency'] else 0)
                    max_target = max_latency_conn["target"]
                    max_target_node = next((n for n in topology_data["nodes"] if n["hostname"] == max_target), None)
                    distant_location = ""
                    if max_target_node:
                        location = max_target_node.get("location", {})
                        country = location.get("country", "Unknown")
                        if country != "Unknown":
                            distant_location = f" (farthest: {country})"
                    
                    stats_text = f"Average Latency: {avg_latency:.1f}ms | Range: {min(latencies):.1f}-{max(latencies):.1f}ms{distant_location}"
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

    def switch_view(self, view_name: str):
        """Switch between different views"""
        self.current_view = view_name
        
        # Hide all sections
        self.query_one("#overview-section").add_class("hidden")
        self.query_one("#topology-section").add_class("hidden") 
        self.query_one("#diagnostics-section").add_class("hidden")
        self.query_one("#bandwidth-section").add_class("hidden")
        
        # Show selected section
        if view_name == "overview":
            self.query_one("#overview-section").remove_class("hidden")
            self.query_one("#tab-indicator").update("Current View: Overview | Press 1=Overview 2=Topology 3=Diagnostics 4=Bandwidth")
        elif view_name == "topology":
            self.query_one("#topology-section").remove_class("hidden")
            self.query_one("#tab-indicator").update("Current View: Network Topology | Press 1=Overview 2=Topology 3=Diagnostics 4=Bandwidth")
        elif view_name == "diagnostics":
            self.query_one("#diagnostics-section").remove_class("hidden")
            self.query_one("#tab-indicator").update("Current View: Diagnostics | Press 1=Overview 2=Topology 3=Diagnostics 4=Bandwidth")
        elif view_name == "bandwidth":
            self.query_one("#bandwidth-section").remove_class("hidden")
            self.query_one("#tab-indicator").update("Current View: Bandwidth Monitor | Press 1=Overview 2=Topology 3=Diagnostics 4=Bandwidth")
            # Immediately update bandwidth display when switching to it
            self.update_bandwidth_display()

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

    async def action_show_overview(self):
        """Switch to overview tab"""
        self.switch_view("overview")

    async def action_show_topology_tab(self):
        """Switch to topology tab"""
        self.switch_view("topology")

    async def action_show_diagnostics(self):
        """Switch to diagnostics tab"""
        self.switch_view("diagnostics")

    async def action_show_bandwidth(self):
        """Switch to bandwidth monitoring tab"""
        self.switch_view("bandwidth")

if __name__ == "__main__":
    try:
        # Add some basic CSS for hiding elements
        app = TailscaleDashboard()
        app.CSS = """
        .hidden {
            display: none;
        }
        """
        print("Starting Tailscale Dashboard...")
        app.run()
    except ImportError as e:
        print(f"Import error: {e}")
        print("Make sure you have installed required dependencies:")
        print("pip install textual psutil")
    except Exception as e:
        print(f"Error starting dashboard: {e}")
        import traceback
        traceback.print_exc()