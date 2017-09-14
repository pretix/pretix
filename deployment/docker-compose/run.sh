echo "Due to racecondition on database initial setup we will only build the database first ..."
docker-compose up --force-recreate --build -d db
echo "Waiting for initial db setup"
sleep 10
echo "Starting now ... get ready :)"
sleep 1
docker-compose up --force-recreate --build
