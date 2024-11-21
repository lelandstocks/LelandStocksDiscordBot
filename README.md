# 🌟 Leland Stocks Discord Bot 🚀

Leland Stocks Discord Bot is a powerful and user-friendly Discord bot designed to provide **real-time stock portfolio updates** and **leaderboard rankings** for users in a simulated stock trading environment. 🏦📈 The bot fetches data from **Investopedia** and delivers it directly to your Discord server with style! 🎉

---

## ✨ Features

- **📊 User Information**: Access detailed stock portfolio data for any user.
- **🏆 Leaderboard**: See the top traders ranked by their portfolio value.
- **🔔 Stock Changes**: Get notified about changes in your stock holdings.
- **📅 Daily Summary**: Receive a daily update featuring top performers and the most active traders.
- **⏰ Scheduled Updates**: Enjoy automatic updates during trading hours.
- **📈 Performance Graphs**: Visualize user performance with dynamic money graphs.
- **🛠 Automated Updates**: The bot fetches the latest leaderboard and stock data automatically.

---

## 🛠️ Setup Instructions

### 📋 Prerequisites

- 🐍 **Python 3.8+**
- 🤖 **Discord account and server**
- 📚 **Investopedia account**
- 🗂️ **Environment variables** stored in a `.env` file

### 🔧 Setup

1. **Clone the repository with submodules**:
    ```bash
    git clone --recursive https://github.com/lelandstocks/LelandStocksDiscordBot.git
    ```

2. **Install dependencies**:
    Ensure you are in the project directory, and then install the required Python packages:
    ```bash
    pip install -r requirements.txt
    ```

3. **Configure environment variables**:
    Create a `.env` file in the project root and add the following variables:
    ```bash
    DISCORD_BOT_TOKEN=your_discord_bot_token
    DISCORD_CHANNEL_ID_Leaderboard=your_leaderboard_channel_id
    DISCORD_CHANNEL_ID_Stocks=your_stocks_channel_id
    PATH_TO_LEADERBOARD_DATA=your_leaderboard_data_path
    TESTING=false  # Set to true for testing mode
    ```

4. **Run the bot**:
    Start the bot with the following command:
    ```bash
    python bot.py
    ```

5. **Automate with a script**:
    You can use the provided `run.sh` script to automatically fetch updates and restart the bot as needed:
    ```bash
    bash run.sh
    ```

---

## 🤝 Contributing

We ❤️ contributions! Follow these steps to contribute:

1. **Fork the repository** 🍴
2. **Create a feature branch**: `git checkout -b feature/AmazingFeature`  
3. **Commit your changes**: `git commit -m 'Add some AmazingFeature'`  
4. **Push to the branch**: `git push origin feature/AmazingFeature`  
5. **Open a Pull Request** 🔄

---

## 🐛 Bug Reports

Found a bug? 🐞 Let us know by opening an issue with:

- **Description**: Clear explanation of the bug.
- **Steps to Reproduce**: How to recreate the issue.
- **Expected Behavior**: What should happen.
- **Screenshots**: (if applicable) 📸

---

## 🌟 Acknowledgements

A huge shoutout to these amazing tools and resources:

- 🛠️ [Discord.py](https://discordpy.readthedocs.io/en/stable/) - Discord API wrapper  
- 📈 [Pandas](https://pandas.pydata.org/) - Data manipulation powerhouse  
- 📚 [Investopedia](https://www.investopedia.com/) - Stock trading simulation platform  
- 🌱 [python-dotenv](https://pypi.org/project/python-dotenv/) - Easy environment variable management  

---

Bring stock trading excitement to your Discord server today! 🌟✨