#!/usr/bin/env bash

echo "Copy src from ../../src. Due to security reasons Docker cant build from parent directories."
cp -r ../../src src_tmp
docker-compose up --force-recreate --build
