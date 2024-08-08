#!/bin/bash
cd /home/ubuntu/scrapperscript
source ../venv/bin/activate
python manage.py shell -c "from core_app.tasks import process_due_vendors; process_due_vendors.delay()"
