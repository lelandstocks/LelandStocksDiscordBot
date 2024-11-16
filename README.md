# Leland Stocks Discord Bot

Leland Stocks Discord Bot is a Discord bot designed to provide real-time stock portfolio updates and leaderboard rankings for users participating in a simulated stock trading environment. The bot fetches data from Investopedia and displays it in a user-friendly format within a Discord server.

## Features

- **User Information**: Retrieve and display detailed information about a user's stock portfolio.
- **Leaderboard**: Display the top users based on their portfolio value.
- **Stock Changes**: Notify users of any changes in their stock holdings.
- **Daily Summary**: Provide a summary of the day's trading activity, including top performers and most active traders.
- **Scheduled Updates**: Automatically send updates during trading hours.

## Setup Instructions

### Prerequisites

- Python 3.8+
- Discord account and server
- Investopedia account
- Environment variables set up in a `.env` file

## 🔧 Configuration

### Environment Variables
- `DISCORD_BOT_TOKEN` - Your Discord bot token
- `DISCORD_CHANNEL_ID_Leaderboard` - Channel ID for leaderboard updates
- `DISCORD_CHANNEL_ID_Stocks` - Channel ID for stock change notifications

### Trading Hours
- Market Open: 9:30 AM EST
- Market Close: 4:00 PM EST
- Updates: Every minute during trading hours

## 🤝 Contributing
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 🐛 Bug Reports
If you find a bug, please open an issue with:
- Detailed description of the bug
- Steps to reproduce
- Expected behavior
- Screenshots (if applicable)

## 🌟 Acknowledgements
- [Discord.py](https://discordpy.readthedocs.io/en/stable/) - Discord API wrapper
- [Pandas](https://pandas.pydata.org/) - Data manipulation
- [Investopedia](https://www.investopedia.com/) - Stock trading simulation
- [python-dotenv](https://pypi.org/project/python-dotenv/) - Environment variable management