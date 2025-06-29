# godly Telegram Referral Bot

A production-ready Telegram bot for referral-based subscriptions, built with python-telegram-bot, MongoDB, and pydantic.

## Features

- Secure config via `.env` and `pydantic`
- All referral logic normalized by user_id
- Robust admin and user notifications
- Monthly referral payout reporting
- MongoDB indexes for performance
- Command-based menu for multi-language support
- Rich logging for development
- Unit tests with pytest

## Setup

1. Clone the repo and `cd` into the folder.
2. Create a `.env` file with:
    ```
    BOT_TOKEN=your-telegram-bot-token
    ADMIN_CHAT_ID=your-admin-chat-id
    MONGO_URI=your-mongodb-uri
    MONGO_DB_NAME=your-db-name
    ```
3. Install dependencies:
    ```
    pip install -r requirements.txt
    ```
4. Run the bot:
    ```
    python bot.py
    ```
5. Run tests:
    ```
    pytest
    ```

## Usage

- Use `/start` to begin registration.
- Use `/myinfo`, `/referralstats`, `/aboutus`, `/contactus`, `/referral_earnings` for bot features.
- Admin receives monthly payout reports automatically.

## Deploying to Railway

1. Push your code to GitHub.
2. Go to [Railway](https://railway.app/) and create a new project.
3. Connect your GitHub repo.
4. Set the following environment variables in the Railway dashboard:
    - `BOT_TOKEN`
    - `ADMIN_CHAT_ID`
    - `MONGO_URI`
    - `MONGO_DB_NAME`
5. Deploy! Railway will run `python bot.py` automatically.