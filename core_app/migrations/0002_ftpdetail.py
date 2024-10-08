# Generated by Django 5.0.7 on 2024-07-25 09:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core_app', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='FtpDetail',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now_add=True, null=True)),
                ('username', models.CharField(max_length=255)),
                ('password', models.CharField(max_length=255)),
                ('host', models.CharField(max_length=255)),
                ('port', models.CharField(max_length=255)),
                ('interval', models.PositiveIntegerField()),
            ],
            options={
                'ordering': ['id'],
            },
        ),
    ]
