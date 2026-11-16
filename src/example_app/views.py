from contextlib import contextmanager

from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from .forms import ItemForm
from .models import Item
from .revisions import (
    CONFLICT_MESSAGE,
    displayed_inventory_revision,
    displayed_revision,
    matches_displayed_revision,
    matches_inventory_revision,
)

PAGE_SIZE = 20


@contextmanager
def read_snapshot():
    """Hold one SQLite read snapshot without taking the writer lock.

    Packaged settings begin every transaction IMMEDIATE, which would serialize
    plain list reads with all writers. A deferred transaction under WAL gives
    the same consistent snapshot while writers keep committing.
    """
    connection = transaction.get_connection()
    if connection.vendor != "sqlite" or connection.in_atomic_block:
        with transaction.atomic():
            yield
        return
    # Connecting reloads transaction_mode from settings; do that first.
    connection.ensure_connection()
    mode = connection.transaction_mode
    connection.transaction_mode = "DEFERRED"
    try:
        with transaction.atomic():
            connection.transaction_mode = mode
            yield
    finally:
        connection.transaction_mode = mode


class ItemReturnNavigation:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page = self.request.GET.get("page", "")
        context["return_page"] = page if page.isascii() and page.isdigit() else ""
        return context

    def get_success_url(self):
        page = self.request.GET.get("page")
        if page:
            page = Paginator(Item.objects.all(), PAGE_SIZE).get_page(page).number
            return f"{self.success_url}?page={page}"
        return str(self.success_url)


class ItemListView(ListView):
    model = Item
    context_object_name = "items"
    paginate_by = PAGE_SIZE
    ordering = ["-updated_at", "-created_at", "-pk"]

    def get(self, request, *args, **kwargs):
        # Page count, displayed rows and whole-stable digest share one snapshot.
        with read_snapshot():
            return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for item in context["items"]:
            item.displayed_revision = displayed_revision(item)
        context["inventory_revision"] = displayed_inventory_revision()
        return context


class ItemCreateView(ItemReturnNavigation, CreateView):
    form_class = ItemForm
    model = Item
    success_url = reverse_lazy("example_app:item-list")


class ItemUpdateView(ItemReturnNavigation, UpdateView):
    form_class = ItemForm
    model = Item
    success_url = reverse_lazy("example_app:item-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["item_revision"] = (
            self.request.POST.get("revision", "")
            if self.request.method == "POST"
            else displayed_revision(self.object)
        )
        return context

    def post(self, request, *args, **kwargs):
        with transaction.atomic():
            # Own SQLite's writer before reading, also in local DEFERRED mode.
            Item.objects.filter(pk=kwargs["pk"]).update(title=F("title"))
            self.object = self.get_object()
            conflict = not matches_displayed_revision(self.object, request.POST.get("revision", ""))
            form = self.get_form()
            valid = form.is_valid()
            if conflict:
                form.add_error(None, CONFLICT_MESSAGE)
                return self.render_to_response(
                    self.get_context_data(form=form, revision_conflict=True), status=409
                )
            return self.form_valid(form) if valid else self.form_invalid(form)


class ItemDeleteView(ItemReturnNavigation, DeleteView):
    model = Item
    success_url = reverse_lazy("example_app:item-list")

    def form_valid(self, form):
        self.object.delete()
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["item_revision"] = (
            self.request.POST.get("revision", "")
            if self.request.method == "POST"
            else displayed_revision(self.object)
        )
        return context

    def post(self, request, *args, **kwargs):
        with transaction.atomic():
            Item.objects.filter(pk=kwargs["pk"]).update(title=F("title"))
            self.object = self.get_object()
            if not matches_displayed_revision(self.object, request.POST.get("revision", "")):
                return self.render_to_response(
                    self.get_context_data(revision_conflict=CONFLICT_MESSAGE), status=409
                )
            return super().post(request, *args, **kwargs)


@require_POST
def item_clear(request):
    with transaction.atomic():
        # Even an empty match acquires SQLite's writer before the inventory read.
        Item.objects.filter(pk=0).update(title=F("title"))
        if not matches_inventory_revision(request.POST.get("revision", "")):
            return JsonResponse(
                {"error": "The stable changed. Reload before releasing all."}, status=409
            )
        Item.objects.all().delete()
    return JsonResponse({"cleared": True})
