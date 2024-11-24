import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import os
import json
import pandas as pd
from pytz import timezone
from dotenv import load_dotenv
import io
# Add yfinance import
import yfinance as yf

# Add caching for expensive operations
from functools import lru_cache
from typing import Optional, Tuple, Dict, Any
from functools import wraps
from time import time

# Load environment variables from .env file
load_dotenv()

# Add required import at the top with other imports
import aiofiles
from typing import Optional, Tuple, Dict, Any

# Remove matplotlib import and add plotly imports
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

# Add this function near the top with other utility functions
async def load_leaderboard_data() -> Optional[Dict[str, Any]]:
    """
    Asynchronously load the latest leaderboard data.
    Returns None if the file doesn't exist or there's an error.
    """
    try:
        if not os.path.exists(LEADERBOARD_LATEST):
            return None

        try:
            async with aiofiles.open(LEADERBOARD_LATEST, mode='r') as f:
                content = await f.read()
                return json.loads(content)
        except ImportError:
            with open(LEADERBOARD_LATEST, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading leaderboard data: {e}")
        return None

# Set up paths
PATH_TO_LEADERBOARD_DATA = os.environ.get('PATH_TO_LEADERBOARD_DATA')
LEADERBOARDS_DIR = os.path.join(PATH_TO_LEADERBOARD_DATA, 'backend/leaderboards')
IN_TIME_DIR = os.path.join(LEADERBOARDS_DIR, 'in_time')
LEADERBOARD_LATEST = os.path.join(LEADERBOARDS_DIR, 'leaderboard-latest.json')
USERNAMES_PATH = os.path.join(PATH_TO_LEADERBOARD_DATA, 'backend/portfolios/usernames.txt')

# Update snapshot paths to be local
SNAPSHOTS_DIR = "./snapshots"
SNAPSHOT_PATH = os.path.join(SNAPSHOTS_DIR, "leaderboard-snapshot.json")
MORNING_SNAPSHOT_PATH = os.path.join(SNAPSHOTS_DIR, "morning-snapshot.json")

# Ensure snapshots directory exists
os.makedirs(SNAPSHOTS_DIR, exist_ok=True)

# Set up Discord bot intents
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

# Ensure the bot token is loaded correctly
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not DISCORD_BOT_TOKEN:
    print("Error: DISCORD_BOT_TOKEN is not set in the environment variables.")
    exit(1)

# Initialize bot instance with command prefix
bot = commands.Bot(command_prefix="$", intents=intents)

# Add debug print to check bot initialization
print("Bot initialized with command prefix '$'")

# Add timezone constants near the top of the file with other constants
EST = timezone('US/Eastern')
PST = timezone('America/Los_Angeles')

def get_user_info(df, username):
    """
    Retrieve and format information for a specific user from the DataFrame.
    """
    df["Money In Account"] = pd.to_numeric(df["Money In Account"], errors="coerce")
    user_row = df[df["Account Name"] == username]
    if user_row.empty:
        return None
    user_data = user_row.iloc[0]
    user_name = user_data["Account Name"]
    user_money = user_data["Money In Account"]
    user_stocks = user_data["Stocks Invested In"]
    formatted_holdings = "\n".join(
        [f"{stock[0]}: {stock[1]} ({stock[2]})" for stock in user_stocks]
    )
    return user_name, user_money, formatted_holdings


def get_latest_in_time_leaderboard():
    """
    Get the most recent leaderboard file from the in_time directory.
    """
    files = [f for f in os.listdir(IN_TIME_DIR) if f.endswith(".json")]
    if not files:
        return None
    files.sort(key=lambda x: parse_leaderboard_timestamp(x))
    latest_file = files[-1]
    return os.path.join(IN_TIME_DIR, latest_file)


def get_pst_time():
    """Helper function to get current time in PST"""
    return datetime.datetime.now(PST)


async def compare_stock_changes(channel):
    """
    Compare current leaderboard with snapshot to detect stock changes, and send updates to the Discord channel as embeds.
    """
    try:
        # Load the current leaderboard data first
        with open(LEADERBOARD_LATEST, "r") as f:
            current_data = json.load(f)

        # Load the snapshot file if it exists
        snapshot_path = SNAPSHOT_PATH
        if os.path.exists(snapshot_path):
            with open(snapshot_path, "r") as f:
                previous_data = json.load(f)

            # Compare holdings for each user
            for username in current_data:
                if username not in previous_data:
                    continue

                # Get current and previous stock symbols
                current_stocks = set(stock[0] for stock in current_data[username][2])
                previous_stocks = set(stock[0] for stock in previous_data[username][2])

                # Find new and removed stocks
                new_stocks = current_stocks - previous_stocks
                removed_stocks = previous_stocks - current_stocks

                if new_stocks or removed_stocks:
                    description = ""
                    for stock in new_stocks:
                        description += f"+ Bought {stock}\n"
                    for stock in removed_stocks:
                        description += f"- Sold {stock}\n"

                    embed = discord.Embed(
                        colour=discord.Colour.green(),
                        title=f"Stock Changes for {username}",
                        description=description,
                        timestamp=get_pst_time(),
                    )
                    stock_channel = bot.get_channel(int(os.environ.get("DISCORD_CHANNEL_ID_Stocks")))
                    if stock_channel:
                        await stock_channel.send(embed=embed)

        # Update the snapshot with current data after comparison
        with open(snapshot_path, "w") as f:
            json.dump(current_data, f)

    except Exception as e:
        await channel.send(f"Error comparing stock changes: {str(e)}")
        import traceback
        traceback.print_exc()


# Load usernames from file
with open(USERNAMES_PATH, "r") as f:
    usernames_list = [line.strip() for line in f.readlines()]


def parse_leaderboard_timestamp(filename):
    """
    Parse the datetime from a leaderboard filename.

    Filename format: leaderboard-YYYY-MM-DD-HH_MM.json
    """
    timestamp_str = filename[len('leaderboard-'):-len('.json')]
    return datetime.datetime.strptime(timestamp_str, '%Y-%m-%d-%H_%M')


# Replace the lru_cache implementation with a time-based cache
class TimedCache:
    def __init__(self, ttl=3600):
        self.cache = {}
        self.ttl = ttl

    def __call__(self, func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            key = str(args) + str(kwargs)
            now = time()
            if key in self.cache:
                result, timestamp = self.cache[key]
                if now - timestamp < self.ttl:
                    return result
                del self.cache[key]
            result = func(*args, **kwargs)
            self.cache[key] = (result, now)
            return result
        return wrapped

# Replace the lru_cache decorator with our custom one
@TimedCache(ttl=3600)
def fetch_stock_data(symbol: str, start_date, end_date):
    return yf.download(symbol, start=start_date, end=end_date, progress=False)

# Optimize the generate_money_graph function
def generate_money_graph(username):
    """Generate a time series graph for a user's account value"""
    try:
        # Get all JSON files sorted by timestamp
        files = sorted([f for f in os.scandir(IN_TIME_DIR) if f.name.endswith('.json')],
                      key=lambda x: parse_leaderboard_timestamp(x.name))
        
        # Load user data first to determine date range
        data = {'timestamp': [], username: []}
        first_value = None
        for file in files:
            try:
                with open(file.path) as f:
                    file_data = json.load(f)
                if username in file_data:
                    timestamp = parse_leaderboard_timestamp(file.name)
                    timestamp = timestamp.replace(tzinfo=datetime.timezone.utc)
                    value = float(file_data[username][0])
                    if first_value is None:
                        first_value = value
                    data['timestamp'].append(timestamp)
                    data[username].append(value)
            except Exception as e:
                print(f"Error reading file {file.name}: {e}")

        if not data['timestamp'] or first_value is None:
            return None, None, None

        # Fetch S&P 500 data for the same time period
        start_date = min(data['timestamp'])
        end_date = max(data['timestamp'])
        
        try:
            spy_data = fetch_stock_data("SPY", start_date, end_date)
            if not spy_data.empty:
                # Normalize S&P data to match user's starting value
                initial_spy = spy_data['Close'].iloc[0]
                spy_values = spy_data['Close'] * (first_value / initial_spy)
                
                # Ensure timezone aware
                if spy_data.index.tz is None:
                    spy_data.index = spy_data.index.tz_localize('UTC')
            else:
                spy_values = None
        except Exception as e:
            print(f"Error fetching S&P 500 data: {e}")
            spy_values = None

        # Create figure with adjusted range
        fig = go.Figure()

        # Add user's trace
        fig.add_trace(
            go.Scatter(
                x=data['timestamp'],
                y=data[username],
                name=f"{username}'s Portfolio",
                line=dict(color='rgb(0, 100, 255)', width=2.5),
                mode='lines+markers',
                marker=dict(size=6)
            )
        )

        # Add S&P 500 trace if available
        if spy_values is not None:
            fig.add_trace(
                go.Scatter(
                    x=spy_data.index,
                    y=spy_values,
                    name='S&P 500 (Normalized)',
                    line=dict(color='rgb(255, 165, 0)', width=2, dash='dot'),
                    mode='lines'
                )
            )

        # Calculate extreme values including S&P 500
        values = data[username]
        all_values = values.copy()
        if spy_values is not None:
            all_values.extend(spy_values.tolist())
        
        lowest_value = min(all_values)
        highest_value = max(all_values)

        # Add markers for user's extreme points
        user_lowest = min(values)
        user_highest = max(values)
        
        fig.add_trace(
            go.Scatter(
                x=[data['timestamp'][values.index(user_lowest)]],
                y=[user_lowest],
                mode='markers+text',
                name='Portfolio Lowest',
                marker=dict(color='red', size=12),
                text=[f'${user_lowest:,.2f}'],
                textposition='top center'
            )
        )

        fig.add_trace(
            go.Scatter(
                x=[data['timestamp'][values.index(user_highest)]],
                y=[user_highest],
                mode='markers+text',
                name='Portfolio Highest',
                marker=dict(color='green', size=12),
                text=[f'${user_highest:,.2f}'],
                textposition='top center'
            )
        )

        # Update layout with adjusted range
        fig.update_layout(
            title=dict(
                text=f"Portfolio Performance vs S&P 500 - {username}",
                x=0.05,
                font=dict(size=16)
            ),
            xaxis_title="Time",
            yaxis_title="Value ($)",
            template="plotly_dark",
            plot_bgcolor='rgba(44, 47, 51, 1)',
            paper_bgcolor='rgba(44, 47, 51, 1)',
            font=dict(color='white'),
            showlegend=True,
            legend=dict(
                yanchor="top",
                y=0.99,
                xanchor="left",
                x=0.01
            ),
            margin=dict(t=30, l=10, r=10, b=10),
            yaxis=dict(
                range=[min(all_values) * 0.95, max(all_values) * 1.05]
            )
        )

        # Format axes
        fig.update_yaxes(tickprefix="$", tickformat=",.0f")
        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128, 128, 128, 0.2)')
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128, 128, 128, 0.2)')

        # Save to buffer
        buf = io.BytesIO()
        fig.write_image(buf, format='png', engine='kaleido')
        buf.seek(0)
        
        return buf, lowest_value, highest_value
    except Exception as e:
        print(f"Error generating money graph: {e}")
        return None, None, None

def get_embed_color():
    """Get the appropriate embed color based on testing mode"""
    testing = os.environ.get('TESTING', 'false').lower() == 'true'
    return 0xFF69B4 if testing else 0x0000FF  # Using hex values directly: hot pink (#FF69B4) and blue (#0000FF)

class UserInfo(commands.Cog):
    """
    Cog to handle user information related commands.
    """

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="userinfo", description="Get user information")
    @app_commands.describe(username="Select a username")
    async def userinfo(self, interaction: discord.Interaction, username: str):
        """
        Respond to the /userinfo command with the user's information.
        """
        try:
            # Defer the response immediately
            await interaction.response.defer(thinking=True)
        except Exception as e:
            # If deferring fails, log the error and exit
            print(f"Failed to defer interaction: {e}")
            return

        try:
            with open(LEADERBOARD_LATEST, "r") as file:
                data = json.load(file)
            df = pd.DataFrame.from_dict(data, orient="index")
            df.reset_index(inplace=True)
            df.columns = [
                "Account Name",
                "Money In Account",
                "Investopedia Link",
                "Stocks Invested In",
            ]

            user_info = get_user_info(df, username)
            if user_info is None:
                await interaction.followup.send(f"User '{username}' not found.")
                return

            user_name, user_money, user_holdings = user_info
            embed = discord.Embed(
                colour=get_embed_color(),
                title=f"Information for {user_name}",
                description=(
                    f"**Current Money:** {user_money}\n\n"
                    f"**Current Holdings:**\n{user_holdings}"
                ),
                timestamp=get_pst_time(),
            )

            # Generate and add the graph
            try:
                graph_buffer, lowest_value, highest_value = generate_money_graph(username)
                if graph_buffer:
                    file = discord.File(graph_buffer, filename="money_graph.png")
                    embed.set_image(url="attachment://money_graph.png")
                    if lowest_value is not None and highest_value is not None:
                        embed.add_field(
                            name="📈 Highest Value",
                            value=f"${highest_value:,.2f}",
                            inline=True,
                        )
                        embed.add_field(
                            name="📉 Lowest Value",
                            value=f"${lowest_value:,.2f}",
                            inline=True,
                        )
                    await interaction.followup.send(embed=embed, file=file)
                else:
                    await interaction.followup.send(embed=embed)
            except Exception as graph_error:
                print(f"Error generating graph: {graph_error}")
                # If graph fails, still send the basic embed
                await interaction.followup.send(embed=embed)

        except Exception as e:
            print(f"Error in userinfo command: {e}")
            await interaction.followup.send(f"Error fetching user info: {str(e)}")

    @userinfo.autocomplete("username")
    async def username_autocomplete(
        self, interaction: discord.Interaction, current: str
    ):
        """
        Provide autocomplete suggestions for usernames based on current input.
        """
        return [
            app_commands.Choice(name=username, value=username)
            for username in usernames_list
            if current.lower() in username.lower()
        ][:25]


async def setup(bot):
    """
    Add the UserInfo cog to the bot.
    """
    await bot.add_cog(UserInfo(bot))


async def setup_hook():
    """
    Run setup when the bot is ready.
    """
    await setup(bot)
    print("Setup hook executed")

bot.setup_hook = setup_hook

def generate_leaderboard_graph(top_users_data):
    """Generate a line chart showing the top 10 users' performance over time"""
    # Get all JSON files sorted by timestamp
    files = sorted([f for f in os.scandir(IN_TIME_DIR) if f.name.endswith('.json')],
                  key=lambda x: parse_leaderboard_timestamp(x.name))

    if not files:
        return None

    # Get top 10 usernames
    usernames = top_users_data['Account Name'].tolist()

    # Create data structure for time series
    data = {
        'timestamp': [],
        **{username: [] for username in usernames}
    }

    # Read data for each timestamp
    for file in files:
        try:
            with open(file.path) as f:
                file_data = json.load(f)
            timestamp = parse_leaderboard_timestamp(file.name)
            data['timestamp'].append(timestamp)
            for username in usernames:
                if username in file_data:
                    data[username].append(float(file_data[username][0]))
                else:
                    data[username].append(None)
        except Exception as e:
            print(f"Error reading file {file.name}: {e}")

    if not data['timestamp']:
        return None

    # Create figure
    fig = go.Figure()

    # Add trace for each user
    colors = px.colors.qualitative.Set3  # Using a color sequence
    for i, username in enumerate(usernames):
        fig.add_trace(
            go.Scatter(
                x=data['timestamp'],
                y=data[username],
                name=username,
                line=dict(color=colors[i % len(colors)], width=2),
                mode='lines+markers',
                marker=dict(size=4)
            )
        )

    # Update layout
    fig.update_layout(
        title=dict(
            text="Top 10 Users Performance Over Time",
            x=0.05,
            font=dict(size=16)
        ),
        xaxis_title="Time",
        yaxis_title="Account Value ($)",
        template="plotly_dark",
        plot_bgcolor='rgba(44, 47, 51, 1)',
        paper_bgcolor='rgba(44, 47, 51, 1)',
        font=dict(color='white'),
        showlegend=True,
        legend=dict(
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01
        ),
        margin=dict(t=30, l=10, r=10, b=10)
    )

    # Format axes
    fig.update_yaxes(tickprefix="$", tickformat=",.0f")
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128, 128, 128, 0.2)')
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128, 128, 128, 0.2)')

    # Save to buffer
    buf = io.BytesIO()
    fig.write_image(buf, format='png', engine='kaleido')
    buf.seek(0)
    
    return buf

# Update the leaderboard command to include the graph
@bot.tree.command(name="leaderboard", description="Get current leaderboard")
async def leaderboard(interaction: discord.Interaction):
    """
    Respond to the /leaderboard command with the top 10 users' info.
    """
    await interaction.response.defer()
    try:
        # Load current data
        current_data = await load_leaderboard_data()
        if not current_data:
            await interaction.followup.send("Error loading leaderboard data")
            return

        # Create DataFrame for displaying
        df = pd.DataFrame.from_dict(current_data, orient="index")
        df.reset_index(inplace=True)
        df.columns = ["Account Name", "Money In Account", "Investopedia Link", "Stocks Invested In"]
        df.sort_values(by="Money In Account", ascending=False, inplace=True)

        # Format description
        top_users = df.head(5)  # Changed from 10 to 5
        description = ""
        for idx, row in enumerate(top_users.iterrows(), 1):
            _, row = row
            money = float(row['Money In Account'])
            description += f"**#{idx} - {row['Account Name']}**\n"
            description += f"Money: ${money:,.2f}\n\n"

        embed = discord.Embed(
            colour=get_embed_color(),
            title="📊 Current Leaderboard",
            description=description,
            timestamp=get_pst_time(),
        )

        # After creating the embed, add the graph
        graph_buffer = generate_leaderboard_graph(top_users)
        if graph_buffer:
            file = discord.File(graph_buffer, filename="leaderboard_graph.png")
            embed.set_image(url="attachment://leaderboard_graph.png")
            await interaction.followup.send(embed=embed, file=file)
        else:
            await interaction.followup.send(embed=embed)

    except Exception as e:
        print(f"Error in leaderboard command: {str(e)}")
        await interaction.followup.send(f"Error fetching leaderboard: {str(e)}")

# Optimize leaderboard updates
@tasks.loop(minutes=1)
async def send_leaderboard():
    """
    Send leaderboard updates only at market open/close or when rankings change.
    """
    now = datetime.datetime.now(EST)
    if now.weekday() >= 5:  # Skip weekends
        return

    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)

    # Only proceed during market hours
    if not (market_open <= now <= market_close):
        return

    try:
        # Load current data using the async function
        current_data = await load_leaderboard_data()
        if not current_data:
            return

        # Load previous data from snapshot
        snapshot_path = "./snapshots/leaderboard-snapshot.json"
        previous_data = None
        if os.path.exists(snapshot_path):
            with open(snapshot_path, "r") as f:
                previous_data = json.load(f)

        # Check if we should send an update
        is_market_open = abs((now - market_open).total_seconds()) < 60
        is_market_close = abs((now - market_close).total_seconds()) < 60
        rankings_changed = have_rankings_changed(previous_data, current_data)

        if is_market_open or is_market_close or rankings_changed:
            # Create DataFrame for displaying
            df = pd.DataFrame.from_dict(current_data, orient="index")
            df.reset_index(inplace=True)
            df.columns = ["Account Name", "Money In Account", "Investopedia Link", "Stocks Invested In"]
            df.sort_values(by="Money In Account", ascending=False, inplace=True)

            # Format description
            top_users = df.head(5)  # Changed from 10 to 5
            description = ""
            for idx, row in enumerate(top_users.iterrows(), 1):
                _, row = row
                money = float(row['Money In Account'])
                description += f"**#{idx} - {row['Account Name']}**\n"
                description += f"Money: ${money:,.2f}\n\n"

            # Send update
            leaderboard_channel = bot.get_channel(int(os.environ.get("DISCORD_CHANNEL_ID_Leaderboard")))
            if leaderboard_channel:
                embed = discord.Embed(
                    colour=get_embed_color(),
                    title="📊 Leaderboard Update!",
                    description=description,
                    timestamp=get_pst_time(),
                )

                # Add graph to the embed
                graph_buffer = generate_leaderboard_graph(top_users)
                if graph_buffer:
                    file = discord.File(graph_buffer, filename="leaderboard_graph.png")
                    embed.set_image(url="attachment://leaderboard_graph.png")

                # Add reason for update
                if is_market_open:
                    embed.set_footer(text="Market Open Update")
                elif is_market_close:
                    embed.set_footer(text="Market Close Update")
                elif rankings_changed:
                    embed.set_footer(text="Rankings Changed")

                await leaderboard_channel.send(embed=embed, file=file if graph_buffer else None)

            # Update snapshot after sending
            with open(snapshot_path, "w") as f:
                json.dump(current_data, f)

    except Exception as e:
        print(f"Error in send_leaderboard: {str(e)}")


@tasks.loop(time=datetime.time(hour=9, minute=30, tzinfo=EST))
async def start_of_day():
    """Create snapshot at market open"""
    now = datetime.datetime.now(EST)
    if now.weekday() < 5:  # Only on weekdays
        await create_morning_snapshot()


@tasks.loop(time=datetime.time(hour=16, minute=0, tzinfo=EST))
async def send_daily_summary():
    """Send daily summary comparing start of day to end of day"""
    now = datetime.datetime.now(EST)
    if now.weekday() < 5:  # Only on weekdays
        try:
            # Load morning snapshot instead of previous day's snapshot
            morning_snapshot_path = MORNING_SNAPSHOT_PATH
            if not os.path.exists(morning_snapshot_path):
                print("No morning snapshot found")
                return

            with open(morning_snapshot_path, "r") as f:
                morning_data = json.load(f)

            # Load end of day data
            with open(LEADERBOARDS_DIR, "r") as f:
                current_data = json.load(f)

            # Calculate performance using morning data
            stats = calculate_daily_performance(morning_data, current_data)

            if stats["performance"]:
                embed = discord.Embed(
                    colour=get_embed_color(),  # Changed this line
                    title="📊 End of Day Trading Summary",
                    description=f"Market Close Summary for {now.strftime('%A, %B %d, %Y')}",
                    timestamp=get_pst_time(),
                )

                # Overall stats
                embed.add_field(
                    name="📈 Market Activity",
                    value=f"Total Trades Today: {stats['total_trades']}\n",
                    inline=False,
                )

                # Top performers
                top_text = "\n".join(
                    [
                        f"**{p['username']}**: {p['change_percent']:+.2f}% (${p['change_amount']:,.2f}) - {p['trades']} trades"
                        for p in stats["performance"][:3]
                    ]
                )
                embed.add_field(name="🏆 Top Performers", value=top_text, inline=False)

                # Bottom performers
                bottom_text = "\n".join(
                    [
                        f"**{p['username']}**: {p['change_percent']:+.2f}% (${p['change_amount']:,.2f}) - {p['trades']} trades"
                        for p in stats["performance"][-3:]
                    ]
                )
                embed.add_field(
                    name="📉 Needs Improvement", value=bottom_text, inline=False
                )

                # Biggest moves
                if stats["biggest_gain"]["username"]:
                    embed.add_field(
                        name="🚀 Biggest Gain",
                        value=f"**{stats['biggest_gain']['username']}**\n{stats['biggest_gain']['percent']:+.2f}% (${stats['biggest_gain']['amount']:,.2f})",
                        inline=True,
                    )

                if stats["biggest_loss"]["username"]:
                    embed.add_field(
                        name="💥 Biggest Loss",
                        value=f"**{stats['biggest_loss']['username']}**\n{stats['biggest_loss']['percent']:+.2f}% (${stats['biggest_loss']['amount']:,.2f})",
                        inline=True,
                    )

                # Most active traders
                active_text = "\n".join(
                    [
                        f"**{p['username']}**: {p['trades']} trades"
                        for p in stats["most_active"]
                    ]
                )
                embed.add_field(
                    name="⚡ Most Active Traders", value=active_text, inline=False
                )

                channel = bot.get_channel(
                    int(os.environ.get("DISCORD_CHANNEL_ID_Leaderboard"))
                )
                if channel:
                    await channel.send(embed=embed)

        except Exception as e:
            print(f"Error in send_daily_summary: {str(e)}")


@send_daily_summary.before_loop
async def before_daily_summary():
    """Ensure bot is ready before starting the daily summary task"""
    await bot.wait_until_ready()


@bot.event
async def on_ready():
    """
    Actions to perform when the bot is fully ready.
    """
    print(f"Logged in as {bot.user}")
    try:
        # Get the leaderboard channel
        leaderboard_channel = bot.get_channel(int(os.environ.get("DISCORD_CHANNEL_ID_Leaderboard")))
        if leaderboard_channel:
            # Do initial comparison with existing snapshot before starting regular tasks
            await compare_stock_changes(leaderboard_channel)

        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")

        # Start all scheduled tasks
        send_leaderboard.start()
        start_of_day.start()
        send_daily_summary.start()
        print("Scheduled tasks started")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

# Run the bot with the provided token from environment variables
try:
    bot.run(DISCORD_BOT_TOKEN)
except Exception as e:
    print(f"Error running the bot: {e}")

async def create_morning_snapshot():
    """Create a snapshot of the leaderboard at market open"""
    try:
        # Load current leaderboard data
        with open(LEADERBOARD_LATEST, "r") as f:
            data = json.load(f)

        # Save as morning snapshot
        with open(MORNING_SNAPSHOT_PATH, "w") as f:
            json.dump(data, f)

        print("Created morning snapshot")
    except Exception as e:
        print(f"Error creating morning snapshot: {e}")

def calculate_daily_performance(morning_data, current_data):
    """
    Calculate performance metrics comparing morning to current data.
    Returns dict with various performance statistics.
    """
    stats = {
        "performance": [],
        "most_active": [],
        "biggest_gain": {"username": None, "amount": 0, "percent": 0},
        "biggest_loss": {"username": None, "amount": 0, "percent": 0},
        "total_trades": 0
    }

    # Calculate metrics for each user
    for username in current_data:
        if username not in morning_data:
            continue

        # Get morning and current values
        morning_value = float(morning_data[username][0])
        current_value = float(current_data[username][0])

        # Calculate changes
        change_amount = current_value - morning_value
        change_percent = (change_amount / morning_value) * 100 if morning_value != 0 else 0

        # Count trades by comparing stock holdings
        morning_stocks = set(stock[0] for stock in morning_data[username][2])
        current_stocks = set(stock[0] for stock in current_data[username][2])
        trades = len(morning_stocks.symmetric_difference(current_stocks))
        stats["total_trades"] += trades

        # Add to performance list
        stats["performance"].append({
            "username": username,
            "change_amount": change_amount,
            "change_percent": change_percent,
            "trades": trades
        })

        # Update biggest gain/loss
        if change_percent > stats["biggest_gain"]["percent"]:
            stats["biggest_gain"] = {
                "username": username,
                "amount": change_amount,
                "percent": change_percent
            }
        if change_percent < stats["biggest_loss"]["percent"]:
            stats["biggest_loss"] = {
                "username": username,
                "amount": change_amount,
                "percent": change_percent
            }

        # Track active traders
        if trades > 0:
            stats["most_active"].append({
                "username": username,
                "trades": trades
            })

    # Sort results
    stats["performance"].sort(key=lambda x: x["change_percent"], reverse=True)
    stats["most_active"].sort(key=lambda x: x["trades"], reverse=True)
    stats["most_active"] = stats["most_active"][:3]  # Keep top 3 most active

    return stats

# Async file operations
import aiofiles  # Add this import

# Move this function earlier in the file, before it's used
async def load_leaderboard_data() -> Optional[Dict[str, Any]]:
    try:
        # Handle case where file doesn't exist
        if not os.path.exists(LEADERBOARD_LATEST):
            return None

        # Use regular open if aiofiles fails
        try:
            async with aiofiles.open(LEADERBOARD_LATEST, mode='r') as f:
                content = await f.read()
                return json.loads(content)
        except ImportError:
            with open(LEADERBOARD_LATEST, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading leaderboard data: {e}")
        return None

def have_rankings_changed(previous_data, current_data):
    """
    Compare previous and current data to check if rankings have changed.
    Returns True only if the order of names has changed in top 5.
    """
    if not previous_data or not current_data:
        return True

    # Get sorted lists of just usernames (no amounts)
    prev_rankings = sorted(
        [(name, float(data[0])) for name, data in previous_data.items()],
        key=lambda x: x[1],
        reverse=True
    )[:5]
    
    curr_rankings = sorted(
        [(name, float(data[0])) for name, data in current_data.items()],
        key=lambda x: x[1],
        reverse=True
    )[:5]

    # Compare just the usernames in their positions
    prev_names = [name for name, _ in prev_rankings]
    curr_names = [name for name, _ in curr_rankings]
    
    return prev_names != curr_names