#!/bin/bash

# Add trap for cleanup on script exit
trap 'stop_bot' EXIT INT TERM

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
            BOT_PID=""
        else
            log "❌ Failed to stop bot"
        fi
    fi
}

# Ensure the bot process is killed when the script exits
trap 'stop_bot; exit' SIGINT SIGTERM

# Only fetch updates without merging
update_repositories() {
    log "🔍 Checking for updates..."
    cd "$MAIN_DIR" || { log "❌ Failed to change to main directory"; return 1; }
    git fetch origin main --depth=1 || { log "⚠️  Warning: Failed to fetch main repository"; return 1; }
    
    cd "$MAIN_DIR/lelandstocks.github.io" || { log "❌ Failed to change to submodule directory"; return 1; }
    git fetch origin master --depth=1 || { log "⚠️  Warning: Failed to fetch submodule"; return 1; }
    cd "$MAIN_DIR" || return 1
    log "✅ Repository check complete"
    return 0
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
        log "Updates available but not merging automatically"
        return 0
    fi
    return 1
}

# Function to resolve merge conflicts
resolve_conflicts() {
    local repo_dir="$1"
    cd "$repo_dir" || return 1
    
    # Stash any local changes
    if ! git stash; then
        log "⚠️ Warning: Failed to stash changes in $repo_dir"
        return 1
    fi
    
    # Force reset to remote branch
    if [[ "$repo_dir" == *"lelandstocks.github.io"* ]]; then
        git reset --hard origin/master
    else
        git reset --hard origin/main
    fi
    
    # Pop stashed changes if any
    git stash pop 2>/dev/null || true
}

# Function to force merge updates
force_merge_repositories() {
    log "🔄 Force merging updates..."
    
    # Main repository
    cd "$MAIN_DIR" || { log "❌ Failed to change to main directory"; return 1; }
    if ! git pull --allow-unrelated-histories origin main; then
        log "⚠️ Merge conflict detected in main repository, attempting to resolve..."
        resolve_conflicts "$MAIN_DIR" || return 1
    fi
    
    # Submodule
    cd "$MAIN_DIR/lelandstocks.github.io" || { log "❌ Failed to change to submodule directory"; return 1; }
    if ! git pull --allow-unrelated-histories origin master; then
        log "⚠️ Merge conflict detected in submodule, attempting to resolve..."
        resolve_conflicts "$MAIN_DIR/lelandstocks.github.io" || return 1
    fi
    
    cd "$MAIN_DIR" || return 1
    log "✅ Merge complete"
    return 0
}

# Main loop
while true; do
    if ! kill -0 $BOT_PID 2>/dev/null; then
        log "🤖 Bot not running, initiating startup sequence..."
        if update_repositories; then
            if check_changes; then
                log "🔄 Changes detected, preparing restart..."
                force_merge_repositories
            else
                log "✅ No updates detected"
            fi

            log "🚀 Starting bot..."
            if command -v pixi &> /dev/null; then
                pixi run update_discord &
                BOT_PID=$!
                log "✨ Bot started with PID: $BOT_PID"
            else
                log "❌ 'pixi' command not found, unable to start bot"
            fi
        fi
    else
        if update_repositories && check_changes; then
            stop_bot
            log "🔄 Changes detected, preparing restart..."
            force_merge_repositories
            
            log "🚀 Starting bot..."
            if command -v pixi &> /dev/null; then
                pixi run update_discord &
                BOT_PID=$!
                log "✨ Bot started with PID: $BOT_PID"
            else
                log "❌ 'pixi' command not found, unable to start bot"
            fi
        else
            log "✅ No updates detected"
        fi
    fi
    
    sleep 30
done
