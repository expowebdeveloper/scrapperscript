from django.db import models
# from jsonfield import JSONField


class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    
    class Meta:
        abstract = True

class VendorSource(BaseModel):
    website =  models.CharField(max_length=255)
    username =  models.CharField(max_length=200, null=True, blank=True)
    password =  models.CharField(max_length=100, null=True, blank=True)
    xpath =  models.JSONField(default=dict())
    
    def __str__(self) -> str:
        return self.website
    class Meta:
        ordering = ['id']

class FtpDetail(BaseModel):
    username  =  models.CharField(max_length=255)
    password = models.CharField(max_length=255)
    host = models.CharField(max_length=255)
    port = models.CharField(max_length=255, null=True, blank=True)
    interval = models.PositiveIntegerField()

    def __str__(self) -> str:
        return self.host
    class Meta:
        ordering = ['id']

class VendorSourceFile(BaseModel):
    vendor = models.ForeignKey(VendorSource, on_delete=models.CASCADE)
    inventory_document = models.FileField(upload_to='media')
    price_document = models.FileField(upload_to='media')