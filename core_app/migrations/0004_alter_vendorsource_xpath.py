# Generated by Django 5.0.7 on 2024-07-25 12:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core_app', '0003_alter_ftpdetail_port'),
    ]

    operations = [
        migrations.AlterField(
            model_name='vendorsource',
            name='xpath',
            field=models.JSONField(default={}),
        ),
    ]
