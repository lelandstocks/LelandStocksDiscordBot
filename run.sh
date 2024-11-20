#!/bin/bash

LAST_MAIN_HASH=""
LAST_SUB_HASH=""
BOT_PID=""

update_repositories() {
    # Fetch updates for main repo
    git fetch origin
    
    # Fetch updates for submodule
    cd lelandstocks.github.io
    git fetch origin
    cd ../
}

check_changes() {
    # Compare local with remote for main repo
    MAIN_CHANGED=$(git rev-list HEAD...origin/main --count 2>/dev/null || echo "0")
    
    # Compare local with remote for submodule
    cd lelandstocks.github.io
    SUB_CHANGED=$(git rev-list HEAD...origin/main --count 2>/dev/null || echo "0")
    cd ../
    
    # Return true if either has changes
    [ "$MAIN_CHANGED" -gt "0" ] || [ "$SUB_CHANGED" -gt "0" ]
}

while true; do
    update_repositories
    
    if check_changes; then
        echo "Remote changes detected, updating repositories..."
        
        # Kill existing bot process if running
        if [ ! -z "$BOT_PID" ]; then
            kill $BOT_PID 2>/dev/null
            sleep 2  # Give process time to terminate
        fi
        
        # Pull changes
        git pull
        cd lelandstocks.github.io && git pull && cd ../
        
        # Start bot in background and save PID
        pixi run update_discord &
        BOT_PID=$!
    fi
    
    sleep 10
done
