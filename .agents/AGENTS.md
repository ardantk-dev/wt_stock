# Project Rules & Workspace Knowledge

## Remote Server SSH Configuration
- **Server Host Alias**: `wt-stock-server` (`35.232.103.214`)
- **SSH Command**: `ssh wt-stock-server`
- **SSH Key**: `C:/Users/yhbyu/.ssh/id_rsa_gcp`
- **Remote Directory**: `/home/ubuntu/wt_stock`
- **Docker Container Name**: `wt-stock-bot`

## Automation Guidelines
- Whenever the user asks to inspect logs, check status, or run tests on the server, execute commands via `ssh wt-stock-server "<command>"`.
- To test Kiwoom API on the server: `ssh wt-stock-server "sudo docker exec wt-stock-bot python3 test_kiwoom.py"`.
- To view container logs: `ssh wt-stock-server "sudo docker-compose -f /home/ubuntu/wt_stock/docker-compose.yml logs --tail=50"`.
