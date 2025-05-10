from django.db import models

class Task(models.Model):
    assignee = models.CharField(max_length=100)
    date = models.DateField()
    task_name = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=[('Active', 'Active'), ('Completed', 'Completed')])
    priority = models.CharField(max_length=20, choices=[('Low', 'Low'), ('Medium', 'Medium'), ('High', 'High')])

    def __str__(self):
        return self.task_name
