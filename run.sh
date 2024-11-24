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

# Only fetch updates without merging
update_repositories() {
    echo "Checking for updates..."
    cd "$MAIN_DIR" || return 1
    git fetch origin main --depth=1 || echo "Warning: Failed to fetch main repository"
    
    cd "$MAIN_DIR/lelandstocks.github.io" || return 1
    git fetch origin master --depth=1 || echo "Warning: Failed to fetch submodule"
    cd "$MAIN_DIR" || return 1
}

# Check for changes without merging
check_changes() {
    cd "$MAIN_DIR" || return 1
    # Check if local is behind remote
    local main_behind=$(git rev-list HEAD..origin/main --count 2>/dev/null)
    
    cd "$MAIN_DIR/lelandstocks.github.io" || return 1
    local sub_behind=$(git rev-list HEAD..origin/master --count 2>/dev/null)
    cd "$MAIN_DIR" || return 1

    # If either repository has changes
    if [ "$main_behind" -gt 0 ] || [ "$sub_behind" -gt 0 ]; then
        echo "Updates available but not merging automatically"
        return 0
    fi
    return 1
}

# Function to force merge updates
force_merge_repositories() {
    echo "Force merging updates..."
    cd "$MAIN_DIR" || return 1
    git pull --allow-unrelated-histories origin main || echo "Warning: Failed to merge main repository"
    
    cd "$MAIN_DIR/lelandstocks.github.io" || return 1
    git pull --allow-unrelated-histories origin master || echo "Warning: Failed to merge submodule"
    cd "$MAIN_DIR" || return 1
}

# Main loop
while true; do
    if ! kill -0 $BOT_PID 2>/dev/null; then
        # Bot not running or crashed, start it
        update_repositories
        
        if check_changes; then
            echo "Changes detected, restarting bot..."
            force_merge_repositories
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
            force_merge_repositories
            
            echo "Starting bot..."
            pixi run update_discord &
            BOT_PID=$!
            echo "Bot started with PID: $BOT_PID"
        fi
    fi

    sleep 30
done
