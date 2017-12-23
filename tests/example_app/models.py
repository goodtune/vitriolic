from django.db import models
from touchtechnology.common.db.models import DateTimeField


class TestDateTimeField(models.Model):

    datetime = DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ('datetime',)

    def __str__(self):
        return str(self.datetime)


class Relative(models.Model):

    name = models.CharField(max_length=10, blank=True, null=True)
    link = models.ForeignKey('TestDateTimeField', on_delete=models.CASCADE)
