from __future__ import annotations

import logging
import random
from contextlib import suppress

from django.db import transaction
from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .models import SimulatedTask
from .tasks import TASK_LABELS, run_simulated_task, visible_tasks

logger = logging.getLogger(__name__)
ACTIVE_ROUTINE_LIMIT = 16


@ensure_csrf_cookie
def task_list(request):
    tasks = visible_tasks()
    return render(request, "tasks_demo/task_list.html", {"tasks": tasks})


@require_POST
def task_create(request):
    try:
        # The configured DB queue shares this database: publish both rows together.
        with transaction.atomic():
            # SQLite is the supported database. Take its writer lock before
            # reading admission state, even with an empty table/local DEFERRED
            # transactions. This no-op UPDATE owns the lock until commit.
            SimulatedTask.objects.filter(pk=0).update(status=F("status"))
            active_count = SimulatedTask.objects.filter(
                status__in=[SimulatedTask.Status.PENDING, SimulatedTask.Status.RUNNING]
            ).count()
            if active_count >= ACTIVE_ROUTINE_LIMIT:
                response = JsonResponse(
                    {"error": f"All {ACTIVE_ROUTINE_LIMIT} routine slots are busy. Please retry."},
                    status=503,
                )
                response["Retry-After"] = "1"
                return response
            label = random.choice(TASK_LABELS)
            task = SimulatedTask.objects.create(label=label)
            backend_task = run_simulated_task.enqueue(task.pk)
            task.backend_task_id = backend_task.id
            task.save(update_fields=["backend_task_id"])
    except Exception:
        # The transaction has rolled back. Logging is best effort.
        with suppress(Exception):
            logger.exception("Could not queue demo routine")
        return JsonResponse({"error": "Routine could not be queued. Please try again."}, status=503)
    return JsonResponse(
        {"id": task.pk, "label": task.label, "status": task.status},
        status=201,
    )


@require_POST
def task_clear(request):
    SimulatedTask.objects.filter(
        status__in=[SimulatedTask.Status.DONE, SimulatedTask.Status.FAILED]
    ).delete()
    return JsonResponse({"cleared": True})


@require_GET
def task_status(request):
    tasks = visible_tasks()
    data = {
        "tasks": [
            {
                "id": t.pk,
                "label": t.label,
                "status": t.status,
                "result": t.result,
                "duration": t.duration,
                "created_at": (t.created_at.isoformat() if t.created_at else None),
                "completed_at": (t.completed_at.isoformat() if t.completed_at else None),
            }
            for t in tasks
        ]
    }
    return JsonResponse(data)
