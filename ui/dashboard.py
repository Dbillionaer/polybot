import time
from datetime import datetime

from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table


class Dashboard:
    """Terminal UI Dashboard for PolyBot."""

    def __init__(self, bot_name="PolyBot 2026"):
        self.bot_name = bot_name
        self.start_time = datetime.now()
        self.trades = []
        self.positions = []
        self.pnl_data = {"today": 0.0, "total": 0.0}

    def generate_layout(self) -> Layout:
        layout = Layout()
        
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3)
        )
        
        layout["main"].split_row(
            Layout(name="positions", ratio=2),
            Layout(name="recent_trades", ratio=3)
        )
        
        return layout

    def update_header(self, layout: Layout):
        uptime = str(datetime.now() - self.start_time).split(".")[0]
        layout["header"].update(
            Panel(
                f"[bold blue]{self.bot_name}[/bold blue] | "
                f"Uptime: {uptime} | "
                f"PnL Today: [green]${self.pnl_data['today']}[/green]",
                style="white on black"
            )
        )

    def update_positions_table(self, layout: Layout):

        table = Table(title="Open Positions")
        table.add_column("Market", justify="left")
        table.add_column("Outcome", justify="center")
        table.add_column("Size", justify="right")
        table.add_column("Avg Price", justify="right")
        table.add_column("Current Price", justify="right")
        table.add_column("PnL", justify="right")
        
        for pos in self.positions:
            table.add_row(
                pos['name'],
                pos['side'],
                str(pos['size']),
                str(pos['avg']),
                str(pos['current']),
                "[green]+$12.50[/green]"
            )

        layout["positions"].update(Panel(table))

    def update_trades_table(self, layout: Layout):

        table = Table(title="Recent Activity")
        table.add_column("Time", justify="left")
        table.add_column("Market", justify="left")
        table.add_column("Side", justify="center")
        table.add_column("Size", justify="right")
        table.add_column("Price", justify="right")
        table.add_column("Strategy", justify="right")
        
        for trade in self.get_latest_trades():
            table.add_row(
                trade['time'],
                trade['market'],
                trade['side'],
                str(trade['size']),
                str(trade['price']),
                trade['strategy']
            )

        layout["recent_trades"].update(Panel(table))

    def get_latest_trades(self):
        # Placeholder
        return [
            {
                "time": "14:22:01",
                "market": "BTC > $100k",
                "side": "BUY",
                "size": "100",
                "price": "0.45",
                "strategy": "AI-Arb"
            },
            {
                "time": "14:25:30",
                "market": "TRUMP Wins 2028",
                "side": "SELL",
                "size": "50",
                "price": "0.62",
                "strategy": "AMM"
            },
        ]

    def render_loop(self):

        layout = self.generate_layout()
        with Live(layout, refresh_per_second=1, screen=True):
            while True:
                self.update_header(layout)
                self.update_positions_table(layout)
                self.update_trades_table(layout)
                time.sleep(1)
