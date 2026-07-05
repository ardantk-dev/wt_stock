#!/bin/bash
# Move to the project directory
cd /home/ubuntu/wt_stock || exit

# Fetch the latest state from remote main branch
git fetch origin main

# Compare local head with remote head
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse @{u})

if [ "$LOCAL" != "$REMOTE" ]; then
    echo "$(date): New commit detected on remote main branch. Pulling changes..."
    git pull origin main
    
    echo "$(date): Rebuilding and restarting docker containers..."
    sudo docker-compose down
    sudo docker-compose up --build -d
    
    # Run sync to restore portfolio just in case
    echo "$(date): Syncing portfolio..."
    sudo docker exec -i wt-stock-bot python3 -c "import telegram_bot; telegram_bot.sync_portfolio()"
    
    echo "$(date): Auto deploy completed successfully!"
fi
