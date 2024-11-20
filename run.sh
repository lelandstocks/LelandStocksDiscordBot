#!/bin/bash

LAST_HASH=""
BOT_PID=""

update_repositories() {
    cd lelandstocks.github.io && git pull && cd ../
    git pull
}

while true; do
    # Get current hash of main repo and submodule
    CURRENT_HASH=$(git rev-parse HEAD; cd lelandstocks.github.io && git rev-parse HEAD && cd ../)
    
    # Check if hash changed
    if [ "$CURRENT_HASH" != "$LAST_HASH" ]; then
        echo "Changes detected, updating..."
        update_repositories
        
        # Kill existing bot process if running
        if [ ! -z "$BOT_PID" ]; then
            kill $BOT_PID 2>/dev/null
        fi
        
        # Start bot in background and save PID
        pixi run update_discord &
        BOT_PID=$!
        
        LAST_HASH=$CURRENT_HASH
    fi
    
    sleep 2
done
