from django.db import models


class Widget(models.Model):
    name = models.CharField(max_length=50)


class Gadget(models.Model):
    name = models.CharField(max_length=50)
