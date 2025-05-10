from django.db import models

class Task(models.Model):
    assignee = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    task_name = models.CharField(max_length=200)
    status = models.CharField(max_length=50)
    priority = models.CharField(max_length=50)

    def __str__(self):
        return f"{self.task_name} ({self.assignee})"