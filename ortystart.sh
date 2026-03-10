#docker run -d \
#  --name orty \
#  --add-host=host.docker.internal:host-gateway \
#  -p 0.0.0.0:8080:8080 \
#  --env-file ./.env \
#  orty:local


uvicorn service.api:app --host 0.0.0.0 --port 8080
