# Generated by Django 5.0.7 on 2024-07-29 10:53

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core_app', '0005_vendorsourcefile'),
    ]

    operations = [
        migrations.RenameField(
            model_name='vendorsourcefile',
            old_name='inventory',
            new_name='inventory_document',
        ),
    ]
