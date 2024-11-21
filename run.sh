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

# Update repositories: main repo and submodule
update_repositories() {
    echo "Fetching updates..."
    # Fetch updates for main repo (using origin/main)
    git fetch origin || echo "Warning: Failed to fetch main repository"
    
    # Fetch updates for submodule (using origin/master)
    cd lelandstocks.github.io || { echo "Failed to navigate to submodule directory."; return; }
    git fetch origin || echo "Warning: Failed to fetch submodule"
    cd ../
}

# Check for changes in the main repo and submodule
check_changes() {
    # Compare local with remote for main repo (using origin/main)
    MAIN_CHANGED=$(git rev-list HEAD...origin/main --count 2>/dev/null || echo "0")
    
    # Compare local with remote for submodule (using origin/master)
    cd lelandstocks.github.io || { echo "Failed to navigate to submodule directory."; return 1; }
    SUB_CHANGED=$(git rev-list HEAD...origin/master --count 2>/dev/null || echo "0")
    cd ../

    echo "Changes detected - Main: $MAIN_CHANGED, Submodule: $SUB_CHANGED"
    
    # Return true if either has changes
    [ "$MAIN_CHANGED" -gt "0" ] || [ "$SUB_CHANGED" -gt "0" ]
}

# Main loop for checking updates and restarting the bot
while true; do
    update_repositories
    
    if check_changes; then
        echo "Remote changes detected, updating repositories..."
        
        # Stop the existing bot if running
        stop_bot
        
        # Pull changes for main repo (using origin/main)
        git pull origin main || echo "Warning: Failed to pull main repository"
        # Pull changes for submodule (using origin/master)
        cd lelandstocks.github.io && git pull origin master && cd ../
    else
        echo "No changes detected."
    fi
    
    # Start the bot only if there were changes detected
    if check_changes; then
        echo "Starting bot..."
        # Start bot in the background and save its PID
        pixi run update_discord &
        BOT_PID=$!
        echo "Bot started with PID: $BOT_PID"
    fi
    
    sleep 10
done
