
import os 
from celery import Celery 
from celery.schedules import crontab, timedelta

# set the default Django settings module for the 'celery' program. 
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scrapperscript.settings') 
  
app = Celery('gfg') 
  
# Using a string here means the worker doesn't  
# have to serialize the configuration object to  
# child processes. - namespace='CELERY' means all  
# celery-related configuration keys should  
# have a `CELERY_` prefix. 
app.config_from_object('django.conf:settings', 
                       namespace='CELERY')

app.conf.beat_schedule = {
    'process-vendors-daily': {
        'task': 'core_app.tasks.process_due_vendors',
        'schedule': crontab(minute=0),  # Run daily at midnight
    },
}


app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks() 
  
# Load task modules from all registered Django app configs. 
app.autodiscover_tasks()