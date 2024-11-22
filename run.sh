#!/bin/bash

LAST_MAIN_HASH=""
LAST_SUB_HASH=""
BOT_PID=""

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
    git fetch origin main --depth=1 || echo "Warning: Failed to fetch main repository"
    
    cd lelandstocks.github.io || { echo "Failed to navigate to submodule directory."; return; }
    git fetch origin master --depth=1 || echo "Warning: Failed to fetch submodule"
    cd ../
}

# Optimize change detection using git rev-parse
check_changes() {
    local current_main=$(git rev-parse HEAD)
    local remote_main=$(git rev-parse origin/main)
    
    cd lelandstocks.github.io || { echo "Failed to navigate to submodule directory."; return 1; }
    local current_sub=$(git rev-parse HEAD)
    local remote_sub=$(git rev-parse origin/master)
    cd ../

    # Compare hashes directly instead of counting commits
    [ "$current_main" != "$remote_main" ] || [ "$current_sub" != "$remote_sub" ]
}

# Main loop
while true; do
    if ! kill -0 $BOT_PID 2>/dev/null; then
        # Bot not running or crashed, start it
        update_repositories
        
        if check_changes; then
            echo "Remote changes detected, updating repositories..."
            git pull origin main --ff-only || echo "Warning: Failed to pull main repository"
            cd lelandstocks.github.io && git pull origin master --ff-only && cd ../
        fi

        echo "Starting bot..."
        pixi run update_discord &
        BOT_PID=$!
        echo "Bot started with PID: $BOT_PID"
    else
        # Only check for updates if bot is running
        if update_repositories && check_changes; then
            stop_bot
            git pull origin main --ff-only || echo "Warning: Failed to pull main repository"
            cd lelandstocks.github.io && git pull origin master --ff-only && cd ../
            
            echo "Starting bot..."
            pixi run update_discord &
            BOT_PID=$!
            echo "Bot started with PID: $BOT_PID"
        fi
    fi

    sleep 300
done
