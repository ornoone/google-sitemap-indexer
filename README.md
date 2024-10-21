# google indexer


## run it 

 requirements:
 
docker + docker compose

```
docker compose up -d
```

will start 4 worker docker 
- backend that listen to port 8000
- huey worker
- redis database
- postgresql database

## dev it 

1. start the databsase
   `docker compose up redis database -d`
2. start the django dev server (autoreload enabled)
   `docker compose -f docker-compose.yaml -f docker-compose.dev.yaml up backend`
3. edit the code

note: the scheduled huey tasks will not be triggered. to make them run, you need to start the worker (and restart it upon code change!)
    `docker compose -f docker-compose.yaml -f docker-compose.dev.yaml run  backend_huey`


A. to create a migration: 
```
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml run backend ./manage.py makemigrations
```

B. to apply the migration
```
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml run backend ./manage.py migrate
```

C. to open a shell
```
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml run backend ./manage.py shell_plus   
```

D. to add an user
```
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml run backend ./manage.py shell_plus   
```