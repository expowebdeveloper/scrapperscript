# Generated by Django 5.0.7 on 2024-07-31 10:35

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core_app', '0010_vendorsource_unit'),
    ]

    operations = [
        migrations.AlterField(
            model_name='vendorsourcefile',
            name='inventory_document',
            field=models.FileField(blank=True, null=True, upload_to='media'),
        ),
        migrations.AlterField(
            model_name='vendorsourcefile',
            name='price_document',
            field=models.FileField(blank=True, null=True, upload_to='media'),
        ),
    ]
