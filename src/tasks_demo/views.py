from __future__ import annotations

import random

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .models import SimulatedTask
from .tasks import TASK_LABELS, reconcile_task_with_backend, run_simulated_task


@ensure_csrf_cookie
def task_list(request):
    tasks = [reconcile_task_with_backend(task) for task in SimulatedTask.objects.all()]
    return render(request, "tasks_demo/task_list.html", {"tasks": tasks})


@require_POST
def task_create(request):
    label = random.choice(TASK_LABELS)
    task = SimulatedTask.objects.create(label=label)
    backend_task = run_simulated_task.enqueue(task.pk)
    task.backend_task_id = backend_task.id
    task.save(update_fields=["backend_task_id"])
    return JsonResponse(
        {"id": task.pk, "label": task.label, "status": task.status},
        status=201,
    )


@require_POST
def task_clear(request):
    SimulatedTask.objects.all().delete()
    return JsonResponse({"cleared": True})


@require_GET
def task_status(request):
    tasks = [reconcile_task_with_backend(task) for task in SimulatedTask.objects.all()]
    data = {
        "tasks": [
            {
                "id": t.pk,
                "label": t.label,
                "status": t.status,
                "result": t.result,
                "duration": t.duration,
                "created_at": (
                    t.created_at.isoformat() if t.created_at else None
                ),
                "completed_at": (
                    t.completed_at.isoformat() if t.completed_at else None
                ),
            }
            for t in tasks
        ]
    }
    return JsonResponse(data)
