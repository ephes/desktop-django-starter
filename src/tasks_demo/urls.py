from django.urls import path

from .views import task_clear, task_create, task_list, task_status

app_name = "tasks_demo"

urlpatterns = [
    path("", task_list, name="task-list"),
    path("run/", task_create, name="task-run"),
    path("status/", task_status, name="task-status"),
    path("clear/", task_clear, name="task-clear"),
]
