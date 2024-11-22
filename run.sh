#!/bin/bash

LAST_MAIN_HASH=""
LAST_SUB_HASH=""
BOT_PID=""
MAIN_DIR=$(pwd)

# Function to stop the bot if it's running
stop_bot() {
    if [ ! -z "$BOT_PID" ]; then
        echo "Stopping existing bot process (PID: $BOT_PID)..."
        kill $BOT_PID 2>/dev/null
        sleep 2  # Give process time to terminate
    fi
}

# More efficient git fetch by only getting the latest commit
update_repositories() {
    echo "Fetching updates..."
    cd "$MAIN_DIR" || return 1
    git fetch origin main --depth=1 || echo "Warning: Failed to fetch main repository"
    
    cd "$MAIN_DIR/lelandstocks.github.io" || return 1
    git fetch origin master --depth=1 || echo "Warning: Failed to fetch submodule"
    cd "$MAIN_DIR" || return 1
}

# Optimize change detection using git rev-parse
check_changes() {
    cd "$MAIN_DIR" || return 1
    local current_main=$(git rev-parse HEAD)
    local remote_main=$(git rev-parse origin/main)
    
    cd "$MAIN_DIR/lelandstocks.github.io" || return 1
    local current_sub=$(git rev-parse HEAD)
    local remote_sub=$(git rev-parse origin/master)
    cd "$MAIN_DIR" || return 1

    # Compare hashes directly instead of counting commits
    [ "$current_main" != "$remote_main" ] || [ "$current_sub" != "$remote_sub" ]
}

# Main loop
while true; do
    if ! kill -0 $BOT_PID 2>/dev/null; then
        # Bot not running or crashed, start it
        update_repositories
        
        if check_changes; then
            echo "Changes detected, restarting bot..."
        fi

        echo "Starting bot..."
        pixi run update_discord &
        BOT_PID=$!
        echo "Bot started with PID: $BOT_PID"
    else
        # Only check for updates if bot is running
        if update_repositories && check_changes; then
            stop_bot
            echo "Changes detected, restarting bot..."
            
            echo "Starting bot..."
            pixi run update_discord &
            BOT_PID=$!
            echo "Bot started with PID: $BOT_PID"
        fi
    fi

    sleep 300
done
