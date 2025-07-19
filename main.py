from textual.app import App, ComposeResult
from textual.widgets import Static, Header, Footer, DataTable
from textual.containers import VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen
from asyncio import create_task, sleep
from ts_backend import get_peers, get_local_ip, get_exit_node_info, get_netcheck, ping

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
        ("r", "refresh", "Refresh Now")
    ]
    
    netcheck_output = reactive("")
    local_ip = reactive("")
    exit_status = reactive("")

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(id="ip-label")
        yield Static(id="exit-label")
        yield Static(id="netcheck")
        self.table = DataTable(zebra_stripes=True)
        self.table.add_columns("Hostname", "IP", "Online", "Exit Node", "OS")
        yield VerticalScroll(self.table)
        yield Footer()

    async def on_mount(self):
        await self.refresh_data()
        create_task(self.refresh_loop())

    async def refresh_loop(self):
        while True:
            await self.refresh_data()
            await sleep(10)

    async def refresh_data(self):
        self.local_ip = get_local_ip()
        advertised, using = get_exit_node_info()
        self.exit_status = f"Exit Nodes: {', '.join(advertised) if advertised else 'None'}\n{using}"
        self.netcheck_output = get_netcheck()
        
        self.update_table()
        self.query_one("#ip-label", Static).update(f"Local IP: {self.local_ip}")
        self.query_one("#exit-label", Static).update(self.exit_status)
        self.query_one("#netcheck", Static).update(f"[Netcheck]\n{self.netcheck_output}")

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
        await self.refresh_data()

if __name__ == "__main__":
    TailscaleDashboard().run()