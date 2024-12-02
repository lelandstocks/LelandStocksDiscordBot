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
import yfinance as yf
from functools import lru_cache
from typing import Optional, Tuple, Dict, Any
from functools import wraps
from time import time
import asyncio
from asyncio import Semaphore
from collections import deque
import traceback

# Load environment variables from .env file
load_dotenv()

#Import necessary libraries for asynchronous file operations and data visualization
import aiofiles
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

def get_last_update_time():
    try:
        if os.path.exists(LAST_UPDATE_FILE):
            with open(LAST_UPDATE_FILE, 'r') as f:
                timestamp_str = f.read().strip()
                return datetime.datetime.fromisoformat(timestamp_str)
    except Exception as e:
        print(f"Error reading last update time: {e}")
    return None

# Asynchronous function to load leaderboard data from the latest JSON file.  Handles file not found and other exceptions.
async def load_leaderboard_data() -> Optional[Dict[str, Any]]:
    async with FILE_OP_SEMAPHORE:
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

# Define file paths using environment variables for flexibility and maintainability.
PATH_TO_LEADERBOARD_DATA = os.environ.get('PATH_TO_LEADERBOARD_DATA')
LEADERBOARDS_DIR = os.path.join(PATH_TO_LEADERBOARD_DATA, 'backend/leaderboards')
IN_TIME_DIR = os.path.join(LEADERBOARDS_DIR, 'in_time')
LEADERBOARD_LATEST = os.path.join(LEADERBOARDS_DIR, 'leaderboard-latest.json')
USERNAMES_PATH = os.path.join(PATH_TO_LEADERBOARD_DATA, 'backend/portfolios/usernames.txt')
SNAPSHOTS_DIR = "./snapshots"
SNAPSHOT_PATH = os.path.join(SNAPSHOTS_DIR, "leaderboard-snapshot.json")
MORNING_SNAPSHOT_PATH = os.path.join(SNAPSHOTS_DIR, "morning-snapshot.json")
LAST_UPDATE_FILE = os.path.join(SNAPSHOTS_DIR, "last_update.txt")

# Create necessary directories
os.makedirs(SNAPSHOTS_DIR, exist_ok=True)

# Initialize last update time functions
def save_last_update_time():
    try:
        os.makedirs(os.path.dirname(LAST_UPDATE_FILE), exist_ok=True)
        with open(LAST_UPDATE_FILE, 'w') as f:
            f.write(datetime.datetime.now(EST).isoformat())
    except Exception as e:
        print(f"Error saving last update time: {e}")
        traceback.print_exc()

def get_last_update_time():
    try:
        if os.path.exists(LAST_UPDATE_FILE):
            with open(LAST_UPDATE_FILE, 'r') as f:
                timestamp_str = f.read().strip()
                return datetime.datetime.fromisoformat(timestamp_str)
        # If file doesn't exist, create it with current time
        save_last_update_time()
        return datetime.datetime.now(EST)
    except Exception as e:
        print(f"Error reading last update time: {e}")
        # Return a timestamp from 30 minutes ago to trigger an update
        return datetime.datetime.now(EST) - datetime.timedelta(minutes=30)

# Set up Discord bot intents.  We need message content and guilds for this bot.
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

# Get the Discord bot token from environment variables.  Exit if not found.
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not DISCORD_BOT_TOKEN:
    print("Error: DISCORD_BOT_TOKEN is not set in the environment variables.")
    exit(1)

# Initialize the Discord bot with command prefix '$' and intents.
bot = commands.Bot(command_prefix="$", intents=intents)
print("Bot initialized with command prefix '$'")

# Define time zones for Eastern and Pacific Standard Time.
EST = timezone('US/Eastern')
PST = timezone('America/Los_Angeles')

# Add concurrency control constants after the timezone definitions
MAX_CONCURRENT_FILE_OPS = 3
MAX_CONCURRENT_API_CALLS = 5
FILE_OP_SEMAPHORE = Semaphore(MAX_CONCURRENT_FILE_OPS)
API_SEMAPHORE = Semaphore(MAX_CONCURRENT_API_CALLS)
TASK_QUEUE = deque()

# Add task management functions
async def queue_task(coro):
    task = asyncio.create_task(coro)
    TASK_QUEUE.append(task)
    await task
    TASK_QUEUE.remove(task)
    return await task

async def cleanup_tasks():
    while TASK_QUEUE:
        task = TASK_QUEUE.popleft()
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

# Function to extract and format user information from a Pandas DataFrame.
def get_user_info(df, username):
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

# Function to get the path to the latest leaderboard file in the 'in_time' directory.
def get_latest_in_time_leaderboard():
    files = [f for f in os.listdir(IN_TIME_DIR) if f.endswith(".json")]
    if not files:
        return None
    files.sort(key=lambda x: parse_leaderboard_timestamp(x))
    latest_file = files[-1]
    return os.path.join(IN_TIME_DIR, latest_file)

# Helper function to get the current time in PST.
def get_pst_time():
    return datetime.datetime.now(PST)

# Asynchronous function to compare stock holdings between the current and previous leaderboards and send updates to Discord.
async def compare_stock_changes(channel):
    try:
        with open(LEADERBOARD_LATEST, "r") as f:
            current_data = json.load(f)

        snapshot_path = SNAPSHOT_PATH
        if os.path.exists(snapshot_path):
            with open(snapshot_path, "r") as f:
                previous_data = json.load(f)

            for username in current_data:
                if username not in previous_data:
                    continue

                current_stocks = set(stock[0] for stock in current_data[username][2])
                previous_stocks = set(stock[0] for stock in previous_data[username][2])

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

        with open(snapshot_path, "w") as f:
            json.dump(current_data, f)

    except Exception as e:
        await channel.send(f"Error comparing stock changes: {str(e)}")
        import traceback
        traceback.print_exc()

# Load usernames from the usernames file.
with open(USERNAMES_PATH, "r") as f:
    usernames_list = [line.strip() for line in f.readlines()]

# Function to parse the timestamp from a leaderboard filename.
def parse_leaderboard_timestamp(filename):
    timestamp_str = filename[len('leaderboard-'):-len('.json')]
    return datetime.datetime.strptime(timestamp_str, '%Y-%m-%d-%H_%M')

#Custom cache class to store and retrieve data with a time-to-live (TTL).  This improves performance by caching expensive operations.
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

#Use the TimedCache to wrap the fetch_stock_data function, caching results for an hour.
@TimedCache(ttl=3600)
async def fetch_stock_data(symbol: str, start_date, end_date):
    async with API_SEMAPHORE:
        return await asyncio.to_thread(
            yf.download, 
            symbol, 
            start=start_date, 
            end=end_date, 
            progress=False
        )

# Function to generate a Plotly graph showing a user's account value over time, along with the S&P 500 for comparison.
def generate_money_graph(username):
    try:
        files = sorted([f for f in os.scandir(IN_TIME_DIR) if f.name.endswith('.json')],
                      key=lambda x: parse_leaderboard_timestamp(x.name))

        data = {'timestamp': [], username: []}
        for file in files:
            try:
                with open(file.path) as f:
                    file_data = json.load(f)
                if username in file_data:
                    timestamp = parse_leaderboard_timestamp(file.name)
                    if timestamp.tzinfo is None:
                        timestamp = timestamp.replace(tzinfo=datetime.timezone.utc)
                    data['timestamp'].append(timestamp)
                    data[username].append(float(file_data[username][0]))
            except Exception as e:
                print(f"Error reading file {file.name}: {e}")

        if not data['timestamp']:
            return None, None, None

        start_date = min(data['timestamp'])
        end_date = max(data['timestamp'])

        try:
            spy_data = fetch_stock_data("SPY", start_date, end_date)
            if not spy_data.empty:
                initial_spy = spy_data['Close'].iloc[0]
                spy_values = spy_data['Close'] * (100000 / initial_spy)

                if spy_data.index.tz is None:
                    spy_data.index = spy_data.index.tz_localize('UTC')
            else:
                spy_values = None
                spy_data = None
        except Exception as e:
            print(f"Error fetching S&P 500 data: {e}")
            spy_values = None
            spy_data = None

        fig = go.Figure()

        fig.add_trace(
            go.Scatter(
                x=data['timestamp'],
                y=data[username],
                name=username,
                line=dict(color='rgb(0, 100, 255)', width=2.5),
                mode='lines+markers',
                marker=dict(size=6)
            )
        )

        if spy_values is not None and not spy_data.empty:
            fig.add_trace(
                go.Scatter(
                    x=spy_data.index,
                    y=spy_values,
                    name='S&P 500 ($100k invested)',
                    line=dict(color='gray', dash='dash'),
                    opacity=0.5
                )
            )

        values = data[username]
        lowest_value = min(values)
        highest_value = max(values)

        fig.add_trace(
            go.Scatter(
                x=[data['timestamp'][values.index(lowest_value)]],
                y=[lowest_value],
                mode='markers+text',
                name='Lowest',
                marker=dict(color='red', size=12),
                text=[f'${lowest_value:,.2f}'],
                textposition='top center'
            )
        )

        fig.add_trace(
            go.Scatter(
                x=[data['timestamp'][values.index(highest_value)]],
                y=[highest_value],
                mode='markers+text',
                name='Highest',
                marker=dict(color='green', size=12),
                text=[f'${highest_value:,.2f}'],
                textposition='top center'
            )
        )

        fig.update_layout(
            title=dict(
                text=f"Account Value Over Time - {username}",
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

        fig.update_yaxes(tickprefix="$", tickformat=",.0f")
        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128, 128, 128, 0.2)')
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128, 128, 128, 0.2)')

        buf = io.BytesIO()
        fig.write_image(buf, format='png', engine='kaleido')
        buf.seek(0)

        return buf, lowest_value, highest_value
    except Exception as e:
        print(f"Error generating money graph: {e}")
        return None, None, None

# Function to determine the embed color based on a testing flag.
def get_embed_color():
    testing = os.environ.get('TESTING', 'false').lower() == 'true'
    return 0xFF69B4 if testing else 0x0000FF

#Cog to handle user information related commands.
class UserInfo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    #Slash command to get user information.  Uses autocompletion for usernames.
    @app_commands.command(name="userinfo", description="Get user information")
    @app_commands.describe(username="Select a username")
    async def userinfo(self, interaction: discord.Interaction, username: str):
        try:
            await interaction.response.defer(thinking=True)
        except Exception as e:
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
                await interaction.followup.send(embed=embed)

        except Exception as e:
            print(f"Error in userinfo command: {e}")
            await interaction.followup.send(f"Error fetching user info: {str(e)}")

    #Autocomplete function for the username parameter of the /userinfo command.
    @userinfo.autocomplete("username")
    async def username_autocomplete(
        self, interaction: discord.Interaction, current: str
    ):
        return [
            app_commands.Choice(name=username, value=username)
            for username in usernames_list
            if current.lower() in username.lower()
        ][:25]

# Function to add the UserInfo cog to the bot.
async def setup(bot):
    await bot.add_cog(UserInfo(bot))

# Function to run setup when the bot is ready.
async def setup_hook():
    await setup(bot)
    print("Setup hook executed")

bot.setup_hook = setup_hook

# Function to generate a Plotly graph showing the top 10 users' performance over time.
def generate_leaderboard_graph(top_users_data):
    files = sorted([f for f in os.scandir(IN_TIME_DIR) if f.name.endswith('.json')],
                  key=lambda x: parse_leaderboard_timestamp(x.name))

    if not files:
        return None

    usernames = top_users_data['Account Name'].tolist()

    data = {
        'timestamp': [],
        **{username: [] for username in usernames}
    }

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

    fig = go.Figure()

    colors = px.colors.qualitative.Set3
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

    fig.update_yaxes(tickprefix="$", tickformat=",.0f")
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128, 128, 128, 0.2)')
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128, 128, 128, 0.2)')

    buf = io.BytesIO()
    fig.write_image(buf, format='png', engine='kaleido')
    buf.seek(0)

    return buf

#Slash command to display the current leaderboard. Includes a graph of top 5 users' performance.
@bot.tree.command(name="leaderboard", description="Get current leaderboard")
async def leaderboard(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        current_data = await load_leaderboard_data()
        if not current_data:
            await interaction.followup.send("Error loading leaderboard data")
            return

        df = pd.DataFrame.from_dict(current_data, orient="index")
        df.reset_index(inplace=True)
        df.columns = ["Account Name", "Money In Account", "Investopedia Link", "Stocks Invested In"]
        df.sort_values(by="Money In Account", ascending=False, inplace=True)

        top_users = df.head(5)
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

#Function to compare previous and current leaderboard data to determine if the top 5 rankings have changed.
def have_rankings_changed(previous_data, current_data):
    if not previous_data or not current_data:
        return True

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

    prev_names = [name for name, _ in prev_rankings]
    curr_names = [name for name, _ in curr_rankings]

    return prev_names != curr_names

#Background task to send leaderboard updates every minute.  Checks for market open/close and ranking changes.
@tasks.loop(minutes=1)
async def send_leaderboard():
    try:
        now = datetime.datetime.now(EST)
        
        # Skip weekends
        if now.weekday() >= 5:
            return

        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)

        # Only proceed during market hours
        if not (market_open <= now <= market_close):
            return

        # Check if it's market open or close (within 1 minute)
        is_market_open = abs((now - market_open).total_seconds()) < 60
        is_market_close = abs((now - market_close).total_seconds()) < 60
        
        # Check if 30 minutes have passed since last update
        last_update = get_last_update_time()
        thirty_mins_passed = (last_update is None or 
                            (now - last_update).total_seconds() >= 1800)

        # Only proceed if one of our conditions is met
        if not (is_market_open or is_market_close or thirty_mins_passed):
            return

        # Rest of the leaderboard update logic
        current_data = await load_leaderboard_data()
        if not current_data:
            return

        leaderboard_channel = bot.get_channel(int(os.environ.get("DISCORD_CHANNEL_ID_Leaderboard")))
        if not leaderboard_channel:
            return

        permissions = leaderboard_channel.permissions_for(leaderboard_channel.guild.me)
        if not permissions.send_messages or not permissions.embed_links:
            return

        df = pd.DataFrame.from_dict(current_data, orient="index")
        df.reset_index(inplace=True)
        df.columns = ["Account Name", "Money In Account", "Investopedia Link", "Stocks Invested In"]
        df.sort_values(by="Money In Account", ascending=False, inplace=True)

        top_users = df.head(5)
        description = ""
        for idx, row in enumerate(top_users.iterrows(), 1):
            _, row = row
            money = float(row['Money In Account'])
            description += f"**#{idx} - {row['Account Name']}**\n"
            description += f"Money: ${money:,.2f}\n\n"

        embed = discord.Embed(
            colour=get_embed_color(),
            title="📊 Leaderboard Update",
            description=description,
            timestamp=get_pst_time(),
        )

        if is_market_open:
            embed.set_footer(text="Market Open Update")
        elif is_market_close:
            embed.set_footer(text="Market Close Update")
        else:
            embed.set_footer(text="30 Minute Update")

        graph_buffer = generate_leaderboard_graph(top_users)
        if graph_buffer:
            file = discord.File(graph_buffer, filename="leaderboard_graph.png")
            embed.set_image(url="attachment://leaderboard_graph.png")
            await leaderboard_channel.send(embed=embed, file=file)
            save_last_update_time()  # Update the timestamp after successful send

        # Also trigger stock changes check
        await compare_stock_changes(leaderboard_channel)

    except Exception as e:
        print(f"Error in send_leaderboard task: {str(e)}")
        traceback.print_exc()

#Background task to create a snapshot of the leaderboard at the start of each trading day (9:30 AM EST).
@tasks.loop(time=datetime.time(hour=9, minute=30, tzinfo=EST))
async def start_of_day():
    now = datetime.datetime.now(EST)
    if now.weekday() < 5:  # Only run on weekdays
        async with FILE_OP_SEMAPHORE:
            try:
                current_data = await load_leaderboard_data()
                if current_data:
                    async with aiofiles.open(MORNING_SNAPSHOT_PATH, 'w') as f:
                        await f.write(json.dumps(current_data))
                    print(f"Created morning snapshot at {now}")
            except Exception as e:
                print(f"Error creating morning snapshot: {e}")
                import traceback
                traceback.print_exc()

@start_of_day.before_loop
async def before_start_of_day():
    await bot.wait_until_ready()

#Background task to send a daily summary at the end of the trading day (4:00 PM EST).  Compares the morning snapshot to the end-of-day data.
@tasks.loop(time=datetime.time(hour=16, minute=0, tzinfo=EST))
async def send_daily_summary():
    now = datetime.datetime.now(EST)
    if now.weekday() >= 5:  # Skip weekends
        return

    try:
        # Check if morning snapshot exists and load it
        if not os.path.exists(MORNING_SNAPSHOT_PATH):
            print("No morning snapshot found, skipping daily summary")
            return

        async with aiofiles.open(MORNING_SNAPSHOT_PATH, 'r') as f:
            content = await f.read()
            morning_data = json.loads(content)

        current_data = await load_leaderboard_data()
        if not current_data:
            print("No current data available, skipping daily summary")
            return

        # Calculate stats only if we have both morning and current data
        stats = calculate_daily_performance(morning_data, current_data)

        # Only send summary if there are actual changes
        if stats["total_trades"] > 0 or any(p["change_amount"] != 0 for p in stats["performance"]):
            channel = bot.get_channel(int(os.environ.get("DISCORD_CHANNEL_ID_Leaderboard")))
            if not channel:
                print("Could not find leaderboard channel")
                return

            embed = discord.Embed(
                colour=get_embed_color(),
                title="📊 End of Day Trading Summary",
                description=f"Market Close Summary for {now.strftime('%A, %B %d, %Y')}",
                timestamp=get_pst_time(),
            )

            # Only add fields if there's meaningful data
            embed.add_field(
                name="📈 Market Activity",
                value=f"Total Trades Today: {stats['total_trades']}\n",
                inline=False,
            )

            if stats["performance"]:
                top_text = "\n".join(
                    [
                        f"**{p['username']}**: {p['change_percent']:+.2f}% (${p['change_amount']:,.2f}) - {p['trades']} trades"
                        for p in stats["performance"][:3]
                        if abs(p["change_percent"]) > 0.01 or p["trades"] > 0
                    ]
                )
                if top_text:
                    embed.add_field(name="🏆 Top Performers", value=top_text, inline=False)

                bottom_text = "\n".join(
                    [
                        f"**{p['username']}**: {p['change_percent']:+.2f}% (${p['change_amount']:,.2f}) - {p['trades']} trades"
                        for p in stats["performance"][-3:]
                        if abs(p["change_percent"]) > 0.01 or p["trades"] > 0
                    ]
                )
                if bottom_text:
                    embed.add_field(name="📉 Needs Improvement", value=bottom_text, inline=False)

            if stats["biggest_gain"]["username"] and abs(stats["biggest_gain"]["percent"]) > 0.01:
                embed.add_field(
                    name="🚀 Biggest Gain",
                    value=f"**{stats['biggest_gain']['username']}**\n{stats['biggest_gain']['percent']:+.2f}% (${stats['biggest_gain']['amount']:,.2f})",
                    inline=True,
                )

            if stats["biggest_loss"]["username"] and abs(stats["biggest_loss"]["percent"]) > 0.01:
                embed.add_field(
                    name="💥 Biggest Loss",
                    value=f"**{stats['biggest_loss']['username']}**\n{stats['biggest_loss']['percent']:+.2f}% (${stats['biggest_loss']['amount']:,.2f})",
                    inline=True,
                )

            active_text = "\n".join(
                [f"**{p['username']}**: {p['trades']} trades" for p in stats["most_active"] if p["trades"] > 0]
            )
            if active_text:
                embed.add_field(name="⚡ Most Active Traders", value=active_text, inline=False)

            if len(embed.fields) > 1:  # Only send if there's meaningful data
                await channel.send(embed=embed)
            else:
                print("No meaningful changes to report in daily summary")

        # Clean up the morning snapshot after sending the summary
        try:
            os.remove(MORNING_SNAPSHOT_PATH)
            print("Removed morning snapshot file")
        except Exception as e:
            print(f"Error removing morning snapshot: {e}")

    except Exception as e:
        print(f"Error in send_daily_summary: {e}")
        import traceback
        traceback.print_exc()

#Before loop function for the send_daily_summary task to ensure the bot is ready before starting the task.
@send_daily_summary.before_loop
async def before_daily_summary():
    await bot.wait_until_ready()

#Asynchronous function to create a snapshot of the leaderboard data at the beginning of the day.
async def create_morning_snapshot():
    try:
        with open(LEADERBOARD_LATEST, "r") as f:
            data = json.load(f)

        with open(MORNING_SNAPSHOT_PATH, "w") as f:
            json.dump(data, f)

    except Exception as e:
        print(f"Error creating morning snapshot: {e}")

#Function to calculate various daily performance metrics (top/bottom performers, biggest gain/loss, most active traders).
def calculate_daily_performance(morning_data, current_data):
    stats = {
        "performance": [],
        "most_active": [],
        "biggest_gain": {"username": None, "amount": 0, "percent": 0},
        "biggest_loss": {"username": None, "amount": 0, "percent": 0},
        "total_trades": 0
    }

    for username in current_data:
        if username not in morning_data:
            continue

        morning_value = float(morning_data[username][0])
        current_value = float(current_data[username][0])

        change_amount = current_value - morning_value
        change_percent = (change_amount / morning_value) * 100 if morning_value != 0 else 0

        morning_stocks = set(stock[0] for stock in morning_data[username][2])
        current_stocks = set(stock[0] for stock in current_data[username][2])
        trades = len(morning_stocks.symmetric_difference(current_stocks))
        stats["total_trades"] += trades

        stats["performance"].append({
            "username": username,
            "change_amount": change_amount,
            "change_percent": change_percent,
            "trades": trades
        })

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

        if trades > 0:
            stats["most_active"].append({
                "username": username,
                "trades": trades
            })

    stats["performance"].sort(key=lambda x: x["change_percent"], reverse=True)
    stats["most_active"].sort(key=lambda x: x["trades"], reverse=True)
    stats["most_active"] = stats["most_active"][:3]

    return stats

#Import aiofiles library for asynchronous file I/O operations.
import aiofiles

#Function to load leaderboard data asynchronously, handling potential errors.
async def load_leaderboard_data() -> Optional[Dict[str, Any]]:
    async with FILE_OP_SEMAPHORE:
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


#Function to check if the top 5 rankings have changed between two leaderboard datasets.
def have_rankings_changed(previous_data, current_data):
    if not previous_data or not current_data:
        return True

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

    prev_names = [name for name, _ in prev_rankings]
    curr_names = [name for name, _ in curr_rankings]

    return prev_names != curr_names

#Event handler for when the bot is ready.  Starts background tasks and syncs slash commands.  Handles potential errors during startup.
@bot.event
async def on_ready():
    try:
        os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
        
        # Register cleanup for graceful shutdown
        bot.loop.create_task(cleanup_tasks())
        
        # Start background tasks
        send_leaderboard.start()
        start_of_day.start()
        send_daily_summary.start()

        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")

    except Exception as e:
        print(f"Error in on_ready: {e}")
        traceback.print_exc()

#Run the bot.  Handles potential errors during bot execution.
try:
    bot.run(DISCORD_BOT_TOKEN)
except Exception as e:
    print(f"Error running the bot: {e}")
    import traceback
    traceback.print_exc()

# Add graceful shutdown handler
async def close_bot():
    print("Shutting down bot...")
    await cleanup_tasks()
    await bot.close()

# Update the main bot run with graceful shutdown
if __name__ == "__main__":
    try:
        bot.run(DISCORD_BOT_TOKEN)
    except KeyboardInterrupt:
        asyncio.run(close_bot())
    except Exception as e:
        print(f"Error running the bot: {e}")
        traceback.print_exc()

# ...existing code...

# Add after the other constant definitions
LAST_LEADERBOARD_UPDATE = None

# Replace the send_leaderboard task with this updated version
@tasks.loop(minutes=1)
async def send_leaderboard():
    try:
        global LAST_LEADERBOARD_UPDATE
        now = datetime.datetime.now(EST)
        
        # Skip weekends
        if now.weekday() >= 5:
            return

        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)

        # Only proceed during market hours
        if not (market_open <= now <= market_close):
            return

        # Check if it's market open or close (within 1 minute)
        is_market_open = abs((now - market_open).total_seconds()) < 60
        is_market_close = abs((now - market_close).total_seconds()) < 60
        
        # Check if 30 minutes have passed since last update
        thirty_mins_passed = (LAST_LEADERBOARD_UPDATE is None or 
                            (now - LAST_LEADERBOARD_UPDATE).total_seconds() >= 1800)

        # Only proceed if one of our conditions is met
        if not (is_market_open or is_market_close or thirty_mins_passed):
            return

        # Rest of the leaderboard update logic
        current_data = await load_leaderboard_data()
        if not current_data:
            return

        leaderboard_channel = bot.get_channel(int(os.environ.get("DISCORD_CHANNEL_ID_Leaderboard")))
        if not leaderboard_channel:
            return

        permissions = leaderboard_channel.permissions_for(leaderboard_channel.guild.me)
        if not permissions.send_messages or not permissions.embed_links:
            return

        df = pd.DataFrame.from_dict(current_data, orient="index")
        df.reset_index(inplace=True)
        df.columns = ["Account Name", "Money In Account", "Investopedia Link", "Stocks Invested In"]
        df.sort_values(by="Money In Account", ascending=False, inplace=True)

        top_users = df.head(5)
        description = ""
        for idx, row in enumerate(top_users.iterrows(), 1):
            _, row = row
            money = float(row['Money In Account'])
            description += f"**#{idx} - {row['Account Name']}**\n"
            description += f"Money: ${money:,.2f}\n\n"

        embed = discord.Embed(
            colour=get_embed_color(),
            title="📊 Leaderboard Update",
            description=description,
            timestamp=get_pst_time(),
        )

        if is_market_open:
            embed.set_footer(text="Market Open Update")
        elif is_market_close:
            embed.set_footer(text="Market Close Update")
        else:
            embed.set_footer(text="30 Minute Update")

        graph_buffer = generate_leaderboard_graph(top_users)
        if graph_buffer:
            file = discord.File(graph_buffer, filename="leaderboard_graph.png")
            embed.set_image(url="attachment://leaderboard_graph.png")
            await leaderboard_channel.send(embed=embed, file=file)
            LAST_LEADERBOARD_UPDATE = now  # Update the timestamp after successful send

    except Exception as e:
        print(f"Error in send_leaderboard task: {str(e)}")
        traceback.print_exc()

# Update on_ready to remove initial leaderboard
@bot.event
async def on_ready():
    try:
        os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
        
        # Register cleanup for graceful shutdown
        bot.loop.create_task(cleanup_tasks())
        
        # Start background tasks
        send_leaderboard.start()
        start_of_day.start()
        send_daily_summary.start()

        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")

    except Exception as e:
        print(f"Error in on_ready: {e}")
        traceback.print_exc()

# Remove the send_initial_leaderboard function as it's no longer needed

# Update constants section
LAST_UPDATE_FILE = os.path.join(SNAPSHOTS_DIR, "last_update.txt")

def save_last_update_time():
    try:
        with open(LAST_UPDATE_FILE, 'w') as f:
            f.write(datetime.datetime.now(EST).isoformat())
    except Exception as e:
        print(f"Error saving last update time: {e}")

def get_last_update_time():
    try:
        if os.path.exists(LAST_UPDATE_FILE):
            with open(LAST_UPDATE_FILE, 'r') as f:
                timestamp_str = f.read().strip()
                return datetime.datetime.fromisoformat(timestamp_str)
    except Exception as e:
        print(f"Error reading last update time: {e}")
    return None

# Replace the send_leaderboard task
@tasks.loop(minutes=1)
async def send_leaderboard():
    try:
        now = datetime.datetime.now(EST)
        
        # Skip weekends
        if now.weekday() >= 5:
            return

        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)

        # Only proceed during market hours
        if not (market_open <= now <= market_close):
            return

        # Check if it's market open or close (within 1 minute)
        is_market_open = abs((now - market_open).total_seconds()) < 60
        is_market_close = abs((now - market_close).total_seconds()) < 60
        
        # Check if 30 minutes have passed since last update
        last_update = get_last_update_time()
        thirty_mins_passed = (last_update is None or 
                            (now - last_update).total_seconds() >= 1800)

        # Only proceed if one of our conditions is met
        if not (is_market_open or is_market_close or thirty_mins_passed):
            return

        # Rest of the leaderboard update logic...
        # ...existing leaderboard update code...

        # After successfully sending the update, save the timestamp
        save_last_update_time()

    except Exception as e:
        print(f"Error in send_leaderboard task: {str(e)}")
        traceback.print_exc()

# Update on_ready to ensure snapshots directory exists
@bot.event
async def on_ready():
    try:
        os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
        
        # Register cleanup for graceful shutdown
        bot.loop.create_task(cleanup_tasks())
        
        # Start background tasks
        send_leaderboard.start()
        start_of_day.start()
        send_daily_summary.start()

        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")

    except Exception as e:
        print(f"Error in on_ready: {e}")
        traceback.print_exc()

