from django.db import models
# from jsonfield import JSONField


class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    
    class Meta:
        abstract = True

class VendorSource(BaseModel):
    WEBSITE_CHOICES = [
        ('hours', 'Hours'),
        ('days', 'Days'),
        ('weeks', 'Weeks'),
    ]
    website =  models.CharField(max_length=255)
    username =  models.CharField(max_length=200, null=True, blank=True)
    password =  models.CharField(max_length=100, null=True, blank=True)
    xpath =  models.JSONField(default=dict())
    interval = models.PositiveIntegerField(null=True, blank=True)
    unit = models.CharField(max_length=10, choices=WEBSITE_CHOICES, null=True, blank=True)

    def __str__(self) -> str:
        return self.website
    class Meta:
        ordering = ['id']

class FtpDetail(BaseModel):
    username  =  models.CharField(max_length=255)
    password = models.CharField(max_length=255)
    host = models.CharField(max_length=255)
    port = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self) -> str:
        return self.host
    class Meta:
        ordering = ['id']

class VendorSourceFile(BaseModel):
    vendor = models.ForeignKey(VendorSource, on_delete=models.CASCADE)
    inventory_document = models.FileField(upload_to='media')
    price_document = models.FileField(upload_to='media')


class VendorLogs(BaseModel):
    vendor = models.ForeignKey(VendorSource, on_delete=models.CASCADE)
    file_download = models.BooleanField(default=False)
    file_upload = models.BooleanField(default=False)
    reason = models.TextField(null=True, blank=True)
    def __str__(self) -> str:
        return self.vendor.website