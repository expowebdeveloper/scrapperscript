# Scapper Script

This project will manage the vendor details.
## Create Virtual environment
```bash
python -m venv <env name>
```
## Activate Virtual environment
```bash
source <env name>/bin/activate
```
## Install Dependencies


```bash
cd <project folder>
pip install -r requirements.txt
```

## Create Database

```python
sudo -u postgres psql
postgres=# create database <db name>;
postgres=# create user <user name> with encrypted password <password>;
postgres=# grant all privileges on database <database> to <username>;

```

## Run Project
```python
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver

```

