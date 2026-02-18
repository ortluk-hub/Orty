 docker run -d   --name orty   --network orty-net   -p 8080:8080   --env-file ./.env   -v orty_data:/app/data   orty:local
