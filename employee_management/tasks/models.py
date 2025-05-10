from django.db import models

class Task(models.Model):
    task_name = models.CharField(max_length=200)
    assignee = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    duration = models.FloatField(default=0)  # Hours
    status = models.CharField(max_length=50)
    priority = models.CharField(max_length=50)

    def __str__(self):
        return f"{self.task_name} - {self.assignee} - {self.duration}h"