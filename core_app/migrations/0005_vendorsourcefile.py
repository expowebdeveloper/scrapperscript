# Generated by Django 5.0.7 on 2024-07-29 10:43

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core_app', '0004_alter_vendorsource_xpath'),
    ]

    operations = [
        migrations.CreateModel(
            name='VendorSourceFile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now_add=True, null=True)),
                ('inventory', models.FileField(upload_to='media')),
                ('price_document', models.FileField(upload_to='media')),
                ('vendor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core_app.vendorsource')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
