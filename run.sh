#!/bin/bash

LAST_MAIN_HASH=""
LAST_SUB_HASH=""
BOT_PID=""

update_repositories() {
    cd lelandstocks.github.io && git pull && cd ../
    git pull
}

while true; do
    # Get current hash of main repo
    CURRENT_MAIN_HASH=$(git rev-parse HEAD)
    
    # Get current hash of submodule
    cd lelandstocks.github.io
    CURRENT_SUB_HASH=$(git rev-parse HEAD)
    cd ../
    
    # Check if either hash changed
    if [ "$CURRENT_MAIN_HASH" != "$LAST_MAIN_HASH" ] || [ "$CURRENT_SUB_HASH" != "$LAST_SUB_HASH" ]; then
        echo "Changes detected..."
        echo "Main repo changed: $([ "$CURRENT_MAIN_HASH" != "$LAST_MAIN_HASH" ] && echo "yes" || echo "no")"
        echo "Submodule changed: $([ "$CURRENT_SUB_HASH" != "$LAST_SUB_HASH" ] && echo "yes" || echo "no")"
        
        update_repositories
        
        # Kill existing bot process if running
        if [ ! -z "$BOT_PID" ]; then
            kill $BOT_PID 2>/dev/null
        fi
        
        # Start bot in background and save PID
        pixi run update_discord &
        BOT_PID=$!
        
        LAST_MAIN_HASH=$CURRENT_MAIN_HASH
        LAST_SUB_HASH=$CURRENT_SUB_HASH
    fi
    
    sleep 2
done
