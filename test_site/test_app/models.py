from django.db import models

# Create your models here.


class Simple(models.Model):
    name = models.CharField(max_length=200, blank=False, null=False)
    version = models.IntegerField
