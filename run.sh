#!/bin/bash

LAST_MAIN_HASH=""
LAST_SUB_HASH=""
BOT_PID=""

update_repositories() {
    echo "Fetching updates..."
    # Fetch updates for main repo
    git fetch origin || echo "Warning: Failed to fetch main repository"
    
    # Fetch updates for submodule
    cd lelandstocks.github.io || exit 1
    git fetch origin || echo "Warning: Failed to fetch submodule"
    cd ../
}

check_changes() {
    # Compare local with remote for main repo
    MAIN_CHANGED=$(git rev-list HEAD...origin/main --count 2>/dev/null || echo "0")
    
    # Compare local with remote for submodule
    cd lelandstocks.github.io || exit 1
    SUB_CHANGED=$(git rev-list HEAD...origin/master --count 2>/dev/null || echo "0")
    cd ../
    
    echo "Changes detected - Main: $MAIN_CHANGED, Submodule: $SUB_CHANGED"
    
    # Return true if either has changes
    [ "$MAIN_CHANGED" -gt "0" ] || [ "$SUB_CHANGED" -gt "0" ]
}

while true; do
    update_repositories
    
    if check_changes; then
        echo "Remote changes detected, updating repositories..."
        
        # Kill existing bot process if running
        if [ ! -z "$BOT_PID" ]; then
            echo "Stopping existing bot process (PID: $BOT_PID)..."
            kill $BOT_PID 2>/dev/null
            sleep 2  # Give process time to terminate
        fi
        
        # Pull changes
        git pull origin main || echo "Warning: Failed to pull main repository"
        cd lelandstocks.github.io && git pull origin master && cd ../
        
        echo "Starting bot..."
        # Start bot in background and save PID
        pixi run update_discord &
        BOT_PID=$!
        echo "Bot started with PID: $BOT_PID"
    else
        echo "No changes detected."
    fi
    
    sleep 10
done
