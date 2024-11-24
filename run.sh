#!/bin/bash

# Add timestamp function
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

LAST_MAIN_HASH=""
LAST_SUB_HASH=""
BOT_PID=""
MAIN_DIR=$(pwd)

# Function to stop the bot if it's running
stop_bot() {
    if [ ! -z "$BOT_PID" ]; then
        log "📥 Stopping bot process (PID: $BOT_PID)..."
        kill $BOT_PID 2>/dev/null
        sleep 2
        if ! kill -0 $BOT_PID 2>/dev/null; then
            log "✅ Bot stopped successfully"
        else
            log "❌ Failed to stop bot"
        fi
    fi
}

# Only fetch updates without merging
update_repositories() {
    log "🔍 Checking for updates..."
    cd "$MAIN_DIR" || { log "❌ Failed to change to main directory"; return 1; }
    git fetch origin main --depth=1 || { log "⚠️  Warning: Failed to fetch main repository"; return 1; }
    
    cd "$MAIN_DIR/lelandstocks.github.io" || { log "❌ Failed to change to submodule directory"; return 1; }
    git fetch origin master --depth=1 || { log "⚠️  Warning: Failed to fetch submodule"; return 1; }
    cd "$MAIN_DIR" || return 1
    log "✅ Repository check complete"
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
    log "🔄 Force merging updates..."
    cd "$MAIN_DIR" || { log "❌ Failed to change to main directory"; return 1; }
    git pull --allow-unrelated-histories origin main || { log "⚠️  Warning: Failed to merge main repository"; return 1; }
    
    cd "$MAIN_DIR/lelandstocks.github.io" || { log "❌ Failed to change to submodule directory"; return 1; }
    git pull --allow-unrelated-histories origin master || { log "⚠️  Warning: Failed to merge submodule"; return 1; }
    cd "$MAIN_DIR" || return 1
    log "✅ Merge complete"
}

# Main loop
while true; do
    if ! kill -0 $BOT_PID 2>/dev/null; then
        log "🤖 Bot not running, initiating startup sequence..."
        update_repositories
        
        if check_changes; then
            log "🔄 Changes detected, preparing restart..."
            force_merge_repositories
        fi

        log "🚀 Starting bot..."
        pixi run update_discord &
        BOT_PID=$!
        log "✨ Bot started with PID: $BOT_PID"
    else
        if update_repositories && check_changes; then
            stop_bot
            log "🔄 Changes detected, preparing restart..."
            force_merge_repositories
            
            log "🚀 Starting bot..."
            pixi run update_discord &
            BOT_PID=$!
            log "✨ Bot started with PID: $BOT_PID"
        fi
    fi

    sleep 30
done
