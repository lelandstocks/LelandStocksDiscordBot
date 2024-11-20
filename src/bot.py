import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import os
import json
import pandas as pd
from pytz import timezone
from dotenv import load_dotenv
import matplotlib.pyplot as plt
import io
# Add yfinance import
import yfinance as yf

# Load environment variables from .env file
load_dotenv()

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

# Initialize bot instance with command prefix
bot = commands.Bot(command_prefix="$", intents=intents)


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
    return datetime.datetime.now(timezone("America/Los_Angeles"))


async def compare_stock_changes(channel):
    """
    Compare current leaderboard with snapshot to detect stock changes, and send updates to the Discord channel as embeds.
    """
    try:
        # Load the snapshot file
        snapshot_path = "./snapshots/leaderboard-snapshot.json"
        if not os.path.exists(snapshot_path):
            # If snapshot doesn't exist, create it and return
            with open(LEADERBOARD_LATEST, "r") as f:
                current_data = json.load(f)
            with open(snapshot_path, "w") as f:
                json.dump(current_data, f)
            return

        # Load both snapshot and current data
        with open(snapshot_path, "r") as f:
            previous_data = json.load(f)
        with open(LEADERBOARD_LATEST, "r") as f:
            current_data = json.load(f)
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
                await channel.send(embed=embed)

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


def generate_money_graph(username):
    """Generate a graph showing money over time for a user"""
    import numpy as np
    
    # Get all files from in_time directory and sort them by datetime
    files = [f for f in os.listdir(IN_TIME_DIR) if f.endswith('.json')]
    files.sort(key=lambda x: parse_leaderboard_timestamp(x))
    
    if not files:
        return None, None, None

    # Get start and end dates
    start_date = parse_leaderboard_timestamp(files[0])
    end_date = parse_leaderboard_timestamp(files[-1])
    
    # Fetch S&P 500 data starting from August 13th
    try:
        spy_start_date = datetime.datetime(2024, 8, 13)
        spy = yf.download('^GSPC', start=spy_start_date, end=end_date, progress=False)
        # Calculate what $100k would be worth based on S&P 500 performance
        initial_spy_price = spy['Close'].iloc[0]
        spy_returns = spy['Close'] / initial_spy_price
        spy_values = 100000 * spy_returns
        # Convert user's timestamps to timezone-aware
        start_date = start_date.replace(tzinfo=spy.index.tz)
        end_date = end_date.replace(tzinfo=spy.index.tz)
        # Filter S&P 500 data to match the user's date range
        spy = spy.loc[start_date:end_date]
        spy_values = spy_values.loc[start_date:end_date]
    except Exception as e:
        print(f"Error fetching S&P 500 data: {e}")
        spy_values = None
    
    # Create DataFrame to store data
    data = {
        'timestamp': [],
        username: [],  # Target user
    }
    
    # Collect data for user
    for file in files:
        try:
            with open(os.path.join(IN_TIME_DIR, file), 'r') as f:
                file_data = json.load(f)
                timestamp = parse_leaderboard_timestamp(file)
                
                if username not in file_data:
                    continue
                
                # Append data
                data['timestamp'].append(timestamp.replace(tzinfo=spy.index.tz))
                data[username].append(float(file_data[username][0]))
                
        except Exception as e:
            print(f"Error reading file {file}: {e}")
            continue
    
    if not data['timestamp']:
        return None, None, None
    
    # Plotting
    plt.style.use('default')
    plt.figure(figsize=(12, 6))
    
    # Plot S&P 500 if data is available
    if spy_values is not None:
        plt.plot(spy.index, spy_values, 
                color='gray', linewidth=1.5, alpha=0.5, 
                label='S&P 500 ($100k invested)', linestyle='--')
    
    # Plot target user
    plt.plot(data['timestamp'], data[username],
             color='blue', linewidth=2.5, alpha=0.8,
             marker='o', markersize=5,
             label=f"{username}")
    
    # Find extreme values for the user
    lowest_value = min(data[username])
    highest_value = max(data[username])
    lowest_idx = data[username].index(lowest_value)
    highest_idx = data[username].index(highest_value)
    lowest_timestamp = data['timestamp'][lowest_idx]
    highest_timestamp = data['timestamp'][highest_idx]
    
    # Customize the plot
    plt.title(f"Account Value Over Time - {username}", 
              loc='left', fontsize=12, fontweight='bold')
    plt.xlabel("Time")
    plt.ylabel("Account Value ($)")
    plt.grid(True, alpha=0.2)
    plt.xticks(rotation=45)
    
    # Add annotations for final values
    last_timestamp = data['timestamp'][-1]
    final_value = data[username][-1]
    plt.text(last_timestamp, final_value, 
            f' Current\n ${final_value:,.2f}', 
            verticalalignment='center', fontsize=8)
    
    # Add annotation for S&P 500 if available
    if spy_values is not None:
        final_spy_value = float(spy_values.iloc[-1].item())  # Proper float conversion
        plt.text(spy.index[-1], final_spy_value, 
                f' S&P 500\n ${final_spy_value:,.2f}', 
                verticalalignment='center', fontsize=8)
    
    # Plot and annotate extreme points
    plt.scatter([lowest_timestamp], [lowest_value], color='red', zorder=5, s=100)
    plt.scatter([highest_timestamp], [highest_value], color='green', zorder=5, s=100)
    
    for value, timestamp, color, label in [
        (lowest_value, lowest_timestamp, 'red', 'Lowest'),
        (highest_value, highest_timestamp, 'green', 'Highest')
    ]:
        plt.annotate(
            f'{label}: ${value:,.2f}',
            xy=(timestamp, value),
            xytext=(10, -20 if label == 'Lowest' else 20),
            textcoords='offset points',
            ha='left',
            color=color,
            fontweight='bold',
            bbox=dict(facecolor='white', edgecolor=color, alpha=0.7, pad=2)
        )
    
    plt.legend(loc='upper left', frameon=True, facecolor='white', edgecolor='none')
    plt.tight_layout()
    
    # Save plot to bytes buffer
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100, bbox_inches='tight', facecolor='white')
    buf.seek(0)
    plt.close()
    
    return buf, lowest_value, highest_value

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


bot.setup_hook = setup_hook


@bot.tree.command(name="leaderboard", description="Get current leaderboard")
@app_commands.describe(count="Number of top users to display (default: 1)")
async def leaderboard(interaction: discord.Interaction, count: int = 1):
    """
    Respond to the /leaderboard command with the top N users' info.
    """
    await interaction.response.defer()
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
        df.sort_values(by="Money In Account", ascending=False, inplace=True)

        # Limit count to be between 1 and 10
        count = max(1, min(count, 10))

        description = ""
        for i in range(min(count, len(df))):
            user_name, user_money, user_stocks = get_user_info(
                df, df.iloc[i]["Account Name"]
            )
            description += f"**#{i+1} - {user_name}**\n"
            description += f"Money: {user_money}\n"
            description += f"Holdings:\n{user_stocks}\n\n"

        embed = discord.Embed(
            colour=get_embed_color(),  # Changed this line
            title="Current Leaderboard",
            description=description,
            timestamp=get_pst_time(),
        )
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"Error fetching leaderboard: {str(e)}")


def have_rankings_changed(previous_data, current_data):
    """
    Compare previous and current data to check if rankings have changed.
    Returns True if rankings changed, False otherwise.
    """
    if not previous_data or not current_data:
        return True
    
    # Convert both datasets into sorted lists of (username, money) tuples
    prev_rankings = [(name, float(data[0])) for name, data in previous_data.items()]
    curr_rankings = [(name, float(data[0])) for name, data in current_data.items()]
    
    # Sort by money in descending order
    prev_rankings.sort(key=lambda x: x[1], reverse=True)
    curr_rankings.sort(key=lambda x: x[1], reverse=True)
    
    # Compare top 10 rankings
    return prev_rankings[:10] != curr_rankings[:10]

@tasks.loop(minutes=1)
async def send_leaderboard():
    """
    Send leaderboard updates only at market open/close or when rankings change.
    """
    now = datetime.datetime.now(timezone("US/Eastern"))
    if now.weekday() >= 5:  # Skip weekends
        return
        
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    
    # Only proceed during market hours
    if not (market_open <= now <= market_close):
        return
        
    try:
        # Load current data
        with open(LEADERBOARD_LATEST, "r") as file:
            current_data = json.load(file)
            
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
            top_users = df.head(10)
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
                
                # Add reason for update
                if is_market_open:
                    embed.set_footer(text="Market Open Update")
                elif is_market_close:
                    embed.set_footer(text="Market Close Update")
                elif rankings_changed:
                    embed.set_footer(text="Rankings Changed")
                    
                await leaderboard_channel.send(embed=embed)
            
            # Update snapshot after sending
            with open(snapshot_path, "w") as f:
                json.dump(current_data, f)
                
    except Exception as e:
        print(f"Error in send_leaderboard: {str(e)}")


@tasks.loop(time=datetime.time(hour=9, minute=30, tzinfo=timezone("US/Eastern")))
async def start_of_day():
    """Create snapshot at market open"""
    now = datetime.datetime.now(timezone("US/Eastern"))
    if now.weekday() < 5:  # Only on weekdays
        await create_morning_snapshot()


@tasks.loop(time=datetime.time(hour=16, minute=0, tzinfo=timezone("US/Eastern")))
async def send_daily_summary():
    """Send daily summary comparing start of day to end of day"""
    now = datetime.datetime.now(timezone("US/Eastern"))
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
            with open(LEADERBOARD_LATEST, "r") as f:
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
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
        # Start all scheduled tasks
        send_leaderboard.start()
        start_of_day.start()
        send_daily_summary.start()
    except Exception as e:
        print(f"Failed to sync commands: {e}")


# Run the bot with the provided token from environment variables
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
bot.run(DISCORD_BOT_TOKEN)