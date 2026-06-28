# GCP Automated Deployment Script for wt_stock
$SERVER_IP = "35.232.103.214"
$USERNAME = "ardantk"
$KEY_PATH = "$env:USERPROFILE\.ssh\gcp_key_ed25519"

Write-Host "=============================================" -ForegroundColor Yellow
Write-Host " Starting GCP Automated Deployment..." -ForegroundColor Yellow
Write-Host "=============================================" -ForegroundColor Yellow

# 1. File Transfer (Local -> GCP VM)
Write-Host "1. Sending files to server..." -ForegroundColor Cyan
$files = @(
    "kiwoom_service.py", 
    "telegram_bot.py", 
    "scheduler.py", 
    "stock_analyzer.py", 
    "run.py", 
    "requirements.txt", 
    "Dockerfile", 
    "docker-compose.yml"
)

foreach ($file in $files) {
    if (Test-Path $file) {
        Write-Host " -> Sending: $file" -ForegroundColor Gray
        $target = $USERNAME + "@" + $SERVER_IP + ":~/wt_stock/"
        scp -i $KEY_PATH -o StrictHostKeyChecking=no $file $target
    }
}

# 2. Restart Bot on Server
Write-Host "2. Restarting bot on server..." -ForegroundColor Cyan
$remoteCmd = "cd ~/wt_stock; docker-compose up -d --build"
$sshTarget = $USERNAME + "@" + $SERVER_IP
ssh -i $KEY_PATH -o StrictHostKeyChecking=no $sshTarget $remoteCmd

Write-Host "=============================================" -ForegroundColor Green
Write-Host " Deployment completed successfully!" -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Green
