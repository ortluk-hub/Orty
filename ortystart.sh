#docker run -d \
#  --name orty \
#  --add-host=host.docker.internal:host-gateway \
#  -p 0.0.0.0:8080:8080 \
#  --env-file ./.env \
#  orty:local


python -m hypercorn service.api:app --bind 0.0.0.0:8080 --worker-class asyncio --access-logfile - --error-logfile -
